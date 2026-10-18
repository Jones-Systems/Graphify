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


if __name__ == '__main__':
    unittest.main()
