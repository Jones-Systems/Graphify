"""Family 2 fragment cache; synthetic fragments only, each fixture owns its scratch."""
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tooling'))
import fragment_cache as fc

spec = importlib.util.spec_from_file_location(
    'structural_adapter_v2_drift', ROOT / 'tooling/refresh_adapter_structural.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

V1 = 'graphify-structural-fragment/v1'
V2 = 'graphify-structural-fragment/v2'
FAMILY_1 = dict(name='graphify-stdlib-structural', version='1')
FAMILY_2 = dict(name='graphify-stdlib-structural', version='2')
CAP_V1 = 1024**2
CAP_V2 = 8 * 1024**2 + 64 * 1024


@contextmanager
def workspace():
    # Same placement as test_fragment_cache: under this checkout or a caller-selected
    # root, never /tmp; TemporaryDirectory removes only its own tree on every exit path.
    parent = os.environ.get('GRAPHIFY_PACK_TEST_ROOT', str(ROOT))
    with tempfile.TemporaryDirectory(prefix='fragment-cache-v2-test-',
                                     dir=Path(parent).resolve()) as directory:
        os.chmod(directory, 0o700)
        yield Path(directory)


def material(schema=V2, family=None, path='pkg/a.py', content='1'):
    return dict(schema='graphify-fragment-key/v1', fragment_schema=schema,
                family=dict(family or (FAMILY_2 if schema == V2 else FAMILY_1)),
                adapter_sha256='a' * 64, runtime_identity_sha256='b' * 64,
                per_file_policy_sha256='3' * 64, path=path, content_sha256=content * 64)


def fragment(m, schema=None, **extra):
    return dict(dict(schema=schema or m['fragment_schema'], path=m['path'],
                     content_sha256=m['content_sha256'], nodes=[], references=[]), **extra)


def entry_bytes(m, f):
    return fc.canonical(dict(schema='graphify-fragment-cache-entry/v1', key_sha256=fc.key(m),
                             key=m, fragment_sha256=fc.sha256(fc.canonical(f)),
                             fragment=f)) + b'\n'


def sized(m, size):
    """Return a fragment whose encoded entry is exactly size bytes."""
    base = len(entry_bytes(m, fragment(m, blob='')))
    f = fragment(m, blob='x' * (size - base))
    assert len(entry_bytes(m, f)) == size
    return f


def entry_path(root, m):
    k = fc.key(m)
    return root / 'objects' / k[:2] / f'{k}.json'


def plant(root, m, data):
    path = entry_path(root, m)
    for directory in (path.parent.parent, path.parent):
        directory.mkdir(mode=0o700, exist_ok=True)
        os.chmod(directory, 0o700)
    path.write_bytes(data)
    return path


def files(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob('*') if not p.is_dir())


class MaterialTests(unittest.TestCase):
    def test_v2_requires_exact_family(self):
        self.assertEqual(len(fc.key(material())), 64)
        self.assertNotEqual(fc.key(material()), fc.key(material(V1, FAMILY_2)))
        for family in (FAMILY_1, dict(FAMILY_2, name='other'), dict(FAMILY_2, version='3'),
                       dict(name='graphify-stdlib-structural', version=2)):
            with self.subTest(family), self.assertRaises(fc.CacheError):
                fc.key(material(family=family))
        for schema in ('graphify-structural-fragment/v3', V2 + ' ', 'other/v2'):
            with self.subTest(schema), self.assertRaises(fc.CacheError):
                fc.key(material(schema=schema))

    def test_v1_pairing_unchanged(self):
        # v1 keys still accept any bounded family, including family 2.
        for family in (FAMILY_1, FAMILY_2, dict(name='x', version='9')):
            self.assertEqual(len(fc.key(material(V1, family))), 64)


class V2CacheTests(unittest.TestCase):
    def test_canonical_round_trip_and_existing_verified(self):
        raw = b'unsupported'
        f = adapter.document_v2('pkg/a.txt', raw, 'unknown', 'unsupported')
        adapter.check_fragment_v2(f, 'pkg/a.txt', adapter.digest(raw))
        m = dict(material(path='pkg/a.txt'), content_sha256=adapter.digest(raw))
        with workspace() as root, fc.FragmentCache.open(str(root), 10**7) as cache:
            self.assertEqual(cache.get(m), ('miss', None, None))
            self.assertEqual(cache.put(m, f), 'stored')
            status, value, sha = cache.get(m)
            self.assertEqual(status, 'hit')
            self.assertEqual(fc.canonical(value), fc.canonical(f))
            self.assertEqual(adapter.encoded(value), adapter.encoded(f))
            self.assertEqual(sha, fc.sha256(fc.canonical(f)))
            self.assertEqual(entry_path(root, m).read_bytes(), entry_bytes(m, f))
            self.assertEqual(cache.put(m, f), 'exists_verified')
            self.assertEqual(cache.stats()['exists'], 1)

    def test_mixed_v1_v2_root_scans_and_accounts_both(self):
        one, two = material(V1), material()
        with workspace() as root:
            with fc.FragmentCache.open(str(root), 10**7) as cache:
                self.assertEqual(cache.put(one, fragment(one)), 'stored')
                self.assertEqual(cache.put(two, fragment(two)), 'stored')
                used = cache.stats()['bytes_used']
            sizes = sum(entry_path(root, m).stat().st_size for m in (one, two))
            self.assertEqual(used, sizes)
            with fc.FragmentCache.open(str(root), 10**7) as cache:
                self.assertEqual(cache.stats()['bytes_used'], sizes)
                self.assertEqual(cache.get(one)[:2], ('hit', fragment(one)))
                self.assertEqual(cache.get(two)[:2], ('hit', fragment(two)))

    def test_schema_confusion_refused_and_preserved(self):
        two, one = material(), material(V1)
        with workspace() as root, fc.FragmentCache.open(str(root), 10**7) as cache:
            # A v2 key never stores a v1 fragment.
            self.assertEqual(cache.put(two, fragment(two, schema=V1)), 'error')
            self.assertEqual(cache.put(two, {k: v for k, v in fragment(two).items()
                                             if k != 'schema'}), 'error')
            self.assertEqual(files(root), [])
        cases = (
            ('v2 key, stored v1 fragment', two, entry_bytes(two, fragment(two, schema=V1))),
            ('v2 key, stored v1 entry', two, entry_bytes(one, fragment(one))),
            ('v1 key, stored v2 entry', one, entry_bytes(two, fragment(two))),
        )
        for label, m, data in cases:
            with self.subTest(label), workspace() as root:
                path = plant(root, m, data)
                with fc.FragmentCache.open(str(root), 10**7) as cache:
                    status, value, reason = cache.get(m)
                    self.assertEqual((status, value), ('corrupt', None))
                    self.assertIsInstance(reason, str)
                    self.assertEqual(cache.put(m, fragment(m)), 'exists_conflict')
                    self.assertEqual(cache.stats()['stored'], 0)
                self.assertEqual(path.read_bytes(), data)
                self.assertEqual(files(root), [str(path.relative_to(root))])

    def test_cap_is_chosen_by_fragment_schema(self):
        m = material()
        with workspace() as root:
            with fc.FragmentCache.open(str(root), 10**8) as cache:
                self.assertEqual(cache.put(m, sized(m, CAP_V2 + 1)), 'error')
                self.assertEqual(files(root), [])
                self.assertEqual(cache.stats()['bytes_used'], 0)
                at_cap = sized(m, CAP_V2)
                self.assertEqual(cache.put(m, at_cap), 'stored')
                self.assertEqual(entry_path(root, m).stat().st_size, CAP_V2)
                self.assertEqual(cache.stats()['bytes_used'], CAP_V2)
            self.assertEqual(files(root), [str(entry_path(root, m).relative_to(root))])
            with fc.FragmentCache.open(str(root), 10**8) as cache:
                status, value, _ = cache.get(m)
                self.assertEqual(status, 'hit')
                self.assertEqual(fc.canonical(value), fc.canonical(at_cap))
        with workspace() as root:
            path = plant(root, m, entry_bytes(m, sized(m, CAP_V2 + 1)))
            with fc.FragmentCache.open(str(root), 10**8) as cache:
                self.assertEqual(cache.get(m), ('corrupt', None, 'entry too large'))
            self.assertEqual(path.stat().st_size, CAP_V2 + 1)
        # v1 keeps its 1 MiB cap for put and read, even below the v2 cap.
        one = material(V1)
        with workspace() as root:
            with fc.FragmentCache.open(str(root), 10**8) as cache:
                self.assertEqual(cache.put(one, sized(one, CAP_V1)), 'stored')
            other = material(V1, path='pkg/b.py')
            with fc.FragmentCache.open(str(root), 10**8) as cache:
                self.assertEqual(cache.put(other, sized(other, CAP_V1 + 1)), 'error')
                self.assertEqual(cache.get(one)[0], 'hit')
            path = plant(root, other, entry_bytes(other, sized(other, 2 * CAP_V1)))
            with fc.FragmentCache.open(str(root), 10**8) as cache:
                self.assertEqual(cache.get(other), ('corrupt', None, 'entry too large'))
            self.assertEqual(path.stat().st_size, 2 * CAP_V1)

    def test_quota_full_falls_back_and_accounts_large_entries(self):
        ms = [material(path=f'pkg/{i}.py') for i in range(3)]
        size = 2 * 1024**2
        with workspace() as root:
            with fc.FragmentCache.open(str(root), 2 * size + 10) as cache:
                for m in ms[:2]:
                    self.assertEqual(cache.put(m, sized(m, size)), 'stored')
                self.assertEqual(cache.stats()['bytes_used'], 2 * size)
                before = files(root)
                self.assertEqual(cache.put(ms[2], sized(ms[2], size)), 'full')
                self.assertEqual(cache.get(ms[2]), ('miss', None, None))
                self.assertEqual(cache.get(ms[0])[0], 'hit')
                stats = cache.stats()
                self.assertEqual((stats['full'], stats['status'], stats['bytes_used']),
                                 (1, 'full', 2 * size))
            self.assertEqual(files(root), before)
            with fc.FragmentCache.open(str(root), 2 * size) as cache:
                self.assertEqual(cache.stats()['bytes_used'], 2 * size)
                self.assertEqual(cache.stats()['status'], 'full')

    def test_corrupt_v2_entries_preserved(self):
        m = material()
        good = entry_bytes(m, fragment(m, nodes=[dict(id='n1', label='a')]))
        cases = dict(truncated=good[:len(good) // 2],
                     edited=good.replace(b'"label":"a"', b'"label":"b"'))
        for label, data in cases.items():
            with self.subTest(label), workspace() as root:
                self.assertNotEqual(data, good)
                path = plant(root, m, data)
                with fc.FragmentCache.open(str(root), 10**7) as cache:
                    status, value, reason = cache.get(m)
                    self.assertEqual((status, value), ('corrupt', None))
                    self.assertIsInstance(reason, str)
                    self.assertEqual(cache.put(m, fragment(m)), 'exists_conflict')
                    self.assertEqual((cache.stats()['corrupt'], cache.stats()['stored']), (1, 0))
                self.assertEqual(path.read_bytes(), data)


class DriftTests(unittest.TestCase):
    def test_constants_equal_adapter(self):
        self.assertEqual(fc.FRAGMENT_SCHEMA, adapter.FRAGMENT)
        self.assertEqual(fc.FRAGMENT_SCHEMA_V2, adapter.FRAGMENT_V2)
        self.assertEqual(fc.FAMILY_V2, dict(name=adapter.NAME, version=adapter.VERSION_V2))
        self.assertEqual(fc.MAX_FRAGMENT_BYTES_V2, adapter.FRAGMENT_BYTES)
        self.assertEqual(fc.MAX_ENTRY_V2, adapter.FRAGMENT_BYTES + 64 * 1024)
        self.assertEqual(fc.MAX_ENTRY, CAP_V1)
        self.assertEqual((V1, V2, FAMILY_2, CAP_V2), (fc.FRAGMENT_SCHEMA, fc.FRAGMENT_SCHEMA_V2,
                                                     fc.FAMILY_V2, fc.MAX_ENTRY_V2))


if __name__ == '__main__':
    unittest.main()
