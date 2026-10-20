"""Synthetic v2 fragment/assembly transitions; the v1 fixture's scratch owns all files."""
import ast
import copy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_refresh_adapter_structural import CONTENT, SCRIPT, adapter, invoke, request as v1_request, scratch

V2 = 'graphify-refresh-response/v2'


def write(p, raw):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(raw)


def fresh(root):
    p = root / f'run-{len(list(root.iterdir()))}'
    p.mkdir()
    return p


def v2_request(root, content, reuse=None):
    """Stage content for extraction, or a fragment instead of content for reuse."""
    reuse = reuse or {}
    stage = fresh(root) / 'stage'
    stage.mkdir()
    files = []
    for name, raw in sorted(content.items()):
        if name in reuse:
            blob = adapter.encoded(reuse[name])
            staged = f'.fragments/{len(files)}.json'
            write(stage / staged, blob)
            files.append(dict(path=name, sha256=adapter.digest(raw), action='reuse',
                              fragment=dict(stage_path=staged, sha256=adapter.digest(blob))))
        else:
            write(stage / name, raw)
            files.append(dict(path=name, sha256=adapter.digest(raw), action='extract', fragment=None))
    source = dict(repository='Fixture/Source', head='a' * 40)
    return dict(schema='graphify-refresh-request/v2', manifest_sha256='b' * 64, source=source,
                input_basis='git_blob', stage=str(stage), files=files,
                policy=dict(schema='graphify-pack-policy/v1', source=source, name='incremental-admission',
                            limitations=[], rules=dict(include=['*.py', '*.md', '*.txt'], deny=['private/*'],
                                                       max_files=256)),
                extractor=dict(protocol='python-json/v2', name=adapter.NAME, version=adapter.VERSION,
                               executable=dict(path=str(Path(sys.executable).resolve()), sha256='c' * 64),
                               script=dict(path=str(SCRIPT), sha256=adapter.digest(SCRIPT.read_bytes()))),
                limits=dict(adapter.LIMITS, seconds=5))


def run_v2(root, content, reuse=None):
    return json.loads(adapter.respond(adapter.encoded(v2_request(root, content, reuse))))


def run_v1(root, content):
    return json.loads(adapter.respond(adapter.encoded(v1_request(fresh(root), content))))


def normalized(result):
    graph, validation = dict(result['graph']), dict(result['validation'])
    for document in (graph, validation):
        document.pop('refresh_request_sha256')
    if result['schema'] == V2:
        validation['limitations'] = [x for x in validation['limitations'] if x != adapter.GIT_LIMITATION]
    return graph, validation, result['coverage']


def triples(result):
    nodes = {n['id']: n for n in result['graph']['nodes']}
    return {(nodes[e['source']]['label'], e['type'], nodes[e['target']]['label'])
            for e in result['graph']['links']}


def unresolved(result):
    return {x['target'] for x in result['validation']['unresolved_references']}


def simple(names):
    return {name: b'def f():\n    pass\n' for name in names}


class StructuralFragmentTests(unittest.TestCase):
    def assert_rejected(self, r):
        result = invoke(adapter.encoded(r))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b'')

    def test_fragment_is_file_local_and_closed(self):
        limits = adapter.LIMITS
        a = adapter.fragment('pkg/a.py', CONTENT['pkg/a.py'], limits)
        self.assertEqual(set(a), {'schema', 'family', 'path', 'content_sha256', 'outcome', 'reason',
                                  'file_node', 'nodes', 'edges', 'references'})
        self.assertEqual((a['schema'], a['family'], a['outcome'], a['reason']),
                         (adapter.FRAGMENT, dict(name=adapter.NAME, version=adapter.VERSION), 'structural', None))
        self.assertEqual(a['content_sha256'], adapter.digest(CONTENT['pkg/a.py']))
        self.assertEqual(a['file_node'], dict(id=adapter.file_id('pkg/a.py'), type='file',
                                              label='pkg/a.py', source_file='pkg/a.py'))
        self.assertEqual({r['target']: r['candidates'] for r in a['references']},
                         {'pkg.b': ['pkg/b.py', 'pkg/b/__init__.py'],
                          'external': ['external.py', 'external/__init__.py'],
                          'pkg': ['pkg.py', 'pkg/__init__.py']})
        self.assertEqual(a, adapter.fragment('pkg/a.py', CONTENT['pkg/a.py'], limits))
        guide = adapter.fragment('docs/guide.md', CONTENT['docs/guide.md'], limits)
        self.assertEqual({r['target']: r['candidates'] for r in guide['references']},
                         {'../pkg/a.py#Example': ['pkg/a.py'], 'missing.py': ['docs/missing.py']})
        escape = adapter.fragment('main.py', b'from ..escape import x\n', limits)
        self.assertEqual(escape['references'], [dict(kind='imports', target='..escape', line=1, candidates=[])])
        for name, reason in (('broken.py', 'SyntaxError'), ('data.txt', 'NotImplementedError')):
            failed = adapter.fragment(name, CONTENT[name], limits)
            self.assertEqual((failed['outcome'], failed['reason'], failed['nodes'], failed['edges'],
                              failed['references']), ('unknown', reason, [], [], []))

    def test_v2_all_extract_matches_v1_and_is_deterministic(self):
        with scratch() as root:
            v1 = run_v1(root, CONTENT)
            r = v2_request(root, CONTENT)
            raw = adapter.encoded(r)
            first, second = invoke(raw), invoke(raw)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(first.stdout, second.stdout)
            v2 = json.loads(first.stdout)
            self.assertEqual(set(v2), {'schema', 'request_sha256', 'graph', 'validation', 'coverage', 'fragments'})
            self.assertEqual(v2['request_sha256'], adapter.digest(raw))
            self.assertEqual(v2['graph']['refresh_request_sha256'], adapter.digest(raw))
            self.assertEqual(v2['validation']['limitations'][-1], adapter.GIT_LIMITATION)
            self.assertEqual(set(v2['fragments']), set(CONTENT))
            self.assertEqual(normalized(v2), normalized(v1))

    def test_add_modify_ambiguity_delete_rename_reuse_equals_full_and_v1(self):
        add = dict(CONTENT, **{'external.py': b'VALUE = 1\n', 'docs/missing.py': b'pass\n'})
        modify = dict(add, **{'pkg/b.py': b'def helper():\n    pass\n\ndef added():\n    pass\n'})
        ambiguous = dict(modify, **{'external/__init__.py': b''})
        delete = {k: v for k, v in ambiguous.items() if k != 'pkg/b.py'}
        rename = {('pkg/z.py' if k == 'pkg/a.py' else k): v for k, v in delete.items()}
        states = [('initial', CONTENT), ('add', add), ('modify', modify), ('ambiguous', ambiguous),
                  ('delete', delete), ('rename', rename)]
        with scratch() as root:
            cache, results = {}, {}
            for name, content in states:
                with self.subTest(state=name):
                    reuse = {p: cache[p] for p, raw in content.items()
                             if p in cache and cache[p]['content_sha256'] == adapter.digest(raw)}
                    mixed = run_v2(root, content, reuse)
                    self.assertEqual(set(mixed['fragments']), set(content) - set(reuse))
                    if name != 'initial':
                        self.assertTrue(reuse)
                        # A pure deletion reuses every remaining fragment and extracts nothing.
                        self.assertEqual(not mixed['fragments'], name == 'delete')
                    self.assertEqual(normalized(mixed), normalized(run_v2(root, content)))
                    self.assertEqual(normalized(mixed), normalized(run_v1(root, content)))
                    cache.update(mixed['fragments'])
                    results[name] = mixed
            initial, added = results['initial'], results['add']
            self.assertIn('external', unresolved(initial))
            self.assertIn('missing.py', unresolved(initial))
            self.assertIn(('pkg/a.py', 'imports', 'external.py'), triples(added))
            self.assertIn(('docs/guide.md', 'links_to', 'docs/missing.py'), triples(added))
            self.assertFalse({'external', 'missing.py'} & unresolved(added))
            self.assertIn('added', {n['label'] for n in results['modify']['graph']['nodes']})
            self.assertIn('external', unresolved(results['ambiguous']))
            self.assertFalse({t for t in triples(results['ambiguous']) if t[2].startswith('external')})
            deleted = results['delete']
            self.assertFalse([n for n in deleted['graph']['nodes'] if n['source_file'] == 'pkg/b.py'])
            self.assertNotIn(('pkg/a.py', 'imports', 'pkg/b.py'), triples(deleted))
            self.assertIn('pkg.b', unresolved(deleted))
            renamed = results['rename']
            self.assertFalse([n for n in renamed['graph']['nodes'] if n['source_file'] == 'pkg/a.py'])
            old = {n['id'] for n in deleted['graph']['nodes'] if n['source_file'] == 'pkg/a.py'}
            new = {n['id'] for n in renamed['graph']['nodes'] if n['source_file'] == 'pkg/z.py'}
            self.assertTrue(old and new and not old & new)
            self.assertIn('../pkg/a.py#Example', unresolved(renamed))
            self.assertIn(('Example', 'contains', 'Example.method'), triples(renamed))

    def test_reuse_and_request_rejections_fail_without_stdout(self):
        content = {'a.py': b'def f():\n    pass\n', 'b.py': b'import a\n'}
        good = adapter.fragment('a.py', content['a.py'], adapter.LIMITS)
        fragment_mutations = [
            lambda f: f.update(path='b.py'),
            lambda f: f.update(content_sha256=adapter.digest(b'other')),
            lambda f: f.update(family=dict(name=adapter.NAME, version='2')),
            lambda f: f.update(family=dict(name='legacy', version=adapter.VERSION)),
            lambda f: f.update(schema='graphify-structural-fragment/v0'),
            lambda f: f.update(extra=True),
            lambda f: f.update(reason='SyntaxError'),
            lambda f: f.update(outcome='unknown', reason='limit'),
            lambda f: f['nodes'][0].update(source_file='b.py'),
            lambda f: f['edges'][0].update(target='structural-v1:' + '0' * 64),
            lambda f: f['references'].append(dict(kind='imports', target='x', line=1, candidates=['../x.py'])),
            lambda f: f.update(file_node=dict(f['file_node'], label='b.py')),
        ]
        request_mutations = [
            lambda r: r['files'][0]['fragment'].update(sha256='0' * 64),
            lambda r: r['files'][0].update(sha256=adapter.digest(b'changed')),
            lambda r: r['files'][0]['fragment'].update(stage_path='b.py'),
            lambda r: r['files'][1].update(action='reuse', fragment=dict(r['files'][0]['fragment'])),
            lambda r: r['files'][0].update(action='extract'),
            lambda r: r['files'][1].update(fragment=dict(stage_path='x.json', sha256='0' * 64)),
            lambda r: r['files'][0].update(action='skip'),
            lambda r: r.update(input_basis='checkout'),
            lambda r: r.update(samples={}),
            lambda r: r['policy'].update(name='refresh-explicit-selection'),
            lambda r: r['policy']['rules'].update(deny=['b.py']),
            lambda r: r['policy']['rules'].update(include=['*.md']),
            lambda r: r['extractor'].update(protocol='python-json/v1'),
            lambda r: r.update(schema='graphify-refresh-request/v1'),
        ]
        with scratch() as root:
            control = v2_request(root, content, {'a.py': good})
            self.assertEqual(invoke(adapter.encoded(control)).returncode, 0)
            for index, mutate in enumerate(fragment_mutations):
                with self.subTest(fragment=index):
                    changed = copy.deepcopy(good)
                    mutate(changed)
                    self.assert_rejected(v2_request(root, content, {'a.py': changed}))
            for index, mutate in enumerate(request_mutations):
                with self.subTest(request=index):
                    changed = copy.deepcopy(control)
                    mutate(changed)
                    self.assert_rejected(changed)
            linked = v2_request(root, content, {'a.py': good})
            staged = Path(linked['stage']) / linked['files'][0]['fragment']['stage_path']
            outside = staged.parent.parent.parent / 'outside.json'
            staged.rename(outside)
            staged.symlink_to(outside)
            self.assert_rejected(linked)

    def test_per_file_limits_are_unknown_reusable_and_v1_fatal(self):
        cases = ((dict(MAX_AST_NODES=3), {'a.py': b'def f():\n    pass\n', 'b.py': b'pass\n'}, 'AST node limit'),
                 (dict(MAX_RECORDS=6), {'a.py': b''.join(b'def f%d():\n    pass\n' % i for i in range(4)),
                                        'b.py': b'pass\n'}, 'record limit'))
        for bounds, content, message in cases:
            with self.subTest(bounds=bounds), scratch() as root, patch.multiple(adapter, **bounds):
                extracted = run_v2(root, content)
                self.assertEqual(extracted['coverage'], {'a.py': 'unknown', 'b.py': 'structural'})
                self.assertIn(dict(source_file='a.py', reason='limit'), extracted['validation']['parser_errors'])
                limited = extracted['fragments']['a.py']
                self.assertEqual((limited['outcome'], limited['reason'], limited['nodes']), ('unknown', 'limit', []))
                self.assertFalse([n for n in extracted['graph']['nodes'] if n['source_file'] == 'a.py'
                                  and n['type'] != 'file'])
                reused = run_v2(root, content, {'a.py': limited})
                self.assertEqual(normalized(reused), normalized(extracted))
                with self.assertRaisesRegex(ValueError, message):
                    run_v1(root, content)
        small = adapter.fragment('a.py', b'def f():\n    pass\n', dict(adapter.LIMITS, output_bytes=64))
        self.assertEqual((small['outcome'], small['reason']), ('unknown', 'limit'))

    def test_global_record_and_output_overflow_fail_the_run(self):
        content = simple(('a.py', 'b.py', 'c.py'))
        with scratch() as root:
            with patch.object(adapter, 'MAX_RECORDS', 6):
                self.assertTrue(all(adapter.fragment(p, raw, adapter.LIMITS)['outcome'] == 'structural'
                                    for p, raw in content.items()))
                with self.assertRaisesRegex(ValueError, 'record limit'):
                    run_v2(root, content)
                reuse = {'a.py': adapter.fragment('a.py', content['a.py'], adapter.LIMITS)}
                with self.assertRaisesRegex(ValueError, 'record limit'):
                    run_v2(root, content, reuse)
            r = v2_request(root, content)
            size = len(adapter.respond(adapter.encoded(r)))
            r['limits']['output_bytes'] = size
            self.assertEqual(len(adapter.respond(adapter.encoded(r))), size)
            r['limits']['output_bytes'] = size - 1
            self.assert_rejected(r)

    def test_no_new_imports_writes_environment_or_subprocess(self):
        tree = ast.parse(SCRIPT.read_bytes())
        imported = {a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        imported |= {n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imported, {'ast', 'contextlib', 'fnmatch', 'hashlib', 'json', 'os', 'pathlib',
                                    're', 'stat', 'sys'})
        self.assertNotIn('open', {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)})
        names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        names |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        self.assertFalse(names & {'environ', 'getenv', 'system', 'popen', 'O_WRONLY', 'O_RDWR',
                                  'O_CREAT', 'O_APPEND', 'O_TRUNC', 'unlink', 'remove', 'rename', 'mkdir',
                                  'makedirs', 'write_bytes', 'write_text', 'socket'})
        with scratch() as root:
            good = adapter.fragment('pkg/b.py', CONTENT['pkg/b.py'], adapter.LIMITS)
            r = v2_request(root, CONTENT, {'pkg/b.py': good})
            stage = Path(r['stage'])
            def snapshot():
                return sorted((str(p.relative_to(root)), p.stat().st_size, p.stat().st_mtime_ns)
                              for p in root.rglob('*'))
            before = snapshot()
            result = invoke(adapter.encoded(r))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(snapshot(), before)
            self.assertFalse((stage / 'pkg/b.py').exists())
            self.assertFalse(list(root.rglob('__pycache__')))


if __name__ == '__main__':
    unittest.main()
