from contextlib import contextmanager, redirect_stdout
import io
import json
import os
from pathlib import Path
import signal
import shlex
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tooling'))
import graph_freshness as freshness
import graph_read as reader

REPO = 'Fixture/Source'
ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def owned_tree():
    # Signals unwind the context so this invocation alone removes its fixtures.
    previous = {}
    def cancel(signum, frame):
        raise KeyboardInterrupt('fixture cancelled')
    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous[sig] = signal.signal(sig, cancel)
        with tempfile.TemporaryDirectory(prefix='.graph-freshness-fixture-', dir=ROOT) as directory:
            yield Path(directory)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def git(root, *args):
    env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               GIT_AUTHOR_NAME='Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
               GIT_COMMITTER_NAME='Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
    return subprocess.check_output(['git', '-C', str(root), *args], env=env, stderr=subprocess.DEVNULL).decode().strip()


def write_store(root, head, mutate=None, coverage=None):
    (root / 'archives').mkdir(exist_ok=True)
    graph = dict(built_at_commit=head, directed=True, nodes=[{'id': 'a'}], links=[])
    payload = {
        'enriched/graph.json': json.dumps(graph).encode(),
        'enriched/validation.json': json.dumps(coverage or {'coverage_meaning': 'Synthetic partial graph'}).encode(),
    }
    payload['enriched/hashes.json'] = json.dumps({Path(k).name: reader.digest(v) for k, v in payload.items()}).encode()
    payload['archive-manifest.json'] = json.dumps(dict(
        schema='portable-graph-archive/v1', source=dict(repository=REPO, head=head),
        files={k: reader.digest(v) for k, v in payload.items()})).encode()
    if mutate:
        mutate(payload)
    archive = root / 'archives' / 'source.tar.gz'
    with tarfile.open(archive, 'w:gz') as handle:
        for name, data in payload.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            handle.addfile(member, io.BytesIO(data))
    catalog = dict(schema=reader.CATALOG_SCHEMA, status='complete', archive_directory='archives',
                   archives=[dict(source=dict(repository=REPO, head=head), archive=archive.name,
                                  sha256=reader.digest(archive.read_bytes()), bytes=archive.stat().st_size)],
                   empty_repositories=[dict(repository='Fixture/Empty', status='empty_repository')])
    path = root / 'catalog.json'
    path.write_text(json.dumps(catalog))
    return path, reader.digest(path.read_bytes())


@contextmanager
def fixture(**kwargs):
    with owned_tree() as root:
        source = root / 'source'
        source.mkdir()
        git(source, 'init', '-q')
        (source / 'file').write_text('one\n')
        git(source, 'add', 'file')
        git(source, 'commit', '-qm', 'fixture')
        head = git(source, 'rev-parse', 'HEAD')
        path, digest = write_store(root, head, **kwargs)
        yield root, source, head, path, digest


def snapshot(root):
    return {str(p.relative_to(root)): (p.stat().st_mtime_ns, p.stat().st_size,
                                     reader.digest(p.read_bytes()) if p.is_file() else None)
            for p in root.rglob('*')}


class FreshnessTests(unittest.TestCase):
    def observe(self, path, sha, source, **kwargs):
        return freshness.observe(path, sha, REPO, source, **kwargs)

    def test_clean_match_and_no_writes(self):
        with fixture() as (root, source, head, path, sha):
            before = snapshot(root)
            result = self.observe(path, sha, source)
            self.assertEqual(result['status'], 'qualified')
            self.assertEqual(result['comparison']['outcome'], 'clean_head_match')
            self.assertEqual(result['source']['before']['head'], head)
            self.assertEqual(result['catalog_sha256'], sha)
            self.assertEqual(len(result['archive_sha256']), 64)
            self.assertEqual(len(result['graph_sha256']), 64)
            self.assertEqual(result['canonical_currentness'], 'unknown')
            self.assertEqual(result['observation']['stability'], 'stable_samples')
            self.assertLessEqual(result['observation']['started_at_utc'], result['observation']['finished_at_utc'])
            self.assertEqual(snapshot(root), before)

    def test_clean_filter_never_executes(self):
        with fixture() as (root, source, head, path, sha):
            marker = root / 'filter-executed'
            script = root / 'filter.py'
            script.write_text(
                'import pathlib, sys\n'
                'pathlib.Path(sys.argv[1]).write_text("executed")\n'
                'sys.stdout.buffer.write(sys.stdin.buffer.read())\n')
            command = ' '.join(shlex.quote(str(arg)) for arg in
                               (sys.executable, '-B', script, marker))
            git(source, 'config', 'filter.fixture.clean', command)
            (source / '.git' / 'info' / 'attributes').write_text('file filter=fixture\n')
            (source / 'file').write_text('two\n')
            os.utime(source / 'file', (1, 1))
            before = snapshot(root)
            result = self.observe(path, sha, source)
            self.assertEqual(
                (marker.exists(), result['status'], result['comparison']['outcome'],
                 result['comparison']['qualified']),
                (False, 'error', 'observation_error', False))
            self.assertEqual(snapshot(root), before)

    def test_process_filters_in_effective_config_never_execute(self):
        scopes = ('local', 'global', 'xdg', 'include', 'gitdir', 'onbranch',
                  'worktree', 'linked_worktree', 'system')
        for scope in scopes:
            with self.subTest(scope=scope), fixture() as (root, source, head, path, sha):
                if scope == 'linked_worktree':
                    linked = root / 'linked'
                    git(source, 'worktree', 'add', '-qb', 'linked-fixture', str(linked), head)
                    source = linked
                git_dir = Path(git(source, 'rev-parse', '--absolute-git-dir'))
                marker = root / 'process-executed'
                script = root / 'process.py'
                # Execution is the violation; no protocol server or lasting child
                # is needed to detect it. An accidental launch exits immediately.
                script.write_text('import pathlib, sys\n'
                                  'pathlib.Path(sys.argv[1]).write_text("executed")\n')
                command = ' '.join(shlex.quote(str(arg)) for arg in
                                   (sys.executable, '-B', script, marker))
                config = root / 'filter-config'
                if scope == 'local':
                    config = source / '.git' / 'config'
                elif scope == 'global':
                    config = root / '.gitconfig'
                elif scope == 'xdg':
                    config = root / 'xdg' / 'git' / 'config'
                    config.parent.mkdir(parents=True)
                elif scope in ('worktree', 'linked_worktree'):
                    git(source, 'config', 'extensions.worktreeConfig', 'true')
                    config = git_dir / 'config.worktree'
                elif scope in ('include', 'gitdir', 'onbranch'):
                    key = 'include.path'
                    if scope == 'gitdir':
                        key = f'includeIf.gitdir:{source}/.git.path'
                    elif scope == 'onbranch':
                        branch = git(source, 'branch', '--show-current')
                        key = f'includeIf.onbranch:{branch}.path'
                    git(source, 'config', key, str(config))
                git(source, 'config', '--file', str(config), 'filter.fixture.process', command)
                info = git_dir / 'info'
                info.mkdir(exist_ok=True)
                (info / 'attributes').write_text('file filter=fixture\n')
                (source / 'file').write_text('two\n')
                os.utime(source / 'file', (1, 1))
                original = subprocess.Popen
                def isolated_config(*args, **kwargs):
                    env = dict(kwargs['env'])
                    env.update(GIT_CONFIG_SYSTEM=str(config) if scope == 'system' else os.devnull)
                    kwargs['env'] = env
                    return original(*args, **kwargs)
                before = snapshot(root)
                with patch.dict(os.environ, {'HOME': str(root), 'XDG_CONFIG_HOME': str(root / 'xdg')}), \
                        patch.object(freshness.subprocess, 'Popen', side_effect=isolated_config) as launch:
                    result = self.observe(path, sha, source)
                self.assertFalse(marker.exists())
                self.assertEqual(result['status'], 'error')
                self.assertEqual(result['comparison']['outcome'], 'observation_error')
                self.assertIn('filter configuration', result['error']['message'])
                self.assertFalse(result['comparison']['qualified'])
                self.assertFalse(any('status' in call.args[0] for call in launch.call_args_list))
                self.assertEqual(snapshot(root), before)

    def test_unused_or_empty_filter_definitions_are_unavailable(self):
        for name, value in (('clean', ''), ('process', ''), ('smudge', 'unused'), ('required', 'false')):
            with self.subTest(name=name), fixture() as (root, source, head, path, sha):
                git(source, 'config', 'filter.Unused.' + name, value)
                result = self.observe(path, sha, source)
                self.assertEqual(result['comparison']['outcome'], 'observation_error')
                self.assertFalse(result['comparison']['qualified'])
                self.assertIsNone(result['source']['before'])

    def test_attributes_without_driver_keep_git_cleanliness_semantics(self):
        for location in ('info', 'worktree', 'index', 'global'):
            with self.subTest(location=location), fixture() as (root, source, head, path, sha):
                if location == 'info':
                    attributes = source / '.git' / 'info' / 'attributes'
                elif location == 'global':
                    attributes = root / 'attributes'
                    git(source, 'config', 'core.attributesFile', str(attributes))
                else:
                    attributes = source / '.gitattributes'
                attributes.write_text('file filter=undefined\n')
                if location in ('worktree', 'index'):
                    git(source, 'add', '.gitattributes')
                    git(source, 'commit', '-qm', 'attributes')
                    head = git(source, 'rev-parse', 'HEAD')
                    path, sha = write_store(root, head)
                    if location == 'index':
                        attributes.unlink()
                os.utime(source / 'file', (1, 1))
                result = self.observe(path, sha, source)
                expected = 'dirty_source' if location == 'index' else 'clean_head_match'
                self.assertEqual(result['comparison']['outcome'], expected)
                (source / 'file').write_text('two\n')
                os.utime(source / 'file', (1, 1))
                self.assertEqual(self.observe(path, sha, source)['comparison']['outcome'], 'dirty_source')

    def test_indexed_submodules_unavailable_without_entering_them(self):
        for initialized in (False, True):
            with self.subTest(initialized=initialized), fixture() as (root, source, head, path, sha):
                marker = root / 'submodule-filter-executed'
                module = source / 'module'
                module.mkdir()
                if initialized:
                    git(module, 'init', '-q')
                    (module / 'file').write_text('one\n')
                    git(module, 'add', 'file')
                    git(module, 'commit', '-qm', 'module')
                    module_head = git(module, 'rev-parse', 'HEAD')
                    script = root / 'module-filter.py'
                    script.write_text('import pathlib, sys\n'
                                      'pathlib.Path(sys.argv[1]).write_text("executed")\n'
                                      'sys.stdout.buffer.write(sys.stdin.buffer.read())\n')
                    command = ' '.join(shlex.quote(str(arg)) for arg in
                                       (sys.executable, '-B', script, marker))
                    git(module, 'config', 'filter.fixture.clean', command)
                    (module / '.git' / 'info' / 'attributes').write_text('file filter=fixture\n')
                    (module / 'file').write_text('two\n')
                    os.utime(module / 'file', (1, 1))
                else:
                    module_head = head
                git(source, 'update-index', '--add', '--cacheinfo', f'160000,{module_head},module')
                before = snapshot(root)
                original = subprocess.Popen
                with patch.object(freshness.subprocess, 'Popen', wraps=original) as launch:
                    result = self.observe(path, sha, source)
                self.assertFalse(marker.exists())
                self.assertIn('indexed submodules', result['error']['message'])
                self.assertFalse(result['comparison']['qualified'])
                self.assertFalse(any('status' in call.args[0] for call in launch.call_args_list))
                self.assertEqual(snapshot(root), before)

    def test_untracked_nested_repository_does_not_execute_its_filter(self):
        with fixture() as (root, source, head, path, sha), \
                fixture() as (nested_root, nested, _, _, _):
            marker = nested_root / 'filter-executed'
            script = nested_root / 'filter.py'
            script.write_text('import pathlib, sys\n'
                              'pathlib.Path(sys.argv[1]).write_text("executed")\n'
                              'sys.stdout.buffer.write(sys.stdin.buffer.read())\n')
            command = ' '.join(shlex.quote(str(arg)) for arg in
                               (sys.executable, '-B', script, marker))
            git(nested, 'config', 'filter.fixture.clean', command)
            (nested / '.git' / 'info' / 'attributes').write_text('file filter=fixture\n')
            (nested / 'file').write_text('two\n')
            os.utime(nested / 'file', (1, 1))
            nested.rename(source / 'embedded')
            before = snapshot(root), snapshot(nested_root)
            result = self.observe(path, sha, source)
            self.assertFalse(marker.exists())
            self.assertEqual(result['comparison']['outcome'], 'dirty_source')
            self.assertEqual((snapshot(root), snapshot(nested_root)), before)

    def test_filter_config_added_before_recheck_cannot_qualify(self):
        with fixture() as (root, source, head, path, sha):
            original = reader.read_graph
            def configure(*args):
                result = original(*args)
                git(source, 'config', 'filter.fixture.required', 'true')
                return result
            with patch.object(reader, 'read_graph', side_effect=configure):
                result = self.observe(path, sha, source)
            self.assertEqual(result['comparison']['outcome'], 'unstable_source')
            self.assertIn('filter configuration', result['source']['recheck_error']['message'])
            self.assertFalse(result['comparison']['qualified'])

    def test_cli_no_writes_and_json(self):
        with fixture() as (root, source, head, path, sha):
            before = snapshot(root)
            output = subprocess.check_output([
                sys.executable, '-B', str(ROOT / 'tooling' / 'graph_freshness.py'),
                '--catalog', str(path), '--catalog-sha256', sha, '--repo', REPO,
                '--source-root', str(source), '--max-bytes', '4096'])
            result = json.loads(output)
            self.assertEqual(result['status'], 'qualified')
            self.assertEqual(result['source']['before']['root'], str(source))
            self.assertLessEqual(len(output), 4096)
            self.assertEqual(snapshot(root), before)

    def test_changed_head(self):
        with fixture() as (_, source, head, path, sha):
            git(source, 'commit', '--allow-empty', '-qm', 'next')
            result = self.observe(path, sha, source)
            self.assertEqual(result['comparison']['outcome'], 'head_mismatch')
            self.assertFalse(result['comparison']['qualified'])

    def test_dirty_tracked_staged_and_untracked(self):
        for kind in ('tracked', 'staged', 'untracked'):
            with self.subTest(kind=kind), fixture() as (_, source, head, path, sha):
                (source / ('new' if kind == 'untracked' else 'file')).write_text('dirty\n')
                if kind == 'staged':
                    git(source, 'add', 'file')
                result = self.observe(path, sha, source)
                self.assertEqual(result['comparison']['outcome'], 'dirty_source')
                self.assertFalse(result['comparison']['qualified'])

    def test_missing_git(self):
        with fixture() as (_, source, head, path, sha):
            with patch.object(freshness.subprocess, 'Popen', side_effect=FileNotFoundError):
                result = self.observe(path, sha, source)
            self.assertEqual(result['error']['type'], 'ObservationError')
            self.assertFalse(result['comparison']['qualified'])

    def test_changes_during_validation(self):
        for change in ('head', 'dirty', 'unavailable'):
            with self.subTest(change=change), fixture() as (_, source, head, path, sha):
                original = reader.read_graph
                def changing(*args):
                    result = original(*args)
                    if change == 'head':
                        git(source, 'commit', '--allow-empty', '-qm', 'changed')
                    elif change == 'dirty':
                        (source / 'file').write_text('changed\n')
                    else:
                        (source / '.git').rename(source / '.unavailable-git')
                    return result
                with patch.object(reader, 'read_graph', side_effect=changing):
                    result = self.observe(path, sha, source)
                self.assertEqual(result['comparison']['outcome'], 'unstable_source')
                self.assertFalse(result['comparison']['qualified'])

    def test_head_changes_within_sample(self):
        with fixture() as (_, source, head, path, sha):
            original = freshness._git
            calls = 0
            def changing(root, *args):
                nonlocal calls
                if args[0] == 'rev-parse' and args[-1] == 'HEAD^{commit}':
                    calls += 1
                    if calls == 2:
                        return b'b' * 40 + b'\n'
                return original(root, *args)
            with patch.object(freshness, '_git', side_effect=changing):
                result = self.observe(path, sha, source)
            self.assertEqual(result['comparison']['outcome'], 'unstable_source')

    def test_corrupt_selection_preserves_reader_failure_type(self):
        with fixture() as (root, source, head, path, sha):
            (root / 'archives' / 'source.tar.gz').write_bytes(b'bad')
            result = self.observe(path, sha, source)
            self.assertEqual(result['error'], {'type': 'StoreError', 'message': 'archive size mismatch'})
            self.assertIsNotNone(result['source']['after'])
            self.assertFalse(result['comparison']['qualified'])
        with fixture(mutate=lambda payload: payload.__setitem__('enriched/graph.json', b'{}')) as (_, source, head, path, sha):
            result = self.observe(path, sha, source)
            self.assertEqual(result['error']['message'], 'member checksum mismatch')

    def test_recheck_failure_does_not_erase_reader_error(self):
        with fixture() as (_, source, head, path, sha):
            original = freshness._observe_source
            with patch.object(freshness, '_observe_source', side_effect=[original(source), freshness.ObservationError('lost root')]):
                result = self.observe(path, '0' * 64, source)
            self.assertEqual(result['error']['type'], 'StoreError')
            self.assertEqual(result['error']['message'], 'catalog checksum mismatch')
            self.assertEqual(result['source']['recheck_error']['type'], 'ObservationError')
            self.assertEqual(result['observation']['stability'], 'unstable')

    def test_empty_or_absent_selection_and_empty_git(self):
        with fixture() as (root, source, head, path, sha):
            for repo in ('Fixture/Empty', 'Fixture/Absent'):
                result = freshness.observe(path, sha, repo, source)
                self.assertEqual(result['error']['message'], 'repository has no selected graph')
                self.assertFalse(result['comparison']['qualified'])
            empty = root / 'empty'
            empty.mkdir()
            git(empty, 'init', '-q')
            result = self.observe(path, sha, empty)
            self.assertEqual(result['error']['type'], 'ObservationError')

    def test_no_root_fallback_or_git_environment_redirection(self):
        with fixture() as (root, source, head, path, sha):
            nested = source / 'nested'
            nested.mkdir()
            for wrong in (nested, root / 'missing', root, source / 'file'):
                result = self.observe(path, sha, wrong)
                self.assertEqual(result['status'], 'error')
            with patch.dict(os.environ, {'GIT_DIR': str(root / 'missing'), 'GIT_WORK_TREE': str(root)}):
                self.assertEqual(self.observe(path, sha, source)['status'], 'qualified')

    def test_missing_provenance_and_coverage(self):
        with fixture() as (_, source, head, path, sha):
            result = self.observe(path, sha, source)
            self.assertEqual(result['validation']['build_provenance']['status'], 'not_verified')
            self.assertEqual(result['validation']['build_provenance']['missing_or_unverified'],
                             ['build_time_inventory', 'build_time_cleanliness'])
            self.assertEqual(result['validation']['coverage']['coverage_meaning'], 'Synthetic partial graph')

    def test_target_match_mismatch_and_authority(self):
        with fixture() as (_, source, head, path, sha):
            for target in (None, head, 'f' * 40):
                result = self.observe(path, sha, source, target_oid=target)
                self.assertEqual(result['canonical_currentness'], 'unknown')
                self.assertEqual(result['target']['authority_basis'], 'not_supplied' if target is None else 'caller_supplied')
                self.assertEqual(result['comparison']['qualified'], target is None or target == head)
                if target:
                    self.assertEqual(result['target']['snapshot_matches'], target == head)
                    self.assertEqual(result['target']['source_matches'], target == head)
                if target == 'f' * 40:
                    self.assertTrue(result['comparison']['local_clean_match'])
                    self.assertEqual(result['comparison']['outcome'], 'target_mismatch')

    def test_invalid_bindings_fail_closed(self):
        with fixture() as (_, source, head, path, sha):
            for target in ('', 'HEAD', head[:8], 'g' * 40):
                self.assertEqual(self.observe(path, sha, source, target_oid=target)['status'], 'error')
            for digest in ('', None, '0' * 64):
                self.assertEqual(self.observe(path, digest, source)['status'], 'error')
            self.assertEqual(self.observe('', sha, source)['status'], 'error')
            self.assertEqual(self.observe(path, sha, '')['status'], 'error')

    def test_git_read_bounds_and_optional_locks(self):
        with fixture() as (_, source, head, path, sha):
            original = subprocess.Popen
            with patch.object(freshness.subprocess, 'Popen', wraps=original) as launch:
                self.assertEqual(self.observe(path, sha, source)['status'], 'qualified')
            for call in launch.call_args_list:
                self.assertIn('--no-optional-locks', call.args[0])
                self.assertEqual(call.kwargs['env']['GIT_OPTIONAL_LOCKS'], '0')
                self.assertEqual(call.kwargs['env']['GIT_NO_LAZY_FETCH'], '1')
            with patch.object(freshness, 'MAX_GIT_BYTES', 1):
                self.assertEqual(self.observe(path, sha, source)['status'], 'error')
            with patch.object(freshness, 'GIT_TIMEOUT', 0):
                self.assertEqual(self.observe(path, sha, source)['status'], 'error')

    def test_output_budget_and_cli_exit(self):
        with fixture(coverage={'limitations': 'x' * 40000}) as (_, source, head, path, sha):
            result = self.observe(path, sha, source)
            raw = freshness.bounded_output(result, 4096)
            self.assertLessEqual(len(raw.encode()), 4096)
            self.assertEqual(json.loads(raw)['truncation_reason'], 'byte_budget')
            args = ['--catalog', str(path), '--catalog-sha256', sha, '--repo', REPO, '--source-root', str(source)]
            for extra, expected in (([], 0), (['--target-oid', 'f' * 40], 2), (['--target-oid', 'HEAD'], 1)):
                with redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(freshness.main(args + extra), expected)
                self.assertLessEqual(len(output.getvalue().encode()), 32768)
            result = self.observe(path, sha, source)
            result['repository'] = 'x' * 10000
            raw = freshness.bounded_output(result, 4096)
            self.assertLessEqual(len(raw.encode()), 4096)
            self.assertFalse(json.loads(raw)['comparison']['qualified'])

    def test_fixture_cleanup_success_failure_and_cancellation(self):
        with owned_tree() as root:
            (root / 'marker').write_text('fixture')
        self.assertFalse(root.exists())
        for failure in (RuntimeError('intentional'), KeyboardInterrupt('cancelled')):
            with self.assertRaises(type(failure)):
                with owned_tree() as root:
                    raise failure
            self.assertFalse(root.exists())
        with self.assertRaises(KeyboardInterrupt):
            with owned_tree() as root:
                signal.raise_signal(signal.SIGTERM)
        self.assertFalse(root.exists())


if __name__ == '__main__':
    unittest.main()
