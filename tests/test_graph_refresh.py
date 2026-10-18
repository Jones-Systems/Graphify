"""Synthetic-only refresh transitions; fixtures own all scratch and subprocesses."""
from contextlib import contextmanager
import copy
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tooling'))
import graph_refresh as refresh
import graph_pack as packer
import graph_read as reader

ADAPTER = '''import hashlib, json, pathlib, sys
raw = sys.stdin.buffer.read()
r = json.loads(raw)
sha = hashlib.sha256(raw).hexdigest()
nodes = []
for f in r['files']:
    data = (pathlib.Path(r['stage']) / f['path']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == f['sha256']
    nodes.append(dict(id=f['path'], source_file=f['path'], label=data.decode().strip()))
graph = dict(source=r['source'], built_at_commit=r['source']['head'], directed=True,
             nodes=nodes, links=[], refresh_request_sha256=sha)
validation = dict(source=r['source'], status='partial', semantic_coverage='unknown',
                  covered_segments_by_file={f['path']: [] for f in r['files']},
                  refresh_request_sha256=sha)
print(json.dumps(dict(schema='graphify-refresh-response/v1', request_sha256=sha,
                      graph=graph, validation=validation,
                      coverage={f['path']: 'structural' for f in r['files']})))
'''


def git(root, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_TERMINAL_PROMPT='0')
    return subprocess.check_output(['git', '-C', str(root), '-c', 'core.hooksPath=/dev/null',
                                    '-c', 'user.name=Synthetic', '-c', 'user.email=fixture@example.invalid',
                                    '-c', 'commit.gpgsign=false', *args], env=env, stderr=subprocess.DEVNULL).decode().strip()


def select(path):
    return dict(path=str(path), sha256=reader.digest(path.read_bytes()))


@contextmanager
def fixture(adapter=ADAPTER):
    parent = os.environ.get('GRAPHIFY_REFRESH_TEST_ROOT', str(Path(__file__).resolve().parents[1]))
    with tempfile.TemporaryDirectory(prefix='graph-refresh-test-', dir=parent) as directory:
        root = Path(directory).resolve()
        source = root / 'source'
        source.mkdir()
        git(source, 'init', '-q')
        (source / 'a.py').write_text('new extraction input\n')
        git(source, 'add', 'a.py')
        git(source, 'commit', '-qm', 'synthetic')
        head = git(source, 'rev-parse', 'HEAD')
        script = root / 'adapter.py'
        script.write_text(adapter)
        lock = root / 'refresh.lock'
        lock.touch()
        task = dict(source=dict(repository='Fixture/Source', head=head), root=str(source),
                    target_oid=None, existing=None,
                    files=[dict(path='a.py', sha256=reader.digest((source / 'a.py').read_bytes()))],
                    deny=['private/*'], destination=str(root / 'transaction'), lock=str(lock),
                    extractor=dict(protocol='python-json/v1', name='synthetic', version='1',
                                   executable=select(Path(sys.executable).resolve()), script=select(script)))
        manifest = dict(schema=refresh.SCHEMA, limits=dict(refresh.LIMITS, seconds=2), tasks=[task])
        yield root, manifest


def run(root, manifest):
    path = root / 'manifest.json'
    raw = packer.encoded(manifest)
    path.write_bytes(raw)
    return refresh.refresh(path, reader.digest(raw))


def one(root, manifest):
    return run(root, manifest)['tasks'][0]


class RefreshTests(unittest.TestCase):
    def add_independent_task(self, root, manifest):
        second = copy.deepcopy(manifest['tasks'][0])
        second['source']['repository'] = 'Fixture/Independent'
        second['destination'] = str(root / 'second')
        lock = root / 'independent.lock'
        lock.touch()
        second['lock'] = str(lock)
        manifest['tasks'].append(second)

    def assert_halted(self, root, result):
        self.assertEqual(result['status'], 'unknown', result)
        self.assertEqual([t['status'] for t in result['tasks']], ['unknown', 'deferred'], result)
        self.assertIn('not started', result['tasks'][1]['reason'])
        self.assertFalse((root / 'second').exists())

    def test_lost_lock_before_pack_halts_independent_task(self):
        for change in ('missing', 'replacement', 'symlink', 'unreadable'):
            with self.subTest(change=change), fixture() as (root, manifest):
                self.add_independent_task(root, manifest)
                original = refresh.run_adapter
                stat = os.stat
                def adapter(*args):
                    response = original(*args)
                    lock = root / 'refresh.lock'
                    if change != 'unreadable':
                        lock.rename(root / 'held.lock')
                        if change == 'replacement':
                            lock.touch()
                        elif change == 'symlink':
                            lock.symlink_to(root / 'held.lock')
                    return response
                def readback(path, *args, **kwargs):
                    if change == 'unreadable' and str(path) == str(root / 'refresh.lock'):
                        raise PermissionError('synthetic lock readback denial')
                    return stat(path, *args, **kwargs)
                with patch.object(refresh, 'run_adapter', adapter), patch.object(os, 'stat', readback):
                    result = run(root, manifest)
                self.assert_halted(root, result)
                self.assertFalse((root / 'transaction/candidate').exists())

    def test_lost_lock_after_pack_halts_and_retains_candidate(self):
        with fixture() as (root, manifest):
            self.add_independent_task(root, manifest)
            original = packer.pack
            def pack(*args):
                result = original(*args)
                (root / 'refresh.lock').rename(root / 'held.lock')
                return result
            with patch.object(packer, 'pack', pack):
                result = run(root, manifest)
            self.assert_halted(root, result)
            self.assertTrue(result['tasks'][0]['retained'])
            self.assertTrue((root / 'transaction/candidate/package.json').is_file())

    def test_lost_lock_overrides_ordinary_failure(self):
        with fixture() as (root, manifest):
            self.add_independent_task(root, manifest)
            def adapter(*args):
                (root / 'refresh.lock').rename(root / 'held.lock')
                raise ValueError('synthetic adapter failure')
            with patch.object(refresh, 'run_adapter', adapter):
                result = run(root, manifest)
            self.assert_halted(root, result)

    def test_lost_lock_overrides_unchanged(self):
        with fixture() as (root, manifest):
            self.assertEqual(one(root, manifest)['status'], 'completed')
            manifest['tasks'][0]['existing'] = select(root / 'transaction/candidate/download-catalog.json')
            manifest['tasks'][0]['destination'] = str(root / 'unchanged')
            self.add_independent_task(root, manifest)
            original = refresh.freshness.observe
            def observe(*args):
                result = original(*args)
                (root / 'refresh.lock').rename(root / 'held.lock')
                return result
            with patch.object(refresh.freshness, 'observe', observe):
                result = run(root, manifest)
            self.assert_halted(root, result)
            self.assertFalse((root / 'unchanged').exists())

    def test_lost_lock_on_cancellation_is_unknown(self):
        with fixture() as (root, manifest):
            self.add_independent_task(root, manifest)
            def adapter(*args):
                (root / 'refresh.lock').rename(root / 'held.lock')
                raise KeyboardInterrupt('synthetic cancellation')
            with patch.object(refresh, 'run_adapter', adapter):
                result = run(root, manifest)
            self.assert_halted(root, result)
            self.assertTrue((root / 'transaction/capture.json').is_file())

    def test_foreign_candidate_before_producer_acquisition_halts_and_preserves(self):
        for kind in ('directory', 'file', 'symlink'):
            with self.subTest(kind=kind), fixture() as (root, manifest):
                self.add_independent_task(root, manifest)
                original = packer.pack
                def pack(inputs, destination):
                    if kind == 'directory':
                        destination.mkdir()
                        (destination / 'foreign').write_text('preserve')
                    elif kind == 'file':
                        destination.write_text('preserve')
                    else:
                        destination.symlink_to('missing-foreign-target')
                    return original(inputs, destination)
                with patch.object(packer, 'pack', pack):
                    result = run(root, manifest)
                self.assert_halted(root, result)
                candidate = root / 'transaction/candidate'
                if kind == 'symlink':
                    self.assertEqual(os.readlink(candidate), 'missing-foreign-target')
                else:
                    retained = candidate / 'foreign' if kind == 'directory' else candidate
                    self.assertEqual(retained.read_text(), 'preserve')

    def test_foreign_candidate_racing_producer_create_is_unknown(self):
        with fixture() as (root, manifest):
            self.add_independent_task(root, manifest)
            original = packer.OwnedOutput.create
            def create(owned):
                if owned.name == 'candidate':
                    os.mkdir('candidate', dir_fd=owned.parent)
                    (root / 'transaction/candidate/foreign').write_text('preserve')
                return original(owned)
            with patch.object(packer.OwnedOutput, 'create', create):
                result = run(root, manifest)
            self.assert_halted(root, result)
            self.assertEqual((root / 'transaction/candidate/foreign').read_text(), 'preserve')

    def test_reconciled_pack_failure_allows_independent_task(self):
        with fixture() as (root, manifest):
            self.add_independent_task(root, manifest)
            original = packer.read_graph
            calls = 0
            def reject_first(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise ValueError('synthetic validation failure after acquisition')
                return original(*args, **kwargs)
            with patch.object(packer, 'read_graph', reject_first):
                result = run(root, manifest)
            self.assertEqual([t['status'] for t in result['tasks']], ['failed', 'completed'], result)
            self.assertFalse((root / 'transaction/candidate').exists())
            self.assertTrue((root / 'second/candidate/package.json').is_file())

    def test_complete_new_extraction_package_and_no_promotion(self):
        with fixture() as (root, manifest):
            marker = root / 'current'
            marker.write_text('old pointer')
            result = run(root, manifest)
            self.assertEqual(result['status'], 'completed', result)
            self.assertFalse(result['promoted'])
            task = result['tasks'][0]
            self.assertEqual(task['canonical_currentness'], 'unknown')
            self.assertEqual(marker.read_text(), 'old pointer')
            candidate = root / 'transaction' / 'candidate'
            catalog, _ = reader.load_catalog(candidate / 'download-catalog.json', task['package']['catalog_sha256'])
            graph, _, sha, _ = reader.read_graph(candidate / 'download-catalog.json', catalog['archives'][0])
            self.assertEqual(graph['nodes'][0]['label'], 'new extraction input')
            self.assertEqual(sha, task['package']['graph_sha256'])
            source = json.loads((root / 'transaction/evidence/source.json').read_bytes())
            self.assertEqual(set(source['input_sha256']), set(packer.NAMES) - {'source'})
            self.assertEqual(source['build_observation'], dict(head=manifest['tasks'][0]['source']['head'], dirty=False, stable=True))
            for name, digest in source['input_sha256'].items():
                self.assertEqual(reader.digest((root / ('transaction/evidence/' + name + '.json')).read_bytes()), digest)
            self.assertLessEqual(len(refresh.bounded_receipt(result)), refresh.MAX_RECEIPT)

    def test_unchanged_assesses_existing_and_does_not_extract(self):
        with fixture() as (root, manifest):
            completed = one(root, manifest)
            self.assertEqual(completed['status'], 'completed', completed)
            task = manifest['tasks'][0]
            task['existing'] = select(root / 'transaction/candidate/download-catalog.json')
            task['destination'] = str(root / 'second')
            with patch.object(refresh, 'run_adapter', side_effect=AssertionError('must not run')):
                result = one(root, manifest)
            self.assertEqual(result['status'], 'unchanged', result)
            self.assertFalse((root / 'second').exists())
            self.assertEqual(result['existing']['comparison']['outcome'], 'clean_head_match')

    def test_changed_head_extracts_even_with_current_and_existing_graph(self):
        with fixture() as (root, manifest):
            initial = one(root, manifest)
            self.assertEqual(initial['status'], 'completed', initial)
            task = manifest['tasks'][0]
            task['existing'] = select(root / 'transaction/candidate/download-catalog.json')
            source = Path(task['root'])
            (source / 'a.py').write_text('changed content\n')
            git(source, 'add', 'a.py')
            git(source, 'commit', '-qm', 'changed')
            task['source']['head'] = git(source, 'rev-parse', 'HEAD')
            task['files'][0]['sha256'] = reader.digest((source / 'a.py').read_bytes())
            task['destination'] = str(root / 'changed')
            (root / 'current').symlink_to(root / 'transaction/candidate', target_is_directory=True)
            result = one(root, manifest)
            self.assertEqual(result['status'], 'completed', result)
            self.assertEqual(result['existing']['comparison']['outcome'], 'head_mismatch')
            self.assertNotEqual(result['package']['graph_sha256'], initial['package']['graph_sha256'])
            self.assertEqual(os.readlink(root / 'current'), str(root / 'transaction/candidate'))

    def test_dirty_missing_head_and_target_defer(self):
        with fixture() as (root, manifest):
            for field in ('dirty', 'missing', 'head', 'target'):
                m = copy.deepcopy(manifest)
                task = m['tasks'][0]
                if field == 'dirty':
                    (Path(task['root']) / 'untracked').write_text('dirty')
                elif field == 'missing':
                    task['root'] = str(root / 'absent')
                elif field == 'head':
                    task['source']['head'] = 'a' * 40
                else:
                    task['target_oid'] = 'b' * 40
                result = one(root, m)
                self.assertEqual(result['status'], 'deferred', (field, result))
                self.assertFalse((root / 'transaction').exists())
                if field == 'dirty':
                    (Path(task['root']) / 'untracked').unlink()

    def test_changed_samples_defer_before_extraction(self):
        with fixture() as (root, manifest):
            original = refresh.source_sample
            calls = 0
            def sample(task):
                nonlocal calls
                calls += 1
                result = original(task)
                if calls == 2:
                    result['status_sha256'] = 'b' * 64
                return result
            with patch.object(refresh, 'source_sample', sample):
                result = one(root, manifest)
            self.assertEqual(result['status'], 'deferred', result)
            self.assertFalse((root / 'transaction').exists())

    def test_source_changes_during_extraction_retain_evidence_without_candidate(self):
        with fixture() as (root, manifest):
            original = refresh.run_adapter
            def change(*args):
                response = original(*args)
                (root / 'source/a.py').write_text('changed during execution')
                return response
            with patch.object(refresh, 'run_adapter', change):
                result = one(root, manifest)
            self.assertIn(result['status'], ('failed', 'deferred'), result)
            self.assertTrue(result['retained'])
            self.assertTrue((root / 'transaction/capture.json').is_file())
            self.assertFalse((root / 'transaction/candidate').exists())

    def test_lock_contention_is_nonzero_deferral(self):
        with fixture() as (root, manifest):
            with (root / 'refresh.lock').open('rb') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = one(root, manifest)
            self.assertEqual(result['status'], 'deferred', result)
            self.assertIn('lock', result['reason'])
            self.assertFalse((root / 'transaction').exists())

    def test_collisions_preserve_existing_file_directory_and_symlink(self):
        with fixture() as (root, manifest):
            for name, kind in (('file', 'file'), ('dir', 'dir'), ('link', 'link')):
                dest = root / name
                if kind == 'file':
                    dest.write_text('preserve')
                elif kind == 'dir':
                    dest.mkdir()
                    (dest / 'keep').write_text('preserve')
                else:
                    dest.symlink_to(root / 'absent')
                manifest['tasks'][0]['destination'] = str(dest)
                result = one(root, manifest)
                self.assertEqual(result['status'], 'deferred', result)
                self.assertTrue(os.path.lexists(dest))
            self.assertEqual((root / 'file').read_text(), 'preserve')
            self.assertEqual((root / 'dir/keep').read_text(), 'preserve')

    def test_extractor_missing_hash_mismatch_and_unsupported_defer(self):
        with fixture() as (root, manifest):
            for change in ('missing', 'digest', 'protocol'):
                m = copy.deepcopy(manifest)
                ex = m['tasks'][0]['extractor']
                if change == 'missing':
                    ex['script']['path'] = str(root / 'absent')
                elif change == 'digest':
                    ex['script']['sha256'] = '0' * 64
                else:
                    ex['protocol'] = 'shell/v1'
                result = one(root, m)
                self.assertEqual(result['status'], 'deferred', result)
                self.assertFalse((root / 'transaction').exists())

    def test_input_allowlist_digests_denies_and_no_follow(self):
        with fixture() as (root, manifest):
            for path in ('../escape', '.git/config', '/absolute', 'a.py'):
                m = copy.deepcopy(manifest)
                m['tasks'][0]['files'][0]['path'] = path
                m['tasks'][0]['deny'] = ['a.py']
                with self.assertRaises(ValueError):
                    run(root, m)
            m = copy.deepcopy(manifest)
            m['tasks'][0]['files'][0]['sha256'] = '0' * 64
            self.assertEqual(one(root, m)['status'], 'failed')
            (root / 'source/link').symlink_to(root / 'source/a.py')
            git(root / 'source', 'add', 'link')
            git(root / 'source', 'commit', '-qm', 'symlink fixture')
            m = copy.deepcopy(manifest)
            m['tasks'][0]['source']['head'] = git(root / 'source', 'rev-parse', 'HEAD')
            m['tasks'][0]['files'][0]['path'] = 'link'
            self.assertEqual(one(root, m)['status'], 'deferred')
            self.assertFalse((root / 'transaction').exists())

    def test_parser_failure_and_output_provenance_mismatch(self):
        for adapter in ("print('{')", "print('{}')", ADAPTER.replace("request_sha256=sha", "request_sha256='wrong'"),
                        ADAPTER.replace("refresh_request_sha256=sha", "refresh_request_sha256='wrong'"),
                        "print('{\"x\":1,\"x\":2}')", "print('{\"x\":NaN}')"):
            with self.subTest(adapter=adapter[:30]), fixture(adapter) as (root, manifest):
                result = one(root, manifest)
                self.assertEqual(result['status'], 'failed', result)
                self.assertFalse((root / 'transaction/candidate').exists())

    def test_command_nonzero_timeout_output_bounds_and_regular_file_writes(self):
        for adapter, status in (("raise SystemExit(7)", 'failed'),
                                ('import time; time.sleep(10)', 'deferred'),
                                ("print('x'*4096)", 'failed'),
                                ("open('forbidden','w').write('x')", 'unknown')):
            with self.subTest(adapter=adapter), fixture(adapter) as (root, manifest):
                manifest['limits'].update(seconds=1, output_bytes=1024)
                result = one(root, manifest)
                self.assertEqual(result['status'], status, result)
                self.assertFalse((root / 'transaction/candidate').exists())
                if (root / 'transaction/forbidden').exists():
                    self.assertEqual((root / 'transaction/forbidden').stat().st_size, 0)

    def test_cancel_stops_remaining_tasks_and_retains_created_evidence(self):
        with fixture() as (root, manifest):
            second = copy.deepcopy(manifest['tasks'][0])
            second['source']['repository'] = 'Fixture/Other'
            second['destination'] = str(root / 'second')
            manifest['tasks'].append(second)
            with patch.object(refresh, 'run_adapter', side_effect=KeyboardInterrupt):
                result = run(root, manifest)
            self.assertEqual([t['status'] for t in result['tasks']], ['deferred', 'deferred'])
            self.assertTrue((root / 'transaction/capture.json').exists())
            self.assertFalse((root / 'second').exists())

    def test_unknown_pack_effect_stops_later_tasks(self):
        with fixture() as (root, manifest):
            second = copy.deepcopy(manifest['tasks'][0])
            second['source']['repository'] = 'Fixture/Other'
            second['destination'] = str(root / 'second')
            manifest['tasks'].append(second)
            third = copy.deepcopy(second)
            third['source']['repository'] = 'Fixture/Third'
            third['destination'] = str(root / 'third')
            manifest['tasks'].append(third)
            with patch.object(packer, 'pack', side_effect=packer.UnknownOutputError('unconfirmed output')):
                result = run(root, manifest)
            self.assertEqual([t['status'] for t in result['tasks']], ['unknown', 'deferred', 'deferred'])
            self.assertFalse((root / 'second').exists())
            self.assertFalse((root / 'third').exists())

    def test_selected_tasks_complete_sequentially_and_release_lock(self):
        with fixture() as (root, manifest):
            second = copy.deepcopy(manifest['tasks'][0])
            second['source']['repository'] = 'Fixture/Second'
            second['destination'] = str(root / 'second')
            manifest['tasks'].append(second)
            original = refresh.run_adapter
            calls = []
            def adapter(*args):
                calls.append(str(args[3]))
                if len(calls) == 2:
                    self.assertTrue((root / 'transaction/candidate/package.json').is_file())
                return original(*args)
            with patch.object(refresh, 'run_adapter', adapter):
                result = run(root, manifest)
            self.assertEqual([t['status'] for t in result['tasks']], ['completed', 'completed'], result)
            self.assertEqual(calls, [str(root / 'transaction'), str(root / 'second')])
            with (root / 'refresh.lock').open('rb') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_corrupt_existing_store_is_not_silently_rebuilt(self):
        with fixture() as (root, manifest):
            original = one(root, manifest)
            self.assertEqual(original['status'], 'completed', original)
            catalog_path = root / 'transaction/candidate/download-catalog.json'
            catalog = json.loads(catalog_path.read_bytes())
            archive = catalog_path.parent / 'archives' / catalog['archives'][0]['archive']
            archive.write_bytes(b'corrupt')
            manifest['tasks'][0]['existing'] = select(catalog_path)
            manifest['tasks'][0]['destination'] = str(root / 'next')
            with patch.object(refresh, 'run_adapter', side_effect=AssertionError('must not extract')):
                result = one(root, manifest)
            self.assertEqual(result['status'], 'failed', result)
            self.assertFalse((root / 'next').exists())

    def test_ambiguous_create_retains_path_and_stops_without_retry(self):
        with fixture() as (root, manifest):
            original = packer.OwnedOutput.create
            calls = 0
            def create(owned):
                nonlocal calls
                calls += 1
                original(owned)
                raise OSError('injected post-create uncertainty')
            with patch.object(packer.OwnedOutput, 'create', create):
                result = one(root, manifest)
            self.assertEqual(result['status'], 'unknown', result)
            self.assertTrue((root / 'transaction').is_dir())
            self.assertEqual(calls, 1)

    def test_manifest_fail_closed_without_writes(self):
        with fixture() as (root, manifest):
            path = root / 'manifest.json'
            for raw in (b'{', b'[]', b'{"x":1,"x":2}', b'{"x":NaN}'):
                path.write_bytes(raw)
                with self.assertRaises(ValueError):
                    refresh.refresh(path, reader.digest(raw))
            for mutate in (lambda m: m.update(extra=True),
                           lambda m: m.update(tasks=[]),
                           lambda m: m['limits'].update(seconds=True),
                           lambda m: m['limits'].update(input_bytes=10**10),
                           lambda m: m['tasks'][0].update(destination=m['tasks'][0]['root'] + '/inside'),
                           lambda m: m['tasks'][0].update(files=[])):
                m = copy.deepcopy(manifest)
                mutate(m)
                with self.assertRaises(ValueError):
                    run(root, m)
            self.assertFalse((root / 'transaction').exists())

    def test_cli_receipt_exit_and_handled_signal(self):
        with fixture('import time; time.sleep(30)') as (root, manifest):
            path = root / 'manifest.json'
            raw = packer.encoded(manifest)
            path.write_bytes(raw)
            command = [sys.executable, '-B', str(Path(refresh.__file__)), '--manifest', str(path),
                       '--manifest-sha256', reader.digest(raw)]
            with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
                try:
                    import time
                    deadline = time.monotonic() + 5
                    while not (root / 'transaction/capture.json').exists() and process.poll() is None:
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(0.02)
                    process.send_signal(signal.SIGTERM)
                    out, err = process.communicate(timeout=5)
                    self.assertEqual(process.returncode, 2, err)
                    self.assertEqual(json.loads(out)['status'], 'deferred')
                    self.assertFalse((root / 'transaction/candidate').exists())
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait()

    def test_fixture_cleans_on_success_failure_and_cancellation(self):
        for exception in (None, RuntimeError, KeyboardInterrupt):
            path = None
            try:
                with fixture() as (root, manifest):
                    path = root
                    (root / 'owned').write_text('fixture scratch')
                    if exception:
                        raise exception()
            except (RuntimeError, KeyboardInterrupt):
                pass
            self.assertFalse(path.exists())

    def test_receipt_bound_fails_closed(self):
        result = dict(status='completed', tasks=['x' * (refresh.MAX_RECEIPT + 1)])
        bounded = refresh.bounded_receipt(result)
        self.assertLessEqual(len(bounded), refresh.MAX_RECEIPT)
        self.assertEqual(json.loads(bounded)['status'], 'unknown')


if __name__ == '__main__':
    unittest.main()
