"""Local synthetic Git repositories and create-only release fixtures only."""
from contextlib import contextmanager, redirect_stdout
from io import StringIO
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('portable_installer', ROOT / 'tooling/install_portable.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def git(root, *arguments):
    env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               GIT_AUTHOR_NAME='Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
               GIT_COMMITTER_NAME='Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
    return subprocess.check_output(['git', '-C', str(root), *arguments], env=env,
                                   stderr=subprocess.DEVNULL).decode().strip()


@contextmanager
def fixture():
    old = {}
    def cancel(signum, frame):
        raise KeyboardInterrupt('fixture cancelled')
    try:
        for sig in installer.SIGNALS:
            old[sig] = signal.signal(sig, cancel)
        with tempfile.TemporaryDirectory(prefix='.portable-install-test-', dir=ROOT) as folder:
            root = Path(folder)
            try:
                source = root / 'source'
                source.mkdir()
                (source / 'tooling').mkdir()
                for name in (*installer.FILES, installer.INSTALLER):
                    (source / name).write_bytes((ROOT / name).read_bytes())
                git(source, 'init', '-q')
                git(source, 'remote', 'add', 'origin', 'https://github.com/Jones-Systems/Graphify.git')
                git(source, 'add', 'tooling')
                git(source, 'commit', '-qm', 'synthetic portable closure')
                revision = git(source, 'rev-parse', 'HEAD')
                destination = root / 'releases'
                destination.mkdir(mode=0o700)
                yield root, source, revision, destination
            finally:
                # Only this fixture's directories need owner write permission for cleanup.
                for parent, directories, _ in os.walk(root, followlinks=False):
                    os.chmod(parent, 0o700)
                    for name in directories:
                        child = Path(parent) / name
                        if not child.is_symlink():
                            child.chmod(0o700)
    finally:
        for sig, handler in old.items():
            signal.signal(sig, handler)


def prepare(source, revision, destination):
    manifest, payloads = installer.prepare(source, revision, destination)
    return manifest, payloads, installer.digest(installer.encoded(manifest))


def snapshot(root):
    return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
            for path in root.rglob('*') if path.is_file() and not path.is_symlink()}


def synthetic(path):
    return ('# synthetic portable closure fixture: ' + path + '\n').encode('ascii')


@contextmanager
def synthetic_fixture():
    """Synthetic bytes for every v2 helper; only the installer is real source."""
    old = {}
    def cancel(signum, frame):
        raise KeyboardInterrupt('fixture cancelled')
    try:
        for sig in installer.SIGNALS:
            old[sig] = signal.signal(sig, cancel)
        with tempfile.TemporaryDirectory(prefix='.portable-install-v2-test-', dir=ROOT) as folder:
            root = Path(folder)
            try:
                source = root / 'source'
                (source / 'tooling').mkdir(parents=True)
                for name in installer.FILES_V2:
                    (source / name).write_bytes(synthetic(name))
                (source / installer.INSTALLER).write_bytes((ROOT / installer.INSTALLER).read_bytes())
                git(source, 'init', '-q')
                git(source, 'remote', 'add', 'origin', 'https://github.com/Jones-Systems/Graphify.git')
                git(source, 'add', 'tooling')
                git(source, 'commit', '-qm', 'synthetic v2 portable closure')
                revision = git(source, 'rev-parse', 'HEAD')
                destination = root / 'releases'
                destination.mkdir(mode=0o700)
                yield root, source, revision, destination
            finally:
                for parent, directories, _ in os.walk(root, followlinks=False):
                    os.chmod(parent, 0o700)
                    for name in directories:
                        child = Path(parent) / name
                        if not child.is_symlink():
                            child.chmod(0o700)
    finally:
        for sig, handler in old.items():
            signal.signal(sig, handler)


class PortableInstallTests(unittest.TestCase):
    def test_deterministic_committed_blobs_not_worktree_contents(self):
        with fixture() as (root, source, revision, destination):
            manifest, payloads, sha = prepare(source, revision, destination)
            original = payloads[installer.FILES[0]]
            (source / installer.FILES[0]).write_text('uncommitted content must not be installed\n')
            (source / 'tooling/unlisted.py').write_text('unlisted\n')
            before = snapshot(source)
            self.assertEqual(prepare(source, revision, destination), (manifest, payloads, sha))
            installer.install(source, revision, destination, sha)
            release = destination / sha
            self.assertEqual((release / installer.FILES[0]).read_bytes(), original)
            self.assertEqual(installer.verify(release, sha), manifest)
            self.assertEqual(snapshot(source), before)
            self.assertEqual(set(release.rglob('*.py')), {release / name for name in installer.FILES})
            self.assertEqual(list(destination.glob('.stage-*')), [])
            self.assertFalse((destination / 'current').exists())

    def test_repeated_install_verifies_without_rewriting(self):
        with fixture() as (_, source, revision, destination):
            _, _, sha = prepare(source, revision, destination)
            installer.install(source, revision, destination, sha)
            before = snapshot(destination)
            installer.install(source, revision, destination, sha)
            self.assertEqual(snapshot(destination), before)

    def test_git_object_reads_explicitly_disable_lazy_fetch(self):
        with fixture() as (_, source, revision, destination):
            original = subprocess.Popen
            commands = []
            def record(command, **kwargs):
                commands.append((command, kwargs['env']))
                return original(command, **kwargs)
            with patch.object(installer.subprocess, 'Popen', side_effect=record):
                prepare(source, revision, destination)
            self.assertTrue(commands)
            for command, environment in commands:
                self.assertIn('--no-lazy-fetch', command)
                self.assertEqual(environment['GIT_NO_REPLACE_OBJECTS'], '1')
                self.assertEqual(environment['GIT_OPTIONAL_LOCKS'], '0')

    def test_identity_and_expected_digest_rejected_before_writes(self):
        with fixture() as (_, source, revision, destination):
            _, _, sha = prepare(source, revision, destination)
            for wrong in ('f' * 64, '../escape', ''):
                with self.subTest(wrong=wrong), self.assertRaises(installer.InstallError):
                    installer.install(source, revision, destination, wrong)
                self.assertEqual(list(destination.iterdir()), [])
            with self.assertRaisesRegex(installer.InstallError, 'source_head_mismatch'):
                installer.prepare(source, 'f' * 40, destination)
            git(source, 'remote', 'set-url', 'origin', 'https://example.invalid/Other/repo.git')
            with self.assertRaisesRegex(installer.InstallError, 'source_repository_mismatch'):
                installer.prepare(source, revision, destination)

    def test_installer_must_match_committed_provenance(self):
        with fixture() as (_, source, _, destination):
            (source / installer.INSTALLER).write_text('# different installer\n')
            git(source, 'add', 'tooling/install_portable.py')
            git(source, 'commit', '-qm', 'different installer fixture')
            revision = git(source, 'rev-parse', 'HEAD')
            with self.assertRaisesRegex(installer.InstallError, 'installer_revision_mismatch'):
                installer.prepare(source, revision, destination)
            self.assertEqual(list(destination.iterdir()), [])

    def test_missing_or_symlink_git_blob_rejected(self):
        for kind in ('missing', 'symlink'):
            with self.subTest(kind=kind), fixture() as (_, source, _, destination):
                path = source / installer.FILES[0]
                path.unlink()
                if kind == 'symlink':
                    path.symlink_to('graph_read.py')
                git(source, 'add', '-A', 'tooling')
                git(source, 'commit', '-qm', 'invalid closure fixture')
                revision = git(source, 'rev-parse', 'HEAD')
                with self.assertRaisesRegex(installer.InstallError, 'missing_or_nonregular_source_blob'):
                    installer.prepare(source, revision, destination)

    def test_overlap_symlinks_and_uncontrolled_destination_rejected(self):
        with fixture() as (root, source, revision, destination):
            link = root / 'link'
            link.symlink_to(destination, target_is_directory=True)
            inner = source / 'releases'
            inner.mkdir()
            for selected in (link, inner, source, source.parent, root / 'missing', str(destination) + '/../releases'):
                with self.subTest(path=str(selected)), self.assertRaises((installer.InstallError, OSError)):
                    installer.prepare(source, revision, selected)
            destination.chmod(0o777)
            with self.assertRaisesRegex(installer.InstallError, 'destination_not_owner_controlled'):
                installer.prepare(source, revision, destination)

    def test_existing_collision_never_replaced_even_when_empty(self):
        for kind in ('directory', 'file', 'symlink'):
            with self.subTest(kind=kind), fixture() as (_, source, revision, destination):
                _, _, sha = prepare(source, revision, destination)
                collision = destination / sha
                if kind == 'directory':
                    collision.mkdir()
                elif kind == 'file':
                    collision.write_text('preserve')
                else:
                    collision.symlink_to(source, target_is_directory=True)
                before = collision.lstat()
                with self.assertRaises((installer.InstallError, OSError)):
                    installer.install(source, revision, destination, sha)
                self.assertEqual(installer.inode(collision.lstat()), installer.inode(before))
                self.assertEqual(list(destination.glob('.stage-*')), [])

    def test_collision_at_publication_is_not_overwritten(self):
        with fixture() as (_, source, revision, destination):
            _, _, sha = prepare(source, revision, destination)
            real = installer.rename_new
            def collide(parent, old, new):
                os.mkdir(new, dir_fd=parent)
                return real(parent, old, new)
            with patch.object(installer, 'rename_new', side_effect=collide), self.assertRaisesRegex(installer.InstallError, 'destination_collision'):
                installer.install(source, revision, destination, sha)
            self.assertEqual(list((destination / sha).iterdir()), [])
            self.assertEqual(list(destination.glob('.stage-*')), [])

    def test_verify_rejects_bytes_modes_extra_files_and_manifest_drift(self):
        for mutation in ('bytes', 'mode', 'extra', 'manifest', 'hardlink', 'symlink', 'directory_mode'):
            with self.subTest(mutation=mutation), fixture() as (root, source, revision, destination):
                _, _, sha = prepare(source, revision, destination)
                installer.install(source, revision, destination, sha)
                release = destination / sha
                module = release / installer.FILES[0]
                if mutation == 'bytes':
                    module.chmod(0o644)
                    module.write_text('tampered')
                    module.chmod(0o444)
                elif mutation == 'mode':
                    module.chmod(0o644)
                elif mutation in ('extra', 'symlink'):
                    module.parent.chmod(0o755)
                    if mutation == 'extra':
                        (module.parent / 'extra.py').write_text('extra')
                    else:
                        module.unlink()
                        module.symlink_to(source / installer.FILES[0])
                    module.parent.chmod(0o555)
                elif mutation == 'manifest':
                    path = release / 'release.json'
                    path.chmod(0o644)
                    path.write_bytes(path.read_bytes().replace(b'Jones-Systems/Graphify', b'Other-System/Graphify'))
                    path.chmod(0o444)
                elif mutation == 'hardlink':
                    os.link(module, root / 'linked')
                else:
                    module.parent.chmod(0o755)
                with self.assertRaises((installer.InstallError, OSError)):
                    installer.verify(release, sha)

    def test_failure_cleans_own_stage_and_preserves_unrelated(self):
        with fixture() as (_, source, revision, destination):
            _, _, sha = prepare(source, revision, destination)
            sibling = destination / '.stage-another-invocation'
            sibling.mkdir()
            (sibling / 'keep').write_text('keep')
            original = installer.Stage.write
            def fail(stage, parent, name, raw):
                original(stage, parent, name, raw)
                raise RuntimeError('injected failure')
            with patch.object(installer.Stage, 'write', fail), self.assertRaisesRegex(RuntimeError, 'injected failure'):
                installer.install(source, revision, destination, sha)
            self.assertEqual(list(destination.iterdir()), [sibling])
            self.assertEqual((sibling / 'keep').read_text(), 'keep')

    def test_handled_sigterm_cleans_stage(self):
        with fixture() as (_, source, revision, destination):
            _, _, sha = prepare(source, revision, destination)
            original = installer.Stage.write
            def cancel(stage, parent, name, raw):
                original(stage, parent, name, raw)
                os.kill(os.getpid(), signal.SIGTERM)
            out = StringIO()
            with patch.object(installer.Stage, 'write', cancel), redirect_stdout(out):
                code = installer.main(['install', '--source', str(source), '--revision', revision,
                                       '--destination', str(destination), '--manifest-sha256', sha])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(out.getvalue())['status'], 'cancelled')
            self.assertEqual(list(destination.iterdir()), [])

    def test_cleanup_refuses_foreign_entries_and_reports_original_failure(self):
        with fixture() as (_, source, revision, destination):
            _, _, sha = prepare(source, revision, destination)
            original = installer.Stage.write
            def interfere(stage, parent, name, raw):
                original(stage, parent, name, raw)
                fd = os.open('foreign', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600, dir_fd=stage.root)
                os.close(fd)
                raise RuntimeError('original failure')
            with patch.object(installer.Stage, 'write', interfere), self.assertRaisesRegex(installer.InstallError, 'cleanup_unknown; original=RuntimeError'):
                installer.install(source, revision, destination, sha)
            stages = list(destination.glob('.stage-*'))
            self.assertEqual(len(stages), 1)
            self.assertTrue((stages[0] / 'foreign').is_file())

    def test_published_failure_requires_readback_and_retains_release(self):
        with fixture() as (_, source, revision, destination):
            _, _, sha = prepare(source, revision, destination)
            with patch.object(installer, 'verify', side_effect=OSError('injected readback failure')), self.assertRaisesRegex(installer.InstallError, 'publication_requires_readback'):
                installer.install(source, revision, destination, sha)
            installer.verify(destination / sha, sha)
            self.assertEqual(list(destination.glob('.stage-*')), [])

    def test_cli_prepare_install_verify_and_five_real_help_commands(self):
        with fixture() as (_, source, revision, destination):
            command = [sys.executable, '-B', str(ROOT / installer.INSTALLER)]
            common = ['--source', str(source), '--revision', revision, '--destination', str(destination)]
            def run(arguments):
                result = subprocess.run(arguments, capture_output=True, text=True, timeout=30,
                                        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                return result.stdout
            prepared = json.loads(run([*command, 'prepare', *common]))
            sha = prepared['manifest_sha256']
            installed = json.loads(run([*command, 'install', *common, '--manifest-sha256', sha]))
            self.assertEqual(installed['manifest'], prepared['manifest'])
            release = destination / sha
            verified = json.loads(run([*command, 'verify', '--release', str(release), '--manifest-sha256', sha]))
            self.assertEqual(verified['status'], 'verified')
            before = snapshot(release)
            for name in installer.FILES:
                self.assertIn('usage:', run([sys.executable, '-B', str(release / name), '--help']))
            # Selected empty catalog exercises the installed reader without source or archive reads.
            catalog = destination / 'synthetic-catalog.json'
            catalog.write_text(json.dumps({'schema': 'private-graph-download-catalog/v1', 'status': 'complete',
                                          'archive_directory': 'archives', 'archives': [], 'empty_repositories': []}))
            result = json.loads(run([sys.executable, '-B', str(release / 'tooling/graph_read.py'),
                                     '--catalog', str(catalog), 'list']))
            self.assertEqual(result['status'], 'ok')
            self.assertEqual(snapshot(release), before)
            self.assertEqual(list(release.rglob('__pycache__')), [])


class PortableClosureV2Tests(unittest.TestCase):
    def prepare(self, source, revision, destination, closure):
        manifest, payloads = installer.prepare(source, revision, destination, closure)
        return manifest, payloads, installer.digest(installer.encoded(manifest))

    def test_v2_closure_is_exact_ten_superset_of_v1(self):
        self.assertEqual(installer.SCHEMA_V2, 'graphify-portable-release/v2')
        self.assertEqual(len(installer.FILES_V2), 10)
        self.assertEqual(len(set(installer.FILES_V2)), 10)
        self.assertEqual(installer.FILES_V2[:5], installer.FILES)
        self.assertEqual(installer.FILES_V2[5:], tuple('tooling/' + name for name in (
            'graph_catalog.py', 'graph_refresh_incremental.py', 'fragment_cache.py',
            'runtime_identity.py', 'refresh_adapter_structural.py')))
        self.assertNotIn(installer.INSTALLER, installer.FILES_V2)

    def test_v2_prepare_deterministic_exact_ten_committed_blobs(self):
        with synthetic_fixture() as (_, source, revision, destination):
            manifest, payloads, sha = self.prepare(source, revision, destination, 'v2')
            (source / 'tooling/unlisted.py').write_text('unlisted\n')
            (source / installer.FILES_V2[-1]).write_text('uncommitted content must not be installed\n')
            self.assertEqual(self.prepare(source, revision, destination, 'v2'), (manifest, payloads, sha))
            self.assertEqual(manifest['schema'], installer.SCHEMA_V2)
            self.assertEqual([record['path'] for record in manifest['files']], list(installer.FILES_V2))
            self.assertEqual(list(payloads), list(installer.FILES_V2))
            for record in manifest['files']:
                listing = git(source, 'ls-tree', revision, '--', record['path']).split()
                self.assertEqual(listing[2], record['blob_oid'])
                self.assertEqual(payloads[record['path']], synthetic(record['path']))
            self.assertEqual(manifest['installer']['sha256'],
                             installer.digest((ROOT / installer.INSTALLER).read_bytes()))
            self.assertEqual(list(destination.iterdir()), [])

    def test_v2_install_then_verify(self):
        with synthetic_fixture() as (_, source, revision, destination):
            manifest, _, sha = self.prepare(source, revision, destination, 'v2')
            self.assertEqual(installer.install(source, revision, destination, sha, 'v2'), manifest)
            release = destination / sha
            self.assertEqual(installer.verify(release, sha, 'v2'), manifest)
            self.assertEqual(set(release.rglob('*.py')), {release / name for name in installer.FILES_V2})
            for name in installer.FILES_V2:
                self.assertEqual((release / name).read_bytes(), synthetic(name))
                self.assertEqual((release / name).stat().st_mode & 0o777, 0o444)
            self.assertEqual(list(destination.glob('.stage-*')), [])
            self.assertFalse((destination / 'current').exists())
            before = snapshot(destination)
            installer.install(source, revision, destination, sha, 'v2')
            self.assertEqual(snapshot(destination), before)

    def test_cross_closure_verify_and_install_rejected(self):
        with synthetic_fixture() as (_, source, revision, destination):
            _, _, v1 = self.prepare(source, revision, destination, 'v1')
            _, _, v2 = self.prepare(source, revision, destination, 'v2')
            self.assertNotEqual(v1, v2)
            installer.install(source, revision, destination, v1, 'v1')
            installer.install(source, revision, destination, v2, 'v2')
            before = snapshot(destination)
            for release, closure in ((v2, 'v1'), (v1, 'v2')):
                with self.subTest(release=release, closure=closure), self.assertRaisesRegex(
                        installer.InstallError, 'release_closure_mismatch'):
                    installer.verify(destination / release, release, closure)
            with self.assertRaisesRegex(installer.InstallError, 'release_closure_mismatch'):
                installer.verify(destination / v2, v2)
            for expected, closure in ((v2, 'v1'), (v1, 'v2')):
                with self.subTest(expected=expected, closure=closure), self.assertRaisesRegex(
                        installer.InstallError, 'manifest_digest_mismatch'):
                    installer.install(source, revision, destination, expected, closure)
            for closure in ('v4', '', None, 'V2'):
                with self.subTest(closure=closure), self.assertRaisesRegex(
                        installer.InstallError, 'invalid_closure_selection'):
                    installer.prepare(source, revision, destination, closure)
            self.assertEqual(snapshot(destination), before)

    def test_v2_manifest_with_v1_schema_or_wrong_length_rejected(self):
        with synthetic_fixture() as (_, source, revision, destination):
            v1, _ = installer.prepare(source, revision, destination, 'v1')
            v2, _ = installer.prepare(source, revision, destination, 'v2')
            installer.validate_manifest(v1, 'v1')
            installer.validate_manifest(v2, 'v2')
            relabelled = {**v2, 'schema': installer.SCHEMA}
            with self.assertRaisesRegex(installer.InstallError, 'invalid_closure'):
                installer.validate_manifest(relabelled, 'v1')
            with self.assertRaisesRegex(installer.InstallError, 'invalid_closure'):
                installer.validate_manifest({**v1, 'schema': installer.SCHEMA_V2}, 'v2')
            for schema in ('graphify-portable-release/v4', ['graphify-portable-release/v2'], None):
                with self.subTest(schema=schema), self.assertRaisesRegex(
                        installer.InstallError, 'invalid_manifest_identity'):
                    installer.validate_manifest({**v2, 'schema': schema}, 'v2')

    def test_missing_tenth_blob_rejected(self):
        with synthetic_fixture() as (_, source, _, destination):
            (source / installer.FILES_V2[-1]).unlink()
            git(source, 'add', '-A', 'tooling')
            git(source, 'commit', '-qm', 'missing tenth helper fixture')
            revision = git(source, 'rev-parse', 'HEAD')
            with self.assertRaisesRegex(installer.InstallError, 'missing_or_nonregular_source_blob'):
                installer.prepare(source, revision, destination, 'v2')
            manifest, _ = installer.prepare(source, revision, destination, 'v1')
            self.assertEqual(len(manifest['files']), 5)
            self.assertEqual(list(destination.iterdir()), [])

    def test_oversize_v2_blob_rejected(self):
        with synthetic_fixture() as (_, source, _, destination):
            (source / installer.FILES_V2[-1]).write_bytes(b'#' * (installer.MAX_BLOB + 1))
            git(source, 'add', 'tooling')
            git(source, 'commit', '-qm', 'oversize helper fixture')
            revision = git(source, 'rev-parse', 'HEAD')
            with self.assertRaisesRegex(installer.InstallError, 'source_blob_limit'):
                installer.prepare(source, revision, destination, 'v2')
            self.assertEqual(list(destination.iterdir()), [])

    def test_same_revision_v1_default_stays_five_file_v1(self):
        with synthetic_fixture() as (_, source, revision, destination):
            default, payloads = installer.prepare(source, revision, destination)
            self.assertEqual(installer.prepare(source, revision, destination, 'v1'), (default, payloads))
            self.assertEqual(default['schema'], installer.SCHEMA)
            self.assertEqual(set(default), {'schema', 'repository', 'revision', 'files', 'installer'})
            self.assertEqual([record['path'] for record in default['files']], list(installer.FILES))
            sha = installer.digest(installer.encoded(default))
            installer.install(source, revision, destination, sha)
            release = destination / sha
            self.assertEqual(installer.verify(release, sha), default)
            self.assertEqual(set(release.rglob('*.py')), {release / name for name in installer.FILES})

    def test_cli_closure_selection(self):
        with synthetic_fixture() as (_, source, revision, destination):
            command = [sys.executable, '-B', str(ROOT / installer.INSTALLER)]
            common = ['--source', str(source), '--revision', revision, '--destination', str(destination)]
            def run(arguments, code=0):
                result = subprocess.run(arguments, capture_output=True, text=True, timeout=30,
                                        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
                self.assertEqual(result.returncode, code, result.stderr + result.stdout)
                return json.loads(result.stdout) if result.stdout else None
            prepared = run([*command, 'prepare', *common, '--closure', 'v2'])
            self.assertEqual(len(prepared['manifest']['files']), 10)
            sha = prepared['manifest_sha256']
            installed = run([*command, 'install', *common, '--manifest-sha256', sha, '--closure', 'v2'])
            self.assertEqual(installed['manifest'], prepared['manifest'])
            verify = [*command, 'verify', '--release', str(destination / sha), '--manifest-sha256', sha]
            self.assertEqual(run([*verify, '--closure', 'v2'])['status'], 'verified')
            for selected in ([], ['--closure', 'v1']):
                with self.subTest(selected=selected):
                    self.assertEqual(run([*verify, *selected], 1),
                                     {'status': 'error', 'reason': 'release_closure_mismatch'})
            self.assertEqual(len(run([*command, 'prepare', *common])['manifest']['files']), 5)
            self.assertIsNone(run([*command, 'prepare', *common, '--closure', 'v4'], 2))


@contextmanager
def closure_fixture(contents, prefix):
    """Commit `contents(path)` for every v3 helper; the installer is always real source."""
    old = {}
    def cancel(signum, frame):
        raise KeyboardInterrupt('fixture cancelled')
    try:
        for sig in installer.SIGNALS:
            old[sig] = signal.signal(sig, cancel)
        with tempfile.TemporaryDirectory(prefix=prefix, dir=ROOT) as folder:
            root = Path(folder)
            try:
                source = root / 'source'
                (source / 'tooling').mkdir(parents=True)
                for name in installer.FILES_V3:
                    (source / name).write_bytes(contents(name))
                (source / installer.INSTALLER).write_bytes((ROOT / installer.INSTALLER).read_bytes())
                git(source, 'init', '-q')
                git(source, 'remote', 'add', 'origin', 'https://github.com/Jones-Systems/Graphify.git')
                git(source, 'add', 'tooling')
                git(source, 'commit', '-qm', 'v3 portable closure fixture')
                revision = git(source, 'rev-parse', 'HEAD')
                destination = root / 'releases'
                destination.mkdir(mode=0o700)
                yield root, source, revision, destination
            finally:
                for parent, directories, _ in os.walk(root, followlinks=False):
                    os.chmod(parent, 0o700)
                    for name in directories:
                        child = Path(parent) / name
                        if not child.is_symlink():
                            child.chmod(0o700)
    finally:
        for sig, handler in old.items():
            signal.signal(sig, handler)


class PortableClosureV3Tests(unittest.TestCase):
    NEW = ('tooling/structural_languages.py', 'tooling/semantic_batch.py')

    def fixture(self):
        return closure_fixture(synthetic, '.portable-install-v3-test-')

    def prepare(self, source, revision, destination, closure):
        manifest, payloads = installer.prepare(source, revision, destination, closure)
        return manifest, payloads, installer.digest(installer.encoded(manifest))

    def commit_change(self, source, message):
        git(source, 'add', '-A', 'tooling')
        git(source, 'commit', '-qm', message)
        return git(source, 'rev-parse', 'HEAD')

    def test_v3_closure_is_exact_twelve_superset_of_v2(self):
        self.assertEqual(installer.SCHEMA_V3, 'graphify-portable-release/v3')
        self.assertEqual(len(installer.FILES_V3), 12)
        self.assertEqual(len({Path(path).name for path in installer.FILES_V3}), 12)
        self.assertEqual(installer.FILES_V3[:10], installer.FILES_V2)
        self.assertEqual(installer.FILES_V3[10:], self.NEW)
        self.assertNotIn(installer.INSTALLER, installer.FILES_V3)
        self.assertEqual(installer.CLOSURES, {
            'v1': (installer.SCHEMA, installer.FILES), 'v2': (installer.SCHEMA_V2, installer.FILES_V2),
            'v3': (installer.SCHEMA_V3, installer.FILES_V3)})

    def test_v3_prepare_deterministic_exact_twelve_committed_blobs(self):
        with self.fixture() as (_, source, revision, destination):
            manifest, payloads, sha = self.prepare(source, revision, destination, 'v3')
            (source / 'tooling/unlisted.py').write_text('unlisted\n')
            for name in self.NEW:
                (source / name).write_text('uncommitted content must not be installed\n')
            self.assertEqual(self.prepare(source, revision, destination, 'v3'), (manifest, payloads, sha))
            self.assertEqual(manifest['schema'], installer.SCHEMA_V3)
            self.assertEqual(set(manifest), {'schema', 'repository', 'revision', 'files', 'installer'})
            self.assertEqual(manifest['revision'], revision)
            self.assertEqual([record['path'] for record in manifest['files']], list(installer.FILES_V3))
            self.assertEqual(list(payloads), list(installer.FILES_V3))
            for record in manifest['files']:
                listing = git(source, 'ls-tree', revision, '--', record['path']).split()
                self.assertEqual((listing[0], listing[2]), (record['source_mode'], record['blob_oid']))
                self.assertEqual(payloads[record['path']], synthetic(record['path']))
                self.assertEqual(record['mode'], '0444')
            self.assertEqual(manifest['installer']['sha256'],
                             installer.digest((ROOT / installer.INSTALLER).read_bytes()))
            v2, _ = installer.prepare(source, revision, destination, 'v2')
            self.assertEqual(manifest['files'][:10], v2['files'])
            self.assertEqual(manifest['installer'], v2['installer'])
            self.assertEqual(list(destination.iterdir()), [])

    def test_v3_install_then_verify_create_only(self):
        with self.fixture() as (_, source, revision, destination):
            manifest, _, sha = self.prepare(source, revision, destination, 'v3')
            self.assertEqual(installer.install(source, revision, destination, sha, 'v3'), manifest)
            release = destination / sha
            self.assertEqual(installer.verify(release, sha, 'v3'), manifest)
            self.assertEqual({path.relative_to(release) for path in release.rglob('*')},
                             {Path('release.json'), Path('tooling'),
                              *(Path(name) for name in installer.FILES_V3)})
            for name in installer.FILES_V3:
                self.assertEqual((release / name).read_bytes(), synthetic(name))
                self.assertEqual((release / name).stat().st_mode & 0o777, 0o444)
            self.assertEqual((release / 'tooling').stat().st_mode & 0o777, 0o555)
            self.assertEqual(release.stat().st_mode & 0o777, 0o555)
            self.assertEqual(sorted(path.name for path in destination.iterdir()), [sha])
            before = snapshot(destination)
            installer.install(source, revision, destination, sha, 'v3')
            self.assertEqual(snapshot(destination), before)

    def test_cross_v1_v2_v3_verify_and_install_rejected(self):
        with self.fixture() as (_, source, revision, destination):
            shas = {closure: self.prepare(source, revision, destination, closure)[2]
                    for closure in ('v1', 'v2', 'v3')}
            self.assertEqual(len(set(shas.values())), 3)
            for closure, sha in shas.items():
                installer.install(source, revision, destination, sha, closure)
            before = snapshot(destination)
            for built, sha in shas.items():
                for selected in set(shas) - {built}:
                    with self.subTest(built=built, selected=selected):
                        with self.assertRaisesRegex(installer.InstallError, 'release_closure_mismatch'):
                            installer.verify(destination / sha, sha, selected)
                        with self.assertRaisesRegex(installer.InstallError, 'manifest_digest_mismatch'):
                            installer.install(source, revision, destination, sha, selected)
            with self.assertRaisesRegex(installer.InstallError, 'release_closure_mismatch'):
                installer.verify(destination / shas['v3'], shas['v3'])
            for closure in ('v4', 'V3', 'v3 ', ''):
                with self.subTest(closure=closure), self.assertRaisesRegex(
                        installer.InstallError, 'invalid_closure_selection'):
                    installer.verify(destination / shas['v3'], shas['v3'], closure)
            self.assertEqual(snapshot(destination), before)

    def test_v3_relabelled_or_wrong_length_manifest_rejected(self):
        with self.fixture() as (_, source, revision, destination):
            v2, _ = installer.prepare(source, revision, destination, 'v2')
            v3, _ = installer.prepare(source, revision, destination, 'v3')
            installer.validate_manifest(v3, 'v3')
            for value, closure in (({**v3, 'schema': installer.SCHEMA_V2}, 'v2'),
                                   ({**v2, 'schema': installer.SCHEMA_V3}, 'v3'),
                                   ({**v3, 'files': v3['files'][:11]}, 'v3'),
                                   ({**v3, 'files': v3['files'][::-1]}, 'v3')):
                with self.subTest(closure=closure, length=len(value['files'])), self.assertRaisesRegex(
                        installer.InstallError, 'invalid_closure|invalid_manifest_record'):
                    installer.validate_manifest(value, closure)

    def test_missing_either_new_module_rejected(self):
        for missing in self.NEW:
            for kind in ('missing', 'symlink'):
                with self.subTest(missing=missing, kind=kind), self.fixture() as (_, source, _, destination):
                    (source / missing).unlink()
                    if kind == 'symlink':
                        (source / missing).symlink_to('graph_read.py')
                    revision = self.commit_change(source, 'invalid v3 closure fixture')
                    with self.assertRaisesRegex(installer.InstallError, 'missing_or_nonregular_source_blob'):
                        installer.prepare(source, revision, destination, 'v3')
                    self.assertEqual(len(installer.prepare(source, revision, destination, 'v2')[0]['files']), 10)
                    self.assertEqual(list(destination.iterdir()), [])

    def test_oversize_new_module_rejected(self):
        for oversize in self.NEW:
            with self.subTest(oversize=oversize), self.fixture() as (_, source, _, destination):
                (source / oversize).write_bytes(b'#' * (installer.MAX_BLOB + 1))
                revision = self.commit_change(source, 'oversize v3 helper fixture')
                with self.assertRaisesRegex(installer.InstallError, 'source_blob_limit'):
                    installer.prepare(source, revision, destination, 'v3')
                self.assertEqual(list(destination.iterdir()), [])

    def test_v3_installer_provenance_and_origin_still_bound(self):
        with self.fixture() as (_, source, revision, destination):
            git(source, 'remote', 'set-url', 'origin', 'https://example.invalid/Other/repo.git')
            with self.assertRaisesRegex(installer.InstallError, 'source_repository_mismatch'):
                installer.prepare(source, revision, destination, 'v3')
            git(source, 'remote', 'set-url', 'origin', 'https://github.com/Jones-Systems/Graphify.git')
            (source / installer.INSTALLER).write_text('# different installer\n')
            revision = self.commit_change(source, 'different installer fixture')
            with self.assertRaisesRegex(installer.InstallError, 'installer_revision_mismatch'):
                installer.prepare(source, revision, destination, 'v3')
            self.assertEqual(list(destination.iterdir()), [])

    def test_v3_verify_rejects_tamper(self):
        for mutation in ('bytes', 'mode', 'extra', 'missing', 'installer', 'directory_mode'):
            with self.subTest(mutation=mutation), self.fixture() as (_, source, revision, destination):
                _, _, sha = self.prepare(source, revision, destination, 'v3')
                installer.install(source, revision, destination, sha, 'v3')
                release = destination / sha
                module = release / self.NEW[0]
                if mutation == 'bytes':
                    module.chmod(0o644)
                    module.write_bytes(synthetic(self.NEW[1]))
                    module.chmod(0o444)
                elif mutation == 'mode':
                    module.chmod(0o644)
                elif mutation in ('extra', 'missing'):
                    module.parent.chmod(0o755)
                    if mutation == 'extra':
                        (module.parent / 'extra.py').write_text('extra')
                    else:
                        (release / self.NEW[1]).unlink()
                    module.parent.chmod(0o555)
                elif mutation == 'installer':
                    path = release / 'release.json'
                    manifest = json.loads(path.read_bytes())
                    manifest['installer']['sha256'] = 'f' * 64
                    path.chmod(0o644)
                    path.write_bytes(installer.encoded(manifest) + b'\n')
                    path.chmod(0o444)
                else:
                    module.parent.chmod(0o755)
                with self.assertRaises((installer.InstallError, OSError)):
                    installer.verify(release, sha, 'v3')

    def test_cli_v3_closure_selection(self):
        with self.fixture() as (_, source, revision, destination):
            command = [sys.executable, '-B', str(ROOT / installer.INSTALLER)]
            common = ['--source', str(source), '--revision', revision, '--destination', str(destination)]
            def run(arguments, code=0):
                result = subprocess.run(arguments, capture_output=True, text=True, timeout=30,
                                        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
                self.assertEqual(result.returncode, code, result.stderr + result.stdout)
                return json.loads(result.stdout) if result.stdout else None
            prepared = run([*command, 'prepare', *common, '--closure', 'v3'])
            self.assertEqual([record['path'] for record in prepared['manifest']['files']],
                             list(installer.FILES_V3))
            sha = prepared['manifest_sha256']
            installed = run([*command, 'install', *common, '--manifest-sha256', sha, '--closure', 'v3'])
            self.assertEqual((installed['status'], installed['manifest']), ('installed', prepared['manifest']))
            verify = [*command, 'verify', '--release', str(destination / sha), '--manifest-sha256', sha]
            self.assertEqual(run([*verify, '--closure', 'v3'])['status'], 'verified')
            for selected in ([], ['--closure', 'v1'], ['--closure', 'v2']):
                with self.subTest(selected=selected):
                    self.assertEqual(run([*verify, *selected], 1),
                                     {'status': 'error', 'reason': 'release_closure_mismatch'})

    def test_real_twelve_helper_release_runs_from_release_only(self):
        """Real helper bytes: CLIs and the family-2 languages load resolve inside the release."""
        real = lambda name: (ROOT / name).read_bytes()
        with closure_fixture(real, '.portable-install-v3-real-test-') as (root, source, revision, destination):
            shas = {closure: self.prepare(source, revision, destination, closure)[2] for closure in ('v2', 'v3')}
            for closure, sha in shas.items():
                installer.install(source, revision, destination, sha, closure)
            release = destination / shas['v3']
            before = snapshot(release)
            outside = root / 'outside'
            outside.mkdir()
            def run(arguments, code=0, flags=('-E', '-s', '-B')):
                # -E/-s drop PYTHONPATH and user site but keep the script directory first.
                result = subprocess.run([sys.executable, *flags, *arguments], capture_output=True,
                                        text=True, timeout=60, cwd=outside, env={'PATH': os.environ['PATH']})
                self.assertEqual(result.returncode, code, result.stderr + result.stdout)
                return result
            for name in ('graph_pack.py', 'graph_refresh_incremental.py', 'semantic_batch.py'):
                with self.subTest(name=name):
                    self.assertIn('usage:', run([str(release / 'tooling' / name), '--help']).stdout)
            for name in ('graph_refresh_incremental.py', 'semantic_batch.py'):
                with self.subTest(name=name, isolated=True):
                    self.assertIn('usage:', run([str(release / 'tooling' / name), '--help'],
                                                flags=('-I', '-B')).stdout)
            probe = ('import os, sys; tooling = sys.argv[1]; sys.path.insert(0, tooling); '
                     'import refresh_adapter_structural as adapter; languages = adapter.load_languages(); '
                     'import semantic_batch, graph_refresh_incremental; '
                     'modules = (adapter, semantic_batch, graph_refresh_incremental, sys.modules["graph_pack"], '
                     'sys.modules["graph_read"], sys.modules["runtime_identity"], sys.modules["fragment_cache"]); '
                     'assert all(os.path.dirname(os.path.realpath(m.__file__)) == tooling for m in modules); '
                     'assert os.path.dirname(languages.__file__) == tooling; print("ok")')
            tooling = os.path.realpath(release / 'tooling')
            self.assertEqual(run(['-c', probe, tooling], flags=('-I', '-B')).stdout.strip(), 'ok')
            missing = run(['-c', probe, os.path.realpath(destination / shas['v2'] / 'tooling')], 1,
                          flags=('-I', '-B'))
            self.assertIn('structural_languages.py', missing.stderr)
            self.assertEqual(snapshot(release), before)
            self.assertEqual(list(release.rglob('__pycache__')), [])


if __name__ == '__main__':
    unittest.main()
