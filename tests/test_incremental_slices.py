"""Sliced v2 incremental builds over synthetic bare mirrors; fixture scratch owns every
repository, store and cache. Build tests need the family-2 adapter (G-F) and the
slice-aware pack (G-I); admission, preflight-hold and digest tests need neither.
Scale qualification runs only with GRAPHIFY_SLICE_SCALE=1 under CPU admission and
writes its measurements to GRAPHIFY_SLICE_SCALE_REPORT when set."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tooling'), str(ROOT / 'tests')]
import fragment_cache
import graph_pack as packer
import graph_read as reader
import graph_refresh as refresh
import graph_refresh_incremental as inc
import refresh_adapter_structural as adapter
import runtime_identity
import semantic_batch as sb
import test_graph_refresh_incremental as base

SIX = [dict(prefix=p + '/', name=p) for p in ('a', 'b', 'c', 'd', 'e')]
FILES = {'a/main.py': b'import b.target\nimport c.other\ndef run():\n    pass\n',
         'b/target.py': b'def target():\n    pass\n',
         'c/other.py': b'class Other:\n    pass\n',
         'c/unrelated.py': b'def alone():\n    pass\n',
         'd/one.py': b'def one():\n    pass\n',
         'e/two.md': b'# Two\n[a](../a/main.py)\n',
         'top.py': b'def top():\n    pass\n'}


def policy(rules=SIX, **slicing):
    limits = dict(rules=rules, max_slice_files=2048, max_slice_bytes=inc.OPERATING_MAX_SLICE_BYTES,
                  max_slice_records=100000)
    limits.update(slicing)
    return dict(schema=inc.POLICY_SCHEMA_V2, include=['*.py', '*.md'], deny=[],
                max_files=32768, max_file_bytes=4 * 1024**2, max_total_bytes=128 * 1024**2,
                slicing=limits)


class Fixture(base.Fixture):
    def manifest_v2(self, commit, previous=None, mode='build', **changes):
        m = dict(schema=inc.SCHEMA_V2, mode=mode, repository=base.REPOSITORY,
                 mirror_git_dir=str(self.mirror), commit=commit,
                 target=dict(oid=None, observed_at=None, method=None), admission_policy=policy(),
                 extractor=dict(protocol='python-json/v2', name='graphify-stdlib-structural',
                                version='2', executable=base.select(base.PYTHON),
                                script=base.select(base.ADAPTER)),
                 runtime_probe=base.select(base.PROBE), state_root=str(self.state),
                 previous_run=previous, destination=str(self.destination()), lock=str(self.lock),
                 cache_quota_bytes=64 * 1024**2, limits=dict(inc.LIMITS_V2, seconds=60))
        m.update(changes)
        return m

    def build(self, commit, previous=None, **changes):
        return self.run(self.manifest_v2(commit, previous=previous, **changes))


def fixture():
    class Context:
        def __enter__(self):
            self.scratch = base.scratch()
            return Fixture(self.scratch.__enter__())

        def __exit__(self, *exc):
            return self.scratch.__exit__(*exc)
    return Context()


def load(selection):
    raw = Path(selection['path']).read_bytes()
    assert reader.digest(raw) == selection['sha256']
    return json.loads(raw)


def entries(result):
    return {e['name']: e for e in load(result['slice_set'])['slices']}


def run_slices(result):
    return {s['name']: s for s in load(result['slice_run'])['slices']}


class AdmissionTests(unittest.TestCase):
    """Pure functions: no Git, adapter, pack or filesystem."""

    def test_bucket_assignment_is_stable_when_paths_are_added(self):
        rules = [dict(prefix='src/', name='src', buckets=8)]
        first = {f'src/m{i}.py': inc.assign_slice(f'src/m{i}.py', rules) for i in range(300)}
        more = [f'src/n{i}.py' for i in range(300)]
        for p in more:
            inc.assign_slice(p, rules)
        self.assertEqual(first, {p: inc.assign_slice(p, rules) for p in first})
        self.assertEqual({v for v in first.values()}, {'src.%02d' % i for i in range(8)})
        self.assertEqual(inc.assign_slice('docs/x.md', rules), inc.REST)

    def test_first_matching_prefix_wins_without_reordering(self):
        rules = [dict(prefix='src/core/', name='core'), dict(prefix='src/', name='src')]
        self.assertEqual(inc.assign_slice('src/core/a.py', rules), 'core')
        self.assertEqual(inc.assign_slice('src/b.py', rules), 'src')
        self.assertEqual(inc.assign_slice('srcx/b.py', rules), inc.REST)

    def test_policy_bounds_fail_closed_and_catalog_cap_is_not_raised(self):
        self.assertEqual(inc.validate_policy_v2(policy()), policy())
        bad = [policy([dict(prefix='a/', name='rest')]),
               policy([dict(prefix='a/', name='x'), dict(prefix='a/', name='y')]),
               policy([dict(prefix='a', name='x')]),
               policy([dict(prefix='../a/', name='x')]),
               policy([dict(prefix='a/', name='x', buckets=17)]),
               policy([dict(prefix='a/', name='x.y')]),
               policy([dict(prefix=f'p{i}/', name=f'p{i}', buckets=16) for i in range(8)]),
               policy(max_slice_files=2049), policy(max_slice_bytes=inc.OPERATING_MAX_SLICE_BYTES + 1),
               policy(max_slice_bytes=inc.MAX_SLICE_BYTES),
               policy(max_slice_records=100001), dict(policy(), max_files=32769),
               dict(policy(), max_total_bytes=128 * 1024**2 + 1),
               dict(policy(), max_file_bytes=4 * 1024**2 + 1)]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                inc.validate_policy_v2(value)
        # 7 x 16 buckets + 15 + rest = 128 possible slices: exactly the catalog cap.
        inc.validate_policy_v2(policy([dict(prefix=f'p{i}/', name=f'p{i}', buckets=16) for i in range(7)]
                                      + [dict(prefix='q/', name='q', buckets=15)]))

    def test_over_limit_slice_holds_and_is_never_split(self):
        files = [dict(path=f'a/{i}.py', blob_oid='0' * 40, bytes=10) for i in range(3)]
        files.append(dict(path='b/x.py', blob_oid='0' * 40, bytes=10))
        slices, _, holds = inc.plan_slices(files, [], policy(max_slice_files=2))
        self.assertEqual(sorted(slices), ['a', 'b'])
        self.assertEqual(len(slices['a']), 3)
        self.assertEqual(holds, [dict(reason='slice_over_limit', slice='a', bounds=['files'],
                                      files=3, bytes=30)])
        _, _, holds = inc.plan_slices(files, [], policy(max_slice_bytes=29))
        self.assertEqual([(h['slice'], h['bounds']) for h in holds], [('a', ['content_bytes'])])
        _, _, holds = inc.plan_slices(files, [], dict(policy(), max_files=3))
        self.assertEqual((holds[0]['reason'], holds[0]['bounds']), ('repository_over_limit', ['files']))

    def test_path_lengths_report_max_and_nearest_rank_p99(self):
        paths = ['a' * n for n in range(1, 201)]
        self.assertEqual(inc.path_lengths(paths), dict(max_bytes=200, p99_bytes=198))
        self.assertEqual(inc.path_lengths(['\u00e9']), dict(max_bytes=2, p99_bytes=2))
        self.assertEqual(inc.path_lengths([]), dict(max_bytes=0, p99_bytes=0))

    def test_stage_names_match_staging_and_avoid_admitted_paths(self):
        files = {'.graphify-path-index.json': 'x', 'b.py': 'y'}
        fragments, index_name, names = inc.stage_names(files, {'b.py': 1})
        self.assertEqual((fragments, index_name, names),
                         ('.graphify-fragments', '_.graphify-path-index.json',
                          {'b.py': '.graphify-fragments/0.json'}))

    def test_resolution_digest_tracks_candidate_ownership_only(self):
        index = {'a/main.py': 'a', 'b/target.py': 'b', 'c/other.py': 'c'}
        before = inc.resolution_digest(['b/target.py', 'b/target/__init__.py'], index)
        self.assertEqual(before, inc.resolution_digest(['b/target/__init__.py', 'b/target.py',
                                                        'b/target.py'], index))
        self.assertEqual(before, inc.resolution_digest(['b/target.py', 'b/target/__init__.py'],
                                                       dict(index, **{'c/new.py': 'c'})))
        moved = dict(index, **{'b/target.py': 'c'})
        removed = {k: v for k, v in index.items() if k != 'b/target.py'}
        self.assertNotEqual(before, inc.resolution_digest(['b/target.py'], moved))
        self.assertNotEqual(before, inc.resolution_digest(['b/target.py', 'b/target/__init__.py'], removed))

    def test_input_digest_binds_files_unsupported_and_identities(self):
        ids = dict.fromkeys(inc.IDENTITY_FIELDS, '1' * 64)
        files = [dict(path='a/x.py', blob_oid='2' * 40, bytes=1)]
        one = inc.input_digest(base.REPOSITORY, 'a', files, [], ids)
        self.assertNotEqual(one, inc.input_digest(base.REPOSITORY, 'a',
                                                  [dict(files[0], blob_oid='3' * 40)], [], ids))
        self.assertNotEqual(one, inc.input_digest(base.REPOSITORY, 'a', files,
                                                  [dict(path='a/l', reason='symlink')], ids))
        self.assertNotEqual(one, inc.input_digest(base.REPOSITORY, 'a', files, [],
                                                  dict(ids, runtime_identity_sha256='4' * 64)))
        self.assertNotEqual(one, inc.input_digest(base.REPOSITORY, 'b', files, [], ids))

    def test_v1_state_schema_and_fields_are_unchanged_and_v2_is_distinct(self):
        self.assertEqual(inc.STATE_SCHEMA, 'graphify-build-state/v1')
        self.assertEqual((sb.STATE_SCHEMA, sb.STATE_FIELDS), (inc.STATE_SCHEMA, inc.STATE_FIELDS))
        self.assertNotEqual(inc.SLICE_STATE_SCHEMA, sb.STATE_SCHEMA)
        self.assertEqual(inc.SLICE_STATE_FIELDS[:len(inc.STATE_FIELDS)], inc.STATE_FIELDS)
        self.assertIn('slice', inc.SLICE_STATE_FIELDS)


class SlicedBuildTests(unittest.TestCase):
    """End to end over a synthetic mirror; requires family-2 adapter and slice pack."""

    def cold(self, fx):
        commit = fx.commit(FILES)
        result = fx.build(commit)
        self.assertEqual(result['status'], 'completed', result)
        return commit, result

    def test_six_slices_one_file_change_runs_one_adapter_and_reuses_five(self):
        with fixture() as fx:
            _, first = self.cold(fx)
            self.assertEqual(sorted(entries(first)), ['a', 'b', 'c', 'd', 'e', 'rest'])
            self.assertEqual(first['counts']['adapter_runs'], 6)
            commit = fx.commit({'d/one.py': b'def one():\n    return 1\n'})
            second = fx.build(commit, previous=first['slice_run'])
            self.assertEqual(second['status'], 'completed', second)
            self.assertEqual((second['counts']['adapter_runs'], second['counts']['slices_built'],
                              second['counts']['slices_reused']), (1, 1, 5))
            self.assertEqual((second['counts']['modified'], second['counts']['unchanged']),
                             (1, len(FILES) - 1))
            old, new = entries(first), entries(second)
            for name in ('a', 'b', 'c', 'e', 'rest'):
                self.assertEqual(new[name], old[name])
                self.assertEqual(run_slices(second)[name]['status'], 'reused')
                self.assertEqual(run_slices(second)[name]['build_state'],
                                 run_slices(first)[name]['build_state'])
            self.assertEqual(new['d']['built_head'], commit)
            self.assertNotEqual(new['d']['package_sha256'], old['d']['package_sha256'])
            self.assertEqual(load(second['slice_set'])['accepted_head'], commit)
            self.assertFalse((Path(second['destination']) / 'slices' / 'a').exists())

    def test_cross_slice_target_removal_reassembles_referrer_not_unrelated(self):
        with fixture() as fx:
            _, first = self.cold(fx)
            a_dir = Path(run_slices(first)['a']['build_state']['path']).parent
            validation = json.loads((a_dir / 'evidence' / 'validation.json').read_bytes())
            crossing = {(r['target_path'], r['target_slice'], r['target_id'])
                        for r in validation['cross_slice_references']}
            self.assertIn(('b/target.py', 'b', inc.structural_file_id('b/target.py')), crossing)
            b_graph = json.loads((Path(run_slices(first)['b']['build_state']['path']).parent
                                  / 'evidence' / 'graph.json').read_bytes())
            self.assertIn(inc.structural_file_id('b/target.py'), {n['id'] for n in b_graph['nodes']})
            commit = fx.commit({'b/target.py': None, 'b/keep.py': b'def keep():\n    pass\n'})
            second = fx.build(commit, previous=first['slice_run'])
            self.assertEqual(second['status'], 'completed', second)
            status = {n: s['status'] for n, s in run_slices(second).items()}
            self.assertEqual(status, dict(a='built', b='built', c='reused', d='reused',
                                          e='reused', rest='reused'))
            self.assertNotEqual(entries(second)['a']['resolution_digest'],
                                entries(first)['a']['resolution_digest'])
            self.assertEqual(entries(second)['a']['input_digest'], entries(first)['a']['input_digest'])
            self.assertEqual(entries(second)['c'], entries(first)['c'])

    def test_state_and_slice_set_hashes_are_consistent_and_v1_planner_refuses(self):
        with fixture() as fx:
            commit, result = self.cold(fx)
            slice_set = load(result['slice_set'])
            self.assertEqual(set(slice_set), {'schema', 'repository', 'accepted_head', 'tree', 'slices'})
            self.assertEqual(slice_set['tree'], result['tree'])
            run = load(result['slice_run'])
            self.assertEqual(run['slice_set_sha256'], result['slice_set']['sha256'])
            paths = set()
            for entry in slice_set['slices']:
                self.assertEqual(set(entry), set(inc.SLICE_ENTRY_FIELDS))
                selection = run_slices(result)[entry['name']]['build_state']
                self.assertEqual(selection['sha256'], entry['build_state_sha256'])
                state = load(selection)
                self.assertEqual((state['schema'], state['slice'], state['commit'], state['package_sha256'],
                                  state['input_digest'], state['resolution_digest']),
                                 (inc.SLICE_STATE_SCHEMA, entry['name'], entry['built_head'],
                                  entry['package_sha256'], entry['input_digest'],
                                  entry['resolution_digest']))
                package = Path(selection['path']).parent / 'candidate' / 'package.json'
                self.assertEqual(reader.digest(package.read_bytes()), entry['package_sha256'])
                self.assertEqual(json.loads(package.read_bytes())['source']['slice'], entry['name'])
                mine = {f['path'] for f in state['files']}
                self.assertFalse(mine & paths)
                paths |= mine
                with self.assertRaises(ValueError):
                    sb.build_state((selection['path'], selection['sha256']))
            self.assertEqual(paths, set(FILES))
            again = fx.build(commit, previous=result['slice_run'])
            self.assertEqual(again['status'], 'unchanged', again)
            self.assertFalse(Path(again['destination']).exists())

    def test_over_limit_slice_holds_before_any_adapter_run_or_output(self):
        with fixture() as fx:
            commit = fx.commit(FILES)
            with patch.object(refresh, 'run_adapter', side_effect=AssertionError('adapter ran')):
                result = fx.build(commit, admission_policy=policy(max_slice_files=1))
            self.assertEqual((result['status'], result['reason']), ('held', 'slice_over_limit'))
            self.assertEqual([(h['slice'], h['bounds']) for h in result['hold']['holds']],
                             [('c', ['files'])])
            self.assertFalse(Path(result['destination']).exists())
            self.assertEqual(fx.entries(), [])

    def test_inventory_only_reads_no_blob_runs_no_adapter_and_leaves_cache(self):
        with fixture() as fx:
            commit = fx.commit(dict(FILES, **{'notes.txt': b'x\n'}))
            with patch.object(inc, 'read_blobs', side_effect=AssertionError('blob read')), \
                    patch.object(refresh, 'run_adapter', side_effect=AssertionError('adapter ran')):
                result = fx.build(commit, mode='inventory_only',
                                  admission_policy=policy(max_slice_files=1))
            self.assertEqual(result['status'], 'inventory', result)
            document = load(result['inventory'])
            self.assertEqual(document['totals']['admitted'], len(FILES))
            self.assertEqual(document['totals']['not_included'], 1)
            self.assertEqual({s['name']: s['status'] for s in document['slices']}['c'], 'slice_over_limit')
            self.assertEqual(document['paths']['b/target.py'], 'b')
            self.assertEqual(document['path_length'], inc.path_lengths(FILES))
            self.assertTrue(all(s['request_bytes_upper_bound'] > 0 for s in document['slices']))
            self.assertEqual(base.listing(result['destination']), [inc.INVENTORY_NAME])
            self.assertFalse((fx.state / inc.CACHE_DIRECTORY).exists())

    def test_tampered_previous_run_fails_closed(self):
        with fixture() as fx:
            _, first = self.cold(fx)
            set_path = Path(first['slice_set']['path'])
            set_path.chmod(0o600)
            set_path.write_bytes(set_path.read_bytes().replace(b'"rest"', b'"rust"'))
            commit = fx.commit({'d/one.py': b'def one():\n    return 2\n'})
            result = fx.build(commit, previous=first['slice_run'])
            self.assertEqual(result['status'], 'failed', result)
            self.assertIn('checksum', result['reason'])


class PreflightTests(unittest.TestCase):
    """Exact preflight holds and adapter refusal; no family-2 adapter output is needed."""

    def test_exact_request_and_input_preflight_hold_before_any_extraction(self):
        with fixture() as fx:
            commit = fx.commit(FILES)
            no_adapter = patch.object(refresh, 'run_adapter', side_effect=AssertionError('adapter ran'))
            with no_adapter, patch.object(inc, 'MAX_REQUEST_V2', 512):
                result = fx.build(commit)
            self.assertEqual((result['status'], result['reason']), ('held', 'slice_over_limit'))
            held = {h['slice']: h for h in result['hold']['holds']}
            self.assertTrue(held and all(h['bounds'] == ['request_bytes'] and h['request_bytes'] > 512
                                         for h in held.values()))
            self.assertFalse(Path(result['destination']).exists())
            tight = dict(inc.LIMITS_V2, seconds=60, input_bytes=len(FILES['a/main.py']))
            with no_adapter:
                result = fx.build(commit, limits=tight)
            self.assertEqual(result['status'], 'held', result)
            self.assertIn('input_bytes', result['hold']['holds'][0]['bounds'])
            self.assertFalse(Path(result['destination']).exists())

    def test_adapter_refusal_is_failed_never_relabelled_or_retried(self):
        with fixture() as fx:
            commit = fx.commit(FILES)
            with patch.object(refresh, 'run_adapter',
                              side_effect=ValueError('extractor nonzero exit')) as adapter:
                result = fx.build(commit)
            self.assertEqual((result['status'], result['reason']),
                             ('failed', 'adapter_rejected: extractor nonzero exit'))
            self.assertEqual(adapter.call_count, 1)
            self.assertEqual(result['failed_slice']['name'], 'a')
            self.assertEqual(result['failed_slice']['bounds'], [])
            self.assertGreater(result['failed_slice']['request_bytes'], 0)
            self.assertIsNone(result['hold'])
            self.assertEqual(result['resources']['adapter_runs'], 1)


C_FILES = {f'c/k{i}.py': b'def k%d():\n    pass\n' % i for i in range(3)}


def slice_dir(result, name):
    return Path(run_slices(result)[name]['build_state']['path']).parent


def slice_evidence(result, name):
    """graph, validation and inventory of one built slice, without the request binding."""
    documents = {n: json.loads((slice_dir(result, name) / 'evidence' / f'{n}.json').read_bytes())
                 for n in ('graph', 'validation', 'inventory')}
    for n in ('graph', 'validation'):
        documents[n].pop('refresh_request_sha256')
    return documents


def adapter_wrapper(change=None, refuse=None):
    """Wrap the real adapter run: optionally refuse a request or alter its response bytes."""
    real, calls = refresh.run_adapter, []

    def run(executable, script, request, cwd, limits):
        body = json.loads(request.read())
        request.seek(0)
        calls.append(body)
        if refuse is not None and refuse(body):
            raise ValueError('extractor nonzero exit')
        raw, evidence = real(executable, script, request, cwd, limits)
        if change is not None:
            response = json.loads(raw)
            change(response)
            raw = packer.encoded(response)
        return raw, evidence
    return run, calls


def reuses(body):
    return any(f['action'] == 'reuse' for f in body['files'])


class CacheTests(unittest.TestCase):
    """r4 I2 follow-on: family-2 fragments are cached once G-J accepts their schema."""

    def test_driver_constants_match_cache_and_adapter(self):
        self.assertEqual(inc.FRAGMENT_SCHEMA_V2, fragment_cache.FRAGMENT_SCHEMA_V2)
        self.assertEqual(inc.FAMILY_V2, fragment_cache.FAMILY_V2)
        self.assertEqual(inc.FRAGMENT_BYTES, adapter.FRAGMENT_BYTES)
        self.assertEqual(inc.MAX_REQUEST_V2, adapter.MAX_REQUEST_V2)
        self.assertEqual(inc.MAX_INDEX_BYTES, adapter.MAX_INDEX_BYTES)
        self.assertNotIn('cache_uncacheable', inc.COUNTS)
        self.assertEqual(len(inc.COUNTS), 11)

    def test_one_changed_file_extracts_one_reuses_the_rest_and_equals_cold(self):
        with fixture() as fx:
            commit = fx.commit(dict(FILES, **C_FILES))
            first = fx.build(commit)
            self.assertEqual((first['status'], first['cache_status']), ('completed', 'ok'), first)
            commit = fx.commit({'c/unrelated.py': b'def alone():\n    return 1\n'})
            second = fx.build(commit, previous=first['slice_run'])
            self.assertEqual((second['status'], second['cache_status']), ('completed', 'ok'), second)
            state = load(run_slices(second)['c']['build_state'])
            n = len(state['files'])
            self.assertEqual(n, 5)
            self.assertEqual({k: state['counts'][k] for k in
                              ('extracted', 'reused', 'cache_hits', 'cache_misses', 'cache_uncacheable')},
                             dict(extracted=1, reused=n - 1, cache_hits=n - 1, cache_misses=1,
                                  cache_uncacheable=0))
            self.assertEqual((second['counts']['extracted'], second['counts']['reused'],
                              second['counts']['adapter_runs']), (1, n - 1, 1))
            cold = fx.build(commit, state_root=str(fx.new_state()))
            self.assertEqual(cold['status'], 'completed', cold)
            self.assertEqual(load(run_slices(cold)['c']['build_state'])['counts']['extracted'], n)
            self.assertEqual(slice_evidence(second, 'c'), slice_evidence(cold, 'c'))
            cold_state = load(run_slices(cold)['c']['build_state'])
            # graph_sha256 differs only through the bound request SHA256 (reuse vs extract).
            for key in ('files', 'input_digest', 'resolution_digest', 'reference_candidates'):
                self.assertEqual(state[key], cold_state[key], key)

    def test_oversize_entries_are_counted_uncacheable_and_not_stored(self):
        with fixture() as fx:
            commit = fx.commit(FILES)
            with patch.object(fragment_cache, 'MAX_ENTRY_V2', 64):
                result = fx.build(commit)
            self.assertEqual((result['status'], result['cache_status']), ('completed', 'degraded'), result)
            self.assertEqual(result['counts']['cache_uncacheable'], len(FILES))
            self.assertEqual(result['cache']['puts'], dict(uncacheable=len(FILES)))
            self.assertEqual(fx.entries(), [])

    def test_unidentified_runtime_disables_caching(self):
        with fixture() as fx:
            commit = fx.commit(FILES)
            unknown = runtime_identity.unidentified('synthetic probe failure')
            with patch.object(runtime_identity, 'identify', return_value=unknown):
                first = fx.build(commit)
                again = fx.build(commit, previous=first['slice_run'])
            for result in (first, again):
                self.assertEqual(result['status'], 'completed', result)
                self.assertEqual(result['cache_status'], 'cache_disabled:runtime_unidentified')
                self.assertEqual(result['counts']['extracted'], len(FILES))
                self.assertEqual(result['counts']['cache_hits'] + result['counts']['cache_misses'], 0)
            self.assertTrue(all(f['key_sha256'] is None
                                for s in run_slices(first).values() for f in load(s['build_state'])['files']))
            self.assertFalse((fx.state / inc.CACHE_DIRECTORY).exists())

    def test_rejected_reuse_falls_back_once_and_never_again(self):
        with fixture() as fx:
            commit = fx.commit(dict(FILES, **C_FILES))
            first = fx.build(commit)
            commit = fx.commit({'c/unrelated.py': b'def alone():\n    return 2\n'})
            run, calls = adapter_wrapper(refuse=reuses)
            with patch.object(refresh, 'run_adapter', run):
                second = fx.build(commit, previous=first['slice_run'])
            self.assertEqual(second['status'], 'completed', second)
            self.assertEqual([reuses(c) for c in calls], [True, False])
            self.assertEqual(load(run_slices(second)['c']['build_state'])['cache_status'], 'reuse_rejected')
            self.assertEqual(second['counts']['adapter_runs'], 2)
            run, calls = adapter_wrapper(refuse=lambda body: True)
            commit = fx.commit({'c/unrelated.py': b'def alone():\n    return 3\n'})
            with patch.object(refresh, 'run_adapter', run):
                third = fx.build(commit, previous=second['slice_run'])
            self.assertEqual((third['status'], third['reason']),
                             ('failed', 'adapter_rejected: extractor nonzero exit'))
            self.assertEqual(len(calls), 2)
            self.assertIsNone(third['hold'])


class SourceBindingTests(unittest.TestCase):
    """r4 I1 check 4: only adapter-bound slice sources pack; tampering is refused unrewritten."""

    def test_tampered_slice_source_is_refused_and_left_as_emitted(self):
        def drop(response):
            for part in ('graph', 'validation'):
                response[part]['source'].pop('slice')

        def rename(response):
            for part in ('graph', 'validation'):
                response[part]['source']['slice'] = 'other'

        with fixture() as fx:
            commit = fx.commit(FILES)
            good = fx.build(commit)
            self.assertEqual(good['status'], 'completed', good)
            for entry in load(good['slice_set'])['slices']:
                package = json.loads((slice_dir(good, entry['name']) / 'candidate' / 'package.json')
                                     .read_bytes())
                self.assertEqual(package['source']['slice'], entry['name'])
            for change in (drop, rename):
                run, _ = adapter_wrapper(change=change)
                with patch.object(refresh, 'run_adapter', run):
                    result = fx.build(commit)
                self.assertEqual(result['status'], 'failed', result)
                self.assertIn('adapter output lacks slice source binding', result['reason'])
                attempt = Path(result['destination']) / 'slices' / 'a' / 'attempts' / '1'
                emitted = json.loads((attempt / 'adapter-response.json').read_bytes())
                self.assertNotEqual(emitted['graph']['source'].get('slice'), 'a')
                self.assertFalse((Path(result['destination']) / 'slices' / 'a' / 'candidate').exists())


def index_files(fx, paths, raw=b'x = 1\n'):
    """Commit many paths sharing one blob through the index; no work-tree files."""
    blob = subprocess.run(['git', '-C', str(fx.work), 'hash-object', '-w', '--stdin'], input=raw,
                          capture_output=True, check=True, timeout=60).stdout.decode().strip()
    listing = ''.join(f'100644 {blob}\t{p}\n' for p in paths).encode()
    subprocess.run(['git', '-C', str(fx.work), 'update-index', '--add', '--index-info'], input=listing,
                   capture_output=True, check=True, timeout=600)
    return fx.publish()


def scale_report(name, result, **extra):
    """Append one measurement line; holds report their preflight numbers instead of slices."""
    target = os.environ.get('GRAPHIFY_SLICE_SCALE_REPORT')
    if target:
        rows = load(result['slice_report'])['slices'] if result.get('slice_report') else None
        with open(target, 'a', encoding='utf-8') as handle:
            handle.write(json.dumps(dict(case=name, status=result['status'], resources=result['resources'],
                                         slices=rows, hold=result.get('hold'), **extra),
                                    sort_keys=True) + '\n')


@unittest.skipUnless(os.environ.get('GRAPHIFY_SLICE_SCALE') == '1',
                     'scale qualification runs only under explicit CPU admission')
class ScaleQualificationTests(unittest.TestCase):
    """r3 V3 measurements at the operating values; results land in the receipt resources."""

    def test_byte_heavy_cold_slice_at_operating_bytes(self):
        with fixture() as fx:
            per_file = inc.OPERATING_MAX_SLICE_BYTES // 24
            body = b''.join(b'def f%d():\n    pass\n' % i for i in range(500))
            padding = b'# ' + b'x' * 77 + b'\n'
            content = body + padding * ((per_file - len(body)) // len(padding))
            commit = fx.commit({f'heavy/m{i:02d}.py': content for i in range(24)})
            result = fx.build(commit, admission_policy=policy([dict(prefix='heavy/', name='heavy')]))
            self.assertEqual(result['status'], 'completed', result)
            row = {r['name']: r for r in load(result['slice_report'])['slices']}['heavy']
            self.assertLessEqual(row['content_bytes'], inc.OPERATING_MAX_SLICE_BYTES)
            for key in ('response_bytes', 'response_input_ratio', 'wall_seconds', 'max_rss_kib_children'):
                self.assertIn(key, row)
            scale_report('byte_heavy', result)

    def test_record_dense_slice_near_record_bound(self):
        with fixture() as fx:
            content = b''.join(b'def f%d():\n    pass\n' % i for i in range(490))
            commit = fx.commit({f'dense/m{i:03d}.py': content for i in range(100)})
            result = fx.build(commit, admission_policy=policy([dict(prefix='dense/', name='dense')]))
            self.assertEqual(result['status'], 'completed', result)
            graph = json.loads((Path(run_slices(result)['dense']['build_state']['path']).parent
                                / 'evidence' / 'graph.json').read_bytes())
            records = len(graph['nodes']) + len(graph['links'])
            self.assertGreater(records, 95000)
            scale_report('record_dense', result, graph_records=records)

    def test_long_path_request_and_index_hold_at_their_byte_bounds(self):
        with fixture() as fx:
            deep = 'L/' + '/'.join(['p' * 200] * 5) + '/'
            commit = index_files(fx, [f'{deep}m{i:04d}.py' for i in range(2048)])
            with patch.object(refresh, 'run_adapter', side_effect=AssertionError('adapter ran')):
                result = fx.build(commit, admission_policy=policy([dict(prefix='L/', name='long')]))
            self.assertEqual(result['status'], 'held', result)
            hold = result['hold']['holds'][0]
            self.assertEqual((hold['slice'], hold['bounds']), ('long', ['request_bytes']))
            self.assertGreater(hold['request_bytes'], inc.MAX_REQUEST_V2)
            self.assertLessEqual(hold['index_bytes'], inc.MAX_INDEX_BYTES)
            scale_report('long_path_request', result)
        with fixture() as fx:
            stem = 'W/' + 'q' * 240 + '/'
            commit = index_files(fx, [f'{stem}m{i:05d}.py' for i in range(32768)])
            with patch.object(refresh, 'run_adapter', side_effect=AssertionError('adapter ran')):
                result = fx.build(commit, admission_policy=policy([dict(prefix='W/', name='wide',
                                                                        buckets=16)]))
            self.assertEqual(result['status'], 'held', result)
            self.assertIn('path_index_over_limit', {h['reason'] for h in result['hold']['holds']})
            scale_report('long_path_index', result)
            inventory = fx.build(commit, mode='inventory_only',
                                 admission_policy=policy([dict(prefix='W/', name='wide', buckets=16)]))
            self.assertEqual(inventory['status'], 'inventory', inventory)
            document = load(inventory['inventory'])
            self.assertFalse(document['path_index']['within_limit'])
            self.assertGreater(document['path_length']['p99_bytes'], 240)
            scale_report('long_path_inventory', inventory, path_length=document['path_length'],
                         path_index=document['path_index'])


if __name__ == '__main__':
    unittest.main()
