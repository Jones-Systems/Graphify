#!/usr/bin/env python3
"""Install Graphify's five portable helpers from explicit local Git blobs.

Linux-only, ordinary-user source installation. No dependencies, graph stores,
bindings, current pointers or services are installed. Expected digests bind
caller-selected source; they do not authenticate a repository or its owner.
"""
import argparse
from contextlib import contextmanager
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
import uuid

SCHEMA = 'graphify-portable-release/v1'
REPOSITORY = 'Jones-Systems/Graphify'
FILES = tuple('tooling/' + name for name in (
    'graph_freshness.py', 'graph_pack.py', 'graph_pull.py', 'graph_read.py', 'graph_refresh.py'))
INSTALLER = 'tooling/install_portable.py'
MAX_BLOB = 1024 * 1024
MAX_MANIFEST = 16384
SIGNALS = {signal.SIGINT, signal.SIGTERM}


class InstallError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise InstallError(code)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def oid(value):
    return isinstance(value, str) and re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', value) is not None


def absolute(value):
    value = os.fspath(value)
    path = Path(value)
    require(path.is_absolute() and value == str(path) and value != '/'
            and all(part not in ('.', '..', '') for part in value[1:].split('/')), 'invalid_path')
    return path


@contextmanager
def directory(path):
    path = absolute(path)
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def signature(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def inode(info):
    return info.st_dev, info.st_ino


def read_file(parent, name, limit, mode=None):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, 'unsafe_file')
        require(before.st_size <= limit, 'file_limit')
        if mode is not None:
            require(stat.S_IMODE(before.st_mode) == mode, 'file_mode_mismatch')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        require(len(raw) <= limit and signature(before) == signature(os.fstat(fd))
                == signature(os.stat(name, dir_fd=parent, follow_symlinks=False)), 'file_changed')
        return raw
    finally:
        os.close(fd)


def git(source, *args, limit=MAX_BLOB):
    """Bound local object reads; do not fetch, run filters, or use replacement refs."""
    env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    env.update(GIT_OPTIONAL_LOCKS='0', GIT_NO_LAZY_FETCH='1', GIT_NO_REPLACE_OBJECTS='1',
               GIT_TERMINAL_PROMPT='0', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
    command = ['git', '--no-optional-locks', '--no-lazy-fetch', '-C', str(source), *args]
    with subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
        try:
            raw = bytearray()
            deadline = time.monotonic() + 10
            with selectors.DefaultSelector() as poll:
                poll.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    require(remaining > 0 and poll.select(remaining), 'git_timeout')
                    block = os.read(process.stdout.fileno(), 65536)
                    if not block:
                        break
                    raw.extend(block)
                    require(len(raw) <= limit, 'git_output_limit')
            require(process.wait(timeout=max(0.001, deadline - time.monotonic())) == 0,
                    'git_read_failed')
            return bytes(raw)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()


def blob_hash(raw, object_id):
    algorithm = hashlib.sha1 if len(object_id) == 40 else hashlib.sha256
    return algorithm(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def source_blob(source, revision, path):
    listing = git(source, 'ls-tree', '-z', revision, '--', path, limit=1024)
    match = re.fullmatch(rb'(100644|100755) blob ([0-9a-f]{40}|[0-9a-f]{64})\t'
                         + re.escape(path.encode()) + rb'\x00', listing)
    require(match is not None, 'missing_or_nonregular_source_blob')
    mode, object_id = (part.decode() for part in match.groups())
    size = git(source, 'cat-file', '-s', object_id, limit=32).strip()
    require(size.isdigit() and int(size) <= MAX_BLOB, 'source_blob_limit')
    raw = git(source, 'cat-file', 'blob', object_id)
    require(len(raw) == int(size) and blob_hash(raw, object_id) == object_id, 'source_blob_changed')
    return {'path': path, 'blob_oid': object_id, 'sha256': digest(raw),
            'bytes': len(raw), 'source_mode': mode, 'mode': '0444'}, raw


def prepare(source, revision, destination):
    source, destination = absolute(source), absolute(destination)
    require(oid(revision), 'invalid_revision')
    require(source != destination and source not in destination.parents
            and destination not in source.parents, 'source_destination_overlap')
    with directory(source), directory(destination) as parent:
        info = os.fstat(parent)
        require(info.st_uid == os.getuid() and not stat.S_IMODE(info.st_mode) & 0o022,
                'destination_not_owner_controlled')
        require(git(source, 'rev-parse', '--show-toplevel', limit=4096).decode().rstrip('\n') == str(source),
                'not_exact_checkout')
        require(git(source, 'rev-parse', '--verify', 'HEAD^{commit}', limit=128).decode().strip()
                == revision, 'source_head_mismatch')
        origin = git(source, 'config', '--local', '--no-includes', '--get-all', 'remote.origin.url', limit=1024).strip()
        require(origin in (b'https://github.com/Jones-Systems/Graphify.git',
                           b'https://github.com/Jones-Systems/Graphify',
                           b'git@github.com:Jones-Systems/Graphify.git'), 'source_repository_mismatch')
        records, payloads = [], {}
        for path in FILES:
            record, raw = source_blob(source, revision, path)
            records.append(record)
            payloads[path] = raw
        installer, raw = source_blob(source, revision, INSTALLER)
        running = absolute(os.path.abspath(__file__))
        with directory(running.parent) as script_parent:
            require(read_file(script_parent, running.name, MAX_BLOB) == raw, 'installer_revision_mismatch')
        manifest = {'schema': SCHEMA, 'repository': REPOSITORY, 'revision': revision,
                    'files': records, 'installer': installer}
        require(git(source, 'rev-parse', '--verify', 'HEAD^{commit}', limit=128).decode().strip()
                == revision, 'source_head_changed')
        return manifest, payloads


def validate_manifest(value):
    require(isinstance(value, dict) and set(value) == {'schema', 'repository', 'revision', 'files', 'installer'},
            'invalid_manifest')
    require(value['schema'] == SCHEMA and value['repository'] == REPOSITORY and oid(value['revision']),
            'invalid_manifest_identity')
    require(isinstance(value['files'], list) and len(value['files']) == len(FILES), 'invalid_closure')
    for record, path in zip([*value['files'], value['installer']], [*FILES, INSTALLER]):
        require(isinstance(record, dict) and set(record) ==
                {'path', 'blob_oid', 'sha256', 'bytes', 'source_mode', 'mode'}, 'invalid_manifest_record')
        require(record['path'] == path and oid(record['blob_oid'])
                and len(record['blob_oid']) == len(value['revision'])
                and isinstance(record['sha256'], str)
                and re.fullmatch(r'[0-9a-f]{64}', record['sha256']) is not None
                and type(record['bytes']) is int and 0 <= record['bytes'] <= MAX_BLOB
                and record['source_mode'] in ('100644', '100755') and record['mode'] == '0444',
                'invalid_manifest_record')


def pairs(values):
    result = {}
    for key, value in values:
        require(key not in result, 'duplicate_json_key')
        result[key] = value
    return result


def verify_fd(root, expected):
    require(isinstance(expected, str) and re.fullmatch(r'[0-9a-f]{64}', expected) is not None,
            'invalid_manifest_digest')
    require(stat.S_IMODE(os.fstat(root).st_mode) == 0o555, 'directory_mode_mismatch')
    require(set(os.listdir(root)) == {'release.json', 'tooling'}, 'unexpected_release_contents')
    raw = read_file(root, 'release.json', MAX_MANIFEST, 0o444)
    try:
        manifest = json.loads(raw, object_pairs_hook=pairs)
    except (ValueError, RecursionError) as exc:
        raise InstallError('invalid_manifest_json') from exc
    validate_manifest(manifest)
    require(raw == encoded(manifest) + b'\n' and digest(encoded(manifest)) == expected,
            'manifest_digest_mismatch')
    tooling = os.open('tooling', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
    try:
        require(stat.S_IMODE(os.fstat(tooling).st_mode) == 0o555, 'directory_mode_mismatch')
        require(set(os.listdir(tooling)) == {Path(path).name for path in FILES}, 'unexpected_release_contents')
        for record in manifest['files']:
            data = read_file(tooling, Path(record['path']).name, MAX_BLOB, 0o444)
            require(len(data) == record['bytes'] and digest(data) == record['sha256']
                    and blob_hash(data, record['blob_oid']) == record['blob_oid'], 'release_file_mismatch')
    finally:
        os.close(tooling)
    return manifest


def verify(release, expected):
    release = absolute(release)
    require(release.name == expected, 'release_name_mismatch')
    with directory(release) as root:
        return verify_fd(root, expected)


def rename_new(parent, old, new):
    # Linux RENAME_NOREPLACE makes even an empty destination a collision.
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, 'renameat2', None)
    require(rename is not None, 'atomic_create_unavailable')
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    if rename(parent, os.fsencode(old), parent, os.fsencode(new), 1) != 0:
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise InstallError('destination_collision')
        raise OSError(error, 'release publication failed')


class Stage:
    """Track only this invocation's entries; refuse cleanup after unknown changes."""
    def __init__(self, parent):
        self.parent = parent
        self.name = '.stage-' + uuid.uuid4().hex
        self.root = self.tooling = None
        self.root_identity = None
        self.tooling_identity = None
        self.files = []
        self.published = False
        self.created = False

    def create(self):
        mask = signal.pthread_sigmask(signal.SIG_BLOCK, SIGNALS)
        try:
            os.mkdir(self.name, mode=0o700, dir_fd=self.parent)
            self.created = True
            self.root = os.open(self.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.parent)
            self.root_identity = inode(os.fstat(self.root))
            os.mkdir('tooling', mode=0o700, dir_fd=self.root)
            self.tooling = os.open('tooling', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.root)
            self.tooling_identity = inode(os.fstat(self.tooling))
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, mask)

    def write(self, parent, name, raw):
        fd = None
        try:
            mask = signal.pthread_sigmask(signal.SIG_BLOCK, SIGNALS)
            try:
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
                self.files.append((parent, name, inode(os.fstat(fd))))
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, mask)
            with os.fdopen(fd, 'wb', closefd=False) as stream:
                stream.write(raw)
                stream.flush()
            os.fchmod(fd, 0o444)
            os.fsync(fd)
        finally:
            if fd is not None:
                os.close(fd)

    def cleanup(self):
        if not self.created or self.published:
            return
        require(self.root is not None, 'cleanup_unknown_root')
        require(inode(os.stat(self.name, dir_fd=self.parent, follow_symlinks=False)) == self.root_identity,
                'cleanup_unknown_root')
        if self.tooling is not None:
            require(inode(os.stat('tooling', dir_fd=self.root, follow_symlinks=False)) == self.tooling_identity,
                    'cleanup_unknown_directory')
        for parent, name, expected in self.files:
            require(inode(os.stat(name, dir_fd=parent, follow_symlinks=False)) == expected,
                    'cleanup_unknown_file')
        for fd in (self.root, self.tooling):
            if fd is not None:
                expected = {name for parent, name, _ in self.files if parent == fd}
                if fd == self.root and self.tooling is not None:
                    expected.add('tooling')
                require(set(os.listdir(fd)) == expected, 'cleanup_unknown_contents')
        os.fchmod(self.root, 0o700)
        if self.tooling is not None:
            os.fchmod(self.tooling, 0o700)
        for parent, name, _ in reversed(self.files):
            os.unlink(name, dir_fd=parent)
        if self.tooling is not None:
            os.rmdir('tooling', dir_fd=self.root)
        os.rmdir(self.name, dir_fd=self.parent)

    def close(self):
        for fd in (self.tooling, self.root):
            if fd is not None:
                os.close(fd)


def install(source, revision, destination, expected):
    require(sys.platform == 'linux', 'unsupported_platform')
    manifest, payloads = prepare(source, revision, destination)
    require(digest(encoded(manifest)) == expected, 'manifest_digest_mismatch')
    destination = absolute(destination)
    with directory(destination) as parent:
        info = os.fstat(parent)
        require(info.st_uid == os.getuid() and not stat.S_IMODE(info.st_mode) & 0o022,
                'destination_not_owner_controlled')
        try:
            os.stat(expected, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            return verify(destination / expected, expected)
        stage = Stage(parent)
        try:
            stage.create()
            for path, raw in payloads.items():
                stage.write(stage.tooling, Path(path).name, raw)
            stage.write(stage.root, 'release.json', encoded(manifest) + b'\n')
            os.fchmod(stage.tooling, 0o555)
            os.fchmod(stage.root, 0o555)
            verify_fd(stage.root, expected)
            os.fsync(stage.tooling)
            os.fsync(stage.root)
            mask = signal.pthread_sigmask(signal.SIG_BLOCK, SIGNALS)
            try:
                require(inode(os.stat(stage.name, dir_fd=parent, follow_symlinks=False))
                        == stage.root_identity, 'stage_identity_changed')
                rename_new(parent, stage.name, expected)
                stage.published = True
                os.fsync(parent)
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, mask)
            verify(destination / expected, expected)
            return manifest
        except BaseException as original:
            mask = signal.pthread_sigmask(signal.SIG_BLOCK, SIGNALS)
            try:
                stage.cleanup()
            except BaseException as cleanup_error:
                raise InstallError('cleanup_unknown; original=' + type(original).__name__
                                   + '; inspect ' + str(destination / stage.name)) from cleanup_error
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, mask)
            if stage.published:
                raise InstallError('publication_requires_readback; inspect ' + str(destination / expected)) from original
            raise
        finally:
            stage.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'install'):
        sub = commands.add_parser(name)
        sub.add_argument('--source', required=True)
        sub.add_argument('--revision', required=True)
        sub.add_argument('--destination', required=True, help='existing owner-controlled release parent')
        if name == 'install':
            sub.add_argument('--manifest-sha256', required=True)
    sub = commands.add_parser('verify')
    sub.add_argument('--release', required=True)
    sub.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args(argv)
    old = {}
    def cancel(signum, frame):
        raise KeyboardInterrupt('cancelled')
    try:
        for sig in SIGNALS:
            old[sig] = signal.signal(sig, cancel)
        if args.command == 'verify':
            manifest = verify(args.release, args.manifest_sha256)
            result = {'status': 'verified', 'manifest_sha256': args.manifest_sha256,
                      'revision': manifest['revision'], 'release': args.release}
        else:
            manifest = (prepare(args.source, args.revision, args.destination)[0] if args.command == 'prepare'
                        else install(args.source, args.revision, args.destination, args.manifest_sha256))
            sha = digest(encoded(manifest))
            result = {'status': 'prepared' if args.command == 'prepare' else 'installed',
                      'manifest': manifest, 'manifest_sha256': sha,
                      'release': str(Path(args.destination) / sha)}
        code = 0
    except KeyboardInterrupt:
        result, code = {'status': 'cancelled'}, 2
    except (InstallError, OSError, ValueError, subprocess.SubprocessError) as exc:
        result, code = {'status': 'error', 'reason': str(exc)}, 1
    finally:
        for sig, handler in old.items():
            signal.signal(sig, handler)
    print(encoded(result).decode())
    return code


if __name__ == '__main__':
    raise SystemExit(main())
