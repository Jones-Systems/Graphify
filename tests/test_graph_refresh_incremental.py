"""Synthetic Git-object incremental builds; fixture scratch owns every repository, store and cache."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
TOOLING = ROOT / 'tooling'
sys.path[:0] = [str(TOOLING), str(ROOT / 'tests')]
import fragment_cache
import graph_catalog as catalog
import graph_pack as packer
import graph_pull as puller
import graph_read as reader
import graph_refresh as refresh
import graph_refresh_incremental as inc
import runtime_identity

ADAPTER = TOOLING / 'refresh_adapter_structural.py'
PROBE = TOOLING / 'runtime_identity.py'
DRIVER = TOOLING / 'graph_refresh_incremental.py'
PYTHON = Path(sys.executable).resolve()
REPOSITORY = 'Fixture/Source'
GIT_LIMITATION = 'Git-object input; checkout cleanliness not observed.'

C1 = {'pkg/__init__.py': b'',
      'pkg/a.py': b'import pkg.b\nimport pkg.c\nclass Example:\n    def method(self):\n        pass\n',
      'pkg/b.py': b'def helper():\n    pass\n',
      'docs/guide.md': b'[a](../pkg/a.py)\n[c](../pkg/c.py)\n',
      'notes.txt': b'not admitted by default\n'}
C2 = {'pkg/b.py': b'def helper():\n    return 1\n', 'pkg/c.py': b'class C:\n    pass\n',
      'docs/guide.md': None}
C3 = {'pkg/c.py': None, 'pkg/d.py': C2['pkg/c.py'], 'pkg/b/__init__.py': b''}


def git(cwd, *args, check=True):
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_TERMINAL_PROMPT='0')
    done = subprocess.run(['git', '-C', str(cwd), '-c', 'core.hooksPath=/dev/null',
                           '-c', 'user.name=Synthetic', '-c', 'user.email=fixture@example.invalid',
                           '-c', 'commit.gpgsign=false', '-c', 'init.defaultBranch=main', *args],
                          env=env, capture_output=True, check=check, timeout=60)
    return done.stdout.decode().strip()


def select(path):
    return dict(path=str(path), sha256=reader.digest(Path(path).read_bytes()))


@contextmanager
def scratch():
    parent = os.environ.get('GRAPHIFY_REFRESH_TEST_ROOT', str(ROOT))
    def cancel(signum, frame):
        raise KeyboardInterrupt('synthetic fixture cancelled')
    previous = signal.signal(signal.SIGTERM, cancel)
    try:
        with tempfile.TemporaryDirectory(prefix='.incremental-test-', dir=parent) as name:
            yield Path(name).resolve()
    finally:
        signal.signal(signal.SIGTERM, previous)


class Fixture:
    """A work repository pushed into an owned bare mirror, plus build/state roots."""

    def __init__(self, root):
        self.root = root
        self.work, self.mirror = root / 'work', root / 'mirror.git'
        self.work.mkdir()
        git(self.work, 'init', '-q')
        git(root, 'init', '-q', '--bare', str(self.mirror))
        for name in ('builds', 'manifests'):
            (root / name).mkdir()
        self.lock = root / 'refresh.lock'
        self.lock.touch()
        self.counter = 0
        self.state = self.new_state()

    def next(self):
        self.counter += 1
        return self.counter

    def new_state(self):
        path = self.root / f'state-{self.next()}'
        path.mkdir(mode=0o700)
        path.chmod(0o700)
        return path

    def destination(self):
        return self.root / 'builds' / f'run-{self.next()}'

    def write(self, changes):
        for name, raw in changes.items():
            path = self.work / name
            if raw is None:
                path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)

    def publish(self):
        git(self.work, 'commit', '-q', '--allow-empty', '-m', 'synthetic')
        git(self.work, 'push', '-q', str(self.mirror), '+HEAD:refs/heads/main')
        return git(self.work, 'rev-parse', 'HEAD')

    def commit(self, changes, add=None):
        self.write(changes)
        git(self.work, 'add', '-A') if add is None else git(self.work, 'add', '--', *add)
        return self.publish()

    def manifest(self, commit, previous=None, state=None, **changes):
        m = dict(schema=inc.SCHEMA, repository=REPOSITORY, mirror_git_dir=str(self.mirror),
                 commit=commit, target=dict(oid=None, observed_at=None, method=None),
                 admission_policy=dict(schema=inc.POLICY_SCHEMA, include=['*.py', '*.md'], deny=[],
                                       max_files=256, max_file_bytes=4 * 1024**2,
                                       max_total_bytes=16 * 1024**2),
                 extractor=dict(protocol='python-json/v2', name='graphify-stdlib-structural',
                                version='1', executable=select(PYTHON), script=select(ADAPTER)),
                 runtime_probe=select(PROBE), state_root=str(state or self.state),
                 previous_state=previous, destination=str(self.destination()), lock=str(self.lock),
                 cache_quota_bytes=64 * 1024**2, limits=dict(refresh.LIMITS, seconds=60))
        m.update(changes)
        return m

    def save(self, manifest):
        path = self.root / 'manifests' / f'{self.next()}.json'
        raw = packer.encoded(manifest)
        path.write_bytes(raw)
        return path, reader.digest(raw)

    def run(self, manifest):
        return inc.incremental(*self.save(manifest))

    def cold(self, commit, **changes):
        """An uncached, previous-free build of the same commit and selection."""
        return self.run(self.manifest(commit, state=self.new_state(), **changes))

    def entries(self, state=None):
        objects = Path(state or self.state) / inc.CACHE_DIRECTORY / 'objects'
        return sorted(objects.glob('*/*.json'))


@contextmanager
def fixture():
    with scratch() as root:
        yield Fixture(root)


def evidence(result):
    base = Path(result['destination']) / 'evidence'
    return {n: json.loads((base / f'{n}.json').read_bytes()) for n in ('graph', 'validation', 'inventory')}


def normalized(result):
    documents = evidence(result)
    for name in ('graph', 'validation'):
        documents[name].pop('refresh_request_sha256')
    return documents


def state(result):
    return json.loads(Path(result['build_state']['path']).read_bytes())


def counts(**values):
    base = dict.fromkeys(inc.COUNTS, 0)
    base.update(values)
    return base


def labels(result):
    nodes = {n['id']: n['label'] for n in evidence(result)['graph']['nodes']}
    return {(nodes[e['source']], e['type'], nodes[e['target']])
            for e in evidence(result)['graph']['links']}


def unresolved(result):
    return {(u['source_file'], u['target']) for u in evidence(result)['validation']['unresolved_references']}


def listing(path):
    return sorted(str(p.relative_to(path)) for p in Path(path).rglob('*'))


class IncrementalTests(unittest.TestCase):
    def assert_cold_equal(self, fx, result, commit, **changes):
        cold = fx.cold(commit, **changes)
        self.assertEqual(cold['status'], 'completed', cold)
        self.assertEqual(normalized(result), normalized(cold))
        self.assertEqual(result['counts']['admitted'], cold['counts']['extracted'])
        return cold

    def test_cold_and_incremental_equivalence_with_exact_counts(self):
        with fixture() as fx:
            c1 = fx.commit(C1)
            first = fx.run(fx.manifest(c1))
            self.assertEqual(first['status'], 'completed', first)
            self.assertEqual(first['cache_status'], 'ok')
            self.assertEqual(first['counts'], counts(admitted=4, added=4, extracted=4, cache_misses=4))
            self.assertEqual(state(first)['counts'], first['counts'])
            self.assertIn(('pkg/a.py', 'pkg.c'), unresolved(first))
            self.assertIn(('pkg/a.py', 'imports', 'pkg/b.py'), labels(first))
            self.assert_cold_equal(fx, first, c1)
            self.assertEqual(len(fx.entries()), 4)

            c2 = fx.commit(C2)
            second = fx.run(fx.manifest(c2, previous=first['build_state']))
            self.assertEqual(second['status'], 'completed', second)
            self.assertEqual(second['counts'], counts(admitted=4, added=1, modified=1, deleted=1,
                                                      reused=2, extracted=2, cache_hits=2, cache_misses=2))
            # The added target resolves the previously unresolved import.
            self.assertIn(('pkg/a.py', 'imports', 'pkg/c.py'), labels(second))
            self.assertNotIn(('pkg/a.py', 'pkg.c'), unresolved(second))
            self.assert_cold_equal(fx, second, c2)

            c3 = fx.commit(C3)
            third = fx.run(fx.manifest(c3, previous=second['build_state']))
            self.assertEqual(third['status'], 'completed', third)
            # A rename is delete+add; stem.py beside stem/__init__.py is ambiguous.
            self.assertEqual(third['counts'], counts(admitted=5, added=2, deleted=1, reused=3,
                                                     extracted=2, cache_hits=3, cache_misses=2))
            self.assertIn(('pkg/a.py', 'pkg.b'), unresolved(third))
            self.assertIn(('pkg/a.py', 'pkg.c'), unresolved(third))
            self.assertNotIn(('pkg/a.py', 'imports', 'pkg/b.py'), labels(third))
            self.assert_cold_equal(fx, third, c3)
            files = {f['path']: f for f in state(third)['files']}
            self.assertEqual(sorted(files), ['pkg/__init__.py', 'pkg/a.py', 'pkg/b.py',
                                             'pkg/b/__init__.py', 'pkg/d.py'])
            self.assertTrue(all(f['key_sha256'] for f in files.values()))

    def test_same_commit_is_unchanged_without_adapter_or_output(self):
        with fixture() as fx:
            c1 = fx.commit(C1)
            first = fx.run(fx.manifest(c1))
            manifest = fx.manifest(c1, previous=first['build_state'])
            with patch.object(refresh, 'run_adapter') as adapter:
                again = fx.run(manifest)
            adapter.assert_not_called()
            self.assertEqual(again['status'], 'unchanged', again)
            self.assertEqual(again['package'], first['package'])
            self.assertEqual(again['build_state'], first['build_state'])
            self.assertEqual(again['attempts'], 0)
            self.assertFalse(Path(manifest['destination']).exists())
            self.assertFalse(again['retained'])

    def test_new_commit_with_identical_admission_reuses_all_and_repacks(self):
        with fixture() as fx:
            first = fx.run(fx.manifest(fx.commit(C1)))
            c2 = fx.commit({'notes.txt': b'changed outside admission\n'})
            second = fx.run(fx.manifest(c2, previous=first['build_state']))
            self.assertEqual(second['status'], 'completed', second)
            self.assertEqual(second['counts'], counts(admitted=4, reused=4, cache_hits=4))
            self.assertNotEqual(second['package'], first['package'])
            self.assertEqual(evidence(second)['graph']['built_at_commit'], c2)
            self.assert_cold_equal(fx, second, c2)

    def test_deny_and_policy_changes_reassemble_the_admitted_set(self):
        with fixture() as fx:
            c1 = fx.commit(C1)
            first = fx.run(fx.manifest(c1))
            policy = dict(fx.manifest(c1)['admission_policy'], deny=['pkg/b.py'])
            denied = fx.run(fx.manifest(c1, previous=first['build_state'], admission_policy=policy))
            self.assertEqual(denied['status'], 'completed', denied)
            self.assertEqual(denied['counts'], counts(admitted=3, deleted=1, reused=3, cache_hits=3))
            self.assertIn(('pkg/a.py', 'pkg.b'), unresolved(denied))
            self.assert_cold_equal(fx, denied, c1, admission_policy=policy)
            widened = dict(policy, include=['*.py', '*.md', '*.txt'])
            more = fx.run(fx.manifest(c1, previous=denied['build_state'], admission_policy=widened))
            self.assertEqual(more['counts'], counts(admitted=4, added=1, reused=3, extracted=1,
                                                    cache_hits=3, cache_misses=1))
            coverage = {f['path']: f['coverage'] for f in evidence(more)['inventory']['files']}
            self.assertEqual(coverage['notes.txt'], 'unknown')
            self.assert_cold_equal(fx, more, c1, admission_policy=widened)

    def test_runtime_and_adapter_changes_miss_the_cache(self):
        with fixture() as fx:
            c1 = fx.commit(C1)
            first = fx.run(fx.manifest(c1))
            original = runtime_identity.identify

            def changed(*args, **kwargs):
                return dict(original(*args, **kwargs), identity_sha256='f' * 64)

            with patch.object(runtime_identity, 'identify', changed):
                runtime = fx.run(fx.manifest(c1, previous=first['build_state']))
            self.assertEqual(runtime['status'], 'completed', runtime)
            self.assertEqual(runtime['counts'], counts(admitted=4, extracted=4, cache_misses=4))
            self.assert_cold_equal(fx, runtime, c1)

            variant = fx.root / 'variant' / ADAPTER.name
            variant.parent.mkdir()
            variant.write_bytes(ADAPTER.read_bytes() + b'\n# synthetic adapter variant\n')
            extractor = dict(fx.manifest(c1)['extractor'], script=select(variant))
            adapted = fx.run(fx.manifest(c1, previous=first['build_state'], extractor=extractor))
            self.assertEqual(adapted['status'], 'completed', adapted)
            self.assertEqual(adapted['counts'], counts(admitted=4, extracted=4, cache_misses=4))
            self.assertEqual(state(adapted)['adapter_sha256'], extractor['script']['sha256'])
            self.assertEqual(normalized(adapted), normalized(first))

    def test_unidentified_runtime_disables_cache_with_correct_graph(self):
        with fixture() as fx:
            c1 = fx.commit(C1)
            unknown = runtime_identity.unidentified('synthetic probe failure')
            with patch.object(runtime_identity, 'identify', return_value=unknown):
                first = fx.run(fx.manifest(c1))
                again = fx.run(fx.manifest(c1, previous=first['build_state']))
            for result in (first, again):
                self.assertEqual(result['status'], 'completed', result)
                self.assertEqual(result['cache_status'], 'cache_disabled:runtime_unidentified')
                self.assertEqual(result['runtime_identity']['identity_sha256'], None)
                self.assertEqual(result['counts']['extracted'], 4)
                self.assertEqual(result['counts']['cache_hits'] + result['counts']['cache_misses'], 0)
            self.assertEqual(state(first)['runtime_identity_sha256'], None)
            self.assertTrue(all(f['key_sha256'] is None for f in state(first)['files']))
            self.assertFalse((fx.state / inc.CACHE_DIRECTORY).exists())
            self.assert_cold_equal(fx, first, c1)

    def test_corrupt_full_and_unusable_cache_fall_back_uncached(self):
        with fixture() as fx:
            c1 = fx.commit(C1)
            first = fx.run(fx.manifest(c1))
            junk = fx.entries()[0]
            junk.write_bytes(b'not json\n')
            corrupt = fx.run(fx.manifest(c1))
            self.assertEqual(corrupt['status'], 'completed', corrupt)
            self.assertEqual(corrupt['cache_status'], 'degraded')
            self.assertEqual(corrupt['counts'], counts(admitted=4, added=4, reused=3, extracted=1,
                                                       cache_hits=3, cache_corrupt=1))
            self.assertEqual(corrupt['cache']['puts'], {'exists_conflict': 1})
            self.assertEqual(junk.read_bytes(), b'not json\n')
            self.assertEqual(normalized(corrupt), normalized(first))

            full = fx.run(fx.manifest(c1, state=fx.new_state(), cache_quota_bytes=0))
            self.assertEqual(full['status'], 'completed', full)
            self.assertEqual(full['cache_status'], 'full')
            self.assertEqual(full['counts'], counts(admitted=4, added=4, extracted=4, cache_misses=4,
                                                    cache_full=4))
            self.assertEqual(normalized(full), normalized(first))

            unusable = fx.new_state()
            (unusable / inc.CACHE_DIRECTORY).mkdir(mode=0o755)
            (unusable / inc.CACHE_DIRECTORY).chmod(0o755)
            fallback = fx.run(fx.manifest(c1, state=unusable))
            self.assertEqual(fallback['status'], 'completed', fallback)
            self.assertTrue(fallback['cache_status'].startswith('cache_unavailable'), fallback)
            self.assertEqual(fallback['counts']['extracted'], 4)
            self.assertEqual(normalized(fallback), normalized(first))

    def test_rejected_reuse_falls_back_once_to_uncached_extraction(self):
        with fixture() as fx:
            c1 = fx.commit(C1)
            first = fx.run(fx.manifest(c1))
            # Valid for the cache's own checks, invalid for the adapter's fragment contract.
            path = next(p for p in fx.entries()
                        if json.loads(p.read_bytes())['fragment']['path'] == 'pkg/b.py')
            entry = json.loads(path.read_bytes())
            entry['fragment'] = dict(entry['fragment'], extra='synthetic')
            entry['fragment_sha256'] = fragment_cache.sha256(fragment_cache.canonical(entry['fragment']))
            path.write_bytes(fragment_cache.canonical(entry) + b'\n')
            preserved = path.read_bytes()
            result = fx.run(fx.manifest(c1))
            self.assertEqual(result['status'], 'completed', result)
            self.assertEqual(result['attempts'], 2)
            self.assertEqual(result['cache_status'], 'reuse_rejected')
            self.assertEqual(result['counts'], counts(admitted=4, added=4, extracted=4, cache_hits=4))
            self.assertEqual(path.read_bytes(), preserved)
            self.assertEqual(normalized(result), normalized(first))
            attempts = set(listing(Path(result['destination']) / 'attempts'))
            self.assertTrue({'1/request.json', '2/request.json', '2/adapter-response.json'} <= attempts)
            self.assertNotIn('1/adapter-response.json', attempts)

    def test_git_attributes_symlinks_gitlinks_and_size_limits_in_bare_mirror(self):
        with fixture() as fx:
            fx.write({'ok.py': b'def ok():\n    pass\n', 'crlf.py': b'x = 1\n', 'filtered.py': b'y = 2\n',
                      'encoded.md': b'# plain\n', 'ident.py': b'# $Id$\n', 'auto.md': b'[ok](ok.py)\n',
                      'large.py': b'#' * 100 + b'\n'})
            os.symlink('ok.py', fx.work / 'link.py')
            git(fx.work, 'add', '-A')
            git(fx.work, 'update-index', '--add', '--cacheinfo', '160000,' + '1' * 40 + ',sub.py')
            fx.publish()
            # Attributes arrive separately so the fixture's own add never applies their conversions.
            commit = fx.commit({'.gitattributes': b'*.py text eol=lf\ncrlf.py eol=crlf\n'
                                b'filtered.py filter=synthetic\nencoded.md working-tree-encoding=UTF-16\n'
                                b'ident.py ident\nauto.md text=auto\n'}, add=['.gitattributes'])
            policy = dict(fx.manifest(commit)['admission_policy'], max_file_bytes=64)
            result = fx.run(fx.manifest(commit, admission_policy=policy))
            self.assertEqual(result['status'], 'completed', result)
            self.assertEqual(state(result)['unsupported'], [
                dict(path='crlf.py', reason='attribute:eol=crlf'),
                dict(path='encoded.md', reason='attribute:working-tree-encoding'),
                dict(path='filtered.py', reason='attribute:filter'),
                dict(path='ident.py', reason='attribute:ident'),
                dict(path='large.py', reason='file_byte_limit'),
                dict(path='link.py', reason='symlink'),
                dict(path='sub.py', reason='gitlink')])
            self.assertEqual(result['counts'], counts(admitted=2, added=2, extracted=2, unsupported=7,
                                                      cache_misses=2))
            self.assertEqual([f['path'] for f in evidence(result)['inventory']['files']], ['auto.md', 'ok.py'])
            self.assertIn(('auto.md', 'links_to', 'ok.py'), labels(result))

    def test_mirror_must_be_bare_and_commit_present(self):
        with fixture() as fx:
            c1 = fx.commit(C1)
            cases = {'non-bare': dict(mirror_git_dir=str(fx.work / '.git')),
                     'missing': dict(mirror_git_dir=str(fx.root / 'absent.git')),
                     'unknown-commit': dict()}
            expected = {'non-bare': 'failed', 'missing': 'deferred', 'unknown-commit': 'failed'}
            for name, change in cases.items():
                with self.subTest(case=name):
                    manifest = fx.manifest('1' * 40 if name == 'unknown-commit' else c1, **change)
                    result = fx.run(manifest)
                    self.assertEqual(result['status'], expected[name], result)
                    self.assertFalse(Path(manifest['destination']).exists())

    def test_target_relation_is_explicit(self):
        with fixture() as fx:
            c1 = fx.commit(C1)
            c2 = fx.commit(C2)
            for target, relation in ((None, 'unknown'), (c1, 'current'), (c2, 'behind'), ('1' * 40, 'unknown')):
                with self.subTest(relation=relation, target=target):
                    target_record = dict(oid=target, observed_at='2026-10-20T00:00:00Z' if target else None,
                                         method='ls-remote' if target else None)
                    result = fx.run(fx.manifest(c1, target=target_record))
                    self.assertEqual(result['status'], 'completed', result)
                    self.assertEqual(result['target_relation'], dict(relation=relation, **target_record))
                    self.assertEqual(state(result)['target_relation'], result['target_relation'])
                    source = json.loads((Path(result['destination']) / 'evidence/source.json').read_bytes())
                    self.assertTrue(any(x.startswith('Target relation: ' + relation)
                                        for x in source['limitations']))

    def test_pack_reader_pull_and_catalog_interoperate(self):
        with fixture() as fx:
            c1 = fx.commit(C1)
            result = fx.run(fx.manifest(c1))
            package_path = Path(result['package']['path'])
            raw, package = packer.selected_input(package_path, result['package']['sha256'], packer.MAX_INPUT)
            self.assertIsNone(package['qualification']['build_observation'])
            self.assertIn('build_observation', package['qualification']['missing_provenance'])
            candidate = package_path.parent
            loaded, sha = reader.load_catalog(candidate / 'download-catalog.json', package['catalog_sha256'])
            _, _, graph_sha, _ = reader.read_graph(candidate / 'download-catalog.json', loaded['archives'][0])
            self.assertEqual(graph_sha, state(result)['graph_sha256'])
            pulled = puller.pull(candidate / 'download-catalog.json', fx.root / 'pulled', [REPOSITORY], sha)
            self.assertEqual(pulled['status'], 'ok')
            assembled = catalog.assemble([(package_path, result['package']['sha256'])], fx.root / 'catalog')
            self.assertEqual((assembled['status'], assembled['repositories']), ('ok', [REPOSITORY]))
            source = json.loads((Path(result['destination']) / 'evidence/source.json').read_bytes())
            self.assertTrue(any('git_blob' in x for x in source['limitations']))
            self.assertIn(GIT_LIMITATION, evidence(result)['validation']['limitations'])

    def test_lock_contention_loss_and_foreign_entries(self):
        with fixture() as fx:
            c1 = fx.commit(C1)
            with self.subTest(case='contention'), open(fx.lock, 'rb') as held:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                manifest = fx.manifest(c1)
                result = fx.run(manifest)
                self.assertEqual((result['status'], result['reason']), ('deferred', 'lock contention'))
                self.assertFalse(Path(manifest['destination']).exists())
            original = refresh.run_adapter
            with self.subTest(case='lock loss'):
                lock = fx.root / 'loss.lock'
                lock.touch()

                def lose(*args):
                    response = original(*args)
                    lock.rename(fx.root / 'held.lock')
                    return response

                manifest = fx.manifest(c1, lock=str(lock))
                with patch.object(refresh, 'run_adapter', lose):
                    result = fx.run(manifest)
                self.assertEqual(result['status'], 'unknown', result)
                self.assertTrue(result['retained'])
                self.assertFalse((Path(manifest['destination']) / 'candidate').exists())
            with self.subTest(case='foreign transaction entry'):
                manifest = fx.manifest(c1)

                def foreign(*args):
                    response = original(*args)
                    (Path(manifest['destination']) / 'foreign').write_text('preserve')
                    return response

                with patch.object(refresh, 'run_adapter', foreign):
                    result = fx.run(manifest)
                self.assertEqual(result['status'], 'unknown', result)
                self.assertEqual((Path(manifest['destination']) / 'foreign').read_text(), 'preserve')
            with self.subTest(case='foreign candidate'):
                pack = packer.pack

                def racing(inputs, destination):
                    destination.mkdir()
                    (destination / 'foreign').write_text('preserve')
                    return pack(inputs, destination)

                manifest = fx.manifest(c1)
                with patch.object(packer, 'pack', racing):
                    result = fx.run(manifest)
                self.assertEqual(result['status'], 'unknown', result)
                self.assertEqual((Path(manifest['destination']) / 'candidate/foreign').read_text(), 'preserve')
            with self.subTest(case='destination collision'):
                manifest = fx.manifest(c1)
                Path(manifest['destination']).mkdir()
                (Path(manifest['destination']) / 'existing').write_text('preserve')
                result = fx.run(manifest)
                self.assertEqual(result['status'], 'deferred', result)
                self.assertEqual(listing(manifest['destination']), ['existing'])

    def test_manifest_and_previous_state_fail_closed(self):
        with fixture() as fx:
            c1 = fx.commit(C1)
            base = fx.manifest(c1)
            invalid = {'extra field': dict(base, extra=True),
                       'relative destination': dict(base, destination='builds/relative'),
                       'cache overlap': dict(base, destination=str(fx.state / inc.CACHE_DIRECTORY / 'x')),
                       'raised policy limit': dict(base, admission_policy=dict(base['admission_policy'],
                                                                               max_files=257)),
                       'previous name': dict(base, previous_state=dict(path=str(fx.root / 'state.json'),
                                                                       sha256='e' * 64))}
            for name, manifest in invalid.items():
                with self.subTest(case=name), self.assertRaises(ValueError):
                    fx.run(manifest)
            path, sha = fx.save(base)
            with self.assertRaises(ValueError):
                inc.incremental(path, 'f' * 64)
            self.assertEqual(listing(fx.root / 'builds'), [])
            v1 = fx.run(fx.manifest(c1, extractor=dict(base['extractor'], protocol='python-json/v1')))
            self.assertEqual(v1['status'], 'deferred', v1)
            probe = fx.root / 'probe' / PROBE.name
            probe.parent.mkdir()
            shutil.copyfile(PROBE, probe)
            moved = fx.run(fx.manifest(c1, runtime_probe=select(probe)))
            self.assertEqual(moved['status'], 'failed', moved)

            first = fx.run(fx.manifest(c1))
            tampered = state(first)
            for f in tampered['files']:
                if f['path'] == 'pkg/a.py':
                    f['sha256'] = 'e' * 64
            target = fx.root / 'tampered' / inc.STATE_NAME
            target.parent.mkdir()
            target.write_bytes(packer.encoded(tampered))
            c2 = fx.commit(C2)
            manifest = fx.manifest(c2, previous=select(target))
            result = fx.run(manifest)
            self.assertEqual(result['status'], 'failed', result)
            self.assertIn('previous build state blob digest mismatch', result['reason'])
            self.assertFalse(Path(manifest['destination']).exists())
            foreign = dict(state(first), repository='Fixture/Other')
            other = fx.root / 'other' / inc.STATE_NAME
            other.parent.mkdir()
            other.write_bytes(packer.encoded(foreign))
            self.assertEqual(fx.run(fx.manifest(c2, previous=select(other)))['status'], 'failed')

    def test_cli_receipt_and_exit_codes(self):
        with fixture() as fx:
            c1 = fx.commit(C1)

            def cli(*args):
                done = subprocess.run([str(PYTHON), '-I', '-B', str(DRIVER), *args], capture_output=True,
                                      timeout=120, env={'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
                                                        'LC_ALL': 'C.UTF-8'})
                return done.returncode, done.stdout

            path, sha = fx.save(fx.manifest(c1))
            code, out = cli('--manifest', str(path), '--manifest-sha256', sha)
            first = packer.strict_json(out)
            self.assertEqual((code, first['status'], first['schema']), (0, 'completed', inc.RESULT_SCHEMA))
            path, sha = fx.save(fx.manifest(c1, previous=first['build_state']))
            code, out = cli('--manifest', str(path), '--manifest-sha256', sha)
            self.assertEqual((code, packer.strict_json(out)['status']), (0, 'unchanged'))
            code, out = cli('--manifest', str(path), '--manifest-sha256', 'f' * 64)
            self.assertEqual((code, packer.strict_json(out)['status']), (1, 'failed'))
            path, sha = fx.save(fx.manifest(c1))
            with open(fx.lock, 'rb') as held:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                code, out = cli('--manifest', str(path), '--manifest-sha256', sha)
            self.assertEqual((code, packer.strict_json(out)['status']), (2, 'deferred'))
            self.assertEqual(cli()[0], 2)
            code, out = cli('--help')
            self.assertEqual(code, 0)
            done = subprocess.run([str(PYTHON), '-B', str(DRIVER), '--help'], capture_output=True, timeout=60,
                                  env={'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'LC_ALL': 'C.UTF-8'})
            self.assertEqual(done.returncode, 0)

    def test_fixture_cleans_on_success_failure_and_cancellation(self):
        seen = []
        with scratch() as root:
            seen.append(root)
        with self.assertRaises(RuntimeError), scratch() as root:
            seen.append(root)
            raise RuntimeError('synthetic failure')
        with self.assertRaises(KeyboardInterrupt), scratch() as root:
            seen.append(root)
            os.kill(os.getpid(), signal.SIGTERM)
        self.assertTrue(all(not p.exists() for p in seen))


if __name__ == '__main__':
    unittest.main()
