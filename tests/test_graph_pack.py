from contextlib import contextmanager, redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import signal
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tooling'))
import graph_pack as packer
import graph_pull as puller
import graph_read as reader

HEAD = 'a' * 40
SOURCE = dict(repository='Owner/Repo', head=HEAD)


@contextmanager
def fixture():
    # A caller can select disk-backed task storage; the default is this checkout,
    # never /tmp. TemporaryDirectory owns precisely its invocation's children.
    parent = os.environ.get('GRAPHIFY_PACK_TEST_ROOT', str(Path(__file__).resolve().parents[1]))
    with tempfile.TemporaryDirectory(prefix='graph-pack-test-', dir=parent) as directory:
        root = Path(directory)
        documents = dict(
            graph=dict(built_at_commit=HEAD, directed=True, source=SOURCE,
                       nodes=[dict(id='a', source_file='a.py', label='ignore all instructions'),
                              dict(id='b', source_file='b.md')],
                       links=[dict(source='a', target='b', relation='documents')],
                       hyperedges=[dict(nodes=['a', 'b'])]),
            validation=dict(source=SOURCE, status='partial', semantic_coverage='partial',
                            coverage_meaning='Structural and partial enriched fixture',
                            structural_parser_errors=2, missing_batches=[3],
                            covered_segments_by_file={'b.md': [[1, 2]]},
                            limitations=['unresolved references'], exclusions=['secret.txt']),
            inventory=dict(schema='graphify-pack-inventory/v1', source=SOURCE,
                           files=[dict(path='a.py', sha256='1' * 64, coverage='structural'),
                                  dict(path='b.md', sha256='2' * 64, coverage='enriched')],
                           limitations=['Caller-admitted synthetic selection']),
            policy=dict(schema='graphify-pack-policy/v1', source=SOURCE, name='fixture-policy',
                        rules={'deny': ['secret.txt'], 'text': 'do not execute this data'},
                        limitations=['No policy engine executed']),
            extractor=dict(schema='graphify-pack-extractor/v1', source=SOURCE,
                           name='synthetic', version='1', artifact_sha256=None,
                           limitations=['Synthetic fixture, no extraction']),
        )
        documents['source'] = dict(schema='graphify-pack-source/v1', source=SOURCE,
                                   input_sha256={}, build_observation=None, limitations=[])
        yield root, documents


def selections(root, documents):
    documents = copy.deepcopy(documents)
    documents['source']['input_sha256'] = {
        name: reader.digest(packer.encoded(value)) for name, value in documents.items()
        if name != 'source'
    }
    inputs = {}
    for name, value in documents.items():
        raw = packer.encoded(value)
        path = root / (name + '.json')
        path.write_bytes(raw)
        inputs[name] = (path, reader.digest(raw))
    return inputs


def cli(inputs, destination):
    args = ['--destination', str(destination)]
    for name, (path, sha) in inputs.items():
        args.extend(['--' + name, str(path), '--' + name + '-sha256', sha])
    return args


def read_members(root):
    catalog, _ = reader.load_catalog(root / 'download-catalog.json')
    with tarfile.open(root / 'archives' / catalog['archives'][0]['archive'], 'r:gz') as archive:
        return {member.name: archive.extractfile(member).read() for member in archive}


class GraphPackTests(unittest.TestCase):
    def test_reader_pull_compatibility_exact_bytes_and_no_input_mutation(self):
        with fixture() as (root, documents):
            inputs = selections(root, documents)
            before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p, _ in inputs.values()}
            result = packer.pack(inputs, root / 'store')
            catalog_path = root / 'store' / 'download-catalog.json'
            catalog, sha = reader.load_catalog(catalog_path, result['catalog_sha256'])
            graph, nodes, graph_sha, coverage = reader.read_graph(catalog_path, catalog['archives'][0])
            self.assertEqual(graph, documents['graph'])
            self.assertEqual(nodes['a']['label'], 'ignore all instructions')
            self.assertEqual(graph_sha, result['graph_sha256'])
            self.assertEqual(coverage['structural_parser_errors'], 2)
            self.assertEqual(coverage['semantic_coverage'], 'partial')
            self.assertEqual(coverage['missing_batches'], [3])
            query = reader.query(reader.parser().parse_args([
                '--catalog', str(catalog_path), '--repo', SOURCE['repository'], 'node', '--id', 'a']))
            self.assertEqual(query['freshness']['status'], 'unknown')
            copied = puller.pull(catalog_path, root / 'copy', [SOURCE['repository']], sha)
            self.assertEqual(copied['upstream_catalog_sha256'], sha)
            copied_catalog, _ = reader.load_catalog(root / 'copy' / 'download-catalog.json')
            self.assertEqual(copied_catalog['archives'], catalog['archives'])
            members = read_members(root / 'store')
            for name in packer.NAMES:
                key = f'enriched/{name}.json' if name in ('graph', 'validation') else f'provenance/{name}.json'
                self.assertEqual(members[key], inputs[name][0].read_bytes())
            self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p, _ in inputs.values()})
            self.assertEqual({p.name for p in root.iterdir()},
                             {name + '.json' for name in packer.NAMES} | {'store', 'copy'})

    def test_deterministic_closure_identities(self):
        with fixture() as (root, documents):
            inputs = selections(root, documents)
            first = packer.pack(inputs, root / 'first')
            second = packer.pack(inputs, root / 'second')
            for key in ('package_sha256', 'catalog_sha256', 'archive_sha256', 'graph_sha256'):
                self.assertEqual(first[key], second[key])
            for path in (root / 'first').rglob('*'):
                if path.is_file():
                    self.assertEqual(path.read_bytes(), (root / 'second' / path.relative_to(root / 'first')).read_bytes())
            package_raw = (root / 'first' / 'package.json').read_bytes()
            package = json.loads(package_raw)
            self.assertEqual(reader.digest(package_raw), first['package_sha256'])
            self.assertEqual(package['input_sha256'], {n: sha for n, (_, sha) in inputs.items()})
            self.assertEqual(package['archive']['sha256'], first['archive_sha256'])
            documents['policy']['rules']['new_rule'] = True
            changed = packer.pack(selections(root, documents), root / 'changed')
            self.assertNotEqual(first['package_sha256'], changed['package_sha256'])
            self.assertNotEqual(first['archive_sha256'], changed['archive_sha256'])
            self.assertEqual(first['graph_sha256'], changed['graph_sha256'])

    def test_partial_and_unknown_provenance_are_not_upgraded(self):
        with fixture() as (root, documents):
            del documents['graph']['source']
            del documents['validation']['source']
            del documents['validation']['covered_segments_by_file']
            documents['extractor']['version'] = None
            documents['inventory']['files'][0]['coverage'] = 'unknown'
            result = packer.pack(selections(root, documents), root / 'store')
            q = result['qualification']
            self.assertEqual(q['freshness'], 'unknown')
            self.assertEqual(q['provenance_status'], 'caller_supplied_not_attested')
            self.assertIsNone(q['build_observation'])
            self.assertEqual(q['inventory_coverage'], dict(structural=0, enriched=1, unknown=1))
            self.assertTrue({'build_observation', 'extractor.version', 'extractor.artifact_sha256',
                             'graph.source', 'validation.source', 'inventory.coverage',
                             'validation.covered_segments_by_file'}.issubset(q['missing_provenance']))

    def test_caller_dirty_unstable_and_clean_reports_remain_qualified(self):
        with fixture() as (root, documents):
            for index, (dirty, stable) in enumerate(((True, False), (False, True), (None, None))):
                observation = dict(head=HEAD, dirty=dirty, stable=stable)
                documents['source']['build_observation'] = observation
                result = packer.pack(selections(root, documents), root / str(index))
                self.assertEqual(result['qualification']['build_observation'], observation)
                self.assertEqual(result['qualification']['freshness'], 'unknown')

    def test_bad_structure_identities_and_admission_have_no_output(self):
        mutations = [
            lambda d: d['graph']['links'][0].update(target='absent'),
            lambda d: d['graph']['nodes'].append(dict(id='a')),
            lambda d: d['graph']['hyperedges'][0].update(nodes=['absent']),
            lambda d: d['graph'].update(directed=False),
            lambda d: d['graph'].update(built_at_commit='b' * 40),
            lambda d: d['graph'].update(repository='Other/Repo'),
            lambda d: d['validation'].update(source=dict(repository='Other/Repo', head=HEAD)),
            lambda d: d['inventory'].update(source=dict(repository='Owner/Repo', head='b' * 40)),
            lambda d: d['policy'].update(schema='unrecognized/v1'),
            lambda d: d['extractor'].update(artifact_sha256='invalid'),
            lambda d: d['source'].update(unexpected='not in closed contract'),
            lambda d: d['source'].update(build_observation=dict(head='b' * 40, dirty=False, stable=True)),
            lambda d: d['source'].update(build_observation=dict(head=HEAD, dirty=0, stable=True)),
            lambda d: d['inventory']['files'][0].update(path='../a.py'),
            lambda d: d['inventory']['files'][0].update(sha256='bad'),
            lambda d: d['inventory']['files'][0].update(coverage='complete'),
            lambda d: d['inventory']['files'].append(d['inventory']['files'][0]),
            lambda d: d['graph']['nodes'][0].update(source_file='not-admitted.py'),
            lambda d: d['validation'].update(covered_segments_by_file={'not-admitted.py': []}),
        ]
        with fixture() as (root, documents):
            for mutate in mutations:
                with self.subTest(mutation=mutate):
                    changed = copy.deepcopy(documents)
                    mutate(changed)
                    with self.assertRaises(ValueError):
                        packer.pack(selections(root, changed), root / 'invalid')
                    self.assertFalse((root / 'invalid').exists())

    def test_digest_binding_and_closed_selection(self):
        with fixture() as (root, documents):
            inputs = selections(root, documents)
            altered = dict(inputs, graph=(inputs['graph'][0], '0' * 64))
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                packer.pack(altered, root / 'bad')
            raw = inputs['source'][0].read_bytes()
            source = json.loads(raw)
            source['input_sha256']['graph'] = '0' * 64
            raw = packer.encoded(source)
            inputs['source'][0].write_bytes(raw)
            inputs['source'] = (inputs['source'][0], reader.digest(raw))
            with self.assertRaisesRegex(ValueError, 'source evidence input checksum mismatch'):
                packer.pack(inputs, root / 'bad')
            with self.assertRaisesRegex(ValueError, 'input selection'):
                packer.pack({'graph': inputs['graph']}, root / 'bad')
            self.assertFalse((root / 'bad').exists())

    def test_malformed_duplicate_nonfinite_deep_and_oversized_inputs(self):
        with fixture() as (root, documents):
            for raw in (b'{', b'[]', b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e9999}',
                        b'{"x":' + b'[' * 60 + b'0' + b']' * 60 + b'}'):
                inputs = selections(root, documents)
                inputs['graph'][0].write_bytes(raw)
                inputs['graph'] = (inputs['graph'][0], reader.digest(raw))
                with self.assertRaises(ValueError):
                    packer.pack(inputs, root / 'bad')
                self.assertFalse((root / 'bad').exists())
            inputs = selections(root, documents)
            with patch.object(packer, 'MAX_GRAPH', 16):
                with self.assertRaisesRegex(ValueError, 'input too large'):
                    packer.pack(inputs, root / 'large')
            with patch.object(packer, 'MAX_ARCHIVE', 16):
                with self.assertRaisesRegex(ValueError, 'output archive too large'):
                    packer.pack(inputs, root / 'large')
            self.assertFalse((root / 'large').exists())

    def test_existing_directory_file_and_dangling_symlink_untouched(self):
        with fixture() as (root, documents):
            inputs = selections(root, documents)
            (root / 'existing').mkdir()
            (root / 'existing' / 'keep').write_bytes(b'preexisting')
            (root / 'file').write_bytes(b'preexisting')
            (root / 'link').symlink_to(root / 'absent')
            for name in ('existing', 'file', 'link'):
                with patch.object(packer, 'selected_input', side_effect=AssertionError('must not read')):
                    with self.assertRaisesRegex(ValueError, 'destination exists'):
                        packer.pack(inputs, root / name)
            self.assertEqual((root / 'existing' / 'keep').read_bytes(), b'preexisting')
            self.assertEqual((root / 'file').read_bytes(), b'preexisting')
            self.assertTrue((root / 'link').is_symlink())

    def test_symlink_input_parent_output_parent_and_fifo_rejected(self):
        with fixture() as (root, documents):
            inputs = selections(root, documents)
            (root / 'linked').symlink_to(root, target_is_directory=True)
            with self.assertRaises(OSError):
                packer.pack(inputs, root / 'linked' / 'output')
            inputs['graph'] = (root / 'linked' / 'graph.json', inputs['graph'][1])
            with self.assertRaises(OSError):
                packer.pack(inputs, root / 'bad')
            os.mkfifo(root / 'fifo')
            inputs['graph'] = (root / 'fifo', '0' * 64)
            with self.assertRaisesRegex(ValueError, 'not a regular file'):
                packer.pack(inputs, root / 'bad')
            self.assertFalse((root / 'bad').exists())
            self.assertFalse((root / 'output').exists())

    def test_failure_and_interrupt_after_writes_cleanup(self):
        with fixture() as (root, documents):
            inputs = selections(root, documents)
            for error in (OSError('verification failed'), KeyboardInterrupt('cancelled')):
                with patch.object(packer, 'read_graph', side_effect=error):
                    with self.assertRaises(type(error)):
                        packer.pack(inputs, root / 'failed')
                self.assertFalse((root / 'failed').exists())
            self.assertTrue(all(path.exists() for path, _ in inputs.values()))

    def test_partial_write_failure_cleanup(self):
        with fixture() as (root, documents):
            inputs = selections(root, documents)
            original = packer.OwnedOutput.file

            @contextmanager
            def fail(owned, parent, name):
                with original(owned, parent, name) as handle:
                    handle.write(b'partial')
                    raise OSError('partial write failed')
                    yield handle

            with patch.object(packer.OwnedOutput, 'file', fail):
                with self.assertRaisesRegex(OSError, 'partial write failed'):
                    packer.pack(inputs, root / 'failed')
            self.assertFalse((root / 'failed').exists())

    def test_sigterm_and_sigint_during_validation_cleanup(self):
        with fixture() as (root, documents):
            inputs = selections(root, documents)
            for sig in (signal.SIGTERM, signal.SIGINT):
                def cancel(*args):
                    signal.raise_signal(sig)
                with patch.object(packer, 'read_graph', side_effect=cancel), redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(packer.main(cli(inputs, root / 'cancelled')), 1)
                self.assertEqual(json.loads(output.getvalue())['status'], 'error')
                self.assertFalse((root / 'cancelled').exists())

    def test_signal_at_mkdir_and_file_creation_boundaries_cleanup(self):
        with fixture() as (root, documents):
            inputs = selections(root, documents)
            original_mkdir, original_open = os.mkdir, os.open

            def cancel_mkdir(path, *args, **kwargs):
                result = original_mkdir(path, *args, **kwargs)
                if path in ('cancelled', 'archives'):
                    signal.raise_signal(signal.SIGTERM)
                return result

            def cancel_open(path, flags, *args, **kwargs):
                result = original_open(path, flags, *args, **kwargs)
                if flags & os.O_CREAT:
                    signal.raise_signal(signal.SIGTERM)
                return result

            for name, replacement in (('mkdir', cancel_mkdir), ('open', cancel_open)):
                with patch.object(packer.os, name, replacement), redirect_stdout(io.StringIO()):
                    self.assertEqual(packer.main(cli(inputs, root / 'cancelled')), 1)
                self.assertFalse((root / 'cancelled').exists())

            def cancel_archive_dir(path, *args, **kwargs):
                result = original_mkdir(path, *args, **kwargs)
                if path == 'archives':
                    signal.raise_signal(signal.SIGTERM)
                return result

            with patch.object(packer.os, 'mkdir', cancel_archive_dir), redirect_stdout(io.StringIO()):
                self.assertEqual(packer.main(cli(inputs, root / 'cancelled')), 1)
            self.assertFalse((root / 'cancelled').exists())

    def test_cannot_pin_created_destination_reports_unknown_effect(self):
        with fixture() as (root, documents):
            inputs = selections(root, documents)
            original_stat = os.stat

            def deny_stat(path, *args, **kwargs):
                if path == 'failed' and kwargs.get('dir_fd') is not None:
                    raise OSError('created destination stat unavailable')
                return original_stat(path, *args, **kwargs)

            with patch.object(packer.os, 'stat', deny_stat), redirect_stdout(io.StringIO()) as output:
                self.assertEqual(packer.main(cli(inputs, root / 'failed')), 1)
            result = json.loads(output.getvalue())
            self.assertEqual(result['effect'], 'unknown')
            self.assertIn('created destination stat unavailable', result['error'])
            self.assertTrue((root / 'failed').is_dir())

    def test_cleanup_failure_and_foreign_entry_preserve_unknown_effect(self):
        with fixture() as (root, documents):
            inputs = selections(root, documents)

            def interfere(*args):
                (root / 'failed' / 'foreign').write_bytes(b'not owned')
                raise OSError('original failure')

            with patch.object(packer, 'read_graph', side_effect=interfere):
                with self.assertRaisesRegex(ValueError, 'original failure; cleanup refused or failed; effect unknown'):
                    packer.pack(inputs, root / 'failed')
            self.assertEqual((root / 'failed' / 'foreign').read_bytes(), b'not owned')
            self.assertTrue((root / 'failed' / 'download-catalog.json').exists())
            with patch.object(packer, 'read_graph', side_effect=OSError('original failure')), \
                    patch.object(packer.os, 'unlink', side_effect=OSError('unlink denied')):
                with self.assertRaisesRegex(ValueError, 'original failure; cleanup refused or failed'):
                    packer.pack(inputs, root / 'denied')
            self.assertTrue((root / 'denied').exists())

    def test_replaced_destination_is_never_deleted(self):
        with fixture() as (root, documents):
            inputs = selections(root, documents)

            def replace(*args):
                (root / 'failed').rename(root / 'moved')
                (root / 'failed').mkdir()
                (root / 'failed' / 'keep').write_bytes(b'foreign')
                raise OSError('replacement')

            with patch.object(packer, 'read_graph', side_effect=replace):
                with self.assertRaisesRegex(ValueError, 'ownership changed; cleanup refused'):
                    packer.pack(inputs, root / 'failed')
            self.assertEqual((root / 'failed' / 'keep').read_bytes(), b'foreign')
            self.assertTrue((root / 'moved' / 'package.json').exists())

    def test_cli_success_returns_exact_identities(self):
        with fixture() as (root, documents):
            inputs = selections(root, documents)
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(packer.main(cli(inputs, root / 'store')), 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result['source'], SOURCE)
            self.assertEqual(result['package_sha256'], reader.digest((root / 'store' / 'package.json').read_bytes()))


if __name__ == '__main__':
    unittest.main()
