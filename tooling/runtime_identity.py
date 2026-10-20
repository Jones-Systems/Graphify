#!/usr/bin/env python3
"""Identify the effective Python runtime of a pinned structural adapter.

Probe mode (`python3 -I -B runtime_identity.py --adapter /abs/adapter.py`) runs
under the exact interpreter that will run the adapter. It loads the adapter
without running its main, calls `fragment()` on two built-in synthetic inputs
to trigger lazy imports, then hashes the interpreter, every loaded module file
and every file-backed executable mapping. It writes nothing and emits one
graphify-runtime-identity/v1 JSON document on stdout.

`identify()` runs that probe as one bounded child process. Any failure gives
status 'unidentified'; callers then disable fragment caching
(cache_disabled:runtime_unidentified) rather than guess.

The probe process approximates, but is not, the extraction process: imports
the synthetic inputs do not reach, environment-dependent dynamic imports and
nondeterministic adapter behaviour stay residual risk. Timestamp-validated
bytecode caches are read, not hashed; only module source paths are hashed.
"""
import hashlib
import json
import os
import resource
import selectors
import signal
import stat
import subprocess
import sys
import time

sys.dont_write_bytecode = True

SCHEMA = 'graphify-runtime-identity/v1'
FIELDS = ('schema', 'status', 'reason', 'implementation', 'version', 'cache_tag',
          'hexversion', 'flags', 'filesystem_encoding', 'executable', 'modules',
          'mapped_objects', 'identity_sha256')
MAX_MODULES = 4096
MAX_MAPPED = 512
MAX_OBJECT_BYTES = 256 * 1024**2
MAX_TOTAL_BYTES = 1024**3
MAX_STDOUT = 64 * 1024
MAX_STDERR = 64 * 1024
ADAPTER_MODULE = 'graphify_runtime_probe_adapter'
# Built-in synthetic inputs; they exercise the .py and .md extraction paths.
PROBE_INPUTS = (('probe/sample.py', b'import os\nfrom . import sibling\nclass Probe:\n'
                 b'    def method(self):\n        pass\n'),
                ('probe/sample.md', b'# Probe\n[sample](sample.py)\n'))
PROBE_LIMITS = dict(file_bytes=4 * 1024**2, input_bytes=16 * 1024**2,
                    output_bytes=8 * 1024**2, seconds=300)
CANCEL_SIGNALS = {signal.SIGINT, signal.SIGTERM}


class Unidentified(ValueError):
    pass


class Unknown(RuntimeError):
    """The probe child may still be running; its effects need reconciliation."""


def require(condition, message):
    if not condition:
        raise Unidentified(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def valid_hash(value):
    return (isinstance(value, str) and len(value) == 64
            and all(c in '0123456789abcdef' for c in value))


def absolute(value):
    return (isinstance(value, str) and value.startswith('/') and '\0' not in value
            and os.path.normpath(value) == value)


def seal(document):
    body = {k: v for k, v in document.items() if k != 'identity_sha256'}
    return dict(body, identity_sha256=hashlib.sha256(canonical(body)).hexdigest())


def unidentified(reason):
    """A closed unidentified document; identity_sha256 stays null."""
    document = dict.fromkeys(FIELDS)
    document.update(schema=SCHEMA, status='unidentified', reason=str(reason)[:512])
    return document


class Hasher:
    """Hash regular files once each, within per-object and total byte bounds."""

    def __init__(self):
        self.seen = {}
        self.total = 0

    def __call__(self, path):
        require(absolute(path), 'object path is not absolute and normalized')
        if path in self.seen:
            return self.seen[path]
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        except OSError as exc:
            raise Unidentified(f'unreadable object {path}: {type(exc).__name__}') from exc
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode), f'object is not a regular file: {path}')
            require(before.st_size <= MAX_OBJECT_BYTES, f'object byte limit: {path}')
            require(self.total + before.st_size <= MAX_TOTAL_BYTES, 'total hashed byte limit')
            sha, count = hashlib.sha256(), 0
            while block := os.read(fd, 1024 * 1024):
                count += len(block)
                require(count <= MAX_OBJECT_BYTES, f'object byte limit: {path}')
                sha.update(block)
            after = os.fstat(fd)
            require(count == before.st_size and
                    (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                    (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                    f'object changed during hashing: {path}')
        except OSError as exc:
            raise Unidentified(f'unreadable object {path}: {type(exc).__name__}') from exc
        finally:
            os.close(fd)
        self.total += count
        self.seen[path] = sha.hexdigest()
        return self.seen[path]


def module_records(modules, hasher, exclude=('__main__', ADAPTER_MODULE)):
    """Classify loaded modules as file, builtin or frozen; anything else is unidentified.

    The probe (`__main__`) and the adapter are excluded: callers pin both by
    their own sha256 (adapter_sha256 and the probe binding).
    """
    records = []
    for name in sorted(modules):
        module = modules[name]
        if name in exclude or module is None:
            continue
        require(len(records) < MAX_MODULES, 'module count limit')
        spec = getattr(module, '__spec__', None)
        origin = getattr(spec, 'origin', None)
        loader = getattr(spec, 'loader', None)
        loader_name = getattr(loader, '__name__', type(loader).__name__)
        # Frozen code lives in the executable even when __file__ names a source file.
        if origin == 'frozen' or loader_name == 'FrozenImporter':
            records.append(dict(name=name, origin='frozen', path=None, sha256=None))
        elif origin == 'built-in' or loader_name == 'BuiltinImporter':
            records.append(dict(name=name, origin='builtin', path=None, sha256=None))
        else:
            file = getattr(module, '__file__', None)
            require(isinstance(file, str) and file.startswith('/'),
                    f'unsupported module origin: {name}')
            path = os.path.realpath(file)
            records.append(dict(name=name, origin='file', path=path, sha256=hasher(path)))
    return records


def mapped_paths(maps_text):
    """Distinct file-backed executable mappings from /proc/self/maps text."""
    paths = set()
    for line in maps_text.splitlines():
        fields = line.split(None, 5)
        require(len(fields) >= 5, 'malformed memory map line')
        if len(fields) < 6 or 'x' not in fields[1] or not fields[5].startswith('/'):
            continue
        path = fields[5]
        require(not path.endswith(' (deleted)'), f'mapped object deleted: {path}')
        paths.add(path)
        require(len(paths) <= MAX_MAPPED, 'mapped object count limit')
    return sorted(paths)


def load_adapter(path):
    import importlib.machinery
    import importlib.util
    # An explicit loader: the driver passes a suffixless /proc/self/fd path.
    loader = importlib.machinery.SourceFileLoader(ADAPTER_MODULE, path)
    spec = importlib.util.spec_from_file_location(ADAPTER_MODULE, path, loader=loader)
    require(spec is not None and spec.loader is not None, 'adapter is not loadable')
    module = importlib.util.module_from_spec(spec)
    sys.modules[ADAPTER_MODULE] = module
    spec.loader.exec_module(module)
    return module


def describe(adapter_path, maps_path='/proc/self/maps'):
    """Return the sealed identity of this process after exercising the adapter."""
    try:
        adapter = load_adapter(adapter_path)
    except Unidentified:
        raise
    except Exception as exc:  # trusted code, but any import failure is only unidentified
        raise Unidentified(f'adapter load failed: {type(exc).__name__}') from exc
    hook = getattr(adapter, 'fragment', None)
    require(callable(hook), 'adapter has no fragment hook')
    limits = getattr(adapter, 'LIMITS', PROBE_LIMITS)
    for path, raw in PROBE_INPUTS:
        try:
            hook(path, raw, dict(limits))
        except Exception as exc:
            raise Unidentified(f'fragment hook failed: {type(exc).__name__}') from exc
    hasher = Hasher()
    modules = module_records(dict(sys.modules), hasher)
    try:
        executable = os.readlink('/proc/self/exe')
        with open(maps_path, encoding='ascii', errors='surrogateescape') as h:
            maps_text = h.read(16 * 1024**2 + 1)
    except OSError as exc:
        raise Unidentified(f'process identity unavailable: {type(exc).__name__}') from exc
    require(len(maps_text) <= 16 * 1024**2, 'memory map size limit')
    mapped = [dict(path=p, sha256=hasher(p)) for p in mapped_paths(maps_text)]
    flags = {name: getattr(sys.flags, name) for name in type(sys.flags).__match_args__}
    return seal(dict(
        schema=SCHEMA, status='identified', reason=None,
        implementation=sys.implementation.name, version=sys.version,
        cache_tag=sys.implementation.cache_tag, hexversion=sys.hexversion, flags=flags,
        filesystem_encoding=sys.getfilesystemencoding(),
        executable=dict(path=executable, sha256=hasher(executable)),
        modules=modules, mapped_objects=mapped))


def probe(argv):
    """CLI body. Adapter stdout is diverted so only the identity reaches fd 1."""
    out = os.dup(1)
    null = os.open(os.devnull, os.O_WRONLY | os.O_CLOEXEC)
    os.dup2(null, 1)
    try:
        if len(argv) != 2 or argv[0] != '--adapter' or not absolute(argv[1]):
            document = unidentified('usage: --adapter /abs/adapter.py')
        else:
            try:
                document = describe(argv[1])
            except Unidentified as exc:
                document = unidentified(str(exc))
            except Exception as exc:  # any probe fault is only unidentified
                document = unidentified(f'probe failed: {type(exc).__name__}')
        raw = canonical(document)
        if len(raw) > MAX_STDOUT:
            raw = canonical(unidentified('identity output byte limit'))
    finally:
        sys.stdout.flush()
        os.dup2(out, 1)
        os.close(null)
        os.close(out)
    view = memoryview(raw)
    while view:
        view = view[os.write(1, view):]
    return 0


# ---- driver side (runs in the caller's process) ----

def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate identity key')
            result[key] = value
        return result

    def constant(value):
        raise Unidentified('non-finite identity number')

    try:
        return json.loads(raw.decode('ascii'), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise Unidentified(f'invalid identity JSON: {type(exc).__name__}') from exc


def validate_identity(raw, python_sha256=None):
    """Parse and validate probe stdout; return a closed document or raise Unidentified."""
    require(len(raw) <= MAX_STDOUT, 'identity output byte limit')
    document = strict_json(raw)
    require(isinstance(document, dict) and tuple(sorted(document)) == tuple(sorted(FIELDS)),
            'identity document is not closed')
    require(document['schema'] == SCHEMA, 'identity schema mismatch')
    if document['status'] == 'unidentified':
        require(isinstance(document['reason'], str) and document['reason'] and
                all(document[k] is None for k in FIELDS if k not in ('schema', 'status', 'reason')),
                'malformed unidentified identity')
        raise Unidentified(document['reason'])
    require(document['status'] == 'identified' and document['reason'] is None,
            'invalid identity status')
    for key in ('implementation', 'version', 'filesystem_encoding'):
        require(isinstance(document[key], str) and document[key], f'invalid {key}')
    require(document['cache_tag'] is None or isinstance(document['cache_tag'], str),
            'invalid cache_tag')
    require(type(document['hexversion']) is int, 'invalid hexversion')
    flags = document['flags']
    require(isinstance(flags, dict) and flags and
            all(isinstance(k, str) and (v is None or type(v) in (int, bool))
                for k, v in flags.items()),
            'invalid flags')
    # The probe must itself run isolated and without bytecode writes, as the adapter does.
    require(flags.get('isolated') == 1 and flags.get('dont_write_bytecode') == 1,
            'probe was not run with -I -B')

    def obj(value, label):
        require(isinstance(value, dict) and sorted(value) == ['path', 'sha256'] and
                absolute(value['path']) and valid_hash(value['sha256']), f'invalid {label}')
        return value['path']

    obj(document['executable'], 'executable')
    if python_sha256 is not None:
        require(document['executable']['sha256'] == python_sha256,
                'probe executable differs from pinned interpreter')
    modules = document['modules']
    require(isinstance(modules, list) and len(modules) <= MAX_MODULES, 'invalid modules')
    names = []
    for m in modules:
        require(isinstance(m, dict) and sorted(m) == ['name', 'origin', 'path', 'sha256'] and
                isinstance(m['name'], str) and m['name'], 'invalid module record')
        if m['origin'] == 'file':
            require(absolute(m['path']) and valid_hash(m['sha256']), 'invalid module file')
        else:
            require(m['origin'] in ('builtin', 'frozen') and m['path'] is None and
                    m['sha256'] is None, 'invalid module origin')
        names.append(m['name'])
    require(names == sorted(set(names)), 'modules not sorted and unique')
    mapped = document['mapped_objects']
    require(isinstance(mapped, list) and 0 < len(mapped) <= MAX_MAPPED, 'invalid mapped objects')
    paths = [obj(m, 'mapped object') for m in mapped]
    require(paths == sorted(set(paths)), 'mapped objects not sorted and unique')
    require(valid_hash(document['identity_sha256']) and
            seal(document)['identity_sha256'] == document['identity_sha256'],
            'identity digest mismatch')
    return document


def pin(path, expected):
    """Open without following symlinks and verify the sha256; return the handle."""
    require(absolute(path), 'pinned path is not absolute and normalized')
    require(valid_hash(expected), 'invalid pinned checksum')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        parts = path.split('/')[1:]
        for part in parts[:-1]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                          dir_fd=fd)
            os.close(fd)
            fd = new
        handle = os.fdopen(os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                                   os.O_CLOEXEC, dir_fd=fd), 'rb')
    finally:
        os.close(fd)
    try:
        require(stat.S_ISREG(os.fstat(handle.fileno()).st_mode), f'not a regular file: {path}')
        require(digest_handle(handle) == expected, f'checksum mismatch: {path}')
    except BaseException:
        handle.close()
        raise
    return handle


def digest_handle(handle):
    s = os.fstat(handle.fileno())
    require(s.st_size <= MAX_OBJECT_BYTES, 'pinned object byte limit')
    handle.seek(0)
    sha, count = hashlib.sha256(), 0
    while block := handle.read(1024 * 1024):
        count += len(block)
        require(count <= MAX_OBJECT_BYTES, 'pinned object byte limit')
        sha.update(block)
    after = os.fstat(handle.fileno())
    require((s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns) ==
            (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
            'pinned object changed during hashing')
    handle.seek(0)
    return sha.hexdigest()


def probe_limits():
    # Bounds regular-file output, not memory, networking, or the process count.
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    signal.pthread_sigmask(signal.SIG_SETMASK, set())


def run_probe(executable, script, adapter, timeout):
    """One direct child (graph_refresh.run_adapter pattern); returns stdout bytes."""
    command = [f'/proc/self/fd/{executable.fileno()}', '-I', '-B',
               f'/proc/self/fd/{script.fileno()}', '--adapter', f'/proc/self/fd/{adapter.fileno()}']
    process = None
    try:
        mask = signal.pthread_sigmask(signal.SIG_BLOCK, CANCEL_SIGNALS)
        try:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, cwd='/', env={'LC_ALL': 'C.UTF-8'},
                                       pass_fds=(executable.fileno(), script.fileno(),
                                                 adapter.fileno()),
                                       start_new_session=True, preexec_fn=probe_limits)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        out, err = bytearray(), bytearray()
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as poll:
            poll.register(process.stdout, selectors.EVENT_READ, (out, MAX_STDOUT))
            poll.register(process.stderr, selectors.EVENT_READ, (err, MAX_STDERR))
            while poll.get_map():
                remaining = deadline - time.monotonic()
                require(remaining > 0, 'probe timeout')
                for key, _ in poll.select(min(remaining, 0.1)):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        poll.unregister(key.fileobj)
                    else:
                        buffer, bound = key.data
                        buffer.extend(chunk)
                        require(len(buffer) <= bound, 'probe output byte limit')
            try:
                code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired as exc:
                raise Unidentified('probe timeout') from exc
        require(code == 0, 'probe nonzero exit')
        return bytes(out)
    finally:
        if process is not None:
            mask = signal.pthread_sigmask(signal.SIG_BLOCK, CANCEL_SIGNALS)
            try:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise Unknown('probe process-group cancellation unconfirmed') from exc
            finally:
                process.stdout.close()
                process.stderr.close()
                signal.pthread_sigmask(signal.SIG_SETMASK, mask)


def identify(python_path, python_sha256, adapter_path, adapter_sha256, *, timeout=60,
             probe_sha256=None):
    """Probe the pinned interpreter+adapter; return a graphify-runtime-identity/v1 dict.

    Never raises for probe failures: they give status 'unidentified' with a
    reason. Raises Unknown only when the child's termination is unconfirmed.
    probe_sha256, when given, pins this module's own bytes as the probe script.
    """
    handles = []
    try:
        require(isinstance(timeout, (int, float)) and not isinstance(timeout, bool) and
                0 < timeout <= 600, 'invalid probe timeout')
        script_path = os.path.realpath(os.path.abspath(__file__))
        if probe_sha256 is None:
            with open(script_path, 'rb') as h:
                probe_sha256 = hashlib.sha256(h.read(MAX_OBJECT_BYTES + 1)).hexdigest()
        for path, sha in ((python_path, python_sha256), (script_path, probe_sha256),
                          (adapter_path, adapter_sha256)):
            handles.append(pin(path, sha))
        executable, script, adapter = handles
        raw = run_probe(executable, script, adapter, timeout)
        # A pinned file rewritten in place during the probe invalidates the result.
        for handle, sha in zip(handles, (python_sha256, probe_sha256, adapter_sha256)):
            require(digest_handle(handle) == sha, 'pinned input changed during probe')
        return validate_identity(raw, python_sha256)
    except Unidentified as exc:
        return unidentified(str(exc))
    except (OSError, ValueError, TypeError, OverflowError, subprocess.SubprocessError) as exc:
        return unidentified(f'probe failed: {type(exc).__name__}')
    finally:
        for handle in handles:
            handle.close()


if __name__ == '__main__':
    raise SystemExit(probe(sys.argv[1:]))
