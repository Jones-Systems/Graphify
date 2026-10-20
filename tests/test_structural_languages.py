"""Family 2 structural extraction; synthetic sources only, owned scratch for every fixture."""
from contextlib import contextmanager
import ast
import copy
import hashlib
import importlib.util
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
SCRIPT = ROOT / 'tooling/refresh_adapter_structural.py'
LANGUAGES = ROOT / 'tooling/structural_languages.py'
sys.path[:0] = [str(ROOT / 'tooling')]
import preflight

spec = importlib.util.spec_from_file_location('structural_adapter_v2', SCRIPT)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

TS = b'''// import { fake } from './fake'
import { helper } from './util';
import type { T } from "./types.js";
import * as path from 'node:path';
import alias from '@/alias';
export { helper as aid } from './util';
export * from './reexport';
const s = "import x from './in-string'";
const token = "opaque-literal-value";
const re = /from '\\.\\/regex'/;
const lazy = import('./lazy');
const cjs = require('./legacy');
/* require('./in-comment') */
export const value = 1;
export default function main() {}
export class Service {
  static create() { return new Service(); }
  run(input: string) { return `${input} require('./tpl')`; }
}
interface Shape { area(): number }
type Id = string;
enum Color { Red }
'''
SWIFT = b'''import Foundation
@testable import struct Kit.Thing
// class Hidden {}
let note = "class Fake { func nope() {} }"
let multi = """
struct AlsoFake {}
"""
public final class Store {
    class func make() -> Store { Store() }
    func load(id: Int) -> String { "\\(id) }" }
    struct Item {}
}
extension Store.Item {
    func describe() {}
}
protocol Feed { func next() }
enum Mode { case a }
actor Worker { func work() {} }
'''
GO = b'''package main

import (
\t"fmt"
\tstr "strings"
\t"example.com/demo/internal/util"
)

// func Hidden() {}
var s = "func Fake() {}"

type (
\tConfig struct{ Name string }
\tID int
)

type Server struct{}

func (s *Server) Start() error { return nil }

func main() {
\tfmt.Println(`type Raw struct{}`)
}
'''
SHELL = b'''#!/usr/bin/env bash
# source ./commented.sh
source "$(dirname "$0")/lib.sh"
. ./common.sh
source "$HOME/.profile"
echo "source ./quoted.sh"
cat <<EOF
source ./heredoc.sh
EOF
setup() {
  :
}
function teardown {
  :
}
'''
MARKDOWN = b'''---
title: Not a heading
---
# Guide
Intro [inline](../src/app.ts "Title") and ![img](pic.png).

Setext Title
------------

## Usage `code`
See [ref][r] and `[code](../src/fake.ts)`.

[r]: ./usage.md
<!-- [hidden](../src/fake.ts) -->
```bash
[fenced](../src/fake.ts)
```
### Deep [Link](usage.md)
# Second
'''
WORKFLOW = b'''on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/setup
      - run: |
          echo "uses: fake/action@v1"
      - uses: docker://alpine:3
'''
CONTENT = {
    'src/app.ts': TS, 'src/util.ts': b'export const helper = 1;\n',
    'src/types.ts': b'export type T = number;\n', 'src/reexport/index.ts': b'export {};\n',
    'src/lazy.tsx': b'export default 1;\n', 'src/legacy.js': b'module.exports = {};\n',
    'src/fake.ts': b'export {};\n',
    'ios/App.swift': SWIFT,
    'go.mod': b'module example.com/demo\n\nrequire (\n\tgithub.com/pkg/errors v0.9.1\n)\n',
    'cmd/main.go': GO, 'internal/util/util.go': b'package util\n',
    'scripts/run.sh': SHELL, 'scripts/lib.sh': b'helper() { :; }\n', 'scripts/common.sh': b':\n',
    'docs/guide.md': MARKDOWN, 'docs/usage.md': b'# Usage\n',
    'package.json': b'{"name":"x","dependencies":{"react":"^18","@scope/pkg":"1"},'
                    b'"devDependencies":{"typescript":"5"},"scripts":{"build":"tsc"}}\n',
    'pyproject.toml': b'[project]\nname = "x"\ndependencies = ["requests>=2.0", "rich[extra]; python_version>\'3\'"]\n'
                      b'[project.optional-dependencies]\ndev = ["pytest"]\n'
                      b'[build-system]\nrequires = ["setuptools>=61"]\n'
                      b'[tool.poetry.dependencies]\npython = "^3.11"\nhttpx = "*"\n',
    '.github/workflows/ci.yml': WORKFLOW,
    '.github/actions/setup/action.yml': b'runs:\n  using: composite\n  steps: []\n',
    'pkg/__init__.py': b'', 'pkg/a.py': b'import pkg.b\nimport external\nclass Example:\n    def method(self):\n        pass\n',
    'pkg/b.py': b'def helper():\n    pass\n',
    'main.py': b'import other\n', 'other.py': b'pass\n', 'other/__init__.py': b'pass\n',
    'data.txt': b'unsupported',
}
SLICES = {'src': 'a', 'docs': 'b', 'scripts': 'b', 'other': 'b'}


def slice_of(p):
    return SLICES.get(p.split('/', 1)[0], 'rest') if '/' in p else 'rest'


@contextmanager
def scratch():
    parent = os.environ.get('GRAPHIFY_REFRESH_TEST_ROOT', str(ROOT))
    def cancel(signum, frame):
        raise KeyboardInterrupt('synthetic fixture cancelled')
    previous = signal.signal(signal.SIGTERM, cancel)
    try:
        with tempfile.TemporaryDirectory(prefix='.structural-v2-test-', dir=parent) as name:
            yield Path(name).resolve()
    finally:
        signal.signal(signal.SIGTERM, previous)


def write(stage, name, raw):
    p = stage / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(raw)


def build(root, content, version='2', reuse=None, slice_name=None, index=None, limits=None):
    """Stage one python-json/v2 request; reuse maps path -> prior fragment of equal content."""
    stage = Path(tempfile.mkdtemp(dir=root))
    files = []
    for i, (p, raw) in enumerate(sorted(content.items())):
        sha = adapter.digest(raw)
        prior = (reuse or {}).get(p)
        if prior is not None and prior['content_sha256'] == sha:
            blob = adapter.encoded(prior)
            write(stage, f'.graphify-fragments/{i}.json', blob)
            files.append(dict(path=p, sha256=sha, action='reuse',
                              fragment=dict(stage_path=f'.graphify-fragments/{i}.json',
                                            sha256=adapter.digest(blob))))
        else:
            write(stage, p, raw)
            files.append(dict(path=p, sha256=sha, action='extract', fragment=None))
    source = dict(repository='Fixture/Source', head='a' * 40)
    request = dict(schema='graphify-refresh-request/v2', manifest_sha256='b' * 64, source=source,
                   input_basis='git_blob', stage=str(stage), files=files,
                   policy=dict(schema='graphify-pack-policy/v1', source=source, name='incremental-admission',
                               rules=dict(include=['*'], deny=[]), limitations=[]),
                   extractor=dict(protocol='python-json/v2', name=adapter.NAME, version=version,
                                  executable=dict(path=str(Path(sys.executable).resolve()), sha256='c' * 64),
                                  script=dict(path=str(SCRIPT), sha256=adapter.digest(SCRIPT.read_bytes()))),
                   limits=limits or dict(file_bytes=4 * 1024**2, input_bytes=16 * 1024**2,
                                         output_bytes=8 * 1024**2, seconds=5))
    if slice_name is not None:
        blob = adapter.encoded(dict(schema=adapter.PATH_INDEX, paths=index))
        write(stage, '.graphify-path-index.json', blob)
        request.update(slice=dict(name=slice_name),
                       path_index=dict(stage_path='.graphify-path-index.json', sha256=adapter.digest(blob)))
    return request


def respond(request):
    return json.loads(adapter.respond(adapter.encoded(request)))


def invoke(raw, script=SCRIPT):
    return subprocess.run([str(Path(sys.executable).resolve()), '-I', '-B', str(script)],
                          input=raw, capture_output=True, timeout=30, env={'LC_ALL': 'C.UTF-8'})


def labels(result, path=None):
    return {(n['type'], n['label']) for n in result['graph']['nodes']
            if path is None or n['source_file'] == path}


def links(result):
    nodes = {n['id']: n for n in result['graph']['nodes']}
    return {(nodes[e['source']]['label'], e['type'], nodes[e['target']]['label'])
            for e in result['graph']['links']}


def unresolved(result, path):
    return {x['target'] for x in result['validation']['unresolved_references'] if x['source_file'] == path}


def stable(result):
    """Response content independent of the request hash (cold/reuse and slice comparisons)."""
    value = copy.deepcopy({k: result[k] for k in ('graph', 'validation', 'coverage')})
    for part in (value['graph'], value['validation']):
        part.pop('refresh_request_sha256')
    return value


class LanguageFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with scratch() as root:
            cls.result = respond(build(root, CONTENT))

    def test_languages_module_is_digest_pinned_and_markers_match_preflight(self):
        self.assertEqual(adapter.LANGUAGES_SHA256, hashlib.sha256(LANGUAGES.read_bytes()).hexdigest())
        self.assertEqual(list(adapter.load_languages().FORBIDDEN_MARKERS), preflight.FORBIDDEN_MARKERS)

    def test_languages_module_imports_no_writer_environment_or_subprocess(self):
        tree = ast.parse(LANGUAGES.read_bytes())
        imported = {a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        imported |= {n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imported, {'json', 'pathlib', 're', 'tomllib'})
        names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        names |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        self.assertFalse(names & {'open', 'environ', 'getenv', 'system', 'popen', 'exec', 'eval',
                                  '__import__', 'unlink', 'remove', 'rename', 'mkdir',
                                  'write_bytes', 'write_text', 'socket'})

    def test_coverage_and_family_identity(self):
        r = self.result
        self.assertEqual(r['graph']['extractor_family'], dict(name=adapter.NAME, version='2'))
        self.assertEqual(r['coverage']['data.txt'], 'unknown')
        self.assertEqual({k for k, v in r['coverage'].items() if v != 'structural'}, {'data.txt'})
        self.assertEqual(r['validation']['parser_errors'], [dict(source_file='data.txt', reason='unsupported')])
        self.assertNotIn('cross_slice_references', r['validation'])
        self.assertEqual(set(r['graph']), {'source', 'built_at_commit', 'refresh_request_sha256',
                                           'extractor_family', 'directed', 'nodes', 'links'})
        for item in r['fragments'].values():
            self.assertEqual(item['schema'], adapter.FRAGMENT_V2)

    def test_typescript_imports_exports_declarations_and_noise(self):
        r, f = self.result, 'src/app.ts'
        self.assertEqual(labels(r, f) - {('file', f)}, {
            ('function', 'main'), ('class', 'Service'), ('method', 'Service.create'),
            ('method', 'Service.run'), ('interface', 'Shape'), ('type', 'Id'), ('enum', 'Color'),
            ('variable', 's'), ('variable', 'token'), ('variable', 're'), ('variable', 'lazy'),
            ('variable', 'cjs'), ('variable', 'value'), ('export', 'aid'), ('export', 'value'),
            ('export', 'default'), ('export', 'Service')})
        imported = {t for s, kind, t in links(r) if s == f and kind == 'imports'}
        self.assertEqual(imported, {'src/util.ts', 'src/types.ts', 'src/reexport/index.ts',
                                    'src/lazy.tsx', 'src/legacy.js'})
        self.assertEqual(unresolved(r, f), {'node:path', '@/alias'})
        self.assertIn(('Service', 'contains', 'Service.run'), links(r))
        raw = adapter.encoded(r)
        for noise in (b'opaque-literal-value', b'in-string', b'regex', b'in-comment', b'tpl'):
            self.assertNotIn(noise, raw)
        self.assertNotIn((f, 'imports', 'src/fake.ts'), links(r))

    def test_swift_imports_and_brace_scoped_declarations(self):
        r, f = self.result, 'ios/App.swift'
        self.assertEqual(labels(r, f) - {('file', f)}, {
            ('class', 'Store'), ('function', 'Store.make'), ('function', 'Store.load'),
            ('struct', 'Store.Item'), ('extension', 'Store.Item'), ('function', 'Store.Item.describe'),
            ('protocol', 'Feed'), ('function', 'Feed.next'), ('enum', 'Mode'), ('actor', 'Worker'),
            ('function', 'Worker.work')})
        self.assertEqual(unresolved(r, f), {'Foundation', 'Kit.Thing'})

    def test_go_package_imports_and_declarations(self):
        r, f = self.result, 'cmd/main.go'
        self.assertEqual(labels(r, f) - {('file', f)}, {
            ('package', 'main'), ('type', 'Config'), ('type', 'ID'), ('type', 'Server'),
            ('method', 'Server.Start'), ('function', 'main')})
        # Module imports stay unresolved so sliced and unsliced assembly agree.
        self.assertEqual(unresolved(r, f), {'fmt', 'strings', 'example.com/demo/internal/util'})
        self.assertEqual(labels(r, 'go.mod') - {('file', 'go.mod')},
                         {('go_module', 'example.com/demo'), ('dependency', 'github.com/pkg/errors')})

    def test_shell_relative_sources_and_functions(self):
        r, f = self.result, 'scripts/run.sh'
        self.assertEqual(labels(r, f) - {('file', f)}, {('function', 'setup'), ('function', 'teardown')})
        self.assertEqual({t for s, kind, t in links(r) if s == f and kind == 'sources'},
                         {'scripts/lib.sh', 'scripts/common.sh'})
        self.assertEqual(unresolved(r, f), {'$HOME/.profile'})

    def test_markdown_headings_and_links(self):
        r, f = self.result, 'docs/guide.md'
        self.assertEqual(labels(r, f) - {('file', f)}, {
            ('heading', 'Guide'), ('heading', 'Setext Title'), ('heading', 'Usage code'),
            ('heading', 'Deep Link'), ('heading', 'Second')})
        self.assertTrue({('Guide', 'contains', 'Setext Title'), ('Guide', 'contains', 'Usage code'),
                         ('Usage code', 'contains', 'Deep Link'), (f, 'contains', 'Second'),
                         (f, 'links_to', 'src/app.ts'), (f, 'links_to', 'docs/usage.md')} <= links(r))
        self.assertFalse({t for s, k, t in links(r) if s == f and t == 'src/fake.ts'})
        self.assertEqual(unresolved(r, f), set())

    def test_manifest_dependency_names_only(self):
        r = self.result
        self.assertEqual(labels(r, 'package.json') - {('file', 'package.json')},
                         {('dependency', x) for x in ('react', '@scope/pkg', 'typescript')})
        self.assertEqual(labels(r, 'pyproject.toml') - {('file', 'pyproject.toml')},
                         {('dependency', x) for x in ('requests', 'rich', 'pytest', 'setuptools', 'httpx')})
        f = '.github/workflows/ci.yml'
        self.assertEqual(labels(r, f) - {('file', f)},
                         {('action', 'actions/checkout'), ('action', 'docker://alpine:3')})
        self.assertIn((f, 'uses', '.github/actions/setup/action.yml'), links(r))
        raw = adapter.encoded(r)
        for value in (b'^18', b'tsc', b'>=2.0', b'fake/action'):
            self.assertNotIn(value, raw)

    def test_python_semantics_preserved(self):
        r = self.result
        self.assertTrue({('class', 'Example'), ('function', 'Example.method')} <= labels(r, 'pkg/a.py'))
        self.assertIn(('pkg/a.py', 'imports', 'pkg/b.py'), links(r))
        self.assertEqual(unresolved(r, 'pkg/a.py'), {'external'})
        self.assertEqual(unresolved(r, 'main.py'), {'other'})


class FamilyContractTests(unittest.TestCase):
    def test_forbidden_marker_file_has_no_records(self):
        marker = preflight.FORBIDDEN_MARKERS[0].encode()
        with scratch() as root:
            r = respond(build(root, {'src/keyfile.ts': b'export const k = "' + marker + b'";\n',
                                     'docs/a.md': b'# A\n'}))
        self.assertEqual(r['coverage']['src/keyfile.ts'], 'unknown')
        self.assertIn(dict(source_file='src/keyfile.ts', reason='forbidden_marker'), r['validation']['parser_errors'])
        self.assertEqual(labels(r, 'src/keyfile.ts'), {('file', 'src/keyfile.ts')})
        self.assertEqual(r['fragments']['src/keyfile.ts']['nodes'], [])
        self.assertNotIn(marker, adapter.encoded(r))

    def test_subprocess_isolated_run_matches_in_process(self):
        with scratch() as root:
            raw = adapter.encoded(build(root, CONTENT))
            result = invoke(raw)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, adapter.respond(raw))

    def test_family_one_never_loads_languages_and_is_unchanged(self):
        with scratch() as root:
            copy_dir = root / 'adapter-only'
            copy_dir.mkdir()
            shutil.copyfile(SCRIPT, copy_dir / SCRIPT.name)
            content = {k: CONTENT[k] for k in ('pkg/__init__.py', 'pkg/a.py', 'pkg/b.py', 'docs/guide.md', 'data.txt')}
            raw = adapter.encoded(build(root, content, version='1'))
            alone, in_tree = invoke(raw, copy_dir / SCRIPT.name), invoke(raw)
            self.assertEqual(in_tree.returncode, 0, in_tree.stderr)
            self.assertEqual(alone.stdout, in_tree.stdout)
            self.assertEqual(json.loads(in_tree.stdout)['graph']['extractor_family']['version'], '1')
            # Family 2 without the pinned module fails closed.
            failed = invoke(adapter.encoded(build(root, content)), copy_dir / SCRIPT.name)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(failed.stdout, b'')

    def test_languages_digest_mismatch_fails_closed(self):
        with scratch() as root:
            copy_dir = root / 'tampered'
            copy_dir.mkdir()
            shutil.copyfile(SCRIPT, copy_dir / SCRIPT.name)
            (copy_dir / LANGUAGES.name).write_bytes(LANGUAGES.read_bytes() + b'\n# altered\n')
            result = invoke(adapter.encoded(build(root, {'docs/a.md': b'# A\n'})), copy_dir / SCRIPT.name)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b'')

    def test_limits_are_closed_and_bounded(self):
        base = dict(file_bytes=4 * 1024**2, input_bytes=16 * 1024**2, output_bytes=8 * 1024**2, seconds=5)
        with scratch() as root:
            content = {'docs/a.md': b'# A\n## B\n'}
            accepted = [dict(base, output_bytes=64 * 1024**2), dict(base, records=100000),
                        dict(base, input_bytes=112 * 1024**2)]
            for limits in accepted:
                with self.subTest(limits=limits):
                    respond(build(root, content, limits=limits))
            rejected = [dict(base, output_bytes=64 * 1024**2 + 1), dict(base, records=100001),
                        dict(base, records=0), dict(base, records=True), dict(base, extra=1)]
            for limits in rejected:
                with self.subTest(limits=limits), self.assertRaises(ValueError):
                    respond(build(root, content, limits=limits))
            with self.assertRaisesRegex(ValueError, 'record limit'):
                respond(build(root, content, limits=dict(base, records=2)))
            with self.assertRaises(ValueError):  # family 1 keeps its 8 MiB output cap
                respond(build(root, content, version='1', limits=dict(base, output_bytes=64 * 1024**2)))
            with self.assertRaises(ValueError):  # and has no records limit
                respond(build(root, content, version='1', limits=dict(base, records=10)))
            with patch.object(adapter, 'MAX_RECORDS', 3):
                r = respond(build(root, {'src/app.ts': TS}, limits=dict(base, records=100)))
            self.assertEqual(r['validation']['parser_errors'], [dict(source_file='src/app.ts', reason='limit')])

    def test_reused_fragment_is_revalidated(self):
        with scratch() as root:
            cold = respond(build(root, {'docs/a.md': b'# A\n'}))
            good = cold['fragments']['docs/a.md']
            for mutate in (lambda f: f['nodes'][0].update(type='bogus'),
                           lambda f: f.update(family=dict(name=adapter.NAME, version='1')),
                           lambda f: f.update(schema=adapter.FRAGMENT)):
                bad = copy.deepcopy(good)
                mutate(bad)
                with self.subTest(bad=bad['nodes'][:1]), self.assertRaises(ValueError):
                    respond(build(root, {'docs/a.md': b'# A\n'}, reuse={'docs/a.md': bad}))

    def test_cold_and_reuse_equal_across_histories(self):
        history = [dict(CONTENT)]
        changed = dict(CONTENT, **{'src/new.ts': b'export function added() {}\n',
                                   'src/util.ts': b'export const helper = 2;\n'})
        history.append(changed)
        deleted = dict(changed)
        del deleted['src/lazy.tsx']
        history.append(deleted)
        renamed = dict(deleted)
        renamed['src/moved.ts'] = renamed.pop('src/new.ts')
        history.append(renamed)
        with scratch() as root:
            prior = {}
            for step, content in enumerate(history):
                cold = respond(build(root, content))
                warm = respond(build(root, content, reuse=prior))
                with self.subTest(step=step):
                    self.assertEqual(stable(cold), stable(warm))
                    for p, item in warm['fragments'].items():
                        self.assertEqual(item, cold['fragments'][p])
                    if step:
                        self.assertLess(len(warm['fragments']), len(cold['fragments']))
                prior = cold['fragments']


def slice_index(content):
    return {p: slice_of(p) for p in sorted(content)}


def sliced(root, content, index=None):
    index = index or slice_index(content)
    results = {}
    for name in sorted(set(index.values())):
        own = {p: raw for p, raw in content.items() if index[p] == name}
        results[name] = respond(build(root, own, slice_name=name, index=index))
    return results


class SliceTests(unittest.TestCase):
    def index(self, content):
        return slice_index(content)

    def sliced(self, root, content, index=None):
        return sliced(root, content, index)

    def test_sliced_union_equals_unsliced(self):
        with scratch() as root:
            whole = respond(build(root, CONTENT))
            parts = self.sliced(root, CONTENT)
        self.assertEqual(set(parts), {'a', 'b', 'rest'})
        key = lambda r: adapter.encoded(r)
        self.assertEqual({key(n) for r in parts.values() for n in r['graph']['nodes']},
                         {key(n) for n in whole['graph']['nodes']})
        sliced_links = {(e['source'], e['target'], e['type'], e['source_file'])
                        for r in parts.values() for e in r['graph']['links']}
        crossing = [x for r in parts.values() for x in r['validation']['cross_slice_references']]
        self.assertTrue(crossing)
        sliced_links |= {(x['source'], x['target_id'], x['type'], x['source_file']) for x in crossing}
        self.assertEqual(sliced_links, {(e['source'], e['target'], e['type'], e['source_file'])
                                        for e in whole['graph']['links']})
        self.assertEqual({key(x) for r in parts.values() for x in r['validation']['unresolved_references']},
                         {key(x) for x in whole['validation']['unresolved_references']})
        index = self.index(CONTENT)
        for name, r in parts.items():
            ids = {n['id'] for n in r['graph']['nodes']}
            self.assertTrue(all(e['source'] in ids and e['target'] in ids for e in r['graph']['links']))
            for x in r['validation']['cross_slice_references']:
                self.assertEqual(set(x), {'source', 'source_file', 'type', 'target', 'line',
                                          'target_path', 'target_id', 'target_slice'})
                self.assertEqual(x['target_id'], adapter.file_id(x['target_path']))
                self.assertEqual(x['target_slice'], index[x['target_path']])
                self.assertNotEqual(x['target_slice'], name)
                self.assertNotIn(x['target_id'], ids)
            # Consumer binding (G-I pack validator): ascending unique sort key, shaped ids.
            order = [(x['source_file'], x['type'], x['target'], x['line'], x['target_path'])
                     for x in r['validation']['cross_slice_references']]
            self.assertEqual(order, sorted(set(order)))
            own = {n['source_file'] for n in r['graph']['nodes']}
            for x in r['validation']['cross_slice_references']:
                self.assertTrue(type(x['line']) is int and x['line'] >= 1)
                self.assertNotIn(x['target_path'], own)
                self.assertIn(x['source_file'], own)
                for field in ('source', 'target_id'):
                    self.assertRegex(x[field], r'\Astructural-v1:[0-9a-f]{64}\Z')
        doc = [x for x in parts['b']['validation']['cross_slice_references'] if x['source_file'] == 'docs/guide.md']
        self.assertIn(('src/app.ts', 'a', '../src/app.ts'), {(x['target_path'], x['target_slice'], x['target']) for x in doc})

    def test_ambiguous_candidate_across_slices_stays_unresolved(self):
        with scratch() as root:
            parts = self.sliced(root, CONTENT)
        rest = parts['rest']
        self.assertEqual(unresolved(rest, 'main.py'), {'other'})
        self.assertFalse([x for x in rest['validation']['cross_slice_references'] if x['source_file'] == 'main.py'])
        self.assertFalse([l for l in rest['graph']['links'] if l['source_file'] == 'main.py'])

    def test_missing_or_inconsistent_path_index_is_rejected(self):
        content = {'docs/a.md': b'[x](../src/b.ts)\n', 'docs/c.md': b'# C\n'}
        index = {'docs/a.md': 'b', 'docs/c.md': 'b', 'src/b.ts': 'a'}
        with scratch() as root:
            r = respond(build(root, content, slice_name='b', index=index))
            self.assertEqual(len(r['validation']['cross_slice_references']), 1)
            bad = [{k: v for k, v in index.items() if k != 'docs/c.md'},
                   dict(index, **{'docs/c.md': 'a'}),
                   dict(index, **{'src/extra.ts': 'b'}),
                   dict(index, **{'docs/a.md/x': 'a'}),
                   dict(index, **{'src/b.ts': 'bad name'})]
            for value in bad:
                with self.subTest(index=value), self.assertRaises(ValueError):
                    respond(build(root, content, slice_name='b', index=value))
            request = build(root, content, slice_name='b', index=index)
            for drop in ('slice', 'path_index'):
                partial = copy.deepcopy(request)
                del partial[drop]
                with self.subTest(drop=drop), self.assertRaises(ValueError):
                    respond(partial)
            with self.assertRaises(ValueError):
                respond(dict(build(root, content, version='1'), slice=dict(name='b')))
            tampered = copy.deepcopy(request)
            tampered['path_index']['sha256'] = '0' * 64
            with self.assertRaises(ValueError):
                respond(tampered)

    def test_sliced_reuse_equals_cold(self):
        with scratch() as root:
            cold = self.sliced(root, CONTENT)
            index = self.index(CONTENT)
            for name, r in cold.items():
                own = {p: raw for p, raw in CONTENT.items() if index[p] == name}
                warm = respond(build(root, own, reuse=r['fragments'], slice_name=name, index=index))
                with self.subTest(slice=name):
                    self.assertEqual(stable(warm), stable(r))
                    self.assertEqual(warm['fragments'], {})


FIRST = ('TS/JS relative imports and workflow uses resolve to the first present candidate in a '
         'declared order; alternatives are not reported.')


class SliceSourceTests(unittest.TestCase):
    def test_sliced_source_binding_and_slice_independent_fragments(self):
        with scratch() as root:
            whole = respond(build(root, CONTENT))
            parts = sliced(root, CONTENT)
        head = dict(repository='Fixture/Source', head='a' * 40)
        self.assertEqual(whole['graph']['source'], head)
        self.assertEqual(whole['validation']['source'], head)
        for name, r in parts.items():
            with self.subTest(slice=name):
                self.assertEqual(r['graph']['source'], dict(head, slice=name))
                self.assertEqual(r['validation']['source'], dict(head, slice=name))
                self.assertEqual(r['graph']['built_at_commit'], head['head'])
                for p, item in r['fragments'].items():
                    self.assertEqual(adapter.encoded(item), adapter.encoded(whole['fragments'][p]))
                    self.assertNotIn(b'slice', adapter.encoded(item))
        self.assertEqual(sum(len(r['fragments']) for r in parts.values()), len(whole['fragments']))

    def test_first_precedence_limitation_is_family_two_only(self):
        content = {'docs/a.md': b'# A\n'}
        with scratch() as root:
            two = respond(build(root, content))
            one = respond(build(root, content, version='1'))
        self.assertEqual(two['validation']['limitations'].count(FIRST), 1)
        self.assertNotIn(FIRST, one['validation']['limitations'])


class PrecedenceTests(unittest.TestCase):
    """r3 V2: 'first' for TS/JS relative imports and workflow uses; 'unique' elsewhere."""

    def targets(self, content, source):
        with scratch() as root:
            r = respond(build(root, content))
        return {t for s, kind, t in links(r) if s == source and kind in ('imports', 'uses', 'sources')}, r

    def test_a_extension_before_index(self):
        main = {'src/main.ts': b"import a from './x';\n"}
        both = dict(main, **{'src/x.ts': b'', 'src/x/index.ts': b''})
        self.assertEqual(self.targets(both, 'src/main.ts')[0], {'src/x.ts'})
        only = dict(main, **{'src/x/index.ts': b''})
        self.assertEqual(self.targets(only, 'src/main.ts')[0], {'src/x/index.ts'})

    def test_b_ts_before_tsx(self):
        content = {'src/main.ts': b"import a from './x';\n", 'src/x.ts': b'', 'src/x.tsx': b''}
        self.assertEqual(self.targets(content, 'src/main.ts')[0], {'src/x.ts'})

    def test_c_literal_js_before_ts_swap(self):
        main = {'src/main.ts': b"import a from './x.js';\n"}
        both = dict(main, **{'src/x.js': b'', 'src/x.ts': b''})
        self.assertEqual(self.targets(both, 'src/main.ts')[0], {'src/x.js'})
        only = dict(main, **{'src/x.ts': b''})
        self.assertEqual(self.targets(only, 'src/main.ts')[0], {'src/x.ts'})

    def test_d_sliced_first_candidate_in_other_slice(self):
        content = {'src/main.ts': b"import a from './x';\n", 'src/x.ts': b'', 'src/x/index.ts': b''}
        index = {'src/main.ts': 'a', 'src/x.ts': 'b', 'src/x/index.ts': 'a'}
        with scratch() as root:
            whole = respond(build(root, content))
            own = respond(build(root, {p: content[p] for p in content if index[p] == 'a'},
                                slice_name='a', index=index))
        expected = {(e['source'], e['target'], e['type'], e['source_file'])
                    for e in whole['graph']['links'] if e['source_file'] == 'src/main.ts' and e['type'] == 'imports'}
        self.assertEqual(expected, {(adapter.file_id('src/main.ts'), adapter.file_id('src/x.ts'),
                                     'imports', 'src/main.ts')})
        crossing = own['validation']['cross_slice_references']
        self.assertEqual([(x['target_path'], x['target_slice'], x['target']) for x in crossing],
                         [('src/x.ts', 'b', './x')])
        self.assertEqual({(x['source'], x['target_id'], x['type'], x['source_file']) for x in crossing}, expected)
        self.assertFalse([e for e in own['graph']['links'] if e['type'] == 'imports'])

    def test_e_workflow_action_yml_before_yaml(self):
        content = {'.github/workflows/w.yml': b'jobs:\n  b:\n    steps:\n      - uses: ./a\n',
                   'a/action.yml': b'runs: {}\n', 'a/action.yaml': b'runs: {}\n'}
        self.assertEqual(self.targets(content, '.github/workflows/w.yml')[0], {'a/action.yml'})

    def test_f_unique_reference_with_two_present_candidates_is_unresolved(self):
        content = {'scripts/run.sh': b'. ./lib.sh\n', 'scripts/lib.sh': b':\n', 'lib.sh': b':\n'}
        found, r = self.targets(content, 'scripts/run.sh')
        self.assertEqual(found, set())
        self.assertEqual(unresolved(r, 'scripts/run.sh'), {'./lib.sh'})


@unittest.skipUnless(os.environ.get('GRAPHIFY_STRUCTURAL_SCALE') == '1',
                     'large synthetic slice fixture requires an explicit serial slot')
class ScaleTests(unittest.TestCase):
    def test_full_slice_and_index_bounds(self):
        content = {f'src/m{i:04d}.ts': f"import {{ x }} from './m{(i + 1) % 2048:04d}';\nexport const x{i} = {i};\n".encode()
                   for i in range(adapter.MAX_FILES_V2)}
        index = {p: 'a' for p in content}
        index.update({f'other/f{i:05d}.md': 'b' for i in range(adapter.MAX_INDEX_PATHS - len(content))})
        with scratch() as root:
            raw = adapter.encoded(build(root, content, slice_name='a', index=dict(sorted(index.items())),
                                        limits=dict(file_bytes=4 * 1024**2, input_bytes=112 * 1024**2,
                                                    output_bytes=64 * 1024**2, seconds=300, records=100000)))
            self.assertLessEqual(len(raw), adapter.MAX_REQUEST_V2)
            result = invoke(raw)
            self.assertEqual(result.returncode, 0, result.stderr[-400:])
            graph = json.loads(result.stdout)['graph']
            self.assertEqual(sum(e['type'] == 'imports' for e in graph['links']), adapter.MAX_FILES_V2)


if __name__ == '__main__':
    unittest.main()
