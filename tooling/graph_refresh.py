#!/usr/bin/env python3
"""Run selected, sequential, create-only refresh candidates; never promote them.

The pinned python-json/v1 adapter is trusted code, not a sandboxed workload.
It must read only the supplied staging tree, emit one JSON response on stdout,
write no files, and spawn no descendants. Process-group cancellation cannot
contain an adapter that escapes its group. Invocation requires separate caller
approval for source reads and extraction (including any model/network effects).
"""
import argparse
from contextlib import ExitStack
import fcntl
import fnmatch
import hashlib
import os
from pathlib import Path
import resource
import selectors
import signal
import subprocess
import sys
import tarfile
import time

sys.dont_write_bytecode = True
import graph_freshness as freshness
import graph_pack as packer
import graph_read as reader

SCHEMA = 'graphify-refresh-manifest/v1'
MAX_MANIFEST = 128 * 1024
MAX_RECEIPT = 64 * 1024
MAX_TASKS = 8
ERRORS = (ValueError, OSError, KeyError, TypeError, RecursionError, OverflowError,
          tarfile.TarError, subprocess.SubprocessError)
LIMITS = dict(file_bytes=4 * 1024**2, input_bytes=16 * 1024**2,
              output_bytes=8 * 1024**2, seconds=300)


class Deferred(ValueError):
    pass


class Unknown(ValueError):
    pass


def absolute(value):
    packer.bounded_text(value, 'absolute path')
    p = Path(value)
    reader.require(p.is_absolute() and str(p) == value and '..' not in p.parts,
                   'path must be absolute and normalized')
    return p


def selection(value):
    packer.closed(value, ('path', 'sha256'), 'selection')
    absolute(value['path'])
    reader.require(reader.valid_hash(value['sha256']), 'invalid selection checksum')


def validate_manifest(m):
    packer.closed(m, ('schema', 'limits', 'tasks'), 'refresh manifest')
    reader.require(m['schema'] == SCHEMA, 'unsupported manifest')
    packer.closed(m['limits'], LIMITS, 'limits')
    for name, maximum in LIMITS.items():
        n = m['limits'][name]
        reader.require(type(n) is int and 1 <= n <= maximum, 'invalid limit ' + name)
    tasks = m['tasks']
    reader.require(isinstance(tasks, list) and 1 <= len(tasks) <= MAX_TASKS, 'invalid task count')
    repos, destinations, roots = set(), [], []
    for t in tasks:
        packer.closed(t, ('source', 'root', 'target_oid', 'existing', 'files', 'deny',
                          'extractor', 'destination', 'lock'), 'task')
        packer.source_identity(t['source'])
        repo = t['source']['repository']
        reader.require(repo not in repos, 'duplicate repository')
        repos.add(repo)
        roots.append(absolute(t['root']))
        destinations.append(absolute(t['destination']))
        absolute(t['lock'])
        reader.require(t['target_oid'] is None or freshness._oid(t['target_oid']), 'invalid target')
        if t['existing'] is not None:
            selection(t['existing'])
        reader.require(isinstance(t['deny'], list) and len(t['deny']) <= 128, 'invalid deny list')
        for pattern in t['deny']:
            packer.bounded_text(pattern, 'deny pattern')
        files = t['files']
        reader.require(isinstance(files, list) and 1 <= len(files) <= 256, 'invalid file count')
        paths = set()
        for f in files:
            packer.closed(f, ('path', 'sha256'), 'admitted file')
            p = packer.file_path(f['path'])
            reader.require('.git' not in Path(p).parts and p not in paths, 'forbidden or duplicate path')
            reader.require(reader.valid_hash(f['sha256']), 'invalid file checksum')
            reader.require(not any(fnmatch.fnmatchcase(p, pat) for pat in t['deny']), 'denied admitted path')
            reader.require(not any(p.startswith(q + '/') or q.startswith(p + '/') for q in paths),
                           'overlapping admitted paths')
            paths.add(p)
        ex = t['extractor']
        packer.closed(ex, ('protocol', 'name', 'version', 'executable', 'script'), 'extractor')
        for key in ('name', 'version'):
            packer.bounded_text(ex[key], 'extractor ' + key)
        reader.require(isinstance(ex['protocol'], str), 'invalid extractor protocol')
        selection(ex['executable'])
        selection(ex['script'])
    for i, destination in enumerate(destinations):
        for other in destinations[:i]:
            reader.require(destination != other and destination not in other.parents
                           and other not in destination.parents, 'overlapping destinations')
        for root in roots:
            reader.require(destination != root and root not in destination.parents
                           and destination not in root.parents, 'destination overlaps source')
        for t in tasks:
            protected = [Path(t['lock']), Path(t['extractor']['executable']['path']),
                         Path(t['extractor']['script']['path'])]
            if t['existing']:
                protected.append(Path(t['existing']['path']))
            reader.require(not any(p == destination or destination in p.parents for p in protected),
                           'destination overlaps selected evidence')
    return m


def raw_selected(path, expected, limit):
    with reader.open_nofollow(path) as handle:
        before = reader.signature(handle)
        reader.require(before[2] <= limit, 'selected file byte limit')
        data = handle.read(limit + 1)
        reader.require(reader.signature(handle) == before and len(data) <= limit,
                       'selected file changed or byte limit exceeded')
    reader.require(reader.digest(data) == expected, 'selected file checksum mismatch')
    return data


def source_sample(task):
    # Do not silently turn an alias/symlink source into a different root binding.
    with packer.directory_fd(task['root']):
        pass
    s = freshness._observe_source(task['root'])
    if not s['stable'] or s['cleanliness'] != 'clean' or s['head'] != task['source']['head']:
        raise Deferred('source missing, dirty, changing, or selected HEAD mismatch')
    if task['target_oid'] is not None and s['head'] != task['target_oid']:
        raise Deferred('caller target does not match source HEAD')
    return s


def capture(task, limits):
    files, total = {}, 0
    for f in task['files']:
        raw = raw_selected(Path(task['root']) / f['path'], f['sha256'], limits['file_bytes'])
        total += len(raw)
        reader.require(total <= limits['input_bytes'], 'admitted total byte limit')
        files[f['path']] = raw
    return files


def pin(stack, selected, limit):
    h = stack.enter_context(reader.open_nofollow(selected['path']))
    sig = reader.signature(h)
    reader.require(sig[2] <= limit, 'adapter byte limit')
    sha = hashlib.sha256()
    count = 0
    while block := h.read(65536):
        count += len(block)
        reader.require(count <= limit, 'adapter byte limit')
        sha.update(block)
    reader.require(sha.hexdigest() == selected['sha256'] and reader.signature(h) == sig,
                   'adapter checksum or stability mismatch')
    h.seek(0)
    return h, sig


def file_write(owned, parent, name, data):
    with owned.file(parent, name) as h:
        h.write(data)


def verify_retained(owned):
    """Reconcile owned staging without deleting unknown or adapter-created entries."""
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
            if fd == owned.directories[0][2] and getattr(owned, 'candidate_started', False):
                # graph_pack owns this separate closure and its unknown-effect handling.
                actual = set(os.listdir(fd)) - {'candidate'}
            else:
                actual = set(os.listdir(fd))
            reader.require(actual == expected, 'unexpected transaction entries')
    except ERRORS as exc:
        raise Unknown('retained transaction ownership requires reconciliation: ' + str(exc)) from exc


def adapter_limits():
    # Bounds regular-file output, not memory, networking, or the process count.
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    signal.pthread_sigmask(signal.SIG_SETMASK, set())


def run_adapter(executable, script, request, cwd, limits):
    """One direct child; bounded pipes/deadline, no shell or inherited environment."""
    command = [f'/proc/self/fd/{executable.fileno()}', '-I', '-B',
               f'/proc/self/fd/{script.fileno()}']
    process = None
    try:
        mask = signal.pthread_sigmask(signal.SIG_BLOCK, packer.CANCEL_SIGNALS)
        try:
            process = subprocess.Popen(command, stdin=request, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, cwd=cwd, env={'LC_ALL': 'C.UTF-8'},
                                       pass_fds=(executable.fileno(), script.fileno()),
                                       start_new_session=True, preexec_fn=adapter_limits)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        data, errors = bytearray(), bytearray()
        deadline = time.monotonic() + limits['seconds']
        with selectors.DefaultSelector() as poll:
            poll.register(process.stdout, selectors.EVENT_READ, data)
            poll.register(process.stderr, selectors.EVENT_READ, errors)
            while poll.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise Deferred('extractor timeout')
                for key, _ in poll.select(min(remaining, 0.1)):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        poll.unregister(key.fileobj)
                    else:
                        key.data.extend(chunk)
                        reader.require(len(data) + len(errors) <= limits['output_bytes'],
                                       'extractor output byte limit')
            try:
                code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired as exc:
                raise Deferred('extractor timeout') from exc
        reader.require(code == 0, 'extractor nonzero exit')
        return bytes(data), dict(stdout_sha256=reader.digest(data),
                                stderr_sha256=reader.digest(errors), exit_code=code)
    finally:
        if process is not None:
            mask = signal.pthread_sigmask(signal.SIG_BLOCK, packer.CANCEL_SIGNALS)
            try:
                # Kill also after parent exit: inherited pipe holders must not persist.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise Unknown('extractor process-group cancellation unconfirmed') from exc
            finally:
                process.stdout.close()
                process.stderr.close()
                signal.pthread_sigmask(signal.SIG_SETMASK, mask)


def task_result(task):
    return dict(repository=task['source']['repository'], source=task['source'],
                destination=task['destination'], status='failed', reason=None,
                existing=None, samples={}, package=None, canonical_currentness='unknown',
                target={'oid': task['target_oid'], 'authority_basis': 'caller_supplied'
                        if task['target_oid'] else 'not_supplied'}, retained=False)


def execute_task(task, limits, manifest_sha):
    result = task_result(task)
    owned = None
    try:
        with ExitStack() as stack:
            lock = stack.enter_context(reader.open_nofollow(task['lock']))
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise Deferred('lock contention') from exc
            # The caller provisions this stable lock inode; no lock path is created/deleted.
            lock_identity = packer.inode(os.fstat(lock.fileno()))
            try:
                before = source_sample(task)
                result['samples']['before'] = before
                captured = capture(task, limits)
                after = source_sample(task)
                result['samples']['after_capture'] = after
                if before != after:
                    raise Deferred('source changed during capture')
            except (OSError, freshness.ObservationError) as exc:
                raise Deferred('source observation or admitted file unavailable') from exc
            if task['existing'] is not None:
                old = task['existing']
                observed = freshness.observe(old['path'], old['sha256'],
                                             task['source']['repository'], task['root'], task['target_oid'])
                result['existing'] = {k: observed[k] for k in
                                      ('status', 'snapshot_head', 'archive_sha256', 'graph_sha256', 'comparison')}
                result['existing']['build_provenance'] = observed['validation']['build_provenance']
                reader.require(observed['status'] != 'error', 'existing snapshot validation failed')
                if observed['source']['before'] != before or observed['source']['after'] != before:
                    raise Deferred('source changed during existing snapshot assessment')
                if observed['comparison']['qualified']:
                    capture(task, limits)
                    result['samples']['after'] = source_sample(task)
                    if result['samples']['after'] != before:
                        raise Deferred('source changed after snapshot assessment')
                    result.update(status='unchanged', reason='validated clean observed-checkout match')
                    return result
            if task['extractor']['protocol'] != 'python-json/v1' or not Path('/proc/self/fd').is_dir():
                raise Deferred('unsupported extractor adapter')
            try:
                executable, executable_sig = pin(stack, task['extractor']['executable'], 64 * 1024**2)
                script, script_sig = pin(stack, task['extractor']['script'], limits['file_bytes'])
            except ERRORS as exc:
                raise Deferred('extractor evidence missing, changed, or invalid') from exc
            destination = Path(task['destination'])
            parent = stack.enter_context(packer.directory_fd(destination.parent))
            owned = packer.OwnedOutput(parent, destination.name)
            stack.callback(owned.close)
            stack.callback(verify_retained, owned)
            try:
                root = owned.create()
            except FileExistsError as exc:
                raise Deferred('output collision; prior destination preserved') from exc
            except OSError as exc:
                raise Unknown('destination creation effect requires reconciliation') from exc
            result['retained'] = True
            stage = owned.mkdir(root, 'inputs')
            directories = {'': stage}
            for path, raw in sorted(captured.items()):
                parts = Path(path).parts
                prefix = ''
                fd = stage
                for part in parts[:-1]:
                    prefix = part if not prefix else prefix + '/' + part
                    if prefix not in directories:
                        directories[prefix] = owned.mkdir(fd, part)
                    fd = directories[prefix]
                file_write(owned, fd, parts[-1], raw)
            source = task['source']
            documents = dict(
                inventory=dict(schema='graphify-pack-inventory/v1', source=source,
                               files=[dict(f, coverage='unknown') for f in task['files']],
                               limitations=['Coverage is reported by the selected adapter, not independently attested.']),
                policy=dict(schema='graphify-pack-policy/v1', source=source, name='refresh-explicit-selection',
                            rules=dict(allow=task['files'], deny=task['deny'], no_follow=True,
                                       git_metadata_denied=True), limitations=[]),
                extractor=dict(schema='graphify-pack-extractor/v1', source=source,
                               name=task['extractor']['name'], version=task['extractor']['version'],
                               artifact_sha256=task['extractor']['script']['sha256'],
                               limitations=['Interpreter identity and adapter protocol are bound by refresh request.']))
            # Inventory coverage remains unknown in the request; final coverage comes from the adapter.
            request = dict(schema='graphify-refresh-request/v1', manifest_sha256=manifest_sha,
                           source=source, stage=str(destination / 'inputs'),
                           files=task['files'], policy=documents['policy'], extractor=task['extractor'],
                           samples=result['samples'], limits=limits)
            request_raw = packer.encoded(request)
            request_sha = reader.digest(request_raw)
            file_write(owned, root, 'request.json', request_raw)
            file_write(owned, root, 'capture.json', packer.encoded(dict(
                schema='graphify-refresh-capture/v1', request_sha256=request_sha,
                manifest_sha256=manifest_sha, source=source, samples=result['samples'],
                files=task['files'])))
            with reader.open_nofollow(destination / 'request.json') as request_file:
                raw, process_evidence = run_adapter(executable, script, request_file, destination, limits)
            file_write(owned, root, 'adapter-response.json', raw)
            result['process'] = process_evidence
            reader.require(reader.signature(executable) == executable_sig and
                           reader.signature(script) == script_sig, 'adapter changed during execution')
            owned.verify_ownership()
            raw_selected(destination / 'request.json', request_sha, MAX_MANIFEST * 4)
            for f in task['files']:
                raw_selected(destination / 'inputs' / f['path'], f['sha256'], limits['file_bytes'])
            capture(task, limits)
            result['samples']['after'] = source_sample(task)
            if result['samples']['after'] != before:
                raise Deferred('source changed during extraction')
            response = packer.strict_json(raw)
            packer.closed(response, ('schema', 'request_sha256', 'graph', 'validation', 'coverage'), 'adapter response')
            reader.require(response['schema'] == 'graphify-refresh-response/v1'
                           and response['request_sha256'] == request_sha, 'adapter request binding mismatch')
            coverage = response['coverage']
            reader.require(isinstance(coverage, dict) and set(coverage) == set(captured), 'coverage selection mismatch')
            for f in documents['inventory']['files']:
                c = coverage[f['path']]
                reader.require(c in ('structural', 'enriched', 'unknown'), 'invalid adapter coverage')
                f['coverage'] = c
            for name in ('graph', 'validation'):
                document = response[name]
                reader.require(isinstance(document, dict) and document.get('source') == source
                               and document.get('refresh_request_sha256') == request_sha,
                               'adapter output provenance mismatch')
                documents[name] = document
            hashes = {n: reader.digest(packer.encoded(d)) for n, d in documents.items()}
            documents['source'] = dict(schema='graphify-pack-source/v1', source=source,
                                       input_sha256=hashes,
                                       build_observation=dict(head=source['head'], dirty=False, stable=True),
                                       limitations=['Equal Git samples cannot exclude transient edits; captured bytes are digest-bound.',
                                                    'Canonical latest source remains unknown; adapter claims are not independently attested.',
                                                    'Refresh request SHA256: ' + request_sha])
            inputs = {}
            evidence = owned.mkdir(root, 'evidence')
            for name, document in documents.items():
                content = packer.encoded(document)
                file_write(owned, evidence, name + '.json', content)
                inputs[name] = (destination / 'evidence' / (name + '.json'), reader.digest(content))
            owned.verify_ownership()
            if packer.inode(os.stat(task['lock'], follow_symlinks=False)) != lock_identity:
                raise Unknown('lock inode changed; concurrent effects require reconciliation')
            owned.candidate_started = True
            result['package'] = packer.pack(inputs, destination / 'candidate')
            result.update(status='completed', reason='new extraction and create-only candidate validated')
    except Deferred as exc:
        result.update(status='deferred', reason=str(exc)[:500])
    except (Unknown, packer.UnknownOutputError) as exc:
        result.update(status='unknown', reason=str(exc)[:500])
    except KeyboardInterrupt:
        result.update(status='deferred', reason='cancelled; no promotion', cancelled=True)
    except ERRORS as exc:
        result.update(status='failed', reason=(type(exc).__name__ + ': ' + str(exc))[:500])
    finally:
        # Outputs deliberately persist as evidence, including incomplete transactions.
        # No failure path deletes a path that an adapter or another writer may have changed.
        if owned is not None and owned.created:
            result['retained'] = True
    return result


def refresh(manifest_path, manifest_sha):
    absolute(str(manifest_path))
    _, manifest = packer.selected_input(manifest_path, manifest_sha, MAX_MANIFEST)
    validate_manifest(manifest)
    results = []
    stopped = False
    for task in manifest['tasks']:
        if stopped:
            result = task_result(task)
            result.update(status='deferred', reason='prior unknown effect or cancellation; not started')
        else:
            result = execute_task(task, manifest['limits'], manifest_sha)
        stopped = stopped or result['status'] == 'unknown' or result.get('cancelled', False)
        results.append(result)
    statuses = {r['status'] for r in results}
    status = next((s for s in ('unknown', 'failed', 'deferred', 'completed', 'unchanged') if s in statuses))
    return dict(schema='graphify-refresh-result/v1', manifest_sha256=manifest_sha,
                status=status, tasks=results, canonical_currentness='unknown', promoted=False,
                limitations=['Selected Python adapter is trusted, not sandboxed; no network, memory or PID isolation.',
                             'Only one direct child runs at a time; escaped descendants are outside group cancellation.',
                             'Equal observations do not prove absence of transient edits or canonical latest source.',
                             'Retained transaction directories require separately authorized creator-owned cleanup.'])


def bounded_receipt(result):
    raw = packer.encoded(result)
    if len(raw) > MAX_RECEIPT:
        # Preserve identity and the non-success effect; never truncate into success.
        raw = packer.encoded(dict(schema='graphify-refresh-result/v1', status='unknown',
                                 manifest_sha256=result.get('manifest_sha256'), promoted=False,
                                 reason='receipt byte bound exceeded; reconcile selected destinations'))
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
            result = refresh(args.manifest, args.manifest_sha256)
        except KeyboardInterrupt:
            result = dict(schema='graphify-refresh-result/v1', status='deferred', reason='cancelled')
        except ERRORS as exc:
            result = dict(schema='graphify-refresh-result/v1', status='failed', reason=str(exc)[:500])
        raw = bounded_receipt(result)
        sys.stdout.buffer.write(raw)
        status = packer.strict_json(raw)['status']
        return 0 if status in ('completed', 'unchanged') else 2 if status == 'deferred' else 1
    finally:
        for sig, handler in old.items():
            signal.signal(sig, handler)


if __name__ == '__main__':
    raise SystemExit(main())
