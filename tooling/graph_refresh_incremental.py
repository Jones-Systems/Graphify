#!/usr/bin/env python3
"""Build one create-only structural candidate from Git objects in a bare mirror.

Input is one graphify-incremental-manifest/v1 file bound by its raw SHA256. The
driver reads only the selected commit's objects from the producer-owned bare
mirror; it never checks out, fetches, or observes a working tree, so the
package records build_observation=null. Admission applies include/deny globs
and size caps to `ls-tree` entries; symlinks, gitlinks, unsafe paths, oversized
blobs and checkout conversions (filter, eol=crlf, working-tree-encoding, ident)
are recorded as unsupported instead of being read. Blobs are verified against
their object IDs. Git runs with isolated configuration, core.autocrlf=false and
core.eol=lf, so `text` without eol=crlf means blob bytes equal checkout bytes on
this basis; checkout cleanliness is still not observed.

File-local fragments are reused from a create-only cache keyed by fragment
schema, family, adapter and runtime identities, per-file policy, path and
content SHA256. Every run resolves cross-file references over all current
admitted fragments in one pinned python-json/v2 adapter run, then packs once.
Cache corruption, quota exhaustion, unusable cache roots, rejected reuse or an
unidentified runtime fall back to uncached extraction and are reported.

The same commit with identical identities and admission, and a verified
previous package, gives `unchanged` without creating output or running the
adapter (the runtime probe still runs). The selected adapter is trusted code,
not a sandboxed workload; lock and retained-transaction guarantees are the
sampled cooperating-writer semantics of graph_refresh. Nothing is promoted.
"""
import argparse
from contextlib import ExitStack
import fcntl
import fnmatch
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
# `python3 -I` omits the script directory; sibling helpers come from this release only.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import fragment_cache
import graph_pack as packer
import graph_read as reader
import graph_refresh as refresh
import runtime_identity

SCHEMA = 'graphify-incremental-manifest/v1'
STATE_SCHEMA = 'graphify-build-state/v1'
RESULT_SCHEMA = 'graphify-incremental-result/v1'
REQUEST_SCHEMA = 'graphify-refresh-request/v2'
RESPONSE_SCHEMA = 'graphify-refresh-response/v2'
POLICY_SCHEMA = 'graphify-admission-policy/v1'
PER_FILE_SCHEMA = 'graphify-per-file-policy/v1'
PROTOCOL = 'python-json/v2'
FAMILY = dict(name='graphify-stdlib-structural', version='1')
FRAGMENT_SCHEMA = fragment_cache.FRAGMENT_SCHEMA
MANIFEST_FIELDS = ('schema', 'repository', 'mirror_git_dir', 'commit', 'target',
                   'admission_policy', 'extractor', 'runtime_probe', 'state_root',
                   'previous_state', 'destination', 'lock', 'cache_quota_bytes', 'limits')
STATE_FIELDS = ('schema', 'repository', 'family', 'commit', 'tree', 'input_basis',
                'admission_policy_sha256', 'adapter_sha256', 'executable_sha256',
                'per_file_policy_sha256', 'runtime_identity_sha256', 'manifest_sha256',
                'request_sha256', 'files', 'unsupported', 'package_sha256', 'catalog_sha256',
                'archive_sha256', 'graph_sha256', 'counts', 'cache_status', 'target_relation')
COUNTS = ('admitted', 'added', 'modified', 'deleted', 'reused', 'extracted', 'unsupported',
          'cache_hits', 'cache_misses', 'cache_corrupt', 'cache_full')
LIMITS = refresh.LIMITS
MAX_FILES = 256
MAX_GLOBS = 128
MAX_UNSUPPORTED = 10000
MAX_TREE_OUTPUT = 32 * 1024**2
MAX_STATE = packer.MAX_INPUT
MAX_RECEIPT = 64 * 1024
GIT_SECONDS = 120
CACHE_DIRECTORY = 'fragment-cache'
STATE_NAME = 'build-state.json'
ATTRIBUTES = ('filter', 'eol', 'text', 'working-tree-encoding', 'ident')
GIT_COMMANDS = ('rev-parse', 'ls-tree', 'check-attr', 'cat-file', 'merge-base')
ERRORS = refresh.ERRORS
Deferred, Unknown = refresh.Deferred, refresh.Unknown


def oid(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', value) is not None


def canonical_sha256(value):
    """SHA256 of sorted-key compact ASCII JSON without a trailing newline."""
    return fragment_cache.sha256(fragment_cache.canonical(value))


def optional_text(value, label):
    if value is not None:
        packer.bounded_text(value, label)


def validate_policy(policy):
    packer.closed(policy, ('schema', 'include', 'deny', 'max_files', 'max_file_bytes',
                           'max_total_bytes'), 'admission policy')
    reader.require(policy['schema'] == POLICY_SCHEMA, 'unsupported admission policy')
    for name, minimum in (('include', 1), ('deny', 0)):
        globs = policy[name]
        reader.require(isinstance(globs, list) and minimum <= len(globs) <= MAX_GLOBS
                       and len(set(map(str, globs))) == len(globs), 'invalid admission globs')
        for glob in globs:
            reader.require(isinstance(glob, str) and 0 < len(glob) <= 256
                           and all(32 <= ord(c) <= 126 for c in glob) and '\\' not in glob
                           and not glob.startswith('/'), 'invalid admission glob')
    for name, maximum in (('max_files', MAX_FILES), ('max_file_bytes', LIMITS['file_bytes']),
                          ('max_total_bytes', LIMITS['input_bytes'])):
        n = policy[name]
        reader.require(type(n) is int and 1 <= n <= maximum, 'invalid admission limit ' + name)
    return policy


def validate_manifest(m):
    packer.closed(m, MANIFEST_FIELDS, 'incremental manifest')
    reader.require(m['schema'] == SCHEMA, 'unsupported manifest')
    packer.source_identity(dict(repository=m['repository'], head=m['commit']))
    reader.require(oid(m['commit']), 'invalid commit')
    target = m['target']
    packer.closed(target, ('oid', 'observed_at', 'method'), 'target')
    reader.require(target['oid'] is None or oid(target['oid']), 'invalid target oid')
    optional_text(target['observed_at'], 'target observed_at')
    optional_text(target['method'], 'target method')
    validate_policy(m['admission_policy'])
    ex = m['extractor']
    packer.closed(ex, ('protocol', 'name', 'version', 'executable', 'script'), 'extractor')
    for key in ('protocol', 'name', 'version'):
        packer.bounded_text(ex[key], 'extractor ' + key)
    refresh.selection(ex['executable'])
    refresh.selection(ex['script'])
    refresh.selection(m['runtime_probe'])
    if m['previous_state'] is not None:
        refresh.selection(m['previous_state'])
        reader.require(Path(m['previous_state']['path']).name == STATE_NAME,
                       'previous state must be a ' + STATE_NAME)
    reader.require(type(m['cache_quota_bytes']) is int and m['cache_quota_bytes'] >= 0,
                   'invalid cache quota')
    packer.closed(m['limits'], LIMITS, 'limits')
    for name, maximum in LIMITS.items():
        n = m['limits'][name]
        reader.require(type(n) is int and 1 <= n <= maximum, 'invalid limit ' + name)
    paths = {k: refresh.absolute(m[k]) for k in ('mirror_git_dir', 'state_root', 'destination', 'lock')}
    destination = paths['destination']
    # A destination may sit below state_root, but never overlaps the cache or selected evidence.
    protected = [paths['mirror_git_dir'], paths['state_root'] / CACHE_DIRECTORY, paths['lock'],
                 Path(ex['executable']['path']), Path(ex['script']['path']),
                 Path(m['runtime_probe']['path'])]
    if m['previous_state'] is not None:
        protected.append(Path(m['previous_state']['path']).parent)
    for p in protected:
        reader.require(p != destination and destination not in p.parents
                       and p not in destination.parents, 'destination overlaps selected evidence')
    reader.require(paths['state_root'] != destination
                   and destination not in paths['state_root'].parents, 'destination overlaps state root')
    return m


# Git object reads -------------------------------------------------------------

def git_environment():
    return {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'LC_ALL': 'C',
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
            'GIT_ATTR_NOSYSTEM': '1', 'GIT_NO_REPLACE_OBJECTS': '1', 'GIT_NO_LAZY_FETCH': '1',
            'GIT_OPTIONAL_LOCKS': '0', 'GIT_TERMINAL_PROMPT': '0'}


def git(mirror, *args, stdin=b'', limit=1024**2, ok=(0,)):
    """One bounded local Git read with a closed command set; returns (code, stdout)."""
    reader.require(args and args[0] in GIT_COMMANDS, 'git command not allowed')
    command = ['git', '--no-optional-locks', '--no-lazy-fetch', '--git-dir=' + str(mirror),
               '-c', 'core.hooksPath=' + os.devnull, '-c', 'core.fsmonitor=false',
               '-c', 'core.attributesFile=' + os.devnull, '-c', 'core.autocrlf=false',
               '-c', 'core.eol=lf', '-c', 'safe.bareRepository=explicit',
               '-c', 'protocol.allow=never', *args]
    process = None
    mask = signal.pthread_sigmask(signal.SIG_BLOCK, packer.CANCEL_SIGNALS)
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, cwd='/', env=git_environment(),
                                   start_new_session=True)
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, mask)
    try:
        out, pending = bytearray(), memoryview(stdin)
        deadline = time.monotonic() + GIT_SECONDS
        os.set_blocking(process.stdin.fileno(), False)
        with selectors.DefaultSelector() as poll:
            poll.register(process.stdout, selectors.EVENT_READ)
            if pending:
                poll.register(process.stdin, selectors.EVENT_WRITE)
            else:
                process.stdin.close()
            while poll.get_map():
                remaining = deadline - time.monotonic()
                reader.require(remaining > 0, 'git timeout')
                for key, _ in poll.select(min(remaining, 0.5)):
                    if key.fileobj is process.stdin:
                        try:
                            pending = pending[os.write(process.stdin.fileno(), pending[:65536]):]
                        except BrokenPipeError:
                            pending = pending[:0]
                        if not pending:
                            poll.unregister(process.stdin)
                            process.stdin.close()
                    else:
                        block = os.read(process.stdout.fileno(), 65536)
                        if not block:
                            poll.unregister(process.stdout)
                        else:
                            out.extend(block)
                            reader.require(len(out) <= limit, 'git output limit')
        code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        reader.require(code in ok, 'git read failed: ' + args[0])
        return code, bytes(out)
    finally:
        mask = signal.pthread_sigmask(signal.SIG_BLOCK, packer.CANCEL_SIGNALS)
        try:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Unknown('git process-group cancellation unconfirmed') from exc
        finally:
            for stream in (process.stdin, process.stdout):
                if not stream.closed:
                    stream.close()
            signal.pthread_sigmask(signal.SIG_SETMASK, mask)


def resolve_commit(mirror, commit):
    with packer.directory_fd(mirror):
        pass
    _, bare = git(mirror, 'rev-parse', '--is-bare-repository', limit=64)
    reader.require(bare.strip() == b'true', 'mirror is not a bare repository')
    _, form = git(mirror, 'rev-parse', '--show-object-format', limit=64)
    reader.require(form.strip() == (b'sha1' if len(commit) == 40 else b'sha256'),
                   'commit does not match mirror object format')
    found = []
    for suffix in ('^{commit}', '^{tree}'):
        _, raw = git(mirror, 'rev-parse', '--verify', '--quiet', '--end-of-options',
                     commit + suffix, limit=256)
        value = raw.strip().decode('ascii')
        reader.require(oid(value) and len(value) == len(commit), 'unresolved commit object')
        found.append(value)
    reader.require(found[0] == commit, 'commit object mismatch')
    return found[1]


ENTRY = re.compile(rb'(\d{6}) (blob|commit|tree) ([0-9a-f]{40}|[0-9a-f]{64}) +(-|\d+)\t(.+)', re.S)


def safe_path(value):
    try:
        packer.file_path(value)
    except ValueError:
        return False
    return '.git' not in PurePosixPath(value).parts


def admission(mirror, commit, policy, limits):
    """Return (admitted [{path, blob_oid, bytes}], unsupported [{path, reason}])."""
    _, listing = git(mirror, 'ls-tree', '-r', '-z', '-l', '--full-tree', commit,
                     limit=MAX_TREE_OUTPUT)
    reader.require(not listing or listing.endswith(b'\0'), 'malformed tree listing')
    admitted, unsupported = [], []
    file_limit = min(policy['max_file_bytes'], limits['file_bytes'])
    for record in listing.split(b'\0')[:-1]:
        match = ENTRY.fullmatch(record)
        reader.require(match is not None, 'malformed tree entry')
        mode, kind, object_id, size, raw_path = match.groups()
        name = raw_path.decode('utf-8', 'backslashreplace')
        if any(fnmatch.fnmatchcase(name, x) for x in policy['deny']):
            continue
        if not any(fnmatch.fnmatchcase(name, x) for x in policy['include']):
            continue
        reason = None
        if mode == b'120000':
            reason = 'symlink'
        elif mode == b'160000':
            reason = 'gitlink'
        elif mode not in (b'100644', b'100755') or kind != b'blob':
            reason = 'unsupported_mode'
        elif name.encode('utf-8', 'surrogatepass') != raw_path or not safe_path(name):
            reason = 'unsafe_path'
        elif int(size) > file_limit:
            reason = 'file_byte_limit'
        if reason:
            unsupported.append(dict(path=name, reason=reason))
            reader.require(len(unsupported) <= MAX_UNSUPPORTED, 'unsupported entry limit')
        else:
            admitted.append(dict(path=name, blob_oid=object_id.decode('ascii'), bytes=int(size)))
    if admitted:
        stdin = b''.join(f['path'].encode() + b'\0' for f in admitted)
        _, raw = git(mirror, 'check-attr', '--stdin', '-z', '--source', commit, *ATTRIBUTES,
                     stdin=stdin, limit=len(stdin) * len(ATTRIBUTES) * 2 + 1024**2)
        fields = raw.split(b'\0')
        reader.require(fields[-1] == b'' and (len(fields) - 1) % 3 == 0, 'malformed attributes')
        values = {}
        for i in range(0, len(fields) - 1, 3):
            path, attribute, value = (x.decode('utf-8', 'surrogateescape') for x in fields[i:i + 3])
            values.setdefault(path, {})[attribute] = value
        reader.require(set(values) == {f['path'] for f in admitted}, 'attribute paths mismatch')
        kept = []
        for f in admitted:
            reason = conversion(values[f['path']])
            if reason:
                unsupported.append(dict(path=f['path'], reason=reason))
                reader.require(len(unsupported) <= MAX_UNSUPPORTED, 'unsupported entry limit')
            else:
                kept.append(f)
        admitted = kept
    reader.require(1 <= len(admitted) <= policy['max_files'], 'admitted file count outside policy')
    reader.require(sum(f['bytes'] for f in admitted) <= min(policy['max_total_bytes'],
                                                             limits['input_bytes']),
                   'admitted total byte limit')
    unsupported.sort(key=lambda u: u['path'])
    return admitted, unsupported


def conversion(attributes):
    """Name the first checkout conversion that would make blob bytes differ."""
    reader.require(set(attributes) == set(ATTRIBUTES), 'incomplete attributes')
    if attributes['filter'] not in ('unspecified', 'unset'):
        return 'attribute:filter'
    if attributes['eol'] == 'crlf':
        return 'attribute:eol=crlf'
    if attributes['working-tree-encoding'] not in ('unspecified', 'unset'):
        return 'attribute:working-tree-encoding'
    if attributes['ident'] not in ('unspecified', 'unset'):
        return 'attribute:ident'
    return None


def blob_hash(raw, object_id):
    algorithm = hashlib.sha1 if len(object_id) == 40 else hashlib.sha256
    return algorithm(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def read_blobs(mirror, files):
    """Read selected blobs with one cat-file --batch; verify size and object ID."""
    if not files:
        return {}
    stdin = b''.join(f['blob_oid'].encode() + b'\n' for f in files)
    _, raw = git(mirror, 'cat-file', '--batch', stdin=stdin,
                 limit=sum(f['bytes'] for f in files) + 160 * len(files))
    contents, offset = {}, 0
    for f in files:
        end = raw.index(b'\n', offset)
        header = raw[offset:end].split(b' ')
        reader.require(len(header) == 3 and header[0].decode() == f['blob_oid']
                       and header[1] == b'blob' and header[2] == str(f['bytes']).encode(),
                       'unexpected blob header')
        data = raw[end + 1:end + 1 + f['bytes']]
        reader.require(raw[end + 1 + f['bytes']:end + 2 + f['bytes']] == b'\n', 'malformed blob batch')
        reader.require(blob_hash(data, f['blob_oid']) == f['blob_oid'], 'blob object ID mismatch')
        contents[f['path']] = data
        offset = end + 2 + f['bytes']
    reader.require(offset == len(raw), 'unexpected blob batch output')
    return contents


def target_relation(mirror, commit, target):
    relation = 'unknown'
    if target['oid'] == commit:
        relation = 'current'
    elif target['oid'] is not None and len(target['oid']) == len(commit):
        code, _ = git(mirror, 'merge-base', '--is-ancestor', commit, target['oid'],
                      limit=1024, ok=(0, 1, 128))
        relation = 'behind' if code == 0 else 'unknown'
    return dict(relation=relation, **target)


# Previous build state ---------------------------------------------------------

def validate_state(state, manifest):
    packer.closed(state, STATE_FIELDS, 'build state')
    reader.require(state['schema'] == STATE_SCHEMA and state['input_basis'] == 'git_blob',
                   'unsupported build state')
    reader.require(state['repository'] == manifest['repository'] and state['family'] == FAMILY,
                   'previous build state identity mismatch')
    for name in ('commit', 'tree'):
        reader.require(oid(state[name]) and len(state[name]) == len(manifest['commit']),
                       'invalid previous ' + name)
    for name in ('admission_policy_sha256', 'adapter_sha256', 'executable_sha256',
                 'per_file_policy_sha256', 'manifest_sha256', 'request_sha256', 'package_sha256',
                 'catalog_sha256', 'archive_sha256', 'graph_sha256'):
        reader.require(reader.valid_hash(state[name]), 'invalid previous ' + name)
    reader.require(state['runtime_identity_sha256'] is None
                   or reader.valid_hash(state['runtime_identity_sha256']), 'invalid previous runtime')
    files = state['files']
    reader.require(isinstance(files, list) and 1 <= len(files) <= MAX_FILES, 'invalid previous files')
    seen = set()
    for f in files:
        packer.closed(f, ('path', 'blob_oid', 'sha256', 'bytes', 'coverage', 'key_sha256'), 'state file')
        reader.require(safe_path(f['path']) and f['path'] not in seen, 'invalid previous path')
        seen.add(f['path'])
        reader.require(oid(f['blob_oid']) and len(f['blob_oid']) == len(manifest['commit'])
                       and reader.valid_hash(f['sha256']) and type(f['bytes']) is int
                       and f['bytes'] >= 0 and f['coverage'] in ('structural', 'enriched', 'unknown')
                       and (f['key_sha256'] is None or reader.valid_hash(f['key_sha256'])),
                       'invalid previous file record')
    reader.require(isinstance(state['unsupported'], list)
                   and len(state['unsupported']) <= MAX_UNSUPPORTED, 'invalid previous unsupported')
    for u in state['unsupported']:
        packer.closed(u, ('path', 'reason'), 'state unsupported')
    packer.closed(state['counts'], COUNTS, 'state counts')
    packer.bounded_text(state['cache_status'], 'cache status')
    packer.closed(state['target_relation'], ('relation', 'oid', 'observed_at', 'method'),
                  'state target relation')
    return state


def load_previous(manifest):
    selected = manifest['previous_state']
    if selected is None:
        return None
    _, state = packer.selected_input(selected['path'], selected['sha256'], MAX_STATE)
    return validate_state(state, manifest)


def previous_package(manifest, state):
    """Verify the package beside the previous state; return its selection."""
    root = Path(manifest['previous_state']['path']).parent / 'candidate'
    package = root / 'package.json'
    packer.selected_input(package, state['package_sha256'], packer.MAX_INPUT)
    catalog, _ = reader.load_catalog(root / 'download-catalog.json', state['catalog_sha256'])
    reader.require(len(catalog['archives']) == 1
                   and catalog['archives'][0]['sha256'] == state['archive_sha256'],
                   'previous package archive mismatch')
    _, _, graph_sha, _ = reader.read_graph(root / 'download-catalog.json', catalog['archives'][0])
    reader.require(graph_sha == state['graph_sha256'], 'previous package graph mismatch')
    return dict(path=str(package), sha256=state['package_sha256'])


# Fragment cache ---------------------------------------------------------------

def open_cache(state_root, quota):
    """Return (cache|None, reason|None); an unusable cache never fails the run."""
    try:
        with packer.directory_fd(state_root) as fd:
            try:
                os.mkdir(CACHE_DIRECTORY, mode=0o700, dir_fd=fd)
            except FileExistsError:
                pass
        return fragment_cache.FragmentCache.open(str(Path(state_root) / CACHE_DIRECTORY), quota), None
    except (OSError, ValueError) as exc:
        return None, 'cache_unavailable: ' + str(exc)[:200]


def key_material(manifest, runtime_sha, per_file_sha, path, content_sha):
    return dict(schema=fragment_cache.KEY_SCHEMA, fragment_schema=FRAGMENT_SCHEMA,
                family=dict(FAMILY), adapter_sha256=manifest['extractor']['script']['sha256'],
                runtime_identity_sha256=runtime_sha, per_file_policy_sha256=per_file_sha,
                path=path, content_sha256=content_sha)


def check_fragment(item, path, content_sha, coverage):
    """Driver-side identity checks; the adapter re-validates structure on reuse."""
    reader.require(isinstance(item, dict) and item.get('schema') == FRAGMENT_SCHEMA
                   and item.get('family') == FAMILY and item.get('path') == path
                   and item.get('content_sha256') == content_sha
                   and item.get('outcome') == coverage, 'adapter fragment identity mismatch')


# Transaction ------------------------------------------------------------------

def result_template(manifest, manifest_sha):
    return dict(schema=RESULT_SCHEMA, manifest_sha256=manifest_sha, status='failed', reason=None,
                repository=manifest['repository'], commit=manifest['commit'],
                destination=manifest['destination'], retained=False, package=None,
                build_state=None, counts=None, cache_status=None, cache=None,
                runtime_identity=None, target_relation=None, attempts=0,
                canonical_currentness='unknown', promoted=False,
                limitations=['Selected Python adapter is trusted, not sandboxed; no network, memory or PID isolation.',
                             'Git-object input; checkout cleanliness and build_observation are not observed.',
                             'Lock and transaction checks are sampled cooperating-writer guarantees.',
                             'Retained transaction directories require separately authorized creator-owned cleanup.'])


def stage_files(owned, stage, contents, reused, fragments_dir):
    """Write extract contents at their paths and reused fragments under fragments_dir."""
    directories = {'': stage}

    def parent_fd(parts):
        prefix, fd = '', stage
        for part in parts:
            prefix = part if not prefix else prefix + '/' + part
            if prefix not in directories:
                directories[prefix] = owned.mkdir(fd, part)
            fd = directories[prefix]
        return fd

    for path, raw in sorted(contents.items()):
        parts = PurePosixPath(path).parts
        refresh.file_write(owned, parent_fd(parts[:-1]), parts[-1], raw)
    staged = {}
    for i, (path, blob) in enumerate(sorted(reused.items())):
        name = f'{i}.json'
        refresh.file_write(owned, parent_fd((fragments_dir,)), name, blob)
        staged[path] = dict(stage_path=fragments_dir + '/' + name, sha256=reader.digest(blob))
    return staged


def fragments_directory(paths):
    name = '.graphify-fragments'
    while any(p == name or p.startswith(name + '/') for p in paths):
        name += '_'
    return name


def attempt(owned, root, attempts_fd, number, manifest, manifest_sha, files, contents, reused,
            executable, script, policy_document):
    """Stage one adapter request, run it, and return (request_sha, raw response, evidence)."""
    destination = Path(manifest['destination'])
    base = owned.mkdir(attempts_fd, str(number))
    stage = owned.mkdir(base, 'inputs')
    stage_path = destination / 'attempts' / str(number) / 'inputs'
    staged = stage_files(owned, stage, {p: contents[p] for p in files if p not in reused},
                         reused, fragments_directory(files))
    request = dict(schema=REQUEST_SCHEMA, manifest_sha256=manifest_sha,
                   source=dict(repository=manifest['repository'], head=manifest['commit']),
                   input_basis='git_blob', stage=str(stage_path),
                   files=[dict(path=p, sha256=files[p], action='reuse' if p in reused else 'extract',
                               fragment=staged.get(p)) for p in sorted(files)],
                   policy=policy_document, extractor=manifest['extractor'], limits=manifest['limits'])
    request_raw = packer.encoded(request)
    request_sha = reader.digest(request_raw)
    refresh.file_write(owned, base, 'request.json', request_raw)
    request_path = destination / 'attempts' / str(number) / 'request.json'
    with reader.open_nofollow(request_path) as request_file:
        raw, evidence = refresh.run_adapter(executable, script, request_file, destination,
                                            manifest['limits'])
    refresh.file_write(owned, base, 'adapter-response.json', raw)
    owned.verify_ownership()
    refresh.raw_selected(request_path, request_sha, len(request_raw))
    for p in sorted(files):
        if p in reused:
            refresh.raw_selected(stage_path / staged[p]['stage_path'], staged[p]['sha256'],
                                 len(reused[p]))
        else:
            refresh.raw_selected(stage_path / p, files[p], len(contents[p]))
    return request_sha, raw, evidence


def validate_response(raw, request_sha, files, extracted):
    response = packer.strict_json(raw)
    packer.closed(response, ('schema', 'request_sha256', 'graph', 'validation', 'coverage',
                             'fragments'), 'adapter response')
    reader.require(response['schema'] == RESPONSE_SCHEMA
                   and response['request_sha256'] == request_sha, 'adapter request binding mismatch')
    coverage = response['coverage']
    reader.require(isinstance(coverage, dict) and set(coverage) == set(files), 'coverage selection mismatch')
    for path, value in coverage.items():
        reader.require(value in ('structural', 'unknown'), 'invalid adapter coverage')
    fragments = response['fragments']
    reader.require(isinstance(fragments, dict) and set(fragments) == set(extracted),
                   'adapter fragment selection mismatch')
    for path, item in fragments.items():
        check_fragment(item, path, files[path], coverage[path])
    return response


def execute(manifest, manifest_sha):
    result = result_template(manifest, manifest_sha)
    owned = None
    cache = None
    try:
        with ExitStack() as stack:
            lock = stack.enter_context(reader.open_nofollow(manifest['lock']))
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise Deferred('lock contention') from exc
            lock_identity = packer.inode(os.fstat(lock.fileno()))
            # Runs on every exit before the locked descriptor closes; loss overrides outcomes.
            stack.callback(refresh.verify_lock, manifest['lock'], lock_identity)
            mirror, commit = manifest['mirror_git_dir'], manifest['commit']
            policy, limits, ex = manifest['admission_policy'], manifest['limits'], manifest['extractor']
            if (ex['protocol'], ex['name'], ex['version']) != (PROTOCOL, FAMILY['name'], FAMILY['version']):
                raise Deferred('unsupported extractor adapter or family')
            reader.require(manifest['runtime_probe']['path']
                           == os.path.realpath(runtime_identity.__file__),
                           "runtime probe is not this driver's runtime_identity module")
            try:
                tree = resolve_commit(mirror, commit)
            except OSError as exc:
                raise Deferred('mirror unavailable') from exc
            admitted, unsupported = admission(mirror, commit, policy, limits)
            relation = result['target_relation'] = target_relation(mirror, commit, manifest['target'])
            previous = load_previous(manifest)
            try:
                executable, executable_sig = refresh.pin(stack, ex['executable'], 64 * 1024**2)
                script, script_sig = refresh.pin(stack, ex['script'], limits['file_bytes'])
            except ERRORS as exc:
                raise Deferred('extractor evidence missing, changed, or invalid') from exc
            try:
                identity = runtime_identity.identify(
                    ex['executable']['path'], ex['executable']['sha256'], ex['script']['path'],
                    ex['script']['sha256'], timeout=min(60, limits['seconds']),
                    probe_sha256=manifest['runtime_probe']['sha256'])
            except runtime_identity.Unknown as exc:
                raise Unknown('runtime probe cancellation unconfirmed') from exc
            runtime_sha = identity['identity_sha256'] if identity['status'] == 'identified' else None
            result['runtime_identity'] = dict(status=identity['status'], reason=identity['reason'],
                                              identity_sha256=runtime_sha)
            policy_sha = canonical_sha256(policy)
            per_file_sha = canonical_sha256(dict(schema=PER_FILE_SCHEMA, input_basis='git_blob',
                                                 checkout_conversion='none',
                                                 output_bytes=limits['output_bytes']))
            identities = dict(tree=tree, admission_policy_sha256=policy_sha,
                              adapter_sha256=ex['script']['sha256'],
                              executable_sha256=ex['executable']['sha256'],
                              per_file_policy_sha256=per_file_sha, runtime_identity_sha256=runtime_sha)
            prior = {f['path']: f for f in previous['files']} if previous else {}
            counts = dict.fromkeys(COUNTS, 0)
            counts.update(admitted=len(admitted), unsupported=len(unsupported))
            if (previous is not None and previous['commit'] == commit and runtime_sha is not None
                    and all(previous[k] == v for k, v in identities.items())
                    and [(f['path'], f['blob_oid']) for f in admitted]
                    == [(f['path'], f['blob_oid']) for f in previous['files']]
                    and unsupported == previous['unsupported']):
                result.update(status='unchanged', reason='same commit, identities and admission',
                              package=previous_package(manifest, previous),
                              build_state=dict(manifest['previous_state']), counts=counts,
                              cache_status='not_used', attempts=0)
                return result
            for f in admitted:
                old = prior.get(f['path'])
                if old is None:
                    counts['added'] += 1
                elif old['blob_oid'] != f['blob_oid']:
                    counts['modified'] += 1
            counts['deleted'] = len(set(prior) - {f['path'] for f in admitted})
            # Unchanged blobs reuse the bound previous digest; content is read only when needed.
            trusted = {}
            for old in prior.values():
                trusted.setdefault(old['blob_oid'], old['sha256'])
            contents = read_blobs(mirror, [f for f in admitted if f['blob_oid'] not in trusted])
            digests = {f['path']: reader.digest(contents[f['path']]) if f['path'] in contents
                       else trusted[f['blob_oid']] for f in admitted}
            reused, keys, cache_reason, read_errors = {}, {}, None, 0
            if runtime_sha is None:
                cache_reason = 'cache_disabled:runtime_unidentified'
            else:
                cache, cache_reason = open_cache(manifest['state_root'], manifest['cache_quota_bytes'])
                if cache is not None:
                    stack.callback(cache.close)
                    for f in admitted:
                        material = key_material(manifest, runtime_sha, per_file_sha, f['path'],
                                                digests[f['path']])
                        keys[f['path']] = (fragment_cache.key(material), material)
                        try:
                            status, item, _ = cache.get(material)
                        except (OSError, ValueError):
                            # An unreadable entry is recomputed uncached, never trusted.
                            read_errors += 1
                            continue
                        if status == 'hit':
                            reused[f['path']] = packer.encoded(item)
            missing = [f for f in admitted if f['path'] not in reused and f['path'] not in contents]
            contents.update(read_blobs(mirror, missing))
            for f in missing:
                reader.require(reader.digest(contents[f['path']]) == digests[f['path']],
                               'previous build state blob digest mismatch')
            source = dict(repository=manifest['repository'], head=commit)
            policy_document = dict(schema='graphify-pack-policy/v1', source=source,
                                   name='incremental-admission', rules=policy, limitations=[])
            destination = Path(manifest['destination'])
            parent = stack.enter_context(packer.directory_fd(destination.parent))
            owned = packer.OwnedOutput(parent, destination.name)
            stack.callback(owned.close)
            stack.callback(refresh.verify_retained, owned)
            try:
                root = owned.create()
            except FileExistsError as exc:
                raise Deferred('output collision; prior destination preserved') from exc
            except OSError as exc:
                raise Unknown('destination creation effect requires reconciliation') from exc
            result['retained'] = True
            attempts_fd = owned.mkdir(root, 'attempts')
            files = {f['path']: digests[f['path']] for f in admitted}
            run = (owned, root, attempts_fd)
            try:
                result['attempts'] = 1
                request_sha, raw, evidence = attempt(*run, 1, manifest, manifest_sha, files,
                                                     contents, reused, executable, script,
                                                     policy_document)
            except ValueError as exc:
                if not reused or 'extractor nonzero exit' not in str(exc):
                    raise
                # Rejected reuse falls back once to an uncached extraction of every file.
                cache_reason = 'reuse_rejected'
                contents.update(read_blobs(mirror, [f for f in admitted if f['path'] in reused]))
                for p in reused:
                    reader.require(reader.digest(contents[p]) == digests[p],
                                   'previous build state blob digest mismatch')
                reused = {}
                result['attempts'] = 2
                request_sha, raw, evidence = attempt(*run, 2, manifest, manifest_sha, files,
                                                     contents, reused, executable, script,
                                                     policy_document)
            result['process'] = evidence
            reader.require(reader.signature(executable) == executable_sig and
                           reader.signature(script) == script_sig, 'adapter changed during execution')
            extracted = [p for p in files if p not in reused]
            response = validate_response(raw, request_sha, files, extracted)
            counts.update(reused=len(reused), extracted=len(extracted))
            puts = {}
            if cache is not None and cache_reason != 'reuse_rejected':
                for p in sorted(extracted):
                    try:
                        outcome = cache.put(keys[p][1], response['fragments'][p])
                    except (OSError, ValueError):
                        outcome = 'error'
                    puts[outcome] = puts.get(outcome, 0) + 1
            if cache is not None:
                stats = cache.stats()
                counts.update(cache_hits=stats['hits'], cache_misses=stats['misses'],
                              cache_corrupt=stats['corrupt'], cache_full=puts.get('full', 0))
                result['cache'] = dict(stats, puts=puts, read_errors=read_errors)
                if cache_reason is None:
                    degraded = (stats['corrupt'] or read_errors or puts.get('error')
                                or puts.get('exists_conflict'))
                    cache_reason = (stats['status'] if stats['status'] != 'ok'
                                    else 'degraded' if degraded else 'ok')
            documents = pack_documents(manifest, source, response, files, relation, request_sha,
                                       identities, unsupported)
            inputs = {}
            evidence_fd = owned.mkdir(root, 'evidence')
            for name, document in documents.items():
                content = packer.encoded(document)
                refresh.file_write(owned, evidence_fd, name + '.json', content)
                inputs[name] = (destination / 'evidence' / (name + '.json'), reader.digest(content))
            owned.verify_ownership()
            refresh.verify_lock(manifest['lock'], lock_identity)
            package = packer.pack(inputs, destination / 'candidate')
            owned.candidate_completed = True
            state = dict(schema=STATE_SCHEMA, repository=manifest['repository'], family=dict(FAMILY),
                         commit=commit, input_basis='git_blob', manifest_sha256=manifest_sha,
                         request_sha256=request_sha, **identities,
                         files=[dict(path=f['path'], blob_oid=f['blob_oid'], sha256=files[f['path']],
                                     bytes=f['bytes'], coverage=response['coverage'][f['path']],
                                     key_sha256=keys[f['path']][0] if f['path'] in keys else None)
                                for f in admitted],
                         unsupported=unsupported, package_sha256=package['package_sha256'],
                         catalog_sha256=package['catalog_sha256'],
                         archive_sha256=package['archive_sha256'], graph_sha256=package['graph_sha256'],
                         counts=counts, cache_status=cache_reason,
                         target_relation=relation)
            state_raw = packer.encoded(state)
            reader.require(len(state_raw) <= MAX_STATE, 'build state byte limit')
            refresh.file_write(owned, root, STATE_NAME, state_raw)
            refresh.raw_selected(destination / STATE_NAME, reader.digest(state_raw), len(state_raw))
            # After pack, only the validated candidate may be untracked by this transaction.
            refresh.verify_retained(owned)
            result.update(status='completed', reason='create-only candidate and build state validated',
                          package=dict(path=str(destination / 'candidate' / 'package.json'),
                                       sha256=package['package_sha256']),
                          build_state=dict(path=str(destination / STATE_NAME),
                                           sha256=reader.digest(state_raw)),
                          counts=counts, cache_status=cache_reason)
    except Deferred as exc:
        result.update(status='deferred', reason=str(exc)[:500])
    except (Unknown, packer.UnknownOutputError, runtime_identity.Unknown) as exc:
        result.update(status='unknown', reason=str(exc)[:500])
    except KeyboardInterrupt:
        result.update(status='deferred', reason='cancelled; no promotion', cancelled=True)
    except ERRORS as exc:
        result.update(status='failed', reason=(type(exc).__name__ + ': ' + str(exc))[:500])
    finally:
        # Outputs persist as evidence, including incomplete transactions; nothing is deleted.
        if owned is not None and owned.created:
            result['retained'] = True
    return result


def pack_documents(manifest, source, response, files, relation, request_sha, identities, unsupported):
    ex = manifest['extractor']
    runtime = identities['runtime_identity_sha256'] or 'unidentified (fragment cache disabled)'
    target = relation['oid'] or 'none'
    documents = dict(
        inventory=dict(schema='graphify-pack-inventory/v1', source=source,
                       files=[dict(path=p, sha256=files[p], coverage=response['coverage'][p])
                              for p in sorted(files)],
                       limitations=['Coverage is reported by the selected adapter, not independently attested.',
                                    'Admitted from Git objects at the selected commit; no checkout was read.']),
        policy=dict(schema='graphify-pack-policy/v1', source=source, name='incremental-admission',
                    rules=manifest['admission_policy'], limitations=[]),
        extractor=dict(schema='graphify-pack-extractor/v1', source=source, name=ex['name'],
                       version=ex['version'], artifact_sha256=ex['script']['sha256'],
                       limitations=['Interpreter identity and adapter protocol are bound by refresh request.',
                                    'Runtime identity: ' + runtime]),
        graph=response['graph'], validation=response['validation'])
    for name in ('graph', 'validation'):
        reader.require(documents[name].get('source') == source
                       and documents[name].get('refresh_request_sha256') == request_sha,
                       'adapter output provenance mismatch')
    hashes = {n: reader.digest(packer.encoded(d)) for n, d in documents.items()}
    documents['source'] = dict(
        schema='graphify-pack-source/v1', source=source, input_sha256=hashes, build_observation=None,
        limitations=['Input basis git_blob: commit ' + source['head'] + ' tree ' + identities['tree']
                     + ' read from a producer-owned bare mirror; no checkout was observed.',
                     'Target relation: ' + relation['relation'] + ' (target ' + target + ', observed_at '
                     + str(relation['observed_at']) + ', method ' + str(relation['method']) + ').',
                     'Canonical latest source remains unknown; adapter claims are not independently attested.',
                     f'Unsupported admitted-pattern entries: {len(unsupported)} (recorded in build state).',
                     'Refresh request SHA256: ' + request_sha])
    return documents


def incremental(manifest_path, manifest_sha):
    refresh.absolute(str(manifest_path))
    _, manifest = packer.selected_input(manifest_path, manifest_sha, refresh.MAX_MANIFEST)
    validate_manifest(manifest)
    return execute(manifest, manifest_sha)


def bounded_receipt(result):
    raw = packer.encoded(result)
    if len(raw) > MAX_RECEIPT:
        # Preserve identity and the non-success effect; never truncate into success.
        raw = packer.encoded(dict(schema=RESULT_SCHEMA, status='unknown',
                                  manifest_sha256=result.get('manifest_sha256'), promoted=False,
                                  reason='receipt byte bound exceeded; reconcile selected destination'))
    return raw


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', required=True)
    p.add_argument('--manifest-sha256', required=True)
    args = p.parse_args(argv)
    old = {}

    def cancel(signum, frame):
        raise KeyboardInterrupt('cancelled')

    for sig in (signal.SIGTERM, signal.SIGINT):
        old[sig] = signal.signal(sig, cancel)
    try:
        try:
            result = incremental(args.manifest, args.manifest_sha256)
        except KeyboardInterrupt:
            result = dict(schema=RESULT_SCHEMA, status='deferred', reason='cancelled', promoted=False)
        except ERRORS as exc:
            result = dict(schema=RESULT_SCHEMA, status='failed', reason=str(exc)[:500], promoted=False)
        raw = bounded_receipt(result)
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()
        status = packer.strict_json(raw)['status']
        return 0 if status in ('completed', 'unchanged') else 2 if status == 'deferred' else 1
    finally:
        for sig, handler in old.items():
            signal.signal(sig, handler)


if __name__ == '__main__':
    raise SystemExit(main())
