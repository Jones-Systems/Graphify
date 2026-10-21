#!/usr/bin/env python3
"""Bounded, content-addressed, create-only cache of structural fragments.

A key is graphify-fragment-key/v1: schema, fragment_schema, family {name,
version}, adapter_sha256, runtime_identity_sha256, per_file_policy_sha256,
path, and content_sha256. key_sha256 is the SHA256 of its canonical compact
sorted ASCII JSON. Commit identity is never part of a key. fragment_schema is
graphify-structural-fragment/v1 with any bounded family, or
graphify-structural-fragment/v2 with exactly family graphify-stdlib-structural
version 2. The entry size cap follows fragment_schema: 1 MiB for v1, and for
v2 the adapter's 8 MiB fragment ceiling plus a 64 KiB key and envelope
allowance. A v2 entry's fragment must also carry the key's fragment_schema.

The caller creates the cache root as an owner-only 0700 directory reached
without symlinks. Entries live at objects/<key[0:2]>/<key>.json as
graphify-fragment-cache-entry/v1. Writes go to an exclusive 0600 temporary file
in the same shard, are fsynced, and are published with os.link, which fails if
the final name exists. A final entry is never replaced or deleted.

Every entry is validated before reuse. An invalid entry is reported as corrupt
and preserved; the caller recomputes without the cache. Quota accounting is a
bounded scan at open plus increments for this instance's writes; a put that
would exceed the quota is refused. There is no eviction or garbage collection.
Handled exceptions remove only this call's temporary file; unhandleable
termination may leave one hidden temporary file, never a partial final entry.
"""

import errno
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat

from graph_pack import bounded_text, closed, file_path, strict_json
from graph_read import StoreError, require, valid_hash

KEY_SCHEMA = 'graphify-fragment-key/v1'
FRAGMENT_SCHEMA = 'graphify-structural-fragment/v1'
# Family 2 values duplicated from refresh_adapter_structural.py, not imported;
# tests/test_fragment_cache_v2.py guards them against drift.
FRAGMENT_SCHEMA_V2 = 'graphify-structural-fragment/v2'
FAMILY_V2 = dict(name='graphify-stdlib-structural', version='2')
MAX_FRAGMENT_BYTES_V2 = 8 * 1024**2
ENTRY_SCHEMA = 'graphify-fragment-cache-entry/v1'
KEY_FIELDS = ('schema', 'fragment_schema', 'family', 'adapter_sha256',
              'runtime_identity_sha256', 'per_file_policy_sha256', 'path',
              'content_sha256')
ENTRY_FIELDS = ('schema', 'key_sha256', 'key', 'fragment_sha256', 'fragment')
MAX_ENTRY = 1024**2
MAX_ENTRY_V2 = MAX_FRAGMENT_BYTES_V2 + 64 * 1024
MAX_SCAN_ENTRIES = 1000000
SHARD = re.compile('[0-9a-f]{2}')
DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


class CacheError(StoreError):
    """The cache root or key material is unusable."""


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def validate_material(material):
    try:
        closed(material, KEY_FIELDS, 'fragment key')
        require(material['schema'] == KEY_SCHEMA, 'unsupported fragment key schema')
        require(material['fragment_schema'] in (FRAGMENT_SCHEMA, FRAGMENT_SCHEMA_V2),
                'unsupported fragment schema')
        family = material['family']
        closed(family, ('name', 'version'), 'fragment family')
        bounded_text(family['name'], 'family name')
        bounded_text(family['version'], 'family version')
        require(material['fragment_schema'] == FRAGMENT_SCHEMA or family == FAMILY_V2,
                'unsupported fragment family')
        for name in ('adapter_sha256', 'runtime_identity_sha256',
                     'per_file_policy_sha256', 'content_sha256'):
            require(valid_hash(material[name]), f'invalid {name}')
        file_path(material['path'])
    except StoreError as error:
        raise CacheError(str(error)) from None
    return material


def key(material):
    """Return key_sha256 for validated graphify-fragment-key/v1 material."""
    return sha256(canonical(validate_material(material)))


def _max_entry(material):
    return MAX_ENTRY_V2 if material['fragment_schema'] == FRAGMENT_SCHEMA_V2 else MAX_ENTRY


def _matches(material, fragment):
    return (isinstance(fragment, dict) and fragment.get('path') == material['path']
            and fragment.get('content_sha256') == material['content_sha256']
            and (material['fragment_schema'] == FRAGMENT_SCHEMA
                 or fragment.get('schema') == material['fragment_schema']))


def _owned_directory(fd, label):
    value = os.fstat(fd)
    require(stat.S_ISDIR(value.st_mode) and value.st_uid == os.geteuid()
            and stat.S_IMODE(value.st_mode) == 0o700,
            f'{label} must be an owner-only 0700 directory')


def _open_root(root):
    require(isinstance(root, (str, os.PathLike)), 'invalid cache root')
    path = Path(root)
    require(path.is_absolute() and os.path.normpath(path) == str(path),
            'cache root must be a normalized absolute path')
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:]:
            child = os.open(part, DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = child
        _owned_directory(fd, 'cache root')
    except BaseException:
        os.close(fd)
        raise
    return fd


def _entry(material, fragment):
    """Return (key_sha256, fragment_sha256, encoded entry bytes)."""
    key_sha = key(material)
    require(_matches(material, fragment), 'fragment does not match its key')
    fragment_sha = sha256(canonical(fragment))
    data = canonical(dict(schema=ENTRY_SCHEMA, key_sha256=key_sha, key=material,
                          fragment_sha256=fragment_sha, fragment=fragment)) + b'\n'
    return key_sha, fragment_sha, data


class FragmentCache:
    """One pinned cache root; use as a context manager or call close()."""

    def __init__(self, fd, quota_bytes):
        self._fd = fd
        self.quota_bytes = quota_bytes
        self.bytes_used = 0
        self.status = 'ok'
        self.counts = dict(hits=0, misses=0, corrupt=0, stored=0, exists=0, full=0)

    @classmethod
    def open(cls, root, quota_bytes):
        try:
            require(type(quota_bytes) is int and quota_bytes >= 0, 'invalid cache quota')
            fd = _open_root(root)
        except OSError as error:
            raise CacheError(f'unusable cache root: {error.strerror or error}') from None
        except StoreError as error:
            raise CacheError(str(error)) from None
        cache = cls(fd, quota_bytes)
        try:
            cache._scan()
        except BaseException:
            cache.close()
            raise
        return cache

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _scan(self):
        """Count bytes of existing regular files; disable writes when unbounded."""
        try:
            objects = os.open('objects', DIRECTORY, dir_fd=self._fd)
        except FileNotFoundError:
            return
        except OSError:
            self.status = 'disabled'
            return
        seen = used = 0
        try:
            _owned_directory(objects, 'objects directory')
            for shard in os.listdir(objects):
                seen += 1
                require(seen <= MAX_SCAN_ENTRIES, 'cache scan limit exceeded')
                value = os.stat(shard, dir_fd=objects, follow_symlinks=False)
                if stat.S_ISREG(value.st_mode):
                    used += value.st_size
                    continue
                require(not stat.S_ISLNK(value.st_mode), 'symlink in objects directory')
                if not stat.S_ISDIR(value.st_mode):
                    continue
                shard_fd = os.open(shard, DIRECTORY, dir_fd=objects)
                try:
                    _owned_directory(shard_fd, 'cache shard')
                    for name in os.listdir(shard_fd):
                        seen += 1
                        require(seen <= MAX_SCAN_ENTRIES, 'cache scan limit exceeded')
                        value = os.stat(name, dir_fd=shard_fd, follow_symlinks=False)
                        if stat.S_ISREG(value.st_mode):
                            used += value.st_size
                finally:
                    os.close(shard_fd)
        except (OSError, StoreError):
            self.status = 'disabled'
            return
        finally:
            os.close(objects)
        self.bytes_used = used
        if used >= self.quota_bytes:
            self.status = 'full'

    def _shard(self, key_sha, create):
        """Return a pinned shard fd, or None when absent and create is false."""
        parent = self._fd
        opened = []
        try:
            for name in ('objects', key_sha[:2]):
                if create:
                    try:
                        os.mkdir(name, mode=0o700, dir_fd=parent)
                    except FileExistsError:
                        pass
                try:
                    fd = os.open(name, DIRECTORY, dir_fd=parent)
                except FileNotFoundError:
                    if create:
                        raise
                    return None
                opened.append(fd)
                _owned_directory(fd, 'cache directory')
                parent = fd
            return opened.pop()
        finally:
            for fd in opened:
                os.close(fd)

    def _read(self, shard, key_sha, material):
        """Return ('hit', fragment, sha) | ('miss', None, None) | ('corrupt', None, reason)."""
        try:
            fd = os.open(f'{key_sha}.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                         | os.O_CLOEXEC, dir_fd=shard)
        except FileNotFoundError:
            return 'miss', None, None
        except OSError as error:
            if error.errno == errno.ELOOP:
                return 'corrupt', None, 'entry is a symlink'
            return 'corrupt', None, f'unreadable entry: {error.strerror or error}'
        limit = _max_entry(material)
        with os.fdopen(fd, 'rb') as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                return 'corrupt', None, 'entry is not a regular file'
            if before.st_size > limit:
                return 'corrupt', None, 'entry too large'
            raw = handle.read(limit + 1)
            after = os.fstat(handle.fileno())
        if len(raw) > limit or (before.st_size, before.st_mtime_ns) != (
                after.st_size, after.st_mtime_ns):
            return 'corrupt', None, 'entry changed or grew during read'
        try:
            entry = strict_json(raw)
            closed(entry, ENTRY_FIELDS, 'cache entry')
            require(entry['schema'] == ENTRY_SCHEMA, 'unsupported cache entry schema')
            require(isinstance(entry['key'], dict)
                    and canonical(entry['key']) == canonical(material), 'entry key mismatch')
            require(entry['key_sha256'] == key_sha
                    and sha256(canonical(entry['key'])) == key_sha, 'entry key_sha256 mismatch')
            fragment = entry['fragment']
            require(isinstance(fragment, dict), 'invalid entry fragment')
            fragment_sha = sha256(canonical(fragment))
            require(entry['fragment_sha256'] == fragment_sha, 'entry fragment_sha256 mismatch')
            require(_matches(material, fragment), 'entry fragment does not match its key')
        except (StoreError, ValueError, RecursionError) as error:
            return 'corrupt', None, str(error) or 'invalid entry'
        return 'hit', fragment, fragment_sha

    def get(self, material):
        key_sha = key(material)
        try:
            shard = self._shard(key_sha, create=False)
        except (OSError, StoreError) as error:
            result = ('corrupt', None, f'unsafe cache directory: {error}')
        else:
            if shard is None:
                result = ('miss', None, None)
            else:
                try:
                    result = self._read(shard, key_sha, material)
                finally:
                    os.close(shard)
        self.counts[{'hit': 'hits', 'miss': 'misses', 'corrupt': 'corrupt'}[result[0]]] += 1
        return result

    def _existing(self, shard, key_sha, material, fragment_sha):
        self.counts['exists'] += 1
        status, _, found = self._read(shard, key_sha, material)
        return 'exists_verified' if status == 'hit' and found == fragment_sha else 'exists_conflict'

    def put(self, material, fragment):
        """Store once; return stored, exists_verified, exists_conflict, full, or error."""
        key(material)
        if self.status == 'disabled':
            return 'error'
        try:
            key_sha, fragment_sha, data = _entry(material, fragment)
        except (StoreError, TypeError, ValueError, RecursionError):
            return 'error'
        if len(data) > _max_entry(material):
            return 'error'
        final = f'{key_sha}.json'
        shard = None
        try:
            shard = self._shard(key_sha, create=False)
            if shard is not None:
                try:
                    os.stat(final, dir_fd=shard, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    return self._existing(shard, key_sha, material, fragment_sha)
            # The quota is checked before any directory is created.
            if self.bytes_used + len(data) > self.quota_bytes:
                self.counts['full'] += 1
                self.status = 'full'
                return 'full'
            if shard is None:
                shard = self._shard(key_sha, create=True)
            return self._publish(shard, final, key_sha, material, fragment_sha, data)
        except (OSError, StoreError):
            return 'error'
        finally:
            if shard is not None:
                os.close(shard)

    def _publish(self, shard, final, key_sha, material, fragment_sha, data):
        temp = f'.{key_sha}.{os.getpid()}.{secrets.token_hex(8)}.tmp'
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                         | os.O_CLOEXEC, 0o600, dir_fd=shard)
        except OSError:
            return 'error'
        handle = os.fdopen(fd, 'wb')
        created = os.fstat(fd)
        try:
            try:
                with handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.link(temp, final, src_dir_fd=shard, dst_dir_fd=shard,
                        follow_symlinks=False)
            except FileExistsError:
                return self._existing(shard, key_sha, material, fragment_sha)
            except OSError:
                return 'error'
            self.bytes_used += len(data)
            self.counts['stored'] += 1
            return 'stored'
        finally:
            # Remove only the temporary name this call created, then persist the shard.
            try:
                current = os.stat(temp, dir_fd=shard, follow_symlinks=False)
                if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                    os.unlink(temp, dir_fd=shard)
                os.fsync(shard)
            except OSError:
                pass

    def stats(self):
        return dict(self.counts, bytes_used=self.bytes_used,
                    quota_bytes=self.quota_bytes, status=self.status)
