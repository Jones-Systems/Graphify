"""Synthetic adapters/modules only; fixture contexts own all scratch and children."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import types
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tooling/runtime_identity.py'
sys.path[:0] = [str(ROOT / 'tooling')]
import runtime_identity as ri

PYTHON = str(Path(sys.executable).resolve())
DEP = b'def summarize(path, raw):\n    return {"path": path, "bytes": len(raw)}\n'
ADAPTER = '''import sys
sys.path.insert(0, {lib!r})
LIMITS = dict(file_bytes=64, input_bytes=128, output_bytes=256, seconds=1)


def fragment(path, raw, limits):
    import probe_dep  # lazy: only fragment() reaches this module
{extra}    return probe_dep.summarize(path, raw)


if __name__ == '__main__':
    raise SystemExit('main must not run during the probe')
'''


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@contextmanager
def scratch():
    parent = os.environ.get('GRAPHIFY_REFRESH_TEST_ROOT', str(ROOT))
    def cancel(signum, frame):
        raise KeyboardInterrupt('synthetic fixture cancelled')
    previous = signal.signal(signal.SIGTERM, cancel)
    try:
        with tempfile.TemporaryDirectory(prefix='.runtime-identity-test-', dir=parent) as name:
            yield Path(name).resolve()
    finally:
        signal.signal(signal.SIGTERM, previous)


def fixture(root, extra='', dep=DEP, source=None):
    lib = root / 'lib'
    lib.mkdir(exist_ok=True)
    (lib / 'probe_dep.py').write_bytes(dep)
    adapter = root / 'adapter.py'
    adapter.write_text(source if source is not None else ADAPTER.format(lib=str(lib), extra=extra))
    return str(adapter), sha256(adapter)


def tree(root):
    return {str(p.relative_to(root)): (p.is_dir(), p.stat().st_size, p.stat().st_mtime_ns)
            for p in sorted(root.rglob('*'))}


class ProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.python_sha = sha256(PYTHON)

    def identify(self, adapter, adapter_sha, **kwargs):
        return ri.identify(PYTHON, self.python_sha, adapter, adapter_sha, **kwargs)

    def assertUnidentified(self, result, reason):
        self.assertEqual(sorted(result), sorted(ri.FIELDS))
        self.assertEqual((result['status'], result['identity_sha256']), ('unidentified', None))
        self.assertIn(reason, result['reason'])

    def test_stable_identity_across_two_probes(self):
        with scratch() as root:
            adapter, adapter_sha = fixture(root)
            first = self.identify(adapter, adapter_sha)
            second = self.identify(adapter, adapter_sha)
        self.assertEqual(first['status'], 'identified', first['reason'])
        self.assertEqual(first, second)
        self.assertEqual(first['executable']['sha256'], self.python_sha)
        self.assertEqual(first['identity_sha256'], ri.seal(first)['identity_sha256'])
        modules = {m['name']: m for m in first['modules']}
        self.assertEqual(modules['probe_dep'], dict(name='probe_dep', origin='file',
                                                    path=str(root / 'lib/probe_dep.py'),
                                                    sha256=hashlib.sha256(DEP).hexdigest()))
        self.assertEqual(modules['sys']['origin'], 'builtin')
        self.assertNotIn(ri.ADAPTER_MODULE, modules)
        self.assertNotIn('__main__', modules)
        self.assertIn(first['executable']['path'], [m['path'] for m in first['mapped_objects']])
        self.assertEqual((first['flags']['isolated'], first['flags']['dont_write_bytecode']), (1, 1))

    def test_identity_changes_with_imported_module_bytes(self):
        with scratch() as root:
            adapter, adapter_sha = fixture(root)
            before = self.identify(adapter, adapter_sha)
            fixture(root, dep=DEP + b'CHANGED = True\n')
            after = self.identify(adapter, adapter_sha)
        self.assertEqual((before['status'], after['status']), ('identified', 'identified'))
        self.assertNotEqual(before['identity_sha256'], after['identity_sha256'])
        dep = lambda doc: next(m for m in doc['modules'] if m['name'] == 'probe_dep')
        self.assertNotEqual(dep(before)['sha256'], dep(after)['sha256'])

    def test_missing_fragment_hook_is_unidentified(self):
        with scratch() as root:
            adapter, adapter_sha = fixture(root, source='LIMITS = {}\n')
            self.assertUnidentified(self.identify(adapter, adapter_sha), 'no fragment hook')

    def test_failing_fragment_hook_is_unidentified(self):
        with scratch() as root:
            adapter, adapter_sha = fixture(root, extra="    raise RuntimeError('synthetic')\n")
            self.assertUnidentified(self.identify(adapter, adapter_sha),
                                    'fragment hook failed: RuntimeError')

    def test_unreadable_module_path_is_unidentified(self):
        with scratch() as root:
            missing = str(root / 'absent/probe_dep.py')
            adapter, adapter_sha = fixture(root, dep=DEP + f'__file__ = {missing!r}\n'.encode())
            self.assertUnidentified(self.identify(adapter, adapter_sha), 'unreadable object')

    def test_unreadable_mapped_path_is_unidentified(self):
        with scratch() as root:
            present = root / 'lib.so'
            present.write_bytes(b'synthetic mapping')
            maps = (f'7f00-7f10 r-xp 00000000 08:01 11 {present}\n'
                    f'7f10-7f20 r--p 00000000 08:01 12 {root}/data only\n'
                    '7f20-7f30 r-xp 00000000 00:00 0 [vdso]\n'
                    '7f30-7f40 rw-p 00000000 00:00 0\n'
                    f'7f40-7f50 r-xp 00001000 08:01 11 {present}\n')
            self.assertEqual(ri.mapped_paths(maps), [str(present)])
            with self.assertRaisesRegex(ri.Unidentified, 'deleted'):
                ri.mapped_paths(f'7f00-7f10 r-xp 00000000 08:01 11 {present} (deleted)\n')
            hasher = ri.Hasher()
            self.assertEqual(hasher(str(present)), hashlib.sha256(b'synthetic mapping').hexdigest())
            for path in (str(root / 'absent.so'), str(root)):
                with self.assertRaises(ri.Unidentified):
                    hasher(path)
        with self.assertRaisesRegex(ri.Unidentified, 'malformed'):
            ri.mapped_paths('garbage\n')

    def test_module_origin_classification(self):
        frozen = types.SimpleNamespace(__spec__=types.SimpleNamespace(origin='frozen', loader=None),
                                       __file__='/nonexistent/frozen_source.py')
        builtin = types.SimpleNamespace(__spec__=types.SimpleNamespace(origin='built-in',
                                                                       loader=None))
        self.assertEqual(ri.module_records({'f': frozen, 'b': builtin, 'gone': None,
                                            '__main__': object()}, ri.Hasher()),
                         [dict(name='b', origin='builtin', path=None, sha256=None),
                          dict(name='f', origin='frozen', path=None, sha256=None)])
        namespace = types.SimpleNamespace(__spec__=types.SimpleNamespace(origin=None, loader=None))
        with self.assertRaisesRegex(ri.Unidentified, 'unsupported module origin'):
            ri.module_records({'ns': namespace}, ri.Hasher())

    def test_no_writes_and_no_bytecode(self):
        pycache = ROOT / 'tooling/__pycache__'
        existed = pycache.exists()
        with scratch() as root:
            adapter, adapter_sha = fixture(root)
            before = tree(root)
            result = self.identify(adapter, adapter_sha)
            self.assertEqual(result['status'], 'identified', result['reason'])
            self.assertEqual(tree(root), before)
            self.assertFalse(any(p.name == '__pycache__' for p in root.rglob('*')))
        self.assertEqual(pycache.exists(), existed)

    def test_adapter_stdout_cannot_corrupt_identity(self):
        with scratch() as root:
            adapter, adapter_sha = fixture(root, extra="    print('noise'); sys.stdout.flush()\n")
            self.assertEqual(self.identify(adapter, adapter_sha)['status'], 'identified')

    def test_pin_mismatch_symlink_and_bad_arguments(self):
        with scratch() as root:
            adapter, adapter_sha = fixture(root)
            self.assertUnidentified(self.identify(adapter, '0' * 64), 'checksum mismatch')
            self.assertUnidentified(ri.identify(PYTHON, '0' * 64, adapter, adapter_sha),
                                    'checksum mismatch')
            self.assertUnidentified(self.identify(adapter, adapter_sha, probe_sha256='0' * 64),
                                    'checksum mismatch')
            link = root / 'link.py'
            link.symlink_to(adapter)
            self.assertUnidentified(self.identify(str(link), adapter_sha), 'probe failed')
            self.assertUnidentified(self.identify('relative.py', adapter_sha), 'absolute')
            self.assertUnidentified(self.identify(adapter, adapter_sha, timeout=0), 'timeout')

    def test_timeout_is_unidentified(self):
        with scratch() as root:
            adapter, adapter_sha = fixture(root, extra='    import time; time.sleep(30)\n')
            self.assertUnidentified(self.identify(adapter, adapter_sha, timeout=1), 'probe timeout')

    def test_cli_direct_invocation(self):
        with scratch() as root:
            adapter, _ = fixture(root)
            command = [PYTHON, '-I', '-B', str(SCRIPT)]
            env = {'LC_ALL': 'C.UTF-8'}
            done = subprocess.run(command + ['--adapter', adapter], capture_output=True,
                                  timeout=60, cwd=root, env=env)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(ri.validate_identity(done.stdout, self.python_sha)['status'],
                             'identified')
            usage = subprocess.run(command + ['--adapter'], capture_output=True, timeout=60,
                                   cwd=root, env=env)
            self.assertEqual(usage.returncode, 0, usage.stderr)
            with self.assertRaisesRegex(ri.Unidentified, 'usage'):
                ri.validate_identity(usage.stdout)


class ValidationTests(unittest.TestCase):
    def document(self):
        return ri.seal(dict(
            schema=ri.SCHEMA, status='identified', reason=None, implementation='cpython',
            version='3.x synthetic', cache_tag='cpython-3x', hexversion=1,
            flags=dict(isolated=1, dont_write_bytecode=1, safe_path=True),
            filesystem_encoding='utf-8', executable=dict(path='/synthetic/python', sha256='a' * 64),
            modules=[dict(name='b', origin='builtin', path=None, sha256=None),
                     dict(name='m', origin='file', path='/synthetic/m.py', sha256='b' * 64)],
            mapped_objects=[dict(path='/synthetic/python', sha256='a' * 64)]))

    def raw(self, value):
        return json.dumps(value).encode()

    def test_accepts_sealed_document(self):
        doc = self.document()
        self.assertEqual(ri.validate_identity(self.raw(doc), 'a' * 64), doc)

    def test_rejects_tampering_and_malformed_documents(self):
        def mutated(change):
            doc = self.document()
            change(doc)
            return self.raw(doc)
        cases = {
            'digest mismatch': mutated(lambda d: d['modules'][1].update(sha256='c' * 64)),
            'not closed': mutated(lambda d: d.update(extra=1)),
            'run with -I -B': self.raw(ri.seal(dict(self.document(), flags=dict(isolated=0,
                                                                            dont_write_bytecode=1)))),
            'sorted and unique': self.raw(ri.seal(dict(self.document(),
                                                       modules=self.document()['modules'][::-1]))),
            'invalid module origin': self.raw(ri.seal(dict(self.document(), modules=[
                dict(name='x', origin='namespace', path=None, sha256=None)]))),
            'duplicate identity key': b'{"schema": 1, "schema": 2}',
            'non-finite': b'{"schema": NaN}',
            'invalid identity JSON': b'\xff',
            'output byte limit': b' ' * (ri.MAX_STDOUT + 1),
            'synthetic reason': self.raw(ri.unidentified('synthetic reason')),
            'malformed unidentified': self.raw(dict(ri.unidentified('x'), version='leak')),
        }
        for reason, raw in cases.items():
            with self.subTest(reason), self.assertRaisesRegex(ri.Unidentified, reason):
                ri.validate_identity(raw)
        with self.assertRaisesRegex(ri.Unidentified, 'differs from pinned'):
            ri.validate_identity(self.raw(self.document()), 'f' * 64)


if __name__ == '__main__':
    unittest.main()
