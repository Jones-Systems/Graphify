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


if __name__ == '__main__':
    unittest.main()
