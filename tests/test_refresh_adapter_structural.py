"""Synthetic source/requests only; fixture contexts own all scratch and children."""
from contextlib import contextmanager
import copy
import hashlib
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

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tooling/refresh_adapter_structural.py'
sys.path[:0] = [str(ROOT / 'tooling'), str(ROOT / 'tests')]
import graph_pack as packer
import graph_pull as puller
import graph_read as reader
import graph_refresh as refresh
from test_graph_refresh import fixture as refresh_fixture, git, run as run_refresh

spec = importlib.util.spec_from_file_location('structural_adapter', SCRIPT)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

CONTENT = {'pkg/__init__.py': b'',
           'pkg/a.py': b'import pkg.b\nimport external\nfrom . import b\nclass Example:\n    async def method(self):\n        def inner():\n            pass\n',
           'pkg/b.py': b'def helper():\n    pass\n',
           'docs/guide.md': b'[source](../pkg/a.py#Example)\n[missing](missing.py)\n[remote](https://example.invalid/)\n',
           'broken.py': b'def invalid(\n', 'data.txt': b'unsupported'}


@contextmanager
def scratch():
    parent = os.environ.get('GRAPHIFY_REFRESH_TEST_ROOT', str(ROOT))
    def cancel(signum, frame):
        raise KeyboardInterrupt('synthetic fixture cancelled')
    previous = signal.signal(signal.SIGTERM, cancel)
    try:
        with tempfile.TemporaryDirectory(prefix='.structural-test-', dir=parent) as name:
            yield Path(name).resolve()
    finally:
        signal.signal(signal.SIGTERM, previous)


def request(root, content=CONTENT):
    stage = root / 'inputs'
    stage.mkdir()
    for name, raw in content.items():
        p = stage / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
    files = [dict(path=p, sha256=adapter.digest(raw)) for p, raw in sorted(content.items())]
    source = dict(repository='Fixture/Source', head='a' * 40)
    sample = dict(root=str(root / 'unopened-source'), head=source['head'], head_after=source['head'],
                  cleanliness='clean', stable=True, status_sha256=adapter.digest(b''))
    return dict(schema='graphify-refresh-request/v1', manifest_sha256='b' * 64, source=source,
                stage=str(stage), files=files,
                policy=dict(schema='graphify-pack-policy/v1', source=source,
                            name='refresh-explicit-selection', limitations=[],
                            rules=dict(allow=files, deny=['private/*'], no_follow=True, git_metadata_denied=True)),
                extractor=dict(protocol='python-json/v1', name=adapter.NAME, version=adapter.VERSION,
                               executable=dict(path=str(Path(sys.executable).resolve()), sha256='c' * 64),
                               script=dict(path=str(SCRIPT), sha256=adapter.digest(SCRIPT.read_bytes()))),
                samples=dict(before=sample, after_capture=sample), limits=dict(adapter.LIMITS, seconds=5))


def invoke(raw):
    return subprocess.run([str(Path(sys.executable).resolve()), '-I', '-B', str(SCRIPT)],
                          input=raw, capture_output=True, timeout=10, env={'LC_ALL': 'C.UTF-8'})


@contextmanager
def integrated_fixture():
    with scratch() as parent:
        with patch.dict(os.environ, {'GRAPHIFY_REFRESH_TEST_ROOT': str(parent)}):
            with refresh_fixture(adapter=SCRIPT.read_text()) as (root, manifest):
                task = manifest['tasks'][0]
                source = Path(task['root'])
                content = dict(CONTENT, **{'a.py': b'def additional():\n    pass\n'})
                for name, raw in content.items():
                    p = source / name
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(raw)
                git(source, 'add', '.')
                git(source, 'commit', '-qm', 'synthetic structural input')
                task['source']['head'] = git(source, 'rev-parse', 'HEAD')
                task['files'] = [dict(path=p, sha256=adapter.digest(raw)) for p, raw in sorted(content.items())]
                task['extractor'].update(name=adapter.NAME, version=adapter.VERSION)
                manifest['limits']['seconds'] = 5
                yield root, manifest


class StructuralAdapterTests(unittest.TestCase):
    def assert_rejected(self, raw):
        result = invoke(raw)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b'')

    def test_deterministic_closed_hash_bound_structural_response(self):
        with scratch() as root:
            r = request(root)
            raw = adapter.encoded(r)
            first, second = invoke(raw), invoke(raw)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(first.stdout, second.stdout)
            result = json.loads(first.stdout)
            self.assertEqual(set(result), {'schema', 'request_sha256', 'graph', 'validation', 'coverage'})
            self.assertEqual(result['request_sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(set(result['coverage']), set(CONTENT))
            self.assertEqual(result['coverage']['broken.py'], 'unknown')
            self.assertEqual(result['coverage']['data.txt'], 'unknown')
            self.assertEqual(set(result['coverage'].values()), {'structural', 'unknown'})
            graph, validation = result['graph'], result['validation']
            self.assertEqual(graph['source'], r['source'])
            self.assertEqual(graph['built_at_commit'], r['source']['head'])
            self.assertEqual(validation['refresh_request_sha256'], result['request_sha256'])
            self.assertEqual(validation['semantic_coverage'], 'none')
            self.assertEqual(validation['structural_parser_errors'], 2)
            nodes = {n['id']: n for n in graph['nodes']}
            self.assertTrue({'Example', 'Example.method', 'Example.method.inner', 'helper'}
                            <= {n['label'] for n in nodes.values()})
            triples = {(nodes[e['source']]['label'], e['type'], nodes[e['target']]['label']) for e in graph['links']}
            self.assertIn(('Example', 'contains', 'Example.method'), triples)
            self.assertIn(('pkg/a.py', 'imports', 'pkg/b.py'), triples)
            self.assertIn(('pkg/a.py', 'imports', 'pkg/__init__.py'), triples)
            self.assertIn(('docs/guide.md', 'links_to', 'pkg/a.py'), triples)
            self.assertTrue(all(n['source_file'] in CONTENT for n in [*graph['nodes'], *graph['links']]))
            self.assertIn('external', {x['target'] for x in validation['unresolved_references']})
            self.assertNotIn('https://example.invalid/', {x['target'] for x in validation['unresolved_references']})

    def test_no_execution_unadmitted_reads_or_staged_mutations(self):
        with scratch() as root:
            marker = root / 'must-not-exist'
            payload = ('from pathlib import Path\nPath(' + repr(str(marker)) + ').touch()\nimport unavailable\n').encode()
            r = request(root, {'a.py': payload})
            stage = Path(r['stage'])
            (stage / 'unadmitted.py').symlink_to(root / 'missing')
            before = (stage / 'a.py').stat()
            result = invoke(adapter.encoded(r))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(marker.exists())
            self.assertEqual(before.st_mtime_ns, (stage / 'a.py').stat().st_mtime_ns)
            self.assertEqual((stage / 'a.py').read_bytes(), payload)
            self.assertFalse(list(root.rglob('__pycache__')))

    def test_invalid_request_admission_and_hash_fail_without_stdout(self):
        with scratch() as root:
            r = request(root)
            invalid = [b'{', b'{"schema":1,"schema":2}', b'[]', b'{"x":NaN}', b'x' * (adapter.MAX_REQUEST + 1)]
            for mutate in (
                lambda d: d.update(schema='wrong'),
                lambda d: d.update(extra=True),
                lambda d: d['source'].update(head='short'),
                lambda d: d['files'].append(d['files'][0]),
                lambda d: d['files'][0].update(path='../escape'),
                lambda d: d['files'][0].update(path='.git/config'),
                lambda d: d['files'][0].update(sha256='0' * 64),
                lambda d: d['policy']['rules'].update(allow=[]),
                lambda d: d['policy']['rules'].update(deny=['*']),
                lambda d: d['policy']['rules'].update(no_follow=False),
                lambda d: d['extractor'].update(name='legacy'),
                lambda d: d['samples']['before'].update(cleanliness='dirty'),
                lambda d: d['limits'].update(output_bytes=True),
            ):
                changed = copy.deepcopy(r)
                mutate(changed)
                invalid.append(adapter.encoded(changed))
            for raw in invalid:
                with self.subTest(raw=raw[:80]):
                    self.assert_rejected(raw)

    def test_symlink_directory_file_hardlink_and_fifo_rejected(self):
        for kind in ('file', 'directory', 'stage', 'hardlink', 'fifo'):
            with self.subTest(kind=kind), scratch() as root:
                r = request(root, {'dir/a.py': b'pass\n'})
                stage = Path(r['stage'])
                selected = stage / 'dir/a.py'
                outside = root / 'outside.py'
                outside.write_bytes(b'pass\n')
                if kind in ('file', 'hardlink', 'fifo'):
                    selected.unlink()
                    if kind == 'file': selected.symlink_to(outside)
                    elif kind == 'hardlink': os.link(outside, selected)
                    else: os.mkfifo(selected)
                elif kind == 'directory':
                    (stage / 'dir').rename(stage / 'real')
                    (stage / 'dir').symlink_to(stage / 'real', target_is_directory=True)
                else:
                    stage.rename(root / 'real-stage')
                    stage.symlink_to(root / 'real-stage', target_is_directory=True)
                self.assert_rejected(adapter.encoded(r))

    def test_input_output_and_record_bounds_fail_without_truncation(self):
        with scratch() as root:
            r = request(root)
            for field in ('file_bytes', 'input_bytes', 'output_bytes'):
                changed = copy.deepcopy(r)
                changed['limits'][field] = 1
                self.assert_rejected(adapter.encoded(changed))
            with patch.object(adapter, 'MAX_RECORDS', 2), self.assertRaisesRegex(ValueError, 'record limit'):
                adapter.respond(adapter.encoded(r))
            with patch.object(adapter, 'MAX_AST_NODES', 1), self.assertRaisesRegex(ValueError, 'AST node limit'):
                adapter.respond(adapter.encoded(r))

    def test_complete_response_output_boundary_and_long_symbol_fail_closed(self):
        with scratch() as root:
            r = request(root, {'a.py': b'def simple():\n    pass\n'})
            size = len(adapter.respond(adapter.encoded(r)))
            r['limits']['output_bytes'] = size
            self.assertEqual(len(adapter.respond(adapter.encoded(r))), size)
            r['limits']['output_bytes'] = size - 1
            self.assert_rejected(adapter.encoded(r))
        with scratch() as root:
            r = request(root, {'a.py': b'def ' + b'a' * 4097 + b'():\n    pass\n'})
            self.assert_rejected(adapter.encoded(r))

    def test_ambiguous_module_and_out_of_package_import_stay_unresolved(self):
        with scratch() as root:
            r = request(root, {'main.py': b'import other\nfrom ..escape import x\n',
                               'other.py': b'pass\n', 'other/__init__.py': b'pass\n'})
            result = json.loads(adapter.respond(adapter.encoded(r)))
            self.assertFalse(result['graph']['links'])
            self.assertEqual({x['target'] for x in result['validation']['unresolved_references']},
                             {'other', '..escape'})

    def test_parser_recursion_and_decode_failures_are_unknown(self):
        with scratch() as root:
            r = request(root, {'a.py': b'pass\n', 'bad.md': b'\xff'})
            with patch.object(adapter.ast, 'parse', side_effect=RecursionError):
                result = json.loads(adapter.respond(adapter.encoded(r)))
            self.assertEqual(result['coverage'], {'a.py': 'unknown', 'bad.md': 'unknown'})
            self.assertEqual(result['validation']['structural_parser_errors'], 2)
            self.assertTrue(all(n['type'] == 'file' for n in result['graph']['nodes']))

    def test_markdown_subset_ignores_code_images_external_and_escaping_links(self):
        with scratch() as root:
            content = {'a.py': b'pass\n', 'readme.md': b'```md\n[code](a.py)\n```\n![image](a.py)\n`[inline](a.py)`\n[escape](../a.py)\n[abs](/a.py)\n[web](https://x/a.py)\n[ok](./a.py#symbol)\n'}
            result = json.loads(adapter.respond(adapter.encoded(request(root, content))))
            self.assertEqual(len(result['graph']['links']), 1)
            self.assertEqual(result['graph']['links'][0]['type'], 'links_to')
            self.assertEqual([x['target'] for x in result['validation']['unresolved_references']], ['../a.py'])

    def test_unchanged_refresh_pack_reader_pull_end_to_end(self):
        with integrated_fixture() as (root, manifest):
            result = run_refresh(root, manifest)
            self.assertEqual(result['status'], 'completed', result)
            self.assertFalse(result['promoted'])
            candidate = root / 'transaction/candidate'
            task = result['tasks'][0]
            catalog_path = candidate / 'download-catalog.json'
            catalog, _ = reader.load_catalog(catalog_path, task['package']['catalog_sha256'])
            graph, _, _, coverage = reader.read_graph(catalog_path, catalog['archives'][0])
            self.assertTrue(any(n['label'] == 'Example.method' for n in graph['nodes']))
            provenance = json.loads((root / 'transaction/candidate/package.json').read_bytes())
            self.assertEqual(provenance['qualification']['inventory_coverage'],
                             {'structural': 5, 'enriched': 0, 'unknown': 2})
            self.assertIn('inventory.coverage', provenance['qualification']['missing_provenance'])
            self.assertNotIn('graph.record_source_files', provenance['qualification']['missing_provenance'])
            extractor = json.loads((root / 'transaction/evidence/extractor.json').read_bytes())
            self.assertEqual(extractor['artifact_sha256'], adapter.digest(SCRIPT.read_bytes()))
            self.assertEqual(extractor['name'], adapter.NAME)
            selected = puller.pull(catalog_path, root / 'copied', ['Fixture/Source'], task['package']['catalog_sha256'])
            self.assertEqual(selected['status'], 'ok')
            cli = subprocess.run([sys.executable, '-B', str(ROOT / 'tooling/graph_read.py'),
                                  '--catalog', str(root / 'copied/download-catalog.json'), '--repo', 'Fixture/Source',
                                  'search', '--text', 'Example.method'], capture_output=True, text=True, timeout=10)
            self.assertEqual(cli.returncode, 0, cli.stderr)
            self.assertIn('Example.method', cli.stdout)

    def test_protocol_rejections_propagate_as_refresh_failed(self):
        for problem in ('schema', 'malformed', 'hash', 'symlink', 'output'):
            with self.subTest(problem=problem), integrated_fixture() as (root, manifest):
                actual = refresh.run_adapter
                def altered(executable, script, original, cwd, limits):
                    r = json.loads(original.read())
                    if problem == 'schema': r['schema'] = 'wrong'
                    elif problem == 'hash': r['files'][0]['sha256'] = '0' * 64
                    elif problem == 'output': r['limits']['output_bytes'] = 1
                    elif problem == 'symlink':
                        alias = root / 'input-alias'
                        alias.symlink_to(r['stage'], target_is_directory=True)
                        r['stage'] = str(alias)
                    raw = b'{' if problem == 'malformed' else adapter.encoded(r)
                    with tempfile.TemporaryFile(dir=root) as selected:
                        selected.write(raw)
                        selected.seek(0)
                        return actual(executable, script, selected, cwd, limits)
                with patch.object(refresh, 'run_adapter', side_effect=altered):
                    result = run_refresh(root, manifest)
                self.assertEqual(result['status'], 'failed', result)
                self.assertFalse((root / 'transaction/candidate').exists())

    def test_fixture_cleanup_success_failure_and_cancellation_is_owned(self):
        with scratch() as survivor:
            for failure in (None, ValueError, KeyboardInterrupt):
                try:
                    with scratch() as owned:
                        (owned / 'file').write_text('synthetic')
                        if failure: raise failure('expected')
                except (ValueError, KeyboardInterrupt):
                    pass
                self.assertFalse(owned.exists())
                self.assertTrue(survivor.exists())
            with self.assertRaises(KeyboardInterrupt):
                with scratch() as cancelled:
                    os.kill(os.getpid(), signal.SIGTERM)
            self.assertFalse(cancelled.exists())
            self.assertTrue(survivor.exists())


if __name__ == '__main__':
    unittest.main()
