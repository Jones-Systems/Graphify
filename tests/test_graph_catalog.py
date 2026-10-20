from contextlib import contextmanager, redirect_stdout
import io
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tooling'))
import graph_catalog as catalogs
import graph_pack as packer
import graph_pull as puller
import graph_read as reader

REPOSITORIES = (('Owner/Zeta', 'c' * 40), ('Owner/Alpha', 'a' * 40), ('Other/Mid', 'b' * 40))


@contextmanager
def workspace():
    # Synthetic packages only, under this checkout (or a caller-selected task root),
    # never /tmp; TemporaryDirectory removes its own children on every exit path.
    parent = os.environ.get('GRAPHIFY_PACK_TEST_ROOT', str(Path(__file__).resolve().parents[1]))
    with tempfile.TemporaryDirectory(prefix='graph-catalog-test-', dir=parent) as directory:
        yield Path(directory)


def build_package(root, repository, head, label='node'):
    """Create one real pack() output from synthetic inputs; return (package path, sha)."""
    source = dict(repository=repository, head=head)
    documents = dict(
        graph=dict(built_at_commit=head, directed=True, source=source,
                   nodes=[dict(id='a', source_file='a.py', label=label), dict(id='b')],
                   links=[dict(source='a', target='b', relation='calls')]),
        validation=dict(source=source, status='partial', limitations=['synthetic'],
                        covered_segments_by_file={'a.py': [[1, 2]]}),
        inventory=dict(schema='graphify-pack-inventory/v1', source=source,
                       files=[dict(path='a.py', sha256='1' * 64, coverage='structural')],
                       limitations=['synthetic']),
        policy=dict(schema='graphify-pack-policy/v1', source=source, name='policy',
                    rules={}, limitations=[]),
        extractor=dict(schema='graphify-pack-extractor/v1', source=source, name='synthetic',
                       version=None, artifact_sha256=None, limitations=['no extraction']),
    )
    documents['source'] = dict(
        schema='graphify-pack-source/v1', source=source, build_observation=None,
        limitations=['caller supplied'],
        input_sha256={n: reader.digest(packer.encoded(v)) for n, v in documents.items()})
    inputs = {}
    directory = root / ('inputs-' + repository.replace('/', '-') + '-' + head[:4] + label)
    directory.mkdir()
    for name, value in documents.items():
        raw = packer.encoded(value)
        (directory / (name + '.json')).write_bytes(raw)
        inputs[name] = (directory / (name + '.json'), reader.digest(raw))
    store = directory.with_name(directory.name.replace('inputs-', 'package-'))
    result = packer.pack(inputs, store)
    return store / 'package.json', result['package_sha256']


def build_all(root):
    return [build_package(root, repo, head) for repo, head in REPOSITORIES]


def rewrite_package(path, mutate):
    package = json.loads(path.read_bytes())
    mutate(package)
    raw = packer.encoded(package)
    path.write_bytes(raw)
    return path, reader.digest(raw)


def cli(selection, destination):
    args = ['--destination', str(destination)]
    for path, sha in selection:
        args.extend(['--package', str(path), sha])
    return args


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob('*'))
            if p.is_file()}


class GraphCatalogTests(unittest.TestCase):
    def test_multi_package_reader_pull_and_exact_archives(self):
        with workspace() as root:
            selection = build_all(root)
            before = snapshot(root)
            result = catalogs.assemble(selection, root / 'catalog')
            self.assertEqual({k: v for k, v in snapshot(root).items() if k in before}, before)
            self.assertEqual(result['status'], 'ok')
            self.assertEqual(result['repositories'], sorted(r for r, _ in REPOSITORIES))
            catalog_path = root / 'catalog' / 'download-catalog.json'
            raw = catalog_path.read_bytes()
            self.assertEqual(reader.digest(raw), result['catalog_sha256'])
            catalog, sha = reader.load_catalog(catalog_path, result['catalog_sha256'])
            self.assertEqual(catalog['schema'], 'private-graph-download-catalog/v1')
            self.assertEqual(catalog['archive_directory'], 'archives')
            self.assertEqual(catalog['empty_repositories'], [])
            self.assertEqual({p.name for p in (root / 'catalog').iterdir()},
                             {'archives', 'download-catalog.json', 'assembly.json'})
            for (path, package_sha), (repo, head) in zip(selection, REPOSITORIES):
                package = json.loads(path.read_bytes())
                entry = next(e for e in catalog['archives'] if e['source']['repository'] == repo)
                self.assertEqual(entry, package['archive'])
                self.assertEqual(entry['source'], dict(repository=repo, head=head))
                self.assertEqual((root / 'catalog' / 'archives' / entry['archive']).read_bytes(),
                                 (path.parent / 'archives' / entry['archive']).read_bytes())
                _, _, graph_sha, _ = reader.read_graph(catalog_path, entry)
                self.assertEqual(graph_sha, package['graph_sha256'])
                listed = next(p for p in result['packages'] if p['source']['repository'] == repo)
                self.assertEqual(listed['package_sha256'], package_sha)
                self.assertEqual(listed['archive_sha256'], entry['sha256'])
            assembly = json.loads((root / 'catalog' / 'assembly.json').read_bytes())
            self.assertEqual(reader.digest((root / 'catalog' / 'assembly.json').read_bytes()),
                             result['assembly_sha256'])
            self.assertEqual(assembly['catalog_sha256'], sha)
            self.assertEqual(assembly['freshness'], 'unknown')
            for item in assembly['packages']:
                self.assertEqual(item['qualification']['freshness'], 'unknown')
                self.assertEqual(item['qualification']['provenance_status'],
                                 'caller_supplied_not_attested')
            query = reader.query(reader.parser().parse_args([
                '--catalog', str(catalog_path), '--catalog-sha256', sha,
                '--repo', 'Other/Mid', 'node', '--id', 'a']))
            self.assertEqual(query['source_head'], 'b' * 40)
            self.assertEqual(query['freshness']['status'], 'unknown')
            listing = reader.query(reader.parser().parse_args(['--catalog', str(catalog_path), 'list']))
            self.assertEqual(len(listing['results']), 3)
            pulled = puller.pull(catalog_path, root / 'pulled', ['Owner/Alpha', 'Owner/Zeta'], sha)
            self.assertEqual(pulled['repositories'], ['Owner/Alpha', 'Owner/Zeta'])
            self.assertEqual(pulled['upstream_catalog_sha256'], sha)

    def test_deterministic_bytes_independent_of_selection_order(self):
        with workspace() as root:
            selection = build_all(root)
            first = catalogs.assemble(selection, root / 'first')
            second = catalogs.assemble(list(reversed(selection)), root / 'second')
            self.assertEqual(first['catalog_sha256'], second['catalog_sha256'])
            self.assertEqual(first['assembly_sha256'], second['assembly_sha256'])
            self.assertEqual(snapshot(root / 'first'), snapshot(root / 'second'))

    def test_cli_success_and_error_envelopes(self):
        with workspace() as root:
            selection = build_all(root)[:2]
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(catalogs.main(cli(selection, root / 'store')), 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result['catalog_sha256'],
                             reader.digest((root / 'store' / 'download-catalog.json').read_bytes()))
            self.assertEqual([p['package_sha256'] for p in result['packages']],
                             [sha for _, sha in sorted(selection, key=lambda s: json.loads(
                                 s[0].read_bytes())['source']['repository'])])
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(catalogs.main(cli([(selection[0][0], '0' * 64)], root / 'bad')), 1)
            result = json.loads(output.getvalue())
            self.assertEqual((result['status'], result['effect']), ('error', 'not_completed'))
            self.assertIn('checksum mismatch', result['error'])
            self.assertFalse((root / 'bad').exists())
            with redirect_stdout(io.StringIO()), patch('sys.stderr', io.StringIO()):
                with self.assertRaises(SystemExit):
                    catalogs.main(['--destination', str(root / 'none')])
            self.assertFalse((root / 'none').exists())

    def test_empty_unbounded_relative_and_malformed_selection_rejected(self):
        with workspace() as root:
            path, sha = build_package(root, 'Owner/Alpha', 'a' * 40)
            cases = [([], root / 'out'), ((), root / 'out'), ([(path, 'nothex')], root / 'out'),
                     ([(path,)], root / 'out'), ([(path, sha)], 'relative-out')]
            for packages, destination in cases:
                with self.subTest(packages=packages, destination=destination):
                    with self.assertRaises(ValueError):
                        catalogs.assemble(packages, destination)
            with patch.object(catalogs, 'MAX_PACKAGES', 1):
                with self.assertRaisesRegex(ValueError, 'select 1..1 packages'):
                    catalogs.assemble([(path, sha), build_package(root, 'Owner/B', 'b' * 40)],
                                      root / 'out')
            with patch.object(catalogs, 'MAX_TOTAL_ARCHIVE', 1):
                with self.assertRaisesRegex(ValueError, 'aggregate archive size'):
                    catalogs.assemble([(path, sha)], root / 'out')
            with patch.object(catalogs, 'MAX_ARCHIVE_EXPANDED', 16):
                with self.assertRaisesRegex(ValueError, 'expanded size'):
                    catalogs.assemble([(path, sha)], root / 'out')
            self.assertFalse((root / 'out').exists())
            self.assertFalse(Path('relative-out').exists())

    def test_duplicate_and_colliding_identities_rejected(self):
        with workspace() as root:
            alpha = build_package(root, 'Owner/Alpha', 'a' * 40)
            other_head = build_package(root, 'Owner/Alpha', 'd' * 40)
            case_only = build_package(root, 'owner/alpha', 'e' * 40)
            for selection, message in (([alpha, alpha], 'duplicate package path'),
                                       ([alpha, other_head], 'duplicate repository'),
                                       ([alpha, case_only], 'duplicate repository'),
                                       ([alpha, (other_head[0], alpha[1])], 'duplicate package checksum')):
                with self.subTest(message=message):
                    with self.assertRaisesRegex(ValueError, message):
                        catalogs.assemble(selection, root / 'out')
            self.assertFalse((root / 'out').exists())

    def test_contradictory_package_declarations_rejected(self):
        mutations = [
            ('graph', lambda p: p.update(graph_sha256='0' * 64), 'contradictory package'),
            ('validation', lambda p: p.update(validation_sha256='0' * 64), 'contradictory package'),
            ('input', lambda p: p['input_sha256'].update(graph='0' * 64), 'contradictory package'),
            ('provenance', lambda p: p['input_sha256'].update(policy='0' * 64),
             'archive provenance contradicts'),
            ('qualification', lambda p: p['qualification'].update(freshness='current'),
             'archive provenance contradicts'),
            ('qualification-source', lambda p: p['qualification'].update(
                source=dict(repository='Owner/Other', head='a' * 40)), 'qualification source'),
            ('source', lambda p: p.update(source=dict(repository='Owner/Other', head='a' * 40)),
             'archive source mismatch'),
            ('archive-source', lambda p: p['archive'].update(
                source=dict(repository='Owner/Alpha', head='f' * 40)), 'archive source mismatch'),
            ('archive-name', lambda p: p['archive'].update(archive='other.tar.gz'),
             'archive identity'),
            ('archive-size', lambda p: p['archive'].update(bytes=p['archive']['bytes'] + 1),
             'catalog contradicts'),
            ('catalog', lambda p: p.update(catalog_sha256='0' * 64), 'checksum mismatch'),
            ('schema', lambda p: p.update(schema='graphify-pack-package/v2'), 'package schema'),
            ('extra', lambda p: p.update(extra=True), 'package fields'),
            ('missing', lambda p: p.pop('qualification'), 'package fields'),
        ]
        with workspace() as root:
            path, _ = build_package(root, 'Owner/Alpha', 'a' * 40)
            original = path.read_bytes()
            for name, mutate, message in mutations:
                with self.subTest(name=name):
                    path.write_bytes(original)
                    with self.assertRaisesRegex(ValueError, message):
                        catalogs.assemble([rewrite_package(path, mutate)], root / 'out')
                    self.assertFalse((root / 'out').exists())

    def test_malformed_and_duplicate_json_fields_rejected(self):
        with workspace() as root:
            path, _ = build_package(root, 'Owner/Alpha', 'a' * 40)
            original = path.read_bytes()
            for raw in (b'{', b'[]', original[:-2] + b',"schema":"x"}\n', b'{"x":NaN}'):
                path.write_bytes(raw)
                with self.assertRaises(ValueError):
                    catalogs.assemble([(path, reader.digest(raw))], root / 'out')
            path.write_bytes(original)
            catalog = path.parent / 'download-catalog.json'
            raw = catalog.read_bytes()
            duplicated = raw[:-2] + b',"status":"complete"}\n'
            catalog.write_bytes(duplicated)
            with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
                catalogs.assemble([rewrite_package(path, lambda p: p.update(
                    catalog_sha256=reader.digest(duplicated)))], root / 'out')
            self.assertFalse((root / 'out').exists())

    def test_archive_and_graph_disagreement_rejected(self):
        with workspace() as root:
            path, sha = build_package(root, 'Owner/Alpha', 'a' * 40)
            other, _ = build_package(root, 'Owner/Alpha', 'a' * 40, label='different')
            package = json.loads(path.read_bytes())
            archive = path.parent / 'archives' / package['archive']['archive']
            original = archive.read_bytes()
            archive.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
            with self.assertRaisesRegex(ValueError, 'archive checksum mismatch'):
                catalogs.assemble([(path, sha)], root / 'out')
            archive.unlink()
            with self.assertRaises(OSError):
                catalogs.assemble([(path, sha)], root / 'out')
            # A different package's valid archive under this package's name.
            foreign = json.loads(other.read_bytes())['archive']['archive']
            archive.write_bytes((other.parent / 'archives' / foreign).read_bytes())
            with self.assertRaisesRegex(ValueError, 'archive (size|checksum) mismatch'):
                catalogs.assemble([(path, sha)], root / 'out')
            archive.write_bytes(original)
            with patch.object(catalogs, 'read_graph', return_value=(None, None, '0' * 64, None)):
                with self.assertRaisesRegex(ValueError, 'package graph checksum mismatch'):
                    catalogs.assemble([(path, sha)], root / 'out')
            self.assertFalse((root / 'out').exists())

    def test_existing_destination_and_symlink_destination_untouched(self):
        with workspace() as root:
            selection = build_all(root)
            (root / 'existing').mkdir()
            (root / 'existing' / 'keep').write_bytes(b'preexisting')
            (root / 'file').write_bytes(b'preexisting')
            (root / 'link').symlink_to(root / 'absent')
            for name in ('existing', 'file', 'link'):
                with patch.object(catalogs, 'selected_input', side_effect=AssertionError('no read')):
                    with self.assertRaisesRegex(ValueError, 'destination exists'):
                        catalogs.assemble(selection, root / name)
            self.assertEqual((root / 'existing' / 'keep').read_bytes(), b'preexisting')
            self.assertEqual(list((root / 'existing').iterdir()), [root / 'existing' / 'keep'])
            self.assertEqual((root / 'file').read_bytes(), b'preexisting')
            self.assertTrue((root / 'link').is_symlink())
            (root / 'linked').symlink_to(root, target_is_directory=True)
            with self.assertRaises(OSError):
                catalogs.assemble(selection, root / 'linked' / 'out')
            self.assertFalse((root / 'out').exists())

    def test_symlink_special_and_read_time_changed_inputs_rejected(self):
        with workspace() as root:
            path, sha = build_package(root, 'Owner/Alpha', 'a' * 40)
            (root / 'alias').mkdir()
            (root / 'alias' / 'package.json').symlink_to(path)
            with self.assertRaises(OSError):
                catalogs.assemble([(root / 'alias' / 'package.json', sha)], root / 'out')
            (root / 'linked').symlink_to(path.parent, target_is_directory=True)
            with self.assertRaises(OSError):
                catalogs.assemble([(root / 'linked' / 'package.json', sha)], root / 'out')
            (root / 'fifo').mkdir()
            os.mkfifo(root / 'fifo' / 'package.json')
            with self.assertRaisesRegex(ValueError, 'not a regular file'):
                catalogs.assemble([(root / 'fifo' / 'package.json', sha)], root / 'out')
            catalog = path.parent / 'download-catalog.json'
            moved = path.parent / 'catalog-original.json'
            catalog.rename(moved)
            catalog.symlink_to(moved)
            with self.assertRaises(OSError):
                catalogs.assemble([(path, sha)], root / 'out')
            catalog.unlink()
            moved.rename(catalog)
            with self.assertRaisesRegex(ValueError, 'named package.json'):
                catalogs.assemble([(catalog, sha)], root / 'out')
            calls = iter(range(1000))
            original = packer.signature

            def changing(handle):
                return original(handle) + (next(calls),)

            with patch.object(packer, 'signature', changing):
                with self.assertRaisesRegex(ValueError, 'changed during read'):
                    catalogs.assemble([(path, sha)], root / 'out')
            self.assertFalse((root / 'out').exists())

    def test_failure_and_cancellation_after_creation_cleanup(self):
        with workspace() as root:
            selection = build_all(root)
            before = snapshot(root)
            for error in (OSError('verification failed'), KeyboardInterrupt('cancelled')):
                with patch.object(catalogs, 'verify_assembled', side_effect=error):
                    with self.assertRaises(type(error)):
                        catalogs.assemble(selection, root / 'failed')
                self.assertFalse((root / 'failed').exists())
            original = catalogs.copy_archive
            calls = []

            def fail_second(owned, directory, record):
                calls.append(record)
                original(owned, directory, record)
                if len(calls) == 2:
                    raise OSError('copy failed')

            with patch.object(catalogs, 'copy_archive', fail_second):
                with self.assertRaisesRegex(OSError, 'copy failed'):
                    catalogs.assemble(selection, root / 'failed')
            self.assertFalse((root / 'failed').exists())
            self.assertEqual(snapshot(root), before)

    def test_signal_during_assembly_cleans_owned_output(self):
        with workspace() as root:
            selection = build_all(root)
            for sig in (signal.SIGTERM, signal.SIGINT):
                with patch.object(catalogs, 'verify_assembled',
                                  side_effect=lambda *a: signal.raise_signal(sig)), \
                        redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(catalogs.main(cli(selection, root / 'cancelled')), 1)
                result = json.loads(output.getvalue())
                self.assertEqual((result['effect'], result['error']), ('not_completed', 'cancelled'))
                self.assertFalse((root / 'cancelled').exists())

    def test_foreign_entry_replacement_and_cleanup_failure_report_unknown(self):
        with workspace() as root:
            selection = build_all(root)

            def interfere(*args):
                (root / 'failed' / 'foreign').write_bytes(b'not owned')
                raise OSError('original failure')

            with patch.object(catalogs, 'verify_assembled', side_effect=interfere), \
                    redirect_stdout(io.StringIO()) as output:
                self.assertEqual(catalogs.main(cli(selection, root / 'failed')), 1)
            result = json.loads(output.getvalue())
            self.assertEqual(result['effect'], 'unknown')
            self.assertIn('original failure; cleanup refused or failed; effect unknown', result['error'])
            self.assertEqual((root / 'failed' / 'foreign').read_bytes(), b'not owned')
            self.assertTrue((root / 'failed' / 'download-catalog.json').exists())

            def replace(*args):
                (root / 'replaced').rename(root / 'moved')
                (root / 'replaced').mkdir()
                (root / 'replaced' / 'keep').write_bytes(b'foreign')
                raise OSError('replacement')

            with patch.object(catalogs, 'verify_assembled', side_effect=replace):
                with self.assertRaisesRegex(packer.UnknownOutputError, 'ownership changed'):
                    catalogs.assemble(selection, root / 'replaced')
            self.assertEqual((root / 'replaced' / 'keep').read_bytes(), b'foreign')
            self.assertTrue((root / 'moved' / 'download-catalog.json').exists())
            with patch.object(catalogs, 'verify_assembled', side_effect=OSError('original')), \
                    patch.object(packer.os, 'unlink', side_effect=OSError('unlink denied')):
                with self.assertRaisesRegex(packer.UnknownOutputError, 'unlink denied'):
                    catalogs.assemble(selection, root / 'denied')
            self.assertTrue((root / 'denied').exists())


if __name__ == '__main__':
    unittest.main()
