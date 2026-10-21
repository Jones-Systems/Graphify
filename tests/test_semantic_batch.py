"""Synthetic build states and approval fixtures only; each fixture owns and removes its scratch."""
import ast
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

TOOLING = Path(__file__).resolve().parents[1] / 'tooling'
sys.path.insert(0, str(TOOLING))
import graph_pack
import graph_refresh_incremental as inc
import semantic_batch as sb

NOW = datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc)
C1, C2, C3 = '1' * 40, '2' * 40, '3' * 40
OWNER = 'Synthetic Owner'


@contextmanager
def workspace():
    # Under this checkout (or a caller-selected task root), never /tmp;
    # TemporaryDirectory removes only its own children on every exit path.
    parent = os.environ.get('GRAPHIFY_PACK_TEST_ROOT', str(Path(__file__).resolve().parents[1]))
    with tempfile.TemporaryDirectory(prefix='semantic-batch-test-',
                                     dir=Path(parent).resolve()) as directory:
        os.chmod(directory, 0o700)
        yield Path(directory)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(root, name, value):
    data = graph_pack.encoded(value) if isinstance(value, dict) else value
    path = root / name
    path.write_bytes(data)
    return [str(path), sha(data)]


def state(repository, commit, files, order=None):
    """A closed graphify-build-state/v1 document; files maps path -> content bytes."""
    paths = order or list(files)
    return dict(
        schema=sb.STATE_SCHEMA, repository=repository,
        family=dict(name='graphify-stdlib-structural', version='1'), commit=commit, tree='e' * 40,
        input_basis='git_blob', admission_policy_sha256='a' * 64, adapter_sha256='a' * 64,
        executable_sha256='a' * 64, per_file_policy_sha256='a' * 64, runtime_identity_sha256=None,
        manifest_sha256='a' * 64, request_sha256='a' * 64,
        files=[dict(path=p, blob_oid='f' * 40, sha256=sha(files[p]), bytes=len(files[p]),
                    coverage='structural', key_sha256=None) for p in paths],
        unsupported=[], package_sha256='a' * 64, catalog_sha256='a' * 64, archive_sha256='a' * 64,
        graph_sha256='a' * 64, counts={}, cache_status='synthetic',
        target_relation=dict(relation='unknown', oid=None, observed_at=None, method=None))


def baseline(repositories, model_id='model-x'):
    return dict(schema=sb.BASELINE_SCHEMA, model_id=model_id,
                repositories=[dict(repository=r, commit=c, files=[dict(path=p, sha256=sha(b))
                                                                 for p, b in files.items()])
                              for r, c, files in repositories])


def rate(model_id='model-x'):
    return dict(schema=sb.RATE_CARD_SCHEMA, model_id=model_id, currency='USD',
                input_per_million_tokens='3', output_per_million_tokens='15',
                source='synthetic fixture rate card')


def plan_argv(states, output, base=None, card=None, ceiling=1000, overhead=150, out=100, hours=24):
    argv = ['plan']
    for s in states:
        argv += ['--build-state', *s]
    argv += ['--baseline', *base] if base else ['--baseline-none']
    if card:
        argv += ['--rate-card', *card]
    return argv + ['--model-id', 'model-x', '--max-output-tokens-per-file', str(out),
                   '--input-overhead-percent', str(overhead), '--requested-ceiling', str(ceiling),
                   '--valid-hours', str(hours), '--output', str(output)]


def run_plan(argv, now=NOW):
    return sb.plan(sb.parser().parse_args(argv), now=now)


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob('*')) if p.is_file()}


V1 = {'a.py': b'aaaa', 'b.py': b'bbbb', 'c.py': b'cccc'}
# a unchanged, b changed (10 bytes), c deleted, d new (7 bytes).
V2 = {'a.py': b'aaaa', 'b.py': b'bbbbbbbbbb', 'd.py': b'ddddddd'}


class PlanTests(unittest.TestCase):
    def test_state_fields_mirror_incremental_driver(self):
        import graph_refresh_incremental as driver
        self.assertEqual(sb.STATE_SCHEMA, driver.STATE_SCHEMA)
        self.assertEqual(sb.STATE_FIELDS, driver.STATE_FIELDS)

    def test_counts_paths_and_deterministic_estimate(self):
        with workspace() as root:
            current = write(root, 's.json', state('Org/one', C2, V2))
            base = write(root, 'b.json', baseline([('Org/one', C1, V1)]))
            result = run_plan(plan_argv([current], root / 'plan.json', base=base))
            plan = graph_pack.strict_json((root / 'plan.json').read_bytes())
        self.assertEqual(result['status'], 'planned')
        self.assertEqual(result['authorizes'], 'nothing')
        repo = plan['repositories'][0]
        self.assertEqual(repo['counts'], dict(new=1, changed=1, deleted=1, unchanged=1))
        self.assertEqual(repo['paths'], dict(new=['d.py'], changed=['b.py'], deleted=['c.py']))
        self.assertEqual(repo['revision_range'], {'from': C1, 'to': C2, 'tree': 'e' * 40})
        self.assertEqual(repo['catch_up'], 'included')
        self.assertEqual(repo['input_bytes'], 17)
        # b: ceil(10/4)=3 -> ceil(3*1.5)=5; d: ceil(7/4)=2 -> 3; output 2 files * 100.
        self.assertEqual(repo['estimated_input_tokens'], 8)
        self.assertEqual(repo['estimated_output_tokens'], 200)
        self.assertEqual(plan['totals']['estimated_total_tokens'], 208)
        self.assertIsNone(plan['estimated_cost'])
        self.assertIn('not a verified tokenizer count or billing quote', plan['estimate']['label'])
        self.assertEqual(plan['created_at'], '2026-10-21T12:00:00Z')
        self.assertEqual(plan['expires_at'], '2026-10-22T12:00:00Z')
        self.assertFalse(plan['existing_semantic_outputs']['written'])
        self.assertEqual(result['plan']['sha256'], sha(graph_pack.encoded(plan)))

    def test_same_commit_with_no_changes_has_no_catch_up_or_work(self):
        with workspace() as root:
            current = write(root, 's.json', state('Org/one', C1, V1))
            base = write(root, 'b.json', baseline([('Org/one', C1, V1)]))
            run_plan(plan_argv([current], root / 'plan.json', base=base))
            plan = graph_pack.strict_json((root / 'plan.json').read_bytes())
        self.assertEqual(plan['repositories'][0]['catch_up'], 'none')
        self.assertEqual(plan['totals']['estimated_total_tokens'], 0)
        self.assertEqual(plan['totals']['unchanged'], 3)

    def test_no_baseline_plans_initial_batch(self):
        with workspace() as root:
            current = write(root, 's.json', state('Org/one', C2, V2))
            run_plan(plan_argv([current], root / 'plan.json'))
            plan = graph_pack.strict_json((root / 'plan.json').read_bytes())
        repo = plan['repositories'][0]
        self.assertEqual(repo['catch_up'], 'initial')
        self.assertEqual(repo['revision_range']['from'], None)
        self.assertEqual(repo['counts'], dict(new=3, changed=0, deleted=0, unchanged=0))
        self.assertIsNone(plan['inputs']['baseline_sha256'])

    def test_reordered_inputs_give_identical_plan_bytes(self):
        with workspace() as root:
            one = write(root, 'one.json', state('Org/one', C2, V2))
            two = write(root, 'two.json', state('Org/two', C3, V1))
            one_r = write(root, 'one-r.json', state('Org/one', C2, V2, order=['d.py', 'b.py', 'a.py']))
            two_r = write(root, 'two-r.json', state('Org/two', C3, V1, order=['c.py', 'a.py', 'b.py']))
            base = write(root, 'b.json', baseline([('Org/two', C1, V1), ('Org/one', C1, V1)]))
            base_r = write(root, 'b-r.json', baseline([('Org/one', C1, dict(reversed(V1.items()))),
                                                        ('Org/two', C1, V1)]))
            run_plan(plan_argv([one, two], root / 'p1.json', base=base))
            run_plan(plan_argv([two_r, one_r], root / 'p2.json', base=base_r))
            p1 = graph_pack.strict_json((root / 'p1.json').read_bytes())
            p2 = graph_pack.strict_json((root / 'p2.json').read_bytes())
        # Input file hashes differ by construction; everything derived from content is equal.
        for p in (p1, p2):
            p.pop('inputs')
            p['existing_semantic_outputs'].pop('baseline_sha256')
        self.assertEqual(p1, p2)
        self.assertEqual([r['repository'] for r in p1['repositories']], ['Org/one', 'Org/two'])

    def test_same_inputs_in_other_argument_order_give_identical_bytes(self):
        with workspace() as root:
            one = write(root, 'one.json', state('Org/one', C2, V2))
            two = write(root, 'two.json', state('Org/two', C3, V1))
            run_plan(plan_argv([one, two], root / 'p1.json'))
            run_plan(plan_argv([two, one], root / 'p2.json'))
            self.assertEqual((root / 'p1.json').read_bytes(), (root / 'p2.json').read_bytes())

    def test_utf8_paths_round_trip_as_ascii_json(self):
        name = 'docs/naïve-日本.md'
        with workspace() as root:
            current = write(root, 's.json', state('Org/one', C2, {name: 'é'.encode()}))
            run_plan(plan_argv([current], root / 'plan.json'))
            raw = (root / 'plan.json').read_bytes()
        raw.decode('ascii')
        plan = graph_pack.strict_json(raw)
        self.assertEqual(plan['repositories'][0]['paths']['new'], [name])
        self.assertEqual(plan['repositories'][0]['input_bytes'], 2)

    def test_path_lists_are_bounded(self):
        files = {f'f{i:03}.md': b'x' for i in range(sb.MAX_LISTED + 10)}
        with workspace() as root:
            current = write(root, 's.json', state('Org/one', C2, files))
            run_plan(plan_argv([current], root / 'plan.json', ceiling=10**6))
            repo = graph_pack.strict_json((root / 'plan.json').read_bytes())['repositories'][0]
        self.assertEqual(len(repo['paths']['new']), sb.MAX_LISTED)
        self.assertEqual(repo['paths_truncated']['new'], 10)
        self.assertEqual(repo['counts']['new'], sb.MAX_LISTED + 10)

    def test_rate_card_cost_only_when_supplied_and_bound(self):
        with workspace() as root:
            current = write(root, 's.json', state('Org/one', C2, V2))
            card = write(root, 'rate.json', rate())
            run_plan(plan_argv([current], root / 'plan.json', card=card))
            plan = graph_pack.strict_json((root / 'plan.json').read_bytes())
            # 3 new files: in 2+5+3=10 tokens, out 300; (10*3 + 300*15) / 1e6.
            self.assertEqual(plan['estimated_cost']['amount'], '0.004530')
            self.assertEqual(plan['estimated_cost']['rate_card_sha256'], card[1])
            self.assertIn('not a billing quote', plan['estimated_cost']['label'])
            with self.assertRaisesRegex(sb.StoreError, 'checksum mismatch'):
                run_plan(plan_argv([current], root / 'p2.json', card=[card[0], '0' * 64]))
            other = write(root, 'rate2.json', rate('model-y'))
            with self.assertRaisesRegex(sb.StoreError, 'rate card model'):
                run_plan(plan_argv([current], root / 'p3.json', card=other))
            self.assertFalse((root / 'p2.json').exists() or (root / 'p3.json').exists())

    def test_ceiling_refuses_without_output(self):
        with workspace() as root:
            current = write(root, 's.json', state('Org/one', C2, V2))
            base = write(root, 'b.json', baseline([('Org/one', C1, V1)]))
            with self.assertRaises(sb.Refused):
                run_plan(plan_argv([current], root / 'plan.json', base=base, ceiling=207))
            self.assertFalse((root / 'plan.json').exists())
            self.assertEqual(run_plan(plan_argv([current], root / 'plan.json', base=base,
                                                ceiling=208))['status'], 'planned')

    def test_output_is_create_only(self):
        with workspace() as root:
            current = write(root, 's.json', state('Org/one', C2, V2))
            (root / 'existing.json').write_bytes(b'keep')
            with self.assertRaises(FileExistsError):
                run_plan(plan_argv([current], root / 'existing.json'))
            self.assertEqual((root / 'existing.json').read_bytes(), b'keep')
            (root / 'target').write_bytes(b'target')
            (root / 'link.json').symlink_to(root / 'target')
            with self.assertRaises(OSError):
                run_plan(plan_argv([current], root / 'link.json'))
            self.assertEqual((root / 'target').read_bytes(), b'target')
            run_plan(plan_argv([current], root / 'plan.json'))
            self.assertEqual(os.stat(root / 'plan.json').st_mode & 0o777, 0o600)

    def test_failed_write_removes_only_its_own_new_file(self):
        with workspace() as root:
            current = write(root, 's.json', state('Org/one', C2, V2))
            with patch.object(sb.os, 'fsync', side_effect=OSError('synthetic')):
                with self.assertRaises(OSError):
                    run_plan(plan_argv([current], root / 'plan.json'))
            self.assertFalse((root / 'plan.json').exists())

    def test_invalid_inputs_fail_closed(self):
        with workspace() as root:
            current = write(root, 's.json', state('Org/one', C2, V2))
            with self.assertRaisesRegex(sb.StoreError, 'checksum mismatch'):
                run_plan(plan_argv([[current[0], '0' * 64]], root / 'p.json'))
            with self.assertRaisesRegex(sb.StoreError, 'duplicate build state repository'):
                run_plan(plan_argv([current, current], root / 'p.json'))
            other_model = write(root, 'b.json', baseline([('Org/one', C1, V1)], model_id='model-y'))
            with self.assertRaisesRegex(sb.StoreError, 'baseline model differs'):
                run_plan(plan_argv([current], root / 'p.json', base=other_model))
            bad = state('Org/one', C2, V2)
            bad['files'][0]['path'] = '../escape'
            with self.assertRaisesRegex(sb.StoreError, 'unsafe inventory path'):
                run_plan(plan_argv([write(root, 'bad.json', bad)], root / 'p.json'))
            extra = dict(state('Org/one', C2, V2), extra=1)
            with self.assertRaisesRegex(sb.StoreError, 'build state fields'):
                run_plan(plan_argv([write(root, 'extra.json', extra)], root / 'p.json'))
            self.assertFalse((root / 'p.json').exists())


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self._workspace = workspace()
        self.root = self._workspace.__enter__()
        self.addCleanup(self._workspace.__exit__, None, None, None)
        self.current = write(self.root, 's.json', state('Org/one', C2, V2))
        self.base = write(self.root, 'b.json', baseline([('Org/one', C1, V1)]))
        result = run_plan(plan_argv([self.current], self.root / 'plan.json', base=self.base, ceiling=500))
        self.plan = [result['plan']['path'], result['plan']['sha256']]

    def approval(self, name='approval.json', **change):
        record = dict(schema=sb.APPROVAL_SCHEMA, plan_sha256=self.plan[1],
                      build_states=[dict(repository='Org/one', sha256=self.current[1])],
                      approved_by=OWNER, approval_source='synthetic fixture message ref',
                      token_ceiling=300, approved_at='2026-10-21T12:30:00Z',
                      expires_at='2026-10-21T18:00:00Z')
        record.update(change)
        return write(self.root, name, record)

    def verify(self, approval=None, current=None, base='default', plan=None, now=NOW + timedelta(hours=1),
               approver=OWNER):
        argv = ['verify', '--build-state', *(current or self.current)]
        base = self.base if base == 'default' else base
        argv += ['--baseline', *base] if base else ['--baseline-none']
        argv += ['--plan', *(plan or self.plan), '--approval', *(approval or self.approval()),
                 '--approver', approver]
        return sb.verify(sb.parser().parse_args(argv), now=now)

    def assertRefused(self, result, reason):
        self.assertEqual(result['status'], 'refused')
        self.assertTrue(any(reason in r for r in result['reasons']), result['reasons'])

    def test_verified_record_authorizes_nothing_and_writes_nothing(self):
        approval = self.approval()
        before = snapshot(self.root)
        result = self.verify(approval)
        self.assertEqual(result['status'], 'verified', result['reasons'])
        self.assertEqual((result['authorizes'], result['executes']), ('nothing', 'nothing'))
        self.assertEqual(result['estimated_total_tokens'], 208)
        self.assertEqual(result['expires_at'], '2026-10-21T18:00:00Z')
        self.assertEqual(snapshot(self.root), before)

    def test_ceiling_order_estimate_approved_requested(self):
        self.assertEqual(self.verify(self.approval(token_ceiling=208))['status'], 'verified')
        self.assertEqual(self.verify(self.approval(token_ceiling=500))['status'], 'verified')
        self.assertRefused(self.verify(self.approval(token_ceiling=207)), 'exceeds approved ceiling')
        self.assertRefused(self.verify(self.approval(token_ceiling=501)), 'exceeds requested ceiling')

    def test_non_matching_plan_sha_and_approver_refuse(self):
        self.assertRefused(self.verify(self.approval(plan_sha256='0' * 64)), 'plan_sha256 does not match')
        self.assertRefused(self.verify(approver='Someone Else'), 'approved_by does not match')
        self.assertRefused(self.verify(self.approval(build_states=[dict(repository='Org/one',
                                                                         sha256='0' * 64)])),
                           'approval build states do not match')

    def test_stale_plan_refuses(self):
        changed = write(self.root, 's2.json', state('Org/one', C3, dict(V2, **{'e.py': b'e'})))
        result = self.verify(current=changed)
        self.assertRefused(result, 'stale plan')
        newer_base = write(self.root, 'b2.json', baseline([('Org/one', C2, V2)]))
        self.assertRefused(self.verify(base=newer_base), 'stale plan')
        self.assertRefused(self.verify(base=None), 'stale plan')

    def test_expired_or_out_of_window_records_refuse(self):
        self.assertRefused(self.verify(now=NOW + timedelta(hours=7)), 'approval expired')
        late = self.approval(expires_at='2026-10-22T12:00:00Z')
        self.assertRefused(self.verify(late, now=NOW + timedelta(hours=25)), 'plan expired')
        self.assertRefused(self.verify(self.approval(expires_at='2026-10-23T00:00:00Z')),
                           'approval expires after the plan')
        self.assertRefused(self.verify(self.approval(approved_at='2026-10-21T11:00:00Z')),
                           'outside plan creation')
        self.assertRefused(self.verify(self.approval(approved_at='2026-10-21T13:30:00Z')),
                           'outside plan creation')

    def test_tampered_plan_is_refused_even_when_rehashed(self):
        plan = graph_pack.strict_json(Path(self.plan[0]).read_bytes())
        plan['totals']['estimated_total_tokens'] = 1
        forged = write(self.root, 'forged.json', plan)
        result = self.verify(self.approval(plan_sha256=forged[1], token_ceiling=100), plan=forged)
        self.assertRefused(result, 'stale plan')
        with self.assertRaisesRegex(sb.StoreError, 'checksum mismatch'):
            self.verify(plan=[self.plan[0], '0' * 64])

    def test_malformed_approval_fails(self):
        approval = self.approval(approved_by='')
        with self.assertRaisesRegex(sb.StoreError, 'approved_by'):
            self.verify(approval)
        with self.assertRaisesRegex(sb.StoreError, 'checksum mismatch'):
            self.verify([self.approval()[0], '0' * 64])
        with self.assertRaisesRegex(sb.StoreError, 'approval record fields'):
            self.verify(self.approval(extra='x'))


class CliTests(unittest.TestCase):
    def run_main(self, argv):
        out = SimpleNamespace(buffer=io.BytesIO())
        with patch.object(sys, 'stdout', out):
            code = sb.main(argv)
        return code, graph_pack.strict_json(out.buffer.getvalue())

    def test_exit_codes_and_status(self):
        with workspace() as root:
            current = write(root, 's.json', state('Org/one', C2, V2))
            code, result = self.run_main(plan_argv([current], root / 'plan.json'))
            self.assertEqual((code, result['status']), (0, 'planned'))
            code, result = self.run_main(plan_argv([current], root / 'p2.json', ceiling=1))
            self.assertEqual((code, result['status']), (1, 'refused'))
            code, result = self.run_main(plan_argv([current], root / 'plan.json'))
            self.assertEqual((code, result['status']), (1, 'failed'))
            self.assertFalse((root / 'p2.json').exists())


class StaticGuardTests(unittest.TestCase):
    ALLOWED = {'argparse', 'datetime', 'decimal', 'os', 'pathlib', 'sys', 're',
               'graph_pack', 'graph_read'}
    FORBIDDEN = ('socket', 'ssl', 'http', 'urllib', 'requests', 'httpx', 'aiohttp', 'subprocess',
                 'anthropic', 'openai', 'asyncio', 'ftplib', 'smtplib', 'xmlrpc')

    def imports(self, name):
        tree = ast.parse((TOOLING / name).read_text(encoding='utf-8'))
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(a.name.split('.')[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                found.add(node.module.split('.')[0])
            elif isinstance(node, ast.Call) and getattr(node.func, 'id', None) == '__import__':
                found.add('__import__')
        return found

    def test_module_imports_only_local_stdlib_helpers(self):
        self.assertLessEqual(self.imports('semantic_batch.py'), self.ALLOWED)
        for helper in ('graph_pack.py', 'graph_read.py'):
            self.assertFalse(self.imports(helper) & set(self.FORBIDDEN), helper)

    def test_source_has_no_credential_or_environment_reads(self):
        source = (TOOLING / 'semantic_batch.py').read_text(encoding='utf-8')
        for word in ('environ', 'getenv', 'importlib', 'exec(', 'eval(', 'token_env', 'api_key'):
            self.assertNotIn(word, source)

    def test_fresh_import_loads_no_network_or_process_modules(self):
        code = ('import sys; sys.path.insert(0, sys.argv[1]); import semantic_batch; '
                'print(",".join(sorted(m for m in sys.modules if m.split(".")[0] in sys.argv[2:])))')
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(TOOLING), *self.FORBIDDEN],
                                capture_output=True, text=True, timeout=60, env={}, cwd='/')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), '')


IDENTITY = dict(dict.fromkeys(sb.IDENTITY_FIELDS, 'a' * 64), runtime_identity_sha256=None)
# V2 split three ways; the same files as the unsliced state('Org/one', C2, V2).
THREE = {'a': {'a.py': V2['a.py']}, 'b': {'b.py': V2['b.py']}, 'rest': {'d.py': V2['d.py']}}


def slice_docs(groups, repository='Org/one', head=C2, tree='e' * 40, built=None, candidates=None,
               old_index=None):
    """A graphify-slice-set/v1 and its v2 slice states, digests computed by the driver itself.

    built maps slice -> earlier head (reused); old_index is the index that slice resolved against.
    """
    built, candidates = built or {}, candidates or {}
    index, raw = inc.path_index({n: [dict(path=p) for p in fs] for n, fs in groups.items()})
    states = {}
    for name, files in groups.items():
        doc = dict(state(repository, built.get(name, head), files), schema=sb.SLICE_STATE_SCHEMA,
                   family=dict(sb.FAMILY_V2), **IDENTITY)
        doc['tree'] = tree if name not in built else 'd' * 40
        found = sorted(set(candidates.get(name, [])))
        doc.update(slice=name, reference_candidates=found,
                   path_index_sha256=sha(raw) if name not in built else '9' * 64,
                   input_digest=inc.input_digest(repository, name, doc['files'], doc['unsupported'],
                                                 {k: doc[k] for k in inc.IDENTITY_FIELDS}),
                   resolution_digest=inc.resolution_digest(
                       found, old_index if name in built and old_index is not None else index))
        states[name] = doc
    record = dict(schema=sb.SLICE_SET_SCHEMA, repository=repository, accepted_head=head, tree=tree,
                  slices=[dict(name=n, package_sha256=s['package_sha256'], built_head=s['commit'],
                               input_digest=s['input_digest'], resolution_digest=s['resolution_digest'],
                               build_state_sha256=None) for n, s in sorted(states.items())])
    return record, states


def write_sliced(root, record, states, tag='s', fix=True):
    """Write states then the slice set; fix=True binds each entry to its written state hash."""
    selections = {}
    for name, doc in states.items():
        selections[name] = write(root, f'{tag}-{name}.json', doc)
    for entry in record['slices']:
        if fix and entry['name'] in selections:
            entry['build_state_sha256'] = selections[entry['name']][1]
    return write(root, f'{tag}-set.json', record), selections


def sliced_argv(argv, slice_sets=(), slice_states=()):
    head, tail = argv[:1], argv[1:]
    for s in slice_sets:
        head += ['--slice-set', *s]
    for s in slice_states:
        head += ['--slice-state', *s]
    return head + tail


def sliced_plan(root, record, states, output, base=None, tag='s', omit=(), extra=(), **options):
    chosen, selections = write_sliced(root, record, states, tag)
    picked = [sel for n, sel in sorted(selections.items()) if n not in omit] + list(extra)
    argv = sliced_argv(plan_argv([], output, base=base, **options), [chosen], picked)
    return run_plan(argv), chosen, selections


class SlicedMirrorTests(unittest.TestCase):
    def test_sliced_schema_and_digests_mirror_incremental_driver(self):
        for name in ('SLICE_STATE_SCHEMA', 'SLICE_SET_SCHEMA', 'SLICE_INPUT_SCHEMA', 'PATH_INDEX_SCHEMA',
                     'FAMILY_V2', 'SLICE_STATE_FIELDS', 'SLICE_ENTRY_FIELDS', 'IDENTITY_FIELDS',
                     'MAX_SLICES', 'MAX_SLICE_FILES', 'MAX_CANDIDATES'):
            self.assertEqual(getattr(sb, name), getattr(inc, name), name)
        self.assertEqual(sb.SLICE_NAME, inc.SLICE_NAME.pattern)
        self.assertEqual(sb.STATE_FIELDS, sb.SLICE_STATE_FIELDS[:len(sb.STATE_FIELDS)])
        record, states = slice_docs(THREE, candidates=dict(a=['b.py', 'zz.py']))
        index, raw = inc.path_index({n: [dict(path=p) for p in fs] for n, fs in THREE.items()})
        for doc in states.values():
            self.assertEqual(sb.slice_input_digest(doc), doc['input_digest'])
            self.assertEqual(sb.slice_resolution_digest(doc['reference_candidates'], index),
                             doc['resolution_digest'])
        self.assertEqual(sb.digest(sb.encoded(dict(schema=sb.PATH_INDEX_SCHEMA, paths=index))), sha(raw))
        self.assertEqual(sb.canonical_sha256(record), inc.canonical_sha256(record))


class SlicedPlanTests(unittest.TestCase):
    def plan_both(self, root, record, states, **options):
        base = write(root, 'b.json', baseline([('Org/one', C1, V1)]))
        unsliced = write(root, 'u.json', state('Org/one', C2, V2))
        run_plan(plan_argv([unsliced], root / 'u-plan.json', base=base, **options))
        result, chosen, selections = sliced_plan(root, record, states, root / 's-plan.json', base=base,
                                                 **options)
        return (graph_pack.strict_json((root / 'u-plan.json').read_bytes()),
                graph_pack.strict_json((root / 's-plan.json').read_bytes()), result, chosen, selections)

    def test_three_slices_plan_identically_to_equivalent_unsliced_state(self):
        with workspace() as root:
            record, states = slice_docs(THREE, candidates=dict(a=['b.py']))
            unsliced, sliced, result, chosen, selections = self.plan_both(root, record, states,
                                                                          card=None)
        self.assertEqual(result['status'], 'planned')
        self.assertEqual((unsliced['schema'], sliced['schema']), (sb.PLAN_SCHEMA, sb.PLAN_SCHEMA_V2))
        self.assertEqual(sliced['repositories'], unsliced['repositories'])
        self.assertEqual(sliced['totals'], unsliced['totals'])
        repo = sliced['repositories'][0]
        self.assertEqual(repo['counts'], dict(new=1, changed=1, deleted=1, unchanged=1))
        self.assertEqual(repo['paths'], dict(new=['d.py'], changed=['b.py'], deleted=['c.py']))
        self.assertEqual(repo['revision_range'], {'from': C1, 'to': C2, 'tree': 'e' * 40})
        self.assertEqual(sliced['totals']['estimated_total_tokens'], 208)
        self.assertEqual(sliced['inputs']['build_states'], [dict(
            repository='Org/one', kind='slice_set', sha256=chosen[1],
            slices=[dict(name=n, sha256=selections[n][1]) for n in ('a', 'b', 'rest')])])
        for key in ('estimate', 'estimated_cost', 'requested_ceiling_tokens', 'limitations', 'authorizes'):
            self.assertEqual(sliced[key], unsliced[key], key)

    def test_reused_slice_with_reproduced_equivalence_uses_accepted_head(self):
        with workspace() as root:
            record, states = slice_docs(THREE, built=dict(b=C1), candidates=dict(b=['a.py']))
            unsliced, sliced, result, _, _ = self.plan_both(root, record, states)
        self.assertEqual(result['status'], 'planned')
        self.assertEqual(states['b']['commit'], C1)
        self.assertEqual(sliced['repositories'], unsliced['repositories'])

    def test_unproved_slice_head_refuses(self):
        old_index = {'a.py': 'rest', 'b.py': 'b', 'd.py': 'rest'}
        with workspace() as root:
            # b was built at C1 when a.py belonged to rest; its resolution differs at C2.
            record, states = slice_docs(THREE, built=dict(b=C1), candidates=dict(b=['a.py']),
                                        old_index=old_index)
            with self.assertRaisesRegex(sb.StoreError, 'unproved slice head b'):
                sliced_plan(root, record, states, root / 'p.json')
            # The same mismatch at the accepted head is a non-reproducing digest, never a pass.
            record, states = slice_docs(THREE, candidates=dict(b=['a.py']))
            states['b']['resolution_digest'] = inc.resolution_digest(['a.py'], old_index)
            record['slices'][1]['resolution_digest'] = states['b']['resolution_digest']
            with self.assertRaisesRegex(sb.StoreError, 'resolution digest does not reproduce: b'):
                sliced_plan(root, record, states, root / 'p.json', tag='h')
            # An earlier built head with an input change is never proved by its record.
            record, states = slice_docs(THREE, built=dict(b=C1))
            states['b']['files'][0]['blob_oid'] = '0' * 40
            with self.assertRaisesRegex(sb.StoreError, 'input digest does not reproduce: b'):
                sliced_plan(root, record, states, root / 'p.json', tag='i')
            self.assertFalse((root / 'p.json').exists())

    def test_missing_extra_duplicate_and_standalone_slices_refuse(self):
        with workspace() as root:
            for omitted in ('a', 'b', 'rest'):
                record, states = slice_docs(THREE)
                with self.assertRaisesRegex(sb.StoreError, 'missing slice ' + omitted):
                    sliced_plan(root, record, states, root / 'p.json', tag='m' + omitted, omit={omitted})
            record, states = slice_docs(THREE)
            stray = write(root, 'stray.json', slice_docs({'c': {'c.py': b'c'}})[1]['c'])
            with self.assertRaisesRegex(sb.StoreError, 'extra slice build state .*Org/one c'):
                sliced_plan(root, record, states, root / 'p.json', tag='x', extra=[stray])
            record, states = slice_docs(THREE)
            again = write(root, 'x-a.json', states['a'])
            with self.assertRaisesRegex(sb.StoreError, 'duplicate slice build state a'):
                sliced_plan(root, record, states, root / 'p.json', tag='x', extra=[again])
            record, states = slice_docs(THREE)
            record['slices'].insert(1, dict(record['slices'][0]))
            with self.assertRaisesRegex(sb.StoreError, 'duplicate slice in slice set'):
                sliced_plan(root, record, states, root / 'p.json', tag='d')
            record, states = slice_docs(THREE)
            record['slices'].reverse()
            with self.assertRaisesRegex(sb.StoreError, 'slice set slices unsorted'):
                sliced_plan(root, record, states, root / 'p.json', tag='o')
            # A slice state alone is never a whole repository, by either option.
            alone = write(root, 'alone.json', slice_docs(THREE)[1]['a'])
            with self.assertRaisesRegex(sb.StoreError, 'build state fields'):
                run_plan(plan_argv([alone], root / 'p.json'))
            with self.assertRaisesRegex(sb.StoreError, 'not named by any slice set'):
                run_plan(sliced_argv(plan_argv([], root / 'p.json'), [], [alone]))
            with self.assertRaisesRegex(sb.StoreError, 'one or more build states are required'):
                run_plan(plan_argv([], root / 'p.json'))
            self.assertFalse((root / 'p.json').exists())

    def test_overlapping_paths_and_wrong_repository_refuse(self):
        with workspace() as root:
            record, states = slice_docs(dict(THREE, b={'b.py': V2['b.py'], 'a.py': V2['a.py']}))
            with self.assertRaisesRegex(sb.StoreError, 'overlapping slice path a.py'):
                sliced_plan(root, record, states, root / 'p.json', tag='v')
            record, states = slice_docs(THREE)
            states['b'] = slice_docs(THREE, repository='Org/two')[1]['b']
            with self.assertRaisesRegex(sb.StoreError, 'slice state repository differs from slice set: b'):
                sliced_plan(root, record, states, root / 'p.json', tag='r')
            record, states = slice_docs(THREE)
            states['b']['slice'] = 'other'
            with self.assertRaisesRegex(sb.StoreError, 'slice state name differs from slice set: b'):
                sliced_plan(root, record, states, root / 'p.json', tag='n')
            record, states = slice_docs(THREE)
            same = write(root, 'same.json', state('Org/one', C2, V2))
            chosen, selections = write_sliced(root, record, states, 'u')
            with self.assertRaisesRegex(sb.StoreError, 'duplicate build state repository'):
                run_plan(sliced_argv(plan_argv([same], root / 'p.json'), [chosen], selections.values()))
            self.assertFalse((root / 'p.json').exists())

    def test_hash_tampering_and_contradictions_refuse(self):
        with workspace() as root:
            record, states = slice_docs(THREE)
            chosen, selections = write_sliced(root, record, states, 't')
            argv = lambda sets, picked: sliced_argv(plan_argv([], root / 'p.json'), sets, picked)
            with self.assertRaisesRegex(sb.StoreError, 'slice set: input checksum mismatch'):
                run_plan(argv([[chosen[0], '0' * 64]], selections.values()))
            bad = dict(selections, b=[selections['b'][0], '0' * 64])
            with self.assertRaisesRegex(sb.StoreError, 'slice build state: input checksum mismatch'):
                run_plan(argv([chosen], bad.values()))
            # A rehashed edited state no longer matches the hash its slice set names.
            states['b']['files'][0]['bytes'] = 1
            edited = write(root, 'edited.json', states['b'])
            with self.assertRaisesRegex(sb.StoreError, 'missing slice b'):
                run_plan(argv([chosen], dict(selections, b=edited).values()))
            for key, value in (('package_sha256', '0' * 64), ('built_head', C3),
                               ('input_digest', '0' * 64), ('resolution_digest', '0' * 64)):
                record, states = slice_docs(THREE)
                record['slices'][0][key] = value
                with self.assertRaisesRegex(sb.StoreError, 'slice state contradicts slice set: a'):
                    sliced_plan(root, record, states, root / 'p.json', tag='c' + key)
            record, states = slice_docs(THREE)
            states['a']['path_index_sha256'] = '0' * 64
            with self.assertRaisesRegex(sb.StoreError, 'slice path index differs from slice set union: a'):
                sliced_plan(root, record, states, root / 'p.json', tag='pi')
            record, states = slice_docs(THREE)
            states['a']['tree'] = 'd' * 40
            with self.assertRaisesRegex(sb.StoreError, 'slice tree differs from slice set: a'):
                sliced_plan(root, record, states, root / 'p.json', tag='tr')
            record, states = slice_docs(THREE)
            states['a']['adapter_sha256'] = 'b' * 64
            states['a']['input_digest'] = record['slices'][0]['input_digest'] = sb.slice_input_digest(states['a'])
            with self.assertRaisesRegex(sb.StoreError, 'slice identities differ'):
                sliced_plan(root, record, states, root / 'p.json', tag='id')
            record, states = slice_docs(THREE)
            states['a']['family'] = dict(name='graphify-stdlib-structural', version='1')
            with self.assertRaisesRegex(sb.StoreError, 'unsupported slice build state'):
                sliced_plan(root, record, states, root / 'p.json', tag='f')
            record, states = slice_docs(THREE)
            record['extra'] = 1
            with self.assertRaisesRegex(sb.StoreError, 'slice set fields'):
                sliced_plan(root, record, states, root / 'p.json', tag='e')
            self.assertFalse((root / 'p.json').exists())

    def test_slice_set_and_v1_state_repositories_plan_together_as_v2(self):
        with workspace() as root:
            record, states = slice_docs(THREE)
            two = write(root, 'two.json', state('Org/two', C3, V1))
            chosen, selections = write_sliced(root, record, states)
            run_plan(sliced_argv(plan_argv([two], root / 'p.json'), [chosen], selections.values()))
            plan = graph_pack.strict_json((root / 'p.json').read_bytes())
        self.assertEqual(plan['schema'], sb.PLAN_SCHEMA_V2)
        self.assertEqual([(s['repository'], s['kind']) for s in plan['inputs']['build_states']],
                         [('Org/one', 'slice_set'), ('Org/two', 'state')])
        self.assertEqual(plan['inputs']['build_states'][1], dict(repository='Org/two', kind='state',
                                                                 sha256=two[1]))
        self.assertEqual(plan['totals']['new'], 6)


class SlicedVerifyTests(unittest.TestCase):
    def setUp(self):
        self._workspace = workspace()
        self.root = self._workspace.__enter__()
        self.addCleanup(self._workspace.__exit__, None, None, None)
        record, states = slice_docs(THREE)
        self.chosen, self.selections = write_sliced(self.root, record, states)
        self.base = write(self.root, 'b.json', baseline([('Org/one', C1, V1)]))
        result = run_plan(sliced_argv(plan_argv([], self.root / 'plan.json', base=self.base, ceiling=500),
                                      [self.chosen], self.selections.values()))
        self.plan = [result['plan']['path'], result['plan']['sha256']]
        self.inputs = graph_pack.strict_json(Path(self.plan[0]).read_bytes())['inputs']['build_states']

    def approval(self, name='approval.json', **change):
        record = dict(schema=sb.APPROVAL_SCHEMA_V2, plan_sha256=self.plan[1], build_states=self.inputs,
                      approved_by=OWNER, approval_source='synthetic fixture message ref',
                      token_ceiling=300, approved_at='2026-10-21T12:30:00Z',
                      expires_at='2026-10-21T18:00:00Z')
        record.update(change)
        return write(self.root, name, record)

    def verify(self, approval=None, sets=None, picked=None, plan=None, now=NOW + timedelta(hours=1)):
        argv = ['verify', '--baseline', *self.base, '--plan', *(plan or self.plan),
                '--approval', *(approval or self.approval()), '--approver', OWNER]
        argv = sliced_argv(argv, [self.chosen] if sets is None else sets,
                           self.selections.values() if picked is None else picked)
        return sb.verify(sb.parser().parse_args(argv), now=now)

    def assertRefused(self, result, reason):
        self.assertEqual(result['status'], 'refused')
        self.assertTrue(any(reason in r for r in result['reasons']), result['reasons'])

    def test_verified_v2_record_authorizes_nothing_and_writes_nothing(self):
        approval = self.approval()
        before = snapshot(self.root)
        result = self.verify(approval)
        self.assertEqual(result['status'], 'verified', result['reasons'])
        self.assertEqual((result['authorizes'], result['executes']), ('nothing', 'nothing'))
        self.assertEqual(result['estimated_total_tokens'], 208)
        self.assertEqual(snapshot(self.root), before)

    def test_v2_ceiling_order_estimate_approved_requested(self):
        self.assertEqual(self.verify(self.approval(token_ceiling=208))['status'], 'verified')
        self.assertEqual(self.verify(self.approval(token_ceiling=500))['status'], 'verified')
        self.assertRefused(self.verify(self.approval(token_ceiling=207)), 'exceeds approved ceiling')
        self.assertRefused(self.verify(self.approval(token_ceiling=501)), 'exceeds requested ceiling')

    def test_approval_slice_binding_must_match_the_plan(self):
        tampered = [dict(self.inputs[0], slices=[dict(s) for s in self.inputs[0]['slices']])]
        tampered[0]['slices'][1]['sha256'] = '0' * 64
        self.assertRefused(self.verify(self.approval(build_states=tampered)),
                           'approval build states do not match')
        fewer = [dict(self.inputs[0], slices=self.inputs[0]['slices'][:2])]
        self.assertRefused(self.verify(self.approval(build_states=fewer)),
                           'approval build states do not match')
        moved = [dict(self.inputs[0], sha256='0' * 64)]
        self.assertRefused(self.verify(self.approval(build_states=moved)),
                           'approval build states do not match')
        as_state = [dict(repository='Org/one', kind='state', sha256=self.inputs[0]['sha256'])]
        self.assertRefused(self.verify(self.approval(build_states=as_state)),
                           'approval build states do not match')
        with self.assertRaisesRegex(sb.StoreError, 'approval build state fields'):
            self.verify(self.approval(build_states=[dict(repository='Org/one', kind='slice_set',
                                                         sha256=self.inputs[0]['sha256'])]))
        with self.assertRaisesRegex(sb.StoreError, 'unsupported approval record'):
            self.verify(self.approval(schema=sb.APPROVAL_SCHEMA))

    def test_omitted_tampered_or_changed_slices_refuse_verify(self):
        names = sorted(self.selections)
        for omitted in names:
            picked = [self.selections[n] for n in names if n != omitted]
            with self.assertRaisesRegex(sb.StoreError, 'missing slice ' + omitted):
                self.verify(picked=picked)
        with self.assertRaisesRegex(sb.StoreError, 'input checksum mismatch'):
            self.verify(sets=[[self.chosen[0], '0' * 64]])
        with self.assertRaisesRegex(sb.StoreError, 'input checksum mismatch'):
            self.verify(picked=[self.selections['a'], self.selections['b'],
                                [self.selections['rest'][0], '0' * 64]])
        with self.assertRaisesRegex(sb.StoreError, 'build state fields'):
            argv = ['verify', '--build-state', *self.selections['a'], '--baseline', *self.base,
                    '--plan', *self.plan, '--approval', *self.approval(), '--approver', OWNER]
            sb.verify(sb.parser().parse_args(argv), now=NOW + timedelta(hours=1))
        # A later consistent slice set with other bytes no longer reproduces the plan.
        record, states = slice_docs(dict(THREE, rest={'d.py': V2['d.py'], 'e.py': b'e'}), head=C3)
        later, picked = write_sliced(self.root, record, states, 'later')
        self.assertRefused(self.verify(sets=[later], picked=picked.values()), 'stale plan')
        # The unsliced equivalent reproduces the counts but not the v2 inputs: still stale.
        unsliced = write(self.root, 'u.json', state('Org/one', C2, V2))
        argv = ['verify', '--build-state', *unsliced, '--baseline', *self.base, '--plan', *self.plan,
                '--approval', *self.approval(), '--approver', OWNER]
        self.assertRefused(sb.verify(sb.parser().parse_args(argv), now=NOW + timedelta(hours=1)),
                           'stale plan')

    def test_tampered_v2_plan_is_refused_even_when_rehashed(self):
        plan = graph_pack.strict_json(Path(self.plan[0]).read_bytes())
        plan['inputs']['build_states'][0]['slices'] = plan['inputs']['build_states'][0]['slices'][:2]
        forged = write(self.root, 'forged.json', plan)
        approval = self.approval(plan_sha256=forged[1], build_states=plan['inputs']['build_states'])
        self.assertRefused(self.verify(approval, plan=forged), 'stale plan')

    def test_v1_plan_with_v2_approval_and_v1_inputs_stay_on_v1_rules(self):
        current = write(self.root, 'v1.json', state('Org/one', C2, V2))
        v1 = run_plan(plan_argv([current], self.root / 'v1-plan.json', base=self.base, ceiling=500))
        v1_plan = [v1['plan']['path'], v1['plan']['sha256']]
        self.assertEqual(graph_pack.strict_json(Path(v1_plan[0]).read_bytes())['schema'], sb.PLAN_SCHEMA)
        base_argv = ['verify', '--build-state', *current, '--baseline', *self.base, '--plan', *v1_plan,
                     '--approver', OWNER]
        good = write(self.root, 'v1-approval.json', dict(
            schema=sb.APPROVAL_SCHEMA, plan_sha256=v1_plan[1],
            build_states=[dict(repository='Org/one', sha256=current[1])], approved_by=OWNER,
            approval_source='synthetic fixture message ref', token_ceiling=300,
            approved_at='2026-10-21T12:30:00Z', expires_at='2026-10-21T18:00:00Z'))
        result = sb.verify(sb.parser().parse_args(base_argv + ['--approval', *good]),
                           now=NOW + timedelta(hours=1))
        self.assertEqual(result['status'], 'verified', result['reasons'])
        wrong = write(self.root, 'v1-wrong.json', dict(
            graph_pack.strict_json(Path(good[0]).read_bytes()), schema=sb.APPROVAL_SCHEMA_V2,
            build_states=[dict(repository='Org/one', kind='state', sha256=current[1])]))
        with self.assertRaisesRegex(sb.StoreError, 'unsupported approval record'):
            sb.verify(sb.parser().parse_args(base_argv + ['--approval', *wrong]),
                      now=NOW + timedelta(hours=1))
        # v1 plans verified with slice-set inputs are stale, never upgraded.
        argv = sliced_argv(['verify', '--baseline', *self.base, '--plan', *v1_plan, '--approval', *good,
                            '--approver', OWNER], [self.chosen], self.selections.values())
        self.assertRefused(sb.verify(sb.parser().parse_args(argv), now=NOW + timedelta(hours=1)),
                           'stale plan')

    def test_cli_exit_codes_for_sliced_refusals(self):
        out = SimpleNamespace(buffer=io.BytesIO())
        argv = sliced_argv(plan_argv([], self.root / 'cli.json'), [self.chosen],
                           [self.selections['a'], self.selections['b']])
        with patch.object(sys, 'stdout', out):
            code = sb.main(argv)
        result = graph_pack.strict_json(out.buffer.getvalue())
        self.assertEqual((code, result['status']), (1, 'failed'))
        self.assertIn('missing slice rest', result['reasons'][0])
        self.assertFalse((self.root / 'cli.json').exists())


class ProducerSliceSetTests(unittest.TestCase):
    """Actual driver output over a synthetic mirror, with built and reused slice heads."""

    def test_driver_slice_set_with_reused_slices_plans_and_omission_refuses(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import test_incremental_slices as fixtures
        with fixtures.fixture() as fx, workspace() as root:
            first = fx.build(fx.commit(fixtures.FILES))
            self.assertEqual(first['status'], 'completed', first)
            change = {'d/one.py': b'def one():\n    return 1\n'}
            head = fx.commit(change)
            second = fx.build(head, previous=first['slice_run'])
            self.assertEqual(second['status'], 'completed', second)
            chosen = [second['slice_set']['path'], second['slice_set']['sha256']]
            run = fixtures.load(second['slice_run'])
            picked = {s['name']: [s['build_state']['path'], s['build_state']['sha256']]
                      for s in run['slices']}
            self.assertEqual({s['status'] for s in run['slices']}, {'built', 'reused'})
            self.assertTrue(any(s['built_head'] != head for s in run['slices']))
            result = run_plan(sliced_argv(plan_argv([], root / 'p.json', ceiling=10**6), [chosen],
                                          picked.values()))
            plan = graph_pack.strict_json((root / 'p.json').read_bytes())
            self.assertEqual(result['status'], 'planned')
            repo = plan['repositories'][0]
            self.assertEqual(repo['revision_range']['to'], head)
            self.assertEqual(repo['revision_range']['tree'], second['tree'])
            self.assertEqual(repo['counts']['new'], len(fixtures.FILES))
            self.assertEqual(repo['input_bytes'], sum(len(b) for b in dict(fixtures.FILES, **change).values()))
            self.assertEqual([s['name'] for s in plan['inputs']['build_states'][0]['slices']],
                             sorted(picked))
            for name in sorted(picked):
                rest = [v for n, v in picked.items() if n != name]
                with self.assertRaisesRegex(sb.StoreError, 'missing slice ' + name.replace('.', r'\.')):
                    run_plan(sliced_argv(plan_argv([], root / 'q.json', ceiling=10**6), [chosen], rest))
            self.assertFalse((root / 'q.json').exists())


if __name__ == '__main__':
    unittest.main()
