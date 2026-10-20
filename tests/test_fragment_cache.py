"""Synthetic fragments only; each fixture owns and removes its scratch directory."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tooling'))
import fragment_cache as fc


@contextmanager
def workspace():
    # Under this checkout (or a caller-selected task root), never /tmp. The parent
    # is resolved so the cache root has no symlink ancestry; TemporaryDirectory
    # creates it 0700 and removes only its own children on every exit path.
    parent = os.environ.get('GRAPHIFY_PACK_TEST_ROOT', str(Path(__file__).resolve().parents[1]))
    with tempfile.TemporaryDirectory(prefix='fragment-cache-test-',
                                     dir=Path(parent).resolve()) as directory:
        os.chmod(directory, 0o700)
        yield Path(directory)


def material(path='pkg/a.py', content='1', policy='3'):
    return dict(schema=fc.KEY_SCHEMA, fragment_schema=fc.FRAGMENT_SCHEMA,
                family=dict(name='graphify-stdlib-structural', version='1'),
                adapter_sha256='a' * 64, runtime_identity_sha256='b' * 64,
                per_file_policy_sha256=policy * 64, path=path, content_sha256=content * 64)


def fragment(m, label='a'):
    return dict(schema=fc.FRAGMENT_SCHEMA, path=m['path'], content_sha256=m['content_sha256'],
                nodes=[dict(id='n1', label=label, line=1)], references=[])


def entry_path(root, m):
    k = fc.key(m)
    return root / 'objects' / k[:2] / f'{k}.json'


def shard_dir(root, m):
    # Explicit 0700 at each level; mkdir(parents=True) would apply the umask.
    shard = entry_path(root, m).parent
    for directory in (shard.parent, shard):
        directory.mkdir(mode=0o700, exist_ok=True)
        os.chmod(directory, 0o700)
    return shard


def snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes() if p.is_file() and not p.is_symlink() else None)
            for p in sorted(root.rglob('*'))}


class KeyTests(unittest.TestCase):
    def test_key_is_canonical_and_excludes_commit(self):
        m = material()
        expected = fc.sha256(json.dumps(m, sort_keys=True, separators=(',', ':'),
                                        ensure_ascii=True).encode())
        self.assertEqual(fc.key(m), expected)
        self.assertEqual(fc.key(dict(reversed(list(m.items())))), expected)
        for field, value in (('path', 'pkg/b.py'), ('content_sha256', '2' * 64),
                             ('per_file_policy_sha256', '4' * 64),
                             ('runtime_identity_sha256', 'c' * 64),
                             ('adapter_sha256', 'd' * 64),
                             ('family', dict(name='graphify-stdlib-structural', version='2'))):
            self.assertNotEqual(fc.key(dict(m, **{field: value})), expected, field)

    def test_closed_key_material(self):
        m = material()
        for bad in (dict(m, commit='e' * 40), {k: v for k, v in m.items() if k != 'path'},
                    dict(m, schema='other/v1'), dict(m, fragment_schema='other/v1'),
                    dict(m, family=dict(name='x', version='1', extra=1)),
                    dict(m, family=dict(name='x', version=1)),
                    dict(m, adapter_sha256='A' * 64), dict(m, path='../a.py'),
                    dict(m, path='/abs.py'), dict(m, path='a/./b.py'), 'not a dict'):
            with self.assertRaises(fc.CacheError):
                fc.key(bad)


class CacheTests(unittest.TestCase):
    def test_miss_store_hit_and_stats(self):
        with workspace() as root, fc.FragmentCache.open(str(root), 10**6) as cache:
            m = material()
            self.assertEqual(cache.get(m), ('miss', None, None))
            self.assertEqual(cache.put(m, fragment(m)), 'stored')
            status, value, sha = cache.get(m)
            self.assertEqual((status, value), ('hit', fragment(m)))
            self.assertEqual(sha, fc.sha256(fc.canonical(fragment(m))))
            path = entry_path(root, m)
            entry = json.loads(path.read_bytes())
            self.assertEqual(set(entry), set(fc.ENTRY_FIELDS))
            self.assertEqual((entry['schema'], entry['key_sha256'], entry['key']),
                             (fc.ENTRY_SCHEMA, fc.key(m), m))
            for directory in (root / 'objects', path.parent):
                self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.stat().st_nlink, 1)
            self.assertEqual(sorted(p.name for p in path.parent.iterdir()), [path.name])
            stats = cache.stats()
            self.assertEqual(stats, dict(hits=1, misses=1, corrupt=0, stored=1, exists=0,
                                         full=0, bytes_used=path.stat().st_size,
                                         quota_bytes=10**6, status='ok'))
            self.assertEqual(cache.put(m, fragment(m)), 'exists_verified')
            self.assertEqual(cache.put(m, fragment(m, label='other')), 'exists_conflict')
            self.assertEqual(cache.get(m)[1], fragment(m))
            self.assertEqual(cache.stats()['exists'], 2)
            with fc.FragmentCache.open(str(root), 10**6) as reopened:
                self.assertEqual(reopened.stats()['bytes_used'], path.stat().st_size)

    def test_corrupt_entries_preserved_byte_identical(self):
        m = material()
        good = fragment(m)
        sha = fc.sha256(fc.canonical(good))
        base = dict(schema=fc.ENTRY_SCHEMA, key_sha256=fc.key(m), key=m,
                    fragment_sha256=sha, fragment=good)
        other = material(path='pkg/other.py')
        cases = {
            'garbage': b'not json',
            'duplicate key': b'{"schema":"a","schema":"b"}',
            'nonfinite': b'{"x":NaN}',
            'array': b'[]',
            'open schema': fc.canonical(dict(base, extra=1)),
            'wrong schema': fc.canonical(dict(base, schema='other/v1')),
            'key mismatch': fc.canonical(dict(base, key=other)),
            'key sha mismatch': fc.canonical(dict(base, key_sha256='0' * 64)),
            'fragment sha mismatch': fc.canonical(dict(base, fragment_sha256='0' * 64)),
            'fragment path mismatch': fc.canonical(dict(
                base, fragment=dict(good, path='x.py'),
                fragment_sha256=fc.sha256(fc.canonical(dict(good, path='x.py'))))),
            'oversized': b'{"x":"' + b'y' * fc.MAX_ENTRY + b'"}',
            'deep': b'[' * 200000 + b']' * 200000,
        }
        for label, data in cases.items():
            with self.subTest(label), workspace() as root:
                path = entry_path(root, m)
                shard_dir(root, m)
                path.write_bytes(data)
                with fc.FragmentCache.open(str(root), 10**9) as cache:
                    status, value, reason = cache.get(m)
                    self.assertEqual((status, value), ('corrupt', None))
                    self.assertIsInstance(reason, str)
                    self.assertEqual(cache.put(m, good), 'exists_conflict')
                    self.assertEqual((cache.stats()['corrupt'], cache.stats()['stored']), (1, 0))
                self.assertEqual(path.read_bytes(), data)

    def test_foreign_entries_preserved(self):
        with workspace() as root:
            m = material()
            shard = shard_dir(root, m)
            foreign = {shard / 'README': b'foreign', shard / '.x.tmp': b'partial',
                       root / 'objects' / 'note': b'note', root / 'other': b'other'}
            for path, data in foreign.items():
                path.write_bytes(data)
            with fc.FragmentCache.open(str(root), 10**6) as cache:
                self.assertEqual(cache.stats()['bytes_used'], sum(map(len, foreign.values())) - 5)
                self.assertEqual(cache.put(m, fragment(m)), 'stored')
                self.assertEqual(cache.get(m)[0], 'hit')
            for path, data in foreign.items():
                self.assertEqual(path.read_bytes(), data)

    def test_concurrent_create_race_never_replaces(self):
        for winner_label, expected in (('a', 'exists_verified'), ('winner', 'exists_conflict')):
            with self.subTest(expected), workspace() as root:
                m = material()
                real_link = os.link
                with fc.FragmentCache.open(str(root), 10**6) as cache, \
                        fc.FragmentCache.open(str(root), 10**6) as rival:
                    def racing_link(*args, **kwargs):
                        with patch.object(fc.os, 'link', real_link):
                            self.assertEqual(rival.put(m, fragment(m, winner_label)), 'stored')
                        return real_link(*args, **kwargs)
                    with patch.object(fc.os, 'link', racing_link):
                        self.assertEqual(cache.put(m, fragment(m)), expected)
                    self.assertEqual(cache.stats()['stored'], 0)
                    self.assertEqual(cache.get(m)[1], fragment(m, winner_label))
                path = entry_path(root, m)
                self.assertEqual(sorted(p.name for p in path.parent.iterdir()), [path.name])

    def test_quota_stops_without_deletion(self):
        with workspace() as root:
            first, second = material(), material(path='pkg/b.py')
            with fc.FragmentCache.open(str(root), 10**6) as cache:
                self.assertEqual(cache.put(first, fragment(first)), 'stored')
                size = cache.stats()['bytes_used']
            before = snapshot(root)
            with fc.FragmentCache.open(str(root), size + 10) as cache:
                self.assertEqual(cache.stats()['status'], 'ok')
                self.assertEqual(cache.put(second, fragment(second)), 'full')
                self.assertEqual(cache.get(second)[0], 'miss')
                self.assertEqual(cache.get(first)[0], 'hit')
                stats = cache.stats()
                self.assertEqual((stats['full'], stats['status'], stats['bytes_used']),
                                 (1, 'full', size))
            self.assertEqual(snapshot(root), before)
            with fc.FragmentCache.open(str(root), size) as cache:
                self.assertEqual(cache.stats()['status'], 'full')

    def test_scan_bound_disables_writes(self):
        with workspace() as root:
            ms = [material(path=f'pkg/{i}.py') for i in range(3)]
            with fc.FragmentCache.open(str(root), 10**6) as cache:
                for m in ms[:2]:
                    self.assertEqual(cache.put(m, fragment(m)), 'stored')
            before = snapshot(root)
            with patch.object(fc, 'MAX_SCAN_ENTRIES', 2), \
                    fc.FragmentCache.open(str(root), 10**6) as cache:
                self.assertEqual(cache.stats()['status'], 'disabled')
                self.assertEqual(cache.put(ms[2], fragment(ms[2])), 'error')
                self.assertEqual(cache.get(ms[0])[0], 'hit')
            self.assertEqual(snapshot(root), before)

    def test_unsafe_root_rejected(self):
        with workspace() as scratch:
            real = scratch / 'real'
            real.mkdir(mode=0o700)
            (scratch / 'link').symlink_to(real)
            (scratch / 'nested').mkdir(mode=0o700)
            (scratch / 'open').mkdir(mode=0o755)
            os.chmod(scratch / 'open', 0o755)
            (scratch / 'file').write_bytes(b'')
            (scratch / 'ancestor').symlink_to(scratch / 'nested')
            (scratch / 'nested' / 'cache').mkdir(mode=0o700)
            for root in (scratch / 'link', scratch / 'ancestor' / 'cache', scratch / 'open',
                         scratch / 'file', scratch / 'missing', 'relative/cache',
                         f'{scratch}/nested/../real'):
                with self.subTest(str(root)), self.assertRaises(fc.CacheError):
                    fc.FragmentCache.open(str(root), 10)
            for quota in (-1, True, 1.5, '1'):
                with self.assertRaises(fc.CacheError):
                    fc.FragmentCache.open(str(real), quota)
            with fc.FragmentCache.open(str(scratch / 'nested' / 'cache'), 10) as cache:
                self.assertEqual(cache.stats()['status'], 'ok')

    def test_symlinked_shard_rejected(self):
        with workspace() as root:
            m = material()
            shard = entry_path(root, m).parent
            outside = root / 'outside'
            outside.mkdir(mode=0o700)
            (root / 'objects').mkdir(mode=0o700)
            with fc.FragmentCache.open(str(root), 10**6) as cache:
                shard.symlink_to(outside)
                self.assertEqual(cache.get(m)[0], 'corrupt')
                self.assertEqual(cache.put(m, fragment(m)), 'error')
            self.assertEqual(list(outside.iterdir()), [])
            with fc.FragmentCache.open(str(root), 10**6) as cache:
                self.assertEqual(cache.stats()['status'], 'disabled')
            self.assertTrue(shard.is_symlink())

    def test_symlinked_entry_preserved(self):
        with workspace() as root:
            m = material()
            path = entry_path(root, m)
            shard_dir(root, m)
            target = root / 'target.json'
            target.write_bytes(b'{}')
            path.symlink_to(target)
            with fc.FragmentCache.open(str(root), 10**6) as cache:
                self.assertEqual(cache.get(m)[:2], ('corrupt', None))
                self.assertEqual(cache.put(m, fragment(m)), 'exists_conflict')
            self.assertTrue(path.is_symlink())
            self.assertEqual(target.read_bytes(), b'{}')

    def test_mismatched_fragment_is_not_stored(self):
        with workspace() as root, fc.FragmentCache.open(str(root), 10**6) as cache:
            m = material()
            for bad in (dict(fragment(m), path='x.py'), dict(fragment(m), content_sha256='0' * 64),
                        [], dict(fragment(m), value=float('nan')), dict(fragment(m), value=object())):
                self.assertEqual(cache.put(m, bad), 'error')
            self.assertEqual(cache.put(m, dict(fragment(m), blob='x' * fc.MAX_ENTRY)), 'error')
            self.assertFalse((root / 'objects').exists() and any((root / 'objects').rglob('*.json')))
            self.assertEqual(cache.stats()['stored'], 0)

    def test_write_failure_and_cancellation_remove_only_own_temporary(self):
        for error, outcome in ((OSError('disk failure'), 'error'),
                               (KeyboardInterrupt('cancelled'), KeyboardInterrupt)):
            with self.subTest(type(error).__name__), workspace() as root:
                m = material()
                shard = shard_dir(root, m)
                (shard / '.foreign.tmp').write_bytes(b'kept')
                with fc.FragmentCache.open(str(root), 10**6) as cache:
                    with patch.object(fc.os, 'fsync', side_effect=error):
                        if outcome == 'error':
                            self.assertEqual(cache.put(m, fragment(m)), 'error')
                        else:
                            with self.assertRaises(outcome):
                                cache.put(m, fragment(m))
                    self.assertEqual(cache.stats()['bytes_used'], 4)
                    self.assertEqual(cache.get(m)[0], 'miss')
                self.assertEqual(sorted(p.name for p in shard.iterdir()), ['.foreign.tmp'])
                self.assertEqual((shard / '.foreign.tmp').read_bytes(), b'kept')

    def test_scratch_cleanup_on_failure(self):
        with self.assertRaises(RuntimeError):
            with workspace() as root:
                with fc.FragmentCache.open(str(root), 10**6) as cache:
                    cache.put(material(), fragment(material()))
                raise RuntimeError('fixture failure')
        self.assertFalse(root.exists())


if __name__ == '__main__':
    unittest.main()
