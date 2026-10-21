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

A graphify-incremental-manifest/v2 selects admission policy v2 and family 2:
the repository is split into slices by ordered prefix rules (optional fixed
SHA256 path buckets) with everything else in `rest`, and each slice is one
package. A staged graphify-path-index/v1 over every admitted path lets each
slice resolve references into other slices. A slice reruns the adapter only
when its path->blob map, identities or resolution digest changed; otherwise
its verified package is reused with its original built head. Every run emits a
graphify-slice-set/v1 for the accepted head and one graphify-build-state/v2 per
built slice. An over-limit slice holds the run; nothing is split automatically.
Mode inventory_only reports admission, slices and a resource preview without
reading blobs, running the adapter or touching the fragment cache. Version 1
manifests keep their exact behavior.
"""
import argparse
from contextlib import ExitStack
import fcntl
import fnmatch
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import resource
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

# Sliced builds (manifest v2). Bounds are D5's; none may be raised by a manifest.
SCHEMA_V2 = 'graphify-incremental-manifest/v2'
RESULT_SCHEMA_V2 = 'graphify-incremental-result/v2'
POLICY_SCHEMA_V2 = 'graphify-admission-policy/v2'
SLICE_STATE_SCHEMA = 'graphify-build-state/v2'
SLICE_SET_SCHEMA = 'graphify-slice-set/v1'
SLICE_RUN_SCHEMA = 'graphify-slice-run/v1'
SLICE_INPUT_SCHEMA = 'graphify-slice-input/v1'
PATH_INDEX_SCHEMA = 'graphify-path-index/v1'
INVENTORY_SCHEMA = 'graphify-admission-inventory/v1'
FAMILY_V2 = dict(name='graphify-stdlib-structural', version='2')
FRAGMENT_SCHEMA_V2 = 'graphify-structural-fragment/v2'
MANIFEST_V2_FIELDS = ('schema', 'mode', 'repository', 'mirror_git_dir', 'commit', 'target',
                      'admission_policy', 'extractor', 'runtime_probe', 'state_root',
                      'previous_run', 'destination', 'lock', 'cache_quota_bytes', 'limits')
MODES = ('build', 'inventory_only')
# A v2 state is a v1 state plus explicit slice fields; G-H v1 refuses it by schema and fields.
SLICE_STATE_FIELDS = STATE_FIELDS + ('slice', 'input_digest', 'resolution_digest',
                                     'path_index_sha256', 'reference_candidates')
# cache_uncacheable: extracted fragments whose cache entry would exceed the v2 entry cap.
SLICE_COUNTS = COUNTS + ('unchanged', 'unknown', 'cache_uncacheable')
RUN_COUNTS = SLICE_COUNTS + ('slices', 'slices_built', 'slices_reused', 'slices_removed',
                             'adapter_runs')
SLICE_ENTRY_FIELDS = ('name', 'package_sha256', 'built_head', 'input_digest', 'resolution_digest',
                      'build_state_sha256')
IDENTITY_FIELDS = ('admission_policy_sha256', 'adapter_sha256', 'executable_sha256',
                   'per_file_policy_sha256', 'runtime_identity_sha256')
LIMITS_V2 = dict(file_bytes=4 * 1024**2, input_bytes=112 * 1024**2,
                 output_bytes=64 * 1024**2, seconds=300, records=100000)
MAX_REPOSITORY_FILES = 32768
MAX_REPOSITORY_BYTES = 128 * 1024**2
MAX_SLICE_FILES = 2048
MAX_SLICE_BYTES = 48 * 1024**2
# r3 operating value: half the slice ceiling until a measured cold response is <= output/1.5.
OPERATING_MAX_SLICE_BYTES = 24 * 1024**2
# Family-2 adapter ceilings (refresh_adapter_structural MAX_REQUEST_V2, FRAGMENT_BYTES).
MAX_REQUEST_V2 = 2 * 1024**2
FRAGMENT_BYTES = 8 * 1024**2
MAX_SLICE_RECORDS = 100000
MAX_INDEX_BYTES = 8 * 1024**2
MAX_RULES = 64
MAX_BUCKETS = 16
# graph_catalog.MAX_PACKAGES: every possible slice must fit one catalog; excess is refused.
MAX_SLICES = 128
MAX_CANDIDATES = 262144
REST = 'rest'
RULE_NAME = re.compile('[A-Za-z0-9][A-Za-z0-9_-]{0,59}')
SLICE_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}')
SLICES_DIRECTORY = 'slices'
SLICE_SET_NAME = 'slice-set.json'
SLICE_RUN_NAME = 'slice-run.json'
INVENTORY_NAME = 'inventory.json'
SLICE_REPORT_NAME = 'slice-report.json'
SLICE_REPORT_SCHEMA = 'graphify-slice-report/v1'


class AdapterRejected(ValueError):
    """The adapter refused a preflighted request; it reports no cause code."""
PATH_INDEX_NAME = 'path-index.json'


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
    validate_globs(policy)
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
    admitted, unsupported = tree_entries(mirror, commit, policy,
                                         min(policy['max_file_bytes'], limits['file_bytes']))
    reader.require(1 <= len(admitted) <= policy['max_files'], 'admitted file count outside policy')
    reader.require(sum(f['bytes'] for f in admitted) <= min(policy['max_total_bytes'],
                                                             limits['input_bytes']),
                   'admitted total byte limit')
    return admitted, unsupported


def tree_entries(mirror, commit, policy, file_limit, tally=None):
    """Apply include/deny and per-entry checks to ls-tree; tally counts skipped entries."""
    _, listing = git(mirror, 'ls-tree', '-r', '-z', '-l', '--full-tree', commit,
                     limit=MAX_TREE_OUTPUT)
    reader.require(not listing or listing.endswith(b'\0'), 'malformed tree listing')
    admitted, unsupported = [], []
    for record in listing.split(b'\0')[:-1]:
        match = ENTRY.fullmatch(record)
        reader.require(match is not None, 'malformed tree entry')
        mode, kind, object_id, size, raw_path = match.groups()
        name = raw_path.decode('utf-8', 'backslashreplace')
        if any(fnmatch.fnmatchcase(name, x) for x in policy['deny']):
            if tally is not None:
                tally['denied'] += 1
            continue
        if not any(fnmatch.fnmatchcase(name, x) for x in policy['include']):
            if tally is not None:
                tally['not_included'] += 1
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
    state_body(state, len(manifest['commit']), MAX_FILES, COUNTS)
    return state


def state_body(state, oid_length, max_files, counts):
    """Field checks shared by v1 states and v2 slice states."""
    for name in ('commit', 'tree'):
        reader.require(oid(state[name]) and len(state[name]) == oid_length,
                       'invalid previous ' + name)
    for name in ('admission_policy_sha256', 'adapter_sha256', 'executable_sha256',
                 'per_file_policy_sha256', 'manifest_sha256', 'request_sha256', 'package_sha256',
                 'catalog_sha256', 'archive_sha256', 'graph_sha256'):
        reader.require(reader.valid_hash(state[name]), 'invalid previous ' + name)
    reader.require(state['runtime_identity_sha256'] is None
                   or reader.valid_hash(state['runtime_identity_sha256']), 'invalid previous runtime')
    files = state['files']
    reader.require(isinstance(files, list) and 1 <= len(files) <= max_files, 'invalid previous files')
    seen = set()
    for f in files:
        packer.closed(f, ('path', 'blob_oid', 'sha256', 'bytes', 'coverage', 'key_sha256'), 'state file')
        reader.require(safe_path(f['path']) and f['path'] not in seen, 'invalid previous path')
        seen.add(f['path'])
        reader.require(oid(f['blob_oid']) and len(f['blob_oid']) == oid_length
                       and reader.valid_hash(f['sha256']) and type(f['bytes']) is int
                       and f['bytes'] >= 0 and f['coverage'] in ('structural', 'enriched', 'unknown')
                       and (f['key_sha256'] is None or reader.valid_hash(f['key_sha256'])),
                       'invalid previous file record')
    reader.require(isinstance(state['unsupported'], list)
                   and len(state['unsupported']) <= MAX_UNSUPPORTED, 'invalid previous unsupported')
    for u in state['unsupported']:
        packer.closed(u, ('path', 'reason'), 'state unsupported')
    packer.closed(state['counts'], counts, 'state counts')
    packer.bounded_text(state['cache_status'], 'cache status')
    packer.closed(state['target_relation'], ('relation', 'oid', 'observed_at', 'method'),
                  'state target relation')


def load_previous(manifest):
    selected = manifest['previous_state']
    if selected is None:
        return None
    _, state = packer.selected_input(selected['path'], selected['sha256'], MAX_STATE)
    return validate_state(state, manifest)


def previous_package(manifest, state):
    """Verify the package beside the previous state; return its selection."""
    return verified_package(Path(manifest['previous_state']['path']).parent / 'candidate', state)


def verified_package(root, state):
    """Verify package, catalog, archive and graph against a state's digests."""
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


def check_fragment(item, path, content_sha, coverage, schema=FRAGMENT_SCHEMA, family=FAMILY):
    """Driver-side identity checks; the adapter re-validates structure on reuse."""
    reader.require(isinstance(item, dict) and item.get('schema') == schema
                   and item.get('family') == family and item.get('path') == path
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


def validate_response(raw, request_sha, files, extracted, schema=FRAGMENT_SCHEMA, family=FAMILY):
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
        check_fragment(item, path, files[path], coverage[path], schema, family)
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


# Sliced builds: manifest v2, admission policy v2, family 2 ---------------------

def validate_globs(policy):
    for name, minimum in (('include', 1), ('deny', 0)):
        globs = policy[name]
        reader.require(isinstance(globs, list) and minimum <= len(globs) <= MAX_GLOBS
                       and len(set(map(str, globs))) == len(globs), 'invalid admission globs')
        for glob in globs:
            reader.require(isinstance(glob, str) and 0 < len(glob) <= 256
                           and all(32 <= ord(c) <= 126 for c in glob) and '\\' not in glob
                           and not glob.startswith('/'), 'invalid admission glob')


def validate_policy_v2(policy):
    packer.closed(policy, ('schema', 'include', 'deny', 'max_files', 'max_file_bytes',
                           'max_total_bytes', 'slicing'), 'admission policy')
    reader.require(policy['schema'] == POLICY_SCHEMA_V2, 'unsupported admission policy')
    validate_globs(policy)
    for name, maximum in (('max_files', MAX_REPOSITORY_FILES),
                          ('max_file_bytes', LIMITS_V2['file_bytes']),
                          ('max_total_bytes', MAX_REPOSITORY_BYTES)):
        n = policy[name]
        reader.require(type(n) is int and 1 <= n <= maximum, 'invalid admission limit ' + name)
    slicing = policy['slicing']
    packer.closed(slicing, ('rules', 'max_slice_files', 'max_slice_bytes', 'max_slice_records'),
                  'slicing')
    for name, maximum in (('max_slice_files', MAX_SLICE_FILES),
                          ('max_slice_bytes', OPERATING_MAX_SLICE_BYTES),
                          ('max_slice_records', MAX_SLICE_RECORDS)):
        n = slicing[name]
        reader.require(type(n) is int and 1 <= n <= maximum, 'invalid slicing limit ' + name)
    rules = slicing['rules']
    reader.require(isinstance(rules, list) and len(rules) <= MAX_RULES, 'invalid slicing rules')
    names, prefixes, possible = set(), set(), 1
    for rule in rules:
        reader.require(isinstance(rule, dict), 'invalid slicing rule')
        packer.closed(rule, ('prefix', 'name') + (('buckets',) if 'buckets' in rule else ()),
                      'slicing rule')
        prefix, name = rule['prefix'], rule['name']
        reader.require(isinstance(prefix, str) and prefix.endswith('/') and safe_path(prefix[:-1])
                       and prefix not in prefixes, 'invalid slicing prefix')
        reader.require(isinstance(name, str) and RULE_NAME.fullmatch(name) is not None
                       and name != REST and name not in names, 'invalid slice rule name')
        prefixes.add(prefix)
        names.add(name)
        if 'buckets' in rule:
            reader.require(type(rule['buckets']) is int and 1 <= rule['buckets'] <= MAX_BUCKETS,
                           'invalid slicing buckets')
        possible += rule.get('buckets', 1)
    # Every possible slice must fit one catalog; the catalog cap is reported, never raised.
    reader.require(possible <= MAX_SLICES, 'possible slices exceed the catalog package cap')
    return policy


def assign_slice(path, rules):
    """First matching prefix wins; buckets are sha256(path) mod a fixed count, so
    adding or removing other paths never moves an existing path."""
    for rule in rules:
        if path.startswith(rule['prefix']):
            if 'buckets' not in rule:
                return rule['name']
            bucket = int(hashlib.sha256(path.encode('utf-8', 'surrogatepass')).hexdigest(), 16)
            return '%s.%02d' % (rule['name'], bucket % rule['buckets'])
    return REST


def plan_slices(admitted, unsupported, policy):
    """Return ({name: files}, {name: unsupported}, holds); empty slices do not exist."""
    slicing = policy['slicing']
    slices, skipped = {}, {}
    for f in admitted:
        slices.setdefault(assign_slice(f['path'], slicing['rules']), []).append(f)
    for u in unsupported:
        skipped.setdefault(assign_slice(u['path'], slicing['rules']), []).append(u)
    holds = []
    total = sum(f['bytes'] for f in admitted)
    if len(admitted) > policy['max_files'] or total > policy['max_total_bytes']:
        holds.append(dict(reason='repository_over_limit', slice=None,
                          bounds=[b for b, over in (('files', len(admitted) > policy['max_files']),
                                                    ('content_bytes', total > policy['max_total_bytes']))
                                  if over], files=len(admitted), bytes=total))
    for name in sorted(slices):
        files = slices[name]
        size = sum(f['bytes'] for f in files)
        bounds = [b for b, over in (('files', len(files) > slicing['max_slice_files']),
                                    ('content_bytes', size > slicing['max_slice_bytes'])) if over]
        if bounds:
            holds.append(dict(reason='slice_over_limit', slice=name, bounds=bounds, files=len(files),
                              bytes=size))
    return slices, skipped, holds


def stage_names(files, reused):
    """(fragments directory, index name, {path: fragment stage path}) exactly as staged."""
    fragments_dir = fragments_directory(files)
    index_name = '.graphify-path-index.json'
    while index_name == fragments_dir or any(p == index_name or p.startswith(index_name + '/')
                                             for p in files):
        index_name = '_' + index_name
    return fragments_dir, index_name, {p: f'{fragments_dir}/{i}.json' for i, p in enumerate(sorted(reused))}


def path_lengths(paths):
    """UTF-8 byte length max and nearest-rank p99 over admitted paths."""
    sizes = sorted(len(p.encode('utf-8', 'surrogatepass')) for p in paths)
    if not sizes:
        return dict(max_bytes=0, p99_bytes=0)
    return dict(max_bytes=sizes[-1], p99_bytes=sizes[max(0, -(-99 * len(sizes) // 100) - 1)])


def path_index(slices):
    paths = {f['path']: name for name, files in slices.items() for f in files}
    raw = packer.encoded(dict(schema=PATH_INDEX_SCHEMA, paths=paths))
    return paths, raw


def slice_identities(policy_sha, ex, per_file_sha, runtime_sha):
    return dict(admission_policy_sha256=policy_sha, adapter_sha256=ex['script']['sha256'],
                executable_sha256=ex['executable']['sha256'], per_file_policy_sha256=per_file_sha,
                runtime_identity_sha256=runtime_sha)


def input_digest(repository, name, files, unsupported, identities):
    """Digest of everything a slice package depends on except cross-slice resolution."""
    return canonical_sha256(dict(
        schema=SLICE_INPUT_SCHEMA, repository=repository, slice=name, family=FAMILY_V2,
        files=sorted([f['path'], f['blob_oid']] for f in files),
        unsupported=sorted([u['path'], u['reason']] for u in unsupported),
        identities={k: identities[k] for k in IDENTITY_FIELDS}))


def resolution_digest(candidates, index):
    """Canonical SHA256 of sorted [(candidate, owning slice or null)] (r2 edge 3)."""
    return canonical_sha256(sorted([c, index.get(c)] for c in set(candidates)))


def fragment_candidates(fragments):
    found = set()
    for item in fragments:
        for reference in item.get('references', ()):
            values = reference.get('candidates') if isinstance(reference, dict) else None
            reader.require(isinstance(values, list), 'invalid fragment reference candidates')
            for value in values:
                reader.require(isinstance(value, str), 'invalid fragment reference candidate')
                found.add(value)
    reader.require(len(found) <= MAX_CANDIDATES, 'reference candidate limit')
    return sorted(found)


def structural_file_id(path):
    """Mirror of the adapter's file_id: record_id(path, 'file', path)."""
    return 'structural-v1:' + reader.digest(packer.encoded([path, 'file', path]))


def check_cross_slice(validation, index, name, own):
    """Every cross-slice record must name an indexed path owned by another slice."""
    records = validation.get('cross_slice_references')
    reader.require(isinstance(records, list), 'adapter omitted cross_slice_references')
    for r in records:
        packer.closed(r, ('source', 'source_file', 'type', 'target', 'line', 'target_path',
                          'target_id', 'target_slice'), 'cross-slice reference')
        reader.require(r['source_file'] in own and r['source'] == structural_file_id(r['source_file'])
                       and r['target_path'] not in own and index.get(r['target_path']) == r['target_slice']
                       and r['target_slice'] != name
                       and r['target_id'] == structural_file_id(r['target_path']),
                       'invalid cross-slice reference')
    return len(records)


def validate_manifest_v2(m):
    packer.closed(m, MANIFEST_V2_FIELDS, 'incremental manifest')
    reader.require(m['schema'] == SCHEMA_V2, 'unsupported manifest')
    reader.require(m['mode'] in MODES, 'invalid mode')
    packer.source_identity(dict(repository=m['repository'], head=m['commit']))
    reader.require(oid(m['commit']), 'invalid commit')
    target = m['target']
    packer.closed(target, ('oid', 'observed_at', 'method'), 'target')
    reader.require(target['oid'] is None or oid(target['oid']), 'invalid target oid')
    optional_text(target['observed_at'], 'target observed_at')
    optional_text(target['method'], 'target method')
    validate_policy_v2(m['admission_policy'])
    ex = m['extractor']
    packer.closed(ex, ('protocol', 'name', 'version', 'executable', 'script'), 'extractor')
    for key in ('protocol', 'name', 'version'):
        packer.bounded_text(ex[key], 'extractor ' + key)
    refresh.selection(ex['executable'])
    refresh.selection(ex['script'])
    refresh.selection(m['runtime_probe'])
    if m['previous_run'] is not None:
        refresh.selection(m['previous_run'])
        reader.require(Path(m['previous_run']['path']).name == SLICE_RUN_NAME,
                       'previous run must be a ' + SLICE_RUN_NAME)
    reader.require(type(m['cache_quota_bytes']) is int and m['cache_quota_bytes'] >= 0,
                   'invalid cache quota')
    packer.closed(m['limits'], LIMITS_V2, 'limits')
    for name, maximum in LIMITS_V2.items():
        n = m['limits'][name]
        reader.require(type(n) is int and 1 <= n <= maximum, 'invalid limit ' + name)
    paths = {k: refresh.absolute(m[k]) for k in ('mirror_git_dir', 'state_root', 'destination', 'lock')}
    protected = [paths['mirror_git_dir'], paths['state_root'] / CACHE_DIRECTORY, paths['lock'],
                 Path(ex['executable']['path']), Path(ex['script']['path']),
                 Path(m['runtime_probe']['path'])]
    if m['previous_run'] is not None:
        protected.append(Path(m['previous_run']['path']).parent)
    disjoint_destination(paths['destination'], protected)
    reader.require(paths['state_root'] != paths['destination']
                   and paths['destination'] not in paths['state_root'].parents,
                   'destination overlaps state root')
    return m


def disjoint_destination(destination, protected):
    for p in protected:
        reader.require(p != destination and destination not in p.parents
                       and p not in destination.parents, 'destination overlaps selected evidence')


def validate_slice_state(state, manifest, name):
    packer.closed(state, SLICE_STATE_FIELDS, 'slice build state')
    reader.require(state['schema'] == SLICE_STATE_SCHEMA and state['input_basis'] == 'git_blob',
                   'unsupported slice build state')
    reader.require(state['repository'] == manifest['repository'] and state['family'] == FAMILY_V2
                   and state['slice'] == name, 'previous slice state identity mismatch')
    state_body(state, len(manifest['commit']), MAX_SLICE_FILES, SLICE_COUNTS)
    for key in ('input_digest', 'resolution_digest', 'path_index_sha256'):
        reader.require(reader.valid_hash(state[key]), 'invalid previous ' + key)
    candidates = state['reference_candidates']
    reader.require(isinstance(candidates, list) and len(candidates) <= MAX_CANDIDATES
                   and all(isinstance(c, str) for c in candidates)
                   and candidates == sorted(set(candidates)), 'invalid previous reference candidates')
    return state


def validate_slice_set(value, repository, oid_length):
    packer.closed(value, ('schema', 'repository', 'accepted_head', 'tree', 'slices'), 'slice set')
    reader.require(value['schema'] == SLICE_SET_SCHEMA and value['repository'] == repository,
                   'slice set identity mismatch')
    for key in ('accepted_head', 'tree'):
        reader.require(oid(value[key]) and len(value[key]) == oid_length, 'invalid slice set ' + key)
    slices = value['slices']
    reader.require(isinstance(slices, list) and 1 <= len(slices) <= MAX_SLICES, 'invalid slice set slices')
    names = []
    for entry in slices:
        packer.closed(entry, SLICE_ENTRY_FIELDS, 'slice set slice')
        reader.require(isinstance(entry['name'], str) and SLICE_NAME.fullmatch(entry['name'])
                       and oid(entry['built_head']) and len(entry['built_head']) == oid_length
                       and all(reader.valid_hash(entry[k]) for k in
                               ('package_sha256', 'input_digest', 'resolution_digest',
                                'build_state_sha256')), 'invalid slice set slice')
        names.append(entry['name'])
    reader.require(names == sorted(set(names)), 'slice set slices unsorted or duplicated')
    return value


def load_previous_run(manifest):
    """Return {slice_set, slice_set_sha256, states: {name: (state, selection)}} or None."""
    selected = manifest['previous_run']
    if selected is None:
        return None
    oid_length = len(manifest['commit'])
    _, run = packer.selected_input(selected['path'], selected['sha256'], MAX_STATE)
    packer.closed(run, ('schema', 'repository', 'accepted_head', 'tree', 'slice_set_sha256',
                        'path_index_sha256', 'slices'), 'slice run')
    reader.require(run['schema'] == SLICE_RUN_SCHEMA and run['repository'] == manifest['repository'],
                   'previous slice run identity mismatch')
    _, slice_set = packer.selected_input(Path(selected['path']).parent / SLICE_SET_NAME,
                                         run['slice_set_sha256'], MAX_STATE)
    validate_slice_set(slice_set, manifest['repository'], oid_length)
    reader.require((slice_set['accepted_head'], slice_set['tree'])
                   == (run['accepted_head'], run['tree']), 'previous slice run head mismatch')
    entries = {e['name']: e for e in slice_set['slices']}
    reader.require(isinstance(run['slices'], list)
                   and [s.get('name') if isinstance(s, dict) else None for s in run['slices']]
                   == list(entries), 'previous slice run contradicts its slice set')
    states = {}
    for item in run['slices']:
        packer.closed(item, ('name', 'status', 'built_head', 'build_state', 'package'), 'slice run slice')
        name, entry = item['name'], entries[item['name']]
        refresh.selection(item['build_state'])
        refresh.selection(item['package'])
        state_path = Path(item['build_state']['path'])
        reader.require(item['status'] in ('built', 'reused') and state_path.name == STATE_NAME
                       and item['build_state']['sha256'] == entry['build_state_sha256']
                       and item['package'] == dict(path=str(state_path.parent / 'candidate' / 'package.json'),
                                                   sha256=entry['package_sha256'])
                       and item['built_head'] == entry['built_head'], 'invalid previous slice run slice')
        _, state = packer.selected_input(state_path, entry['build_state_sha256'], MAX_STATE)
        validate_slice_state(state, manifest, name)
        reader.require(state['package_sha256'] == entry['package_sha256']
                       and state['commit'] == entry['built_head']
                       and state['input_digest'] == entry['input_digest']
                       and state['resolution_digest'] == entry['resolution_digest'],
                       'previous slice state contradicts its slice set')
        states[name] = (state, item['build_state'])
    return dict(slice_set=slice_set, slice_set_sha256=run['slice_set_sha256'], states=states)


def key_material_v2(manifest, runtime_sha, per_file_sha, path, content_sha):
    return dict(key_material(manifest, runtime_sha, per_file_sha, path, content_sha),
                fragment_schema=FRAGMENT_SCHEMA_V2, family=dict(FAMILY_V2))


def cache_entry_bytes(material, fragment):
    """Exact size of the cache entry put() would write (fragment_cache entry v1 encoding)."""
    canonical = fragment_cache.canonical
    return len(canonical(dict(schema=fragment_cache.ENTRY_SCHEMA, key_sha256=fragment_cache.key(material),
                              key=material, fragment_sha256=fragment_cache.sha256(canonical(fragment)),
                              fragment=fragment))) + 1


def cache_accepts_v2(manifest, per_file_sha):
    """The fragment cache must recognize family-2 fragments; otherwise run uncached."""
    probe = key_material_v2(manifest, '0' * 64, per_file_sha, 'probe', '0' * 64)
    try:
        fragment_cache.validate_material(probe)
    except ValueError:
        return False
    return True


def inventory_document(manifest, tree, policy_sha, admitted, unsupported, tally, slices, holds,
                       index, index_raw, previous, run):
    by_extension, by_reason = {}, {}
    for f in admitted:
        ext = PurePosixPath(f['path']).suffix or '(none)'
        by_extension[ext] = by_extension.get(ext, 0) + 1
    for u in unsupported:
        by_reason[u['reason']] = by_reason.get(u['reason'], 0) + 1
    held = {h['slice'] for h in holds if h['slice'] is not None}
    prior = previous['states'] if previous else {}
    rows = []
    for name in sorted(slices):
        files = slices[name]
        old = prior.get(name)
        if old is None:
            preview = 'new'
        elif sorted((f['path'], f['blob_oid']) for f in old[0]['files']) == sorted(
                (f['path'], f['blob_oid']) for f in files):
            preview = 'paths_and_blobs_unchanged'
        else:
            preview = 'paths_or_blobs_changed'
        size = sum(f['bytes'] for f in files)
        # Without blob reads, an all-reuse request with full digests bounds the real one.
        paths = {f['path']: '0' * 64 for f in files}
        _, index_name, names = stage_names(paths, paths)
        upper = len(run.request_raw(name, 1, paths, {p: dict(stage_path=names[p], sha256='0' * 64)
                                                     for p in paths}, index_name, '0' * 64))
        status = 'slice_over_limit' if name in held else 'admissible'
        if upper > MAX_REQUEST_V2 and name not in held:
            status = 'slice_over_limit'
            holds.append(dict(reason='slice_over_limit', slice=name, bounds=['request_bytes'],
                              files=len(files), bytes=size))
        rows.append(dict(name=name, files=len(files), bytes=size, status=status, preview=preview,
                         path_length=path_lengths(paths), request_bytes_upper_bound=upper,
                         stage_bytes_if_built=size + len(index_raw)))
    return dict(schema=INVENTORY_SCHEMA, repository=manifest['repository'], commit=manifest['commit'],
                tree=tree, admission_policy_sha256=policy_sha,
                totals=dict(admitted=len(admitted), admitted_bytes=sum(f['bytes'] for f in admitted),
                            unsupported=len(unsupported), **tally),
                admitted_by_extension=dict(sorted(by_extension.items())),
                unsupported_by_reason=dict(sorted(by_reason.items())),
                slices=rows, removed_slices=sorted(set(prior) - set(slices)), holds=holds,
                path_length=path_lengths(index),
                path_index=dict(entries=len(index), bytes=len(index_raw),
                                sha256=reader.digest(index_raw),
                                within_limit=len(index_raw) <= MAX_INDEX_BYTES),
                paths=index, unsupported=unsupported,
                limitations=['Inventory reads the Git tree and attributes only; no blob, adapter or cache was used.',
                             'Forbidden-marker detection is adapter-side and was not performed.',
                             'Preview compares path->blob maps only; identities and cross-slice resolution are evaluated at build.',
                             'request_bytes_upper_bound assumes every file is reused; the build preflights the exact request.',
                             'Global denies do not make the remaining inventory default-deny; review before building.'])


def verify_sliced_retained(owned, completed):
    """refresh.verify_retained for many slice candidates: each completed slice
    directory may hold its own pack-owned `candidate`; nothing else is untracked."""
    if not owned.created:
        return
    try:
        reader.require(bool(owned.directories), 'created transaction has no pinned identity')
        for parent, name, _, expected in owned.directories:
            reader.require(packer.inode(os.stat(name, dir_fd=parent, follow_symlinks=False)) == expected,
                           'transaction directory identity changed')
        for parent, name, expected in owned.files:
            reader.require(packer.inode(os.stat(name, dir_fd=parent, follow_symlinks=False)) == expected,
                           'transaction file identity changed')
        for _, _, fd, _ in owned.directories:
            expected = {n for p, n, _ in owned.files if p == fd}
            expected.update(n for p, n, _, _ in owned.directories if p == fd)
            actual = set(os.listdir(fd))
            if fd in completed:
                actual.discard('candidate')
            reader.require(actual == expected, 'unexpected transaction entries')
    except ERRORS as exc:
        raise Unknown('retained transaction ownership requires reconciliation: ' + str(exc)) from exc


def logical_bytes(path):
    """Logical st_size of every non-directory entry below path, without following links."""
    total, pending = 0, [str(path)]
    while pending:
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    pending.append(entry.path)
                else:
                    total += entry.stat(follow_symlinks=False).st_size
    return total


def sliced_result(manifest, manifest_sha):
    result = result_template(manifest, manifest_sha)
    for key in ('package', 'build_state'):
        del result[key]
    result.update(schema=RESULT_SCHEMA_V2, mode=manifest['mode'], tree=None, hold=None,
                  slice_set=None, slice_run=None, inventory=None, slices=[], resources=None)
    result['limitations'] = result['limitations'] + [
        'Reused slices keep their original built head; equivalence is proved by equal input and resolution digests.',
        'Child max RSS is getrusage(RUSAGE_CHILDREN) over all waited children of this process.']
    return result


class SlicedRun:
    """One locked sliced transaction; slices build in name order, one adapter run each."""

    def __init__(self, manifest, manifest_sha, stack, result):
        self.m, self.sha, self.stack, self.result = manifest, manifest_sha, stack, result
        self.owned = self.cache = None
        self.completed = set()

    def write(self, fd, name, data, relative):
        refresh.file_write(self.owned, fd, name, data)
        refresh.raw_selected(Path(self.m['destination']) / relative, reader.digest(data), len(data))
        return dict(path=str(Path(self.m['destination']) / relative), sha256=reader.digest(data))

    def create(self):
        destination = Path(self.m['destination'])
        parent = self.stack.enter_context(packer.directory_fd(destination.parent))
        self.owned = packer.OwnedOutput(parent, destination.name)
        self.stack.callback(self.owned.close)
        self.stack.callback(verify_sliced_retained, self.owned, self.completed)
        try:
            root = self.owned.create()
        except FileExistsError as exc:
            raise Deferred('output collision; prior destination preserved') from exc
        except OSError as exc:
            raise Unknown('destination creation effect requires reconciliation') from exc
        self.result['retained'] = True
        return root

    def request_raw(self, name, number, files, fragments, index_name, index_sha):
        """The exact adapter request bytes; preflight and staging share this builder."""
        m = self.m
        stage = Path(m['destination']) / SLICES_DIRECTORY / name / 'attempts' / str(number) / 'inputs'
        request = dict(schema=REQUEST_SCHEMA, manifest_sha256=self.sha,
                       source=dict(repository=m['repository'], head=m['commit']),
                       input_basis='git_blob', stage=str(stage),
                       files=[dict(path=p, sha256=files[p], action='reuse' if p in fragments else 'extract',
                                   fragment=fragments.get(p)) for p in sorted(files)],
                       policy=self.policy_document, extractor=m['extractor'],
                       limits=dict(m['limits'], records=min(
                           m['limits']['records'], m['admission_policy']['slicing']['max_slice_records'])),
                       slice=dict(name=name), path_index=dict(stage_path=index_name, sha256=index_sha))
        return packer.encoded(request)

    def preflight(self, name, admitted, index_raw, trusted):
        """Exact request, index, file and content bytes of attempt 1 before any adapter run.
        Blobs are read only to hash them; nothing is extracted, staged or written."""
        m = self.m
        unread = [f for f in admitted if f['blob_oid'] not in trusted]
        contents = read_blobs(m['mirror_git_dir'], unread)
        digests = {f['path']: reader.digest(contents[f['path']]) if f['path'] in contents
                   else trusted[f['blob_oid']] for f in admitted}
        del contents
        lookups = dict(hits=0, misses=0, corrupt=0, errors=0, oversize=0, invalid=0)
        keys, reuse = {}, {}
        if self.cache is not None:
            for f in admitted:
                material = key_material_v2(m, self.runtime_sha, self.per_file_sha, f['path'],
                                           digests[f['path']])
                keys[f['path']] = (fragment_cache.key(material), material)
                try:
                    status, item, _ = self.cache.get(material)
                except (OSError, ValueError):
                    lookups['errors'] += 1
                    continue
                lookups[dict(hit='hits', miss='misses', corrupt='corrupt')[status]] += 1
                if status == 'hit':
                    blob = packer.encoded(item)
                    if not (isinstance(item, dict) and item.get('schema') == FRAGMENT_SCHEMA_V2
                            and item.get('family') == FAMILY_V2 and item.get('path') == f['path']
                            and item.get('content_sha256') == digests[f['path']]
                            and item.get('outcome') in ('structural', 'unknown')):
                        # Revalidated here as well as by the cache; a mismatch is extracted.
                        lookups['invalid'] += 1
                    elif len(blob) > FRAGMENT_BYTES:
                        # The adapter would refuse it; extract instead and say so.
                        lookups['oversize'] += 1
                    else:
                        reuse[f['path']] = (reader.digest(blob), len(blob))
        _, index_name, names = stage_names(digests, reuse)
        fragments = {p: dict(stage_path=names[p], sha256=reuse[p][0]) for p in reuse}
        raw = self.request_raw(name, 1, digests, fragments, index_name, reader.digest(index_raw))
        content = sum(f['bytes'] for f in admitted)
        extracted = sum(f['bytes'] for f in admitted if f['path'] not in reuse)
        # Attempt 1 stages reused fragments; an uncached fallback stages every content byte.
        input_bytes = len(index_raw) + max(extracted + sum(v[1] for v in reuse.values()), content)
        slicing, limits = m['admission_policy']['slicing'], m['limits']
        bounds = [bound for bound, over in (
            ('files', len(admitted) > min(slicing['max_slice_files'], MAX_SLICE_FILES)),
            ('content_bytes', content > slicing['max_slice_bytes']),
            ('index_bytes', len(index_raw) > MAX_INDEX_BYTES),
            ('request_bytes', len(raw) > MAX_REQUEST_V2),
            ('input_bytes', input_bytes > limits['input_bytes'])) if over]
        return dict(name=name, files=len(admitted), content_bytes=content, index_bytes=len(index_raw),
                    request_bytes=len(raw), input_bytes=input_bytes, bounds=bounds,
                    request_sha256=reader.digest(raw), digests=digests, reuse=reuse, keys=keys,
                    lookups=lookups)

    def attempt(self, attempts_fd, number, name, files, contents, reused, index_raw, expected=None):
        m = self.m
        destination = Path(m['destination'])
        attempts = destination / SLICES_DIRECTORY / name / 'attempts' / str(number)
        base = self.owned.mkdir(attempts_fd, str(number))
        stage = self.owned.mkdir(base, 'inputs')
        fragments_dir, index_name, names = stage_names(files, reused)
        staged = stage_files(self.owned, stage, {p: contents[p] for p in files if p not in reused},
                             reused, fragments_dir)
        reader.require({p: s['stage_path'] for p, s in staged.items()} == names, 'staging name mismatch')
        # Copy staging: every staged input, including the index, is a new nlink == 1 file.
        refresh.file_write(self.owned, stage, index_name, index_raw)
        index_sha = reader.digest(index_raw)
        request_raw = self.request_raw(name, number, files, staged, index_name, index_sha)
        request_sha = reader.digest(request_raw)
        reader.require(expected is None or request_sha == expected, 'request differs from preflight')
        refresh.file_write(self.owned, base, 'request.json', request_raw)
        with reader.open_nofollow(attempts / 'request.json') as request_file:
            try:
                raw, evidence = refresh.run_adapter(self.executable, self.script, request_file,
                                                    destination, m['limits'])
            except Deferred:
                raise
            except ValueError as exc:
                if str(exc) in ('extractor nonzero exit', 'extractor output byte limit'):
                    raise AdapterRejected(str(exc)) from exc
                raise
        refresh.file_write(self.owned, base, 'adapter-response.json', raw)
        verify_sliced_retained(self.owned, self.completed)
        refresh.raw_selected(attempts / 'request.json', request_sha, len(request_raw))
        refresh.raw_selected(attempts / 'inputs' / index_name, index_sha, len(index_raw))
        for p in sorted(files):
            if p in reused:
                refresh.raw_selected(attempts / 'inputs' / staged[p]['stage_path'], staged[p]['sha256'],
                                     len(reused[p]))
            else:
                refresh.raw_selected(attempts / 'inputs' / p, files[p], len(contents[p]))
        return request_sha, raw, evidence

    def build(self, slices_fd, name, admitted, skipped, index, index_raw, prior, input_sha, pre):
        """Run the adapter for one preflighted slice, pack it, and write its v2 state."""
        m, mirror, started = self.m, self.m['mirror_git_dir'], time.monotonic()
        self.failing = pre
        relative = Path(SLICES_DIRECTORY) / name
        slice_fd = self.owned.mkdir(slices_fd, name)
        attempts_fd = self.owned.mkdir(slice_fd, 'attempts')
        digests, keys = pre['digests'], pre['keys']
        reused, items = {}, {}
        for p, (sha, size) in pre['reuse'].items():
            status, item, _ = self.cache.get(keys[p][1])
            blob = packer.encoded(item) if status == 'hit' else b''
            reader.require(reader.digest(blob) == sha and len(blob) == size,
                           'fragment cache changed after preflight')
            reused[p], items[p] = blob, item
        contents = read_blobs(mirror, [f for f in admitted if f['path'] not in reused])
        for p, raw in contents.items():
            reader.require(reader.digest(raw) == digests[p], 'previous build state blob digest mismatch')
        files = {f['path']: digests[f['path']] for f in admitted}
        cache_reason = self.cache_reason
        attempts = 1
        try:
            request_sha, raw, evidence = self.attempt(attempts_fd, 1, name, files, contents, reused,
                                                      index_raw, pre['request_sha256'])
        except AdapterRejected as exc:
            if not reused or str(exc) != 'extractor nonzero exit':
                raise
            # Rejected reuse falls back once to an uncached extraction of this slice.
            cache_reason = 'reuse_rejected'
            contents.update(read_blobs(mirror, [f for f in admitted if f['path'] in reused]))
            for p in reused:
                reader.require(reader.digest(contents[p]) == digests[p],
                               'previous build state blob digest mismatch')
            reused, items, attempts = {}, {}, 2
            self.attempts += 1
            self.adapter_runs += 1
            request_sha, raw, evidence = self.attempt(attempts_fd, 2, name, files, contents, reused,
                                                      index_raw)
        finally:
            self.attempts += 1
            self.adapter_runs += 1
        reader.require(reader.signature(self.executable) == self.executable_sig and
                       reader.signature(self.script) == self.script_sig, 'adapter changed during execution')
        extracted = [p for p in files if p not in reused]
        response = validate_response(raw, request_sha, files, extracted, FRAGMENT_SCHEMA_V2, FAMILY_V2)
        sliced_source = dict(repository=m['repository'], head=m['commit'], slice=name)
        for part in ('graph', 'validation'):
            # The adapter alone binds the slice; its output is never rewritten here.
            reader.require(isinstance(response[part], dict)
                           and response[part].get('source') == sliced_source,
                           'adapter output lacks slice source binding')
        crossing = check_cross_slice(response['validation'], index, name, set(files))
        items.update(response['fragments'])
        candidates = fragment_candidates(items[p] for p in sorted(items))
        resolution = resolution_digest(candidates, index)
        puts = {}
        if self.cache is not None and cache_reason != 'reuse_rejected':
            for p in sorted(extracted):
                material, item = keys[p][1], response['fragments'][p]
                try:
                    # put() reports an oversize entry only as 'error'; measure it first.
                    if cache_entry_bytes(material, item) > fragment_cache.MAX_ENTRY_V2:
                        outcome = 'uncacheable'
                    else:
                        outcome = self.cache.put(material, item)
                except (OSError, ValueError, TypeError, RecursionError):
                    outcome = 'error'
                puts[outcome] = puts.get(outcome, 0) + 1
        lookups = pre['lookups']
        counts = dict.fromkeys(SLICE_COUNTS, 0)
        old = {f['path']: f for f in prior['files']} if prior else {}
        for f in admitted:
            if f['path'] not in old:
                counts['added'] += 1
            elif old[f['path']]['blob_oid'] != f['blob_oid']:
                counts['modified'] += 1
        counts.update(admitted=len(admitted), unsupported=len(skipped), reused=len(reused),
                      extracted=len(extracted), deleted=len(set(old) - set(files)),
                      unknown=sum(1 for p in files if response['coverage'][p] == 'unknown'),
                      cache_hits=lookups['hits'], cache_misses=lookups['misses'],
                      cache_corrupt=lookups['corrupt'], cache_full=puts.get('full', 0),
                      cache_uncacheable=puts.get('uncacheable', 0))
        counts['unchanged'] = counts['admitted'] - counts['added'] - counts['modified']
        if self.cache is not None and cache_reason is None:
            degraded = (lookups['corrupt'] or lookups['errors'] or lookups['oversize']
                        or lookups['invalid'] or puts.get('error') or puts.get('exists_conflict')
                        or puts.get('uncacheable'))
            status = self.cache.stats()['status']
            cache_reason = status if status != 'ok' else 'degraded' if degraded else 'ok'
        documents = pack_documents(m, sliced_source, response, files, self.relation, request_sha,
                                   dict(self.identities, tree=self.tree), skipped)
        inputs = {}
        evidence_fd = self.owned.mkdir(slice_fd, 'evidence')
        for part, document in documents.items():
            content = packer.encoded(document)
            refresh.file_write(self.owned, evidence_fd, part + '.json', content)
            inputs[part] = (Path(m['destination']) / relative / 'evidence' / (part + '.json'),
                            reader.digest(content))
        verify_sliced_retained(self.owned, self.completed)
        refresh.verify_lock(m['lock'], self.lock_identity)
        package = packer.pack(inputs, Path(m['destination']) / relative / 'candidate')
        self.completed.add(slice_fd)
        state = dict(schema=SLICE_STATE_SCHEMA, repository=m['repository'], family=dict(FAMILY_V2),
                     commit=m['commit'], input_basis='git_blob', manifest_sha256=self.sha,
                     request_sha256=request_sha, tree=self.tree, **self.identities,
                     files=[dict(path=f['path'], blob_oid=f['blob_oid'], sha256=files[f['path']],
                                 bytes=f['bytes'], coverage=response['coverage'][f['path']],
                                 key_sha256=keys[f['path']][0] if f['path'] in keys else None)
                            for f in admitted],
                     unsupported=skipped, package_sha256=package['package_sha256'],
                     catalog_sha256=package['catalog_sha256'], archive_sha256=package['archive_sha256'],
                     graph_sha256=package['graph_sha256'], counts=counts, cache_status=cache_reason,
                     target_relation=self.relation, slice=name, input_digest=input_sha,
                     resolution_digest=resolution, path_index_sha256=reader.digest(index_raw),
                     reference_candidates=candidates)
        state_raw = packer.encoded(state)
        reader.require(len(state_raw) <= MAX_STATE, 'build state byte limit')
        selection = self.write(slice_fd, STATE_NAME, state_raw, relative / STATE_NAME)
        self.cache_puts.append(puts)
        self.lookups.append(lookups)
        self.failing = None
        staged_input = len(index_raw) + sum(f['bytes'] for f in admitted if f['path'] not in reused) + sum(
            len(b) for b in reused.values())
        return state, selection, dict(
            preflight_summary(pre), status='built', attempts=attempts, cache_status=cache_reason,
            cross_slice_references=crossing, staged_input_bytes=staged_input, response_bytes=len(raw),
            response_input_ratio=round(len(raw) / staged_input, 4), process=evidence,
            wall_seconds=round(time.monotonic() - started, 3),
            max_rss_kib_children=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)


def preflight_summary(pre):
    """The bounded, receipt-safe part of a preflight record."""
    return {k: pre[k] for k in ('name', 'files', 'content_bytes', 'index_bytes', 'request_bytes',
                                'input_bytes', 'bounds')}


def execute_sliced(manifest, manifest_sha):
    result = sliced_result(manifest, manifest_sha)
    started = time.monotonic()
    run = None
    try:
        with ExitStack() as stack:
            run = SlicedRun(manifest, manifest_sha, stack, result)
            lock = stack.enter_context(reader.open_nofollow(manifest['lock']))
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise Deferred('lock contention') from exc
            run.lock_identity = packer.inode(os.fstat(lock.fileno()))
            stack.callback(refresh.verify_lock, manifest['lock'], run.lock_identity)
            mirror, commit, m = manifest['mirror_git_dir'], manifest['commit'], manifest
            policy, limits, ex = m['admission_policy'], m['limits'], m['extractor']
            if (ex['protocol'], ex['name'], ex['version']) != (PROTOCOL, FAMILY_V2['name'],
                                                               FAMILY_V2['version']):
                raise Deferred('unsupported extractor adapter or family')
            reader.require(m['runtime_probe']['path'] == os.path.realpath(runtime_identity.__file__),
                           "runtime probe is not this driver's runtime_identity module")
            try:
                tree = run.tree = result['tree'] = resolve_commit(mirror, commit)
            except OSError as exc:
                raise Deferred('mirror unavailable') from exc
            tally = dict(denied=0, not_included=0)
            admitted, unsupported = tree_entries(mirror, commit, policy,
                                                 min(policy['max_file_bytes'], limits['file_bytes']),
                                                 tally)
            reader.require(admitted, 'admitted file count outside policy')
            slices, skipped, holds = plan_slices(admitted, unsupported, policy)
            index, index_raw = path_index(slices)
            if len(index_raw) > MAX_INDEX_BYTES:
                holds.append(dict(reason='path_index_over_limit', slice=None, bounds=['index_bytes'],
                                  files=len(index), bytes=len(index_raw)))
            run.relation = result['target_relation'] = target_relation(mirror, commit, m['target'])
            previous = load_previous_run(m)
            prior_states = previous['states'] if previous else {}
            disjoint_destination(Path(m['destination']),
                                 [Path(s[1]['path']).parent for s in prior_states.values()])
            policy_sha = canonical_sha256(policy)
            source = dict(repository=m['repository'], head=commit)
            run.policy_document = dict(schema='graphify-pack-policy/v1', source=source,
                                       name='incremental-admission', rules=policy, limitations=[])
            rows = {name: dict(name=name, status='planned') for name in slices}
            for h in holds:
                if h['slice'] is not None:
                    rows[h['slice']]['status'] = 'slice_over_limit'
            result['slices'] = [rows[n] for n in sorted(rows)]
            if m['mode'] == 'inventory_only':
                root = run.create()
                document = inventory_document(m, tree, policy_sha, admitted, unsupported, tally,
                                              slices, holds, index, index_raw, previous, run)
                raw = packer.encoded(document)
                reader.require(len(raw) <= MAX_STATE, 'inventory byte limit')
                result.update(status='inventory', hold=dict(holds=holds) if holds else None,
                              reason='admission inventory written; nothing extracted or packed',
                              inventory=run.write(root, INVENTORY_NAME, raw, Path(INVENTORY_NAME)))
                verify_sliced_retained(run.owned, run.completed)
                return result
            if holds:
                # Hold before any adapter run or output: no slice is split or partially built.
                result.update(status='held', reason=holds[0]['reason'], hold=dict(holds=holds))
                return result
            try:
                run.executable, run.executable_sig = refresh.pin(stack, ex['executable'], 64 * 1024**2)
                run.script, run.script_sig = refresh.pin(stack, ex['script'], limits['file_bytes'])
            except ERRORS as exc:
                raise Deferred('extractor evidence missing, changed, or invalid') from exc
            try:
                identity = runtime_identity.identify(
                    ex['executable']['path'], ex['executable']['sha256'], ex['script']['path'],
                    ex['script']['sha256'], timeout=min(60, limits['seconds']),
                    probe_sha256=m['runtime_probe']['sha256'])
            except runtime_identity.Unknown as exc:
                raise Unknown('runtime probe cancellation unconfirmed') from exc
            runtime_sha = run.runtime_sha = (identity['identity_sha256']
                                             if identity['status'] == 'identified' else None)
            result['runtime_identity'] = dict(status=identity['status'], reason=identity['reason'],
                                              identity_sha256=runtime_sha)
            run.per_file_sha = canonical_sha256(dict(schema=PER_FILE_SCHEMA, input_basis='git_blob',
                                                     checkout_conversion='none',
                                                     output_bytes=limits['output_bytes']))
            run.identities = slice_identities(policy_sha, ex, run.per_file_sha, runtime_sha)
            # Decide reuse per slice before any output exists; equal digests are the
            # only basis for reuse at another head (the equivalence proof).
            plan = {}
            for name in sorted(slices):
                digest_now = input_digest(m['repository'], name, slices[name], skipped.get(name, []),
                                          run.identities)
                old = prior_states.get(name)
                reuse = (old is not None and runtime_sha is not None
                         and old[0]['input_digest'] == digest_now
                         and resolution_digest(old[0]['reference_candidates'], index)
                         == old[0]['resolution_digest'])
                plan[name] = (digest_now, old if reuse else None)
            if (previous is not None and all(o is not None for _, o in plan.values())
                    and set(plan) == set(prior_states)
                    and previous['slice_set']['accepted_head'] == commit
                    and previous['slice_set']['tree'] == tree):
                for name, (_, old) in plan.items():
                    verified_package(Path(old[1]['path']).parent / 'candidate', old[0])
                    rows[name]['status'] = 'reused'
                result.update(status='unchanged', reason='same accepted head; every slice reused',
                              slice_set=dict(path=str(Path(m['previous_run']['path']).parent
                                                      / SLICE_SET_NAME),
                                             sha256=previous['slice_set_sha256']),
                              slice_run=dict(m['previous_run']), cache_status='not_used',
                              counts=run_counts(slices, skipped, prior_states, [], 0))
                return result
            trusted = {}
            for state, _ in prior_states.values():
                for f in state['files']:
                    trusted.setdefault(f['blob_oid'], f['sha256'])
            run.cache_reason = None
            if runtime_sha is None:
                run.cache_reason = 'cache_disabled:runtime_unidentified'
            elif not cache_accepts_v2(m, run.per_file_sha):
                run.cache_reason = 'cache_disabled:fragment_schema_unsupported'
            else:
                run.cache, run.cache_reason = open_cache(m['state_root'], m['cache_quota_bytes'])
                if run.cache is not None:
                    stack.callback(run.cache.close)
            cache_before = run.cache.stats()['bytes_used'] if run.cache is not None else None
            # Preflight every slice to build; any bound over its value holds the whole run.
            checked = {name: run.preflight(name, slices[name], index_raw, trusted)
                       for name in sorted(slices) if plan[name][1] is None}
            holds = [dict(preflight_summary(pre), reason='slice_over_limit', slice=name)
                     for name, pre in checked.items() if pre['bounds']]
            if holds:
                for h in holds:
                    rows[h['slice']]['status'] = 'slice_over_limit'
                    del h['name']
                result.update(status='held', reason='slice_over_limit', hold=dict(holds=holds))
                return result
            run.attempts = run.adapter_runs = 0
            run.cache_puts, run.lookups, run.failing = [], [], None
            root = run.create()
            index_selection = run.write(root, PATH_INDEX_NAME, index_raw, Path(PATH_INDEX_NAME))
            slices_fd = run.owned.mkdir(root, SLICES_DIRECTORY)
            built, report, entries = [], [], {}
            for name in sorted(slices):
                digest_now, old = plan[name]
                if old is not None:
                    state, selection = old
                    verified_package(Path(selection['path']).parent / 'candidate', state)
                    rows[name].update(status='reused', built_head=state['commit'])
                    report.append(dict(rows[name], files=len(slices[name])))
                else:
                    prior = prior_states.get(name)
                    state, selection, row = run.build(slices_fd, name, slices[name],
                                                      skipped.get(name, []), index, index_raw,
                                                      prior[0] if prior else None, digest_now,
                                                      checked[name])
                    built.append(state)
                    rows[name]['status'] = 'built'
                    report.append(row)
                entries[name] = (state, selection, 'reused' if old is not None else 'built')
            slice_set = dict(schema=SLICE_SET_SCHEMA, repository=m['repository'], accepted_head=commit,
                             tree=tree, slices=[dict(name=n, package_sha256=s['package_sha256'],
                                                     built_head=s['commit'], input_digest=s['input_digest'],
                                                     resolution_digest=s['resolution_digest'],
                                                     build_state_sha256=sel['sha256'])
                                                for n, (s, sel, _) in sorted(entries.items())])
            set_raw = packer.encoded(slice_set)
            result['slice_set'] = run.write(root, SLICE_SET_NAME, set_raw, Path(SLICE_SET_NAME))
            slice_run = dict(schema=SLICE_RUN_SCHEMA, repository=m['repository'], accepted_head=commit,
                             tree=tree, slice_set_sha256=reader.digest(set_raw),
                             path_index_sha256=index_selection['sha256'],
                             slices=[dict(name=n, status=status, built_head=s['commit'],
                                          build_state=dict(sel),
                                          package=dict(path=str(Path(sel['path']).parent / 'candidate'
                                                                / 'package.json'),
                                                       sha256=s['package_sha256']))
                                     for n, (s, sel, status) in sorted(entries.items())])
            result['slice_run'] = run.write(root, SLICE_RUN_NAME, packer.encoded(slice_run),
                                            Path(SLICE_RUN_NAME))
            counts = run_counts(slices, skipped, prior_states, built, run.adapter_runs)
            if run.cache is not None:
                stats, puts = run.cache.stats(), {}
                for item in run.cache_puts:
                    for k, v in item.items():
                        puts[k] = puts.get(k, 0) + v
                lookups = {k: sum(x[k] for x in run.lookups) for k in
                           ('hits', 'misses', 'corrupt', 'errors', 'oversize', 'invalid')}
                counts.update(cache_hits=lookups['hits'], cache_misses=lookups['misses'],
                              cache_corrupt=lookups['corrupt'], cache_full=puts.get('full', 0))
                result['cache'] = dict(status=stats['status'], quota_bytes=stats['quota_bytes'],
                                       bytes_used=stats['bytes_used'], lookups=lookups, puts=puts,
                                       bytes_written=stats['bytes_used'] - cache_before)
            report_raw = packer.encoded(dict(schema=SLICE_REPORT_SCHEMA, repository=m['repository'],
                                             accepted_head=commit, slices=report))
            result['slice_report'] = run.write(root, SLICE_REPORT_NAME, report_raw,
                                               Path(SLICE_REPORT_NAME))
            verify_sliced_retained(run.owned, run.completed)
            statuses = sorted({s['cache_status'] for s in built})
            result.update(status='completed',
                          reason='slice set written; changed slices built, unchanged slices reused',
                          counts=counts, attempts=run.attempts,
                          cache_status=('not_used' if not built
                                        else statuses[0] if len(statuses) == 1 else 'mixed:' + ','.join(statuses)))
    except AdapterRejected as exc:
        # The adapter gives no cause code: never relabel this as an over-limit hold.
        failing = getattr(run, 'failing', None)
        result.update(status='failed', reason='adapter_rejected: ' + str(exc),
                      failed_slice=preflight_summary(failing) if failing else None)
    except Deferred as exc:
        result.update(status='deferred', reason=str(exc)[:500])
    except (Unknown, packer.UnknownOutputError, runtime_identity.Unknown) as exc:
        result.update(status='unknown', reason=str(exc)[:500])
    except KeyboardInterrupt:
        result.update(status='deferred', reason='cancelled; no promotion', cancelled=True)
    except ERRORS as exc:
        result.update(status='failed', reason=(type(exc).__name__ + ': ' + str(exc))[:500])
    finally:
        owned = run.owned if run is not None else None
        if owned is not None and owned.created:
            result['retained'] = True
        resources = dict(wall_seconds=round(time.monotonic() - started, 3),
                         max_rss_kib_self=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                         max_rss_kib_children=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
                         adapter_runs=getattr(run, 'adapter_runs', 0), build_bytes=None)
        if owned is not None and owned.created:
            try:
                resources['build_bytes'] = logical_bytes(manifest['destination'])
            except OSError:
                pass
        result['resources'] = resources
    return result


def run_counts(slices, skipped, prior_states, built, adapter_runs):
    """Repository-level counts; a rename is reported as one added and one deleted path."""
    counts = dict.fromkeys(RUN_COUNTS, 0)
    old = {f['path']: f for state, _ in prior_states.values() for f in state['files']}
    admitted = [f for files in slices.values() for f in files]
    for f in admitted:
        if f['path'] not in old:
            counts['added'] += 1
        elif old[f['path']]['blob_oid'] != f['blob_oid']:
            counts['modified'] += 1
    counts.update(admitted=len(admitted), deleted=len(set(old) - {f['path'] for f in admitted}),
                  unsupported=sum(len(v) for v in skipped.values()),
                  reused=sum(s['counts']['reused'] for s in built),
                  cache_uncacheable=sum(s['counts']['cache_uncacheable'] for s in built),
                  extracted=sum(s['counts']['extracted'] for s in built),
                  slices=len(slices), slices_built=len(built),
                  slices_reused=len(slices) - len(built),
                  slices_removed=len(set(prior_states) - set(slices)), adapter_runs=adapter_runs)
    counts['unchanged'] = counts['admitted'] - counts['added'] - counts['modified']
    built_names = {s['slice'] for s in built}
    counts['unknown'] = (sum(s['counts']['unknown'] for s in built)
                         + sum(sum(1 for f in state['files'] if f['coverage'] == 'unknown')
                               for name, (state, _) in prior_states.items()
                               if name in slices and name not in built_names))
    return counts


def incremental(manifest_path, manifest_sha):
    refresh.absolute(str(manifest_path))
    _, manifest = packer.selected_input(manifest_path, manifest_sha, refresh.MAX_MANIFEST)
    if manifest.get('schema') == SCHEMA_V2:
        validate_manifest_v2(manifest)
        return execute_sliced(manifest, manifest_sha)
    validate_manifest(manifest)
    return execute(manifest, manifest_sha)


def bounded_receipt(result):
    raw = packer.encoded(result)
    if len(raw) > MAX_RECEIPT:
        # Preserve identity and the non-success effect; never truncate into success.
        raw = packer.encoded(dict(schema=result.get('schema', RESULT_SCHEMA), status='unknown',
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
        # inventory is a v2 inventory_only success; held (v2 over-limit) has no effect, like deferred.
        return (0 if status in ('completed', 'unchanged', 'inventory')
                else 2 if status in ('deferred', 'held') else 1)
    finally:
        for sig, handler in old.items():
            signal.signal(sig, handler)


if __name__ == '__main__':
    raise SystemExit(main())
