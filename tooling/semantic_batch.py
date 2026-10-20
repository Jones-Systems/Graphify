#!/usr/bin/env python3
"""Plan one semantic batch and verify an owner approval record against it.

`plan` reads only explicitly named, SHA256-bound inputs: structural build-state
files (graphify-build-state/v1, at most one per repository), a semantic baseline
(graphify-semantic-baseline/v1) or --baseline-none, and an optional rate card
(graphify-semantic-rate-card/v1). It compares each build state's admitted files
with the baseline by content SHA256 and writes one create-only plan
(graphify-semantic-batch-plan/v1) to an explicit path. The plan reports per
repository the revision range, new/changed/deleted/unchanged counts with bounded
path lists, input bytes, and estimated tokens. Each new or changed file is
estimated as ceil(ceil(bytes / 4) * overhead_percent / 100) input tokens plus a
fixed max output per file. These are heuristic estimates, not tokenizer counts
or billing quotes. Cost appears only when a hashed rate card is supplied. A plan
whose estimate exceeds the requested ceiling is refused and nothing is written.

`verify` reads a plan, an approval record (graphify-semantic-approval/v1) and the
current inputs, all SHA256-bound, and writes nothing. It recomputes the plan
from the current inputs and refuses on any binding, freshness, expiry or ceiling
mismatch. The required order is estimate <= approved ceiling <= requested
ceiling. A verified result authorizes and executes nothing.

There is no executor, and no model, provider, network or credential access.
Existing semantic outputs are neither read beyond the named baseline nor
written. Approval records come from the owner's coordinator; this tool never
creates one.
"""
import argparse
from datetime import datetime, timedelta, timezone
from decimal import ROUND_CEILING, Decimal, InvalidOperation
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
# `python3 -I` omits the script directory; sibling helpers come from this release only.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from graph_pack import bounded_text, closed, encoded, file_path, selected_input
from graph_read import StoreError, digest, require, valid_hash

PLAN_SCHEMA = 'graphify-semantic-batch-plan/v1'
BASELINE_SCHEMA = 'graphify-semantic-baseline/v1'
RATE_CARD_SCHEMA = 'graphify-semantic-rate-card/v1'
APPROVAL_SCHEMA = 'graphify-semantic-approval/v1'
VERIFICATION_SCHEMA = 'graphify-semantic-approval-verification/v1'
# Mirrors graph_refresh_incremental.STATE_SCHEMA/STATE_FIELDS (equality is tested);
# not imported so this module stays free of the driver's Git subprocess code.
STATE_SCHEMA = 'graphify-build-state/v1'
STATE_FIELDS = ('schema', 'repository', 'family', 'commit', 'tree', 'input_basis',
                'admission_policy_sha256', 'adapter_sha256', 'executable_sha256',
                'per_file_policy_sha256', 'runtime_identity_sha256', 'manifest_sha256',
                'request_sha256', 'files', 'unsupported', 'package_sha256', 'catalog_sha256',
                'archive_sha256', 'graph_sha256', 'counts', 'cache_status', 'target_relation')
STATE_FILE_FIELDS = ('path', 'blob_oid', 'sha256', 'bytes', 'coverage', 'key_sha256')
PLAN_FIELDS = ('schema', 'created_at', 'expires_at', 'model_id', 'inputs', 'estimate',
               'requested_ceiling_tokens', 'repositories', 'totals', 'estimated_cost',
               'existing_semantic_outputs', 'authorizes', 'limitations')
APPROVAL_FIELDS = ('schema', 'plan_sha256', 'build_states', 'approved_by', 'approval_source',
                   'token_ceiling', 'approved_at', 'expires_at')
CATEGORIES = ('new', 'changed', 'deleted', 'unchanged')
LISTED = ('new', 'changed', 'deleted')
BYTES_PER_TOKEN = 4
MAX_INPUT = 16 * 1024**2
MAX_REPOSITORIES = 64
MAX_FILES = 100000
MAX_LISTED = 50
MAX_TOKENS = 10**12
MAX_VALID_HOURS = 168
TIME = '%Y-%m-%dT%H:%M:%SZ'
ESTIMATE_LABEL = ('Heuristic estimate: ceil(bytes/4) x overhead per file plus a fixed output '
                  'per file; not a verified tokenizer count or billing quote.')
COST_LABEL = ('Rate card applied to the heuristic token estimate; not a billing quote. '
              'Rate card accuracy is not verified.')
LIMITATIONS = [
    ESTIMATE_LABEL,
    'Planning authorizes nothing; execution requires a separate owner approval for this exact plan SHA256.',
    'No executor exists; no model, provider, network or credential was used.',
    'Existing semantic outputs are retained unchanged and are not inspected beyond the named baseline.',
]


class Refused(StoreError):
    """A well-formed request that must not proceed (stale, expired, over ceiling)."""


def utc(value, label):
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', value),
            'invalid ' + label)
    try:
        return datetime.strptime(value, TIME).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise StoreError('invalid ' + label) from exc


def stamp(moment):
    return moment.astimezone(timezone.utc).strftime(TIME)


def tokens(value, label, minimum=0):
    require(type(value) is int and minimum <= value <= MAX_TOKENS, 'invalid ' + label)
    return value


def model(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/@-]{0,199}', value),
            'invalid model id')
    return value


def commit_id(value, label):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', value),
            'invalid ' + label)
    return value


def repository(value):
    bounded_text(value, 'repository')
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', value)
            is not None, 'invalid repository')
    return value


def decimal(value, label):
    require(isinstance(value, str) and re.fullmatch(r'\d{1,9}(\.\d{1,9})?', value), 'invalid ' + label)
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise StoreError('invalid ' + label) from exc


# Inputs ----------------------------------------------------------------------

def load(selection, label):
    """Read one explicitly selected file bound by SHA256; return its JSON object."""
    path, sha = selection
    require(valid_hash(sha), 'invalid ' + label + ' sha256')
    try:
        _, value = selected_input(path, sha, MAX_INPUT)
    except OSError as exc:
        raise StoreError(label + ' unreadable: ' + type(exc).__name__) from exc
    except StoreError as exc:
        raise StoreError(label + ': ' + str(exc)) from exc
    return value


def build_state(selection):
    state = load(selection, 'build state')
    closed(state, STATE_FIELDS, 'build state')
    require(state['schema'] == STATE_SCHEMA and state['input_basis'] == 'git_blob',
            'unsupported build state')
    repository(state['repository'])
    commit_id(state['commit'], 'build state commit')
    commit_id(state['tree'], 'build state tree')
    files = state['files']
    require(isinstance(files, list) and len(files) <= MAX_FILES, 'invalid build state files')
    seen = {}
    for f in files:
        closed(f, STATE_FILE_FIELDS, 'build state file')
        file_path(f['path'])
        require(f['path'] not in seen, 'duplicate build state path')
        require(valid_hash(f['sha256']) and type(f['bytes']) is int and f['bytes'] >= 0,
                'invalid build state file record')
        seen[f['path']] = (f['sha256'], f['bytes'])
    return dict(repository=state['repository'], commit=state['commit'], tree=state['tree'],
                sha256=selection[1], files=seen)


def baseline(selection):
    if selection is None:
        return None
    value = load(selection, 'semantic baseline')
    closed(value, ('schema', 'model_id', 'repositories'), 'semantic baseline')
    require(value['schema'] == BASELINE_SCHEMA, 'unsupported semantic baseline')
    model(value['model_id'])
    repos = value['repositories']
    require(isinstance(repos, list) and len(repos) <= MAX_REPOSITORIES, 'invalid baseline repositories')
    result = {}
    for r in repos:
        closed(r, ('repository', 'commit', 'files'), 'baseline repository')
        repository(r['repository'])
        require(r['repository'] not in result, 'duplicate baseline repository')
        commit_id(r['commit'], 'baseline commit')
        require(isinstance(r['files'], list) and len(r['files']) <= MAX_FILES, 'invalid baseline files')
        files = {}
        for f in r['files']:
            closed(f, ('path', 'sha256'), 'baseline file')
            file_path(f['path'])
            require(f['path'] not in files and valid_hash(f['sha256']), 'invalid baseline file')
            files[f['path']] = f['sha256']
        result[r['repository']] = dict(commit=r['commit'], files=files)
    return dict(model_id=value['model_id'], sha256=selection[1], repositories=result)


def rate_card(selection, model_id):
    if selection is None:
        return None
    value = load(selection, 'rate card')
    closed(value, ('schema', 'model_id', 'currency', 'input_per_million_tokens',
                   'output_per_million_tokens', 'source'), 'rate card')
    require(value['schema'] == RATE_CARD_SCHEMA, 'unsupported rate card')
    require(value['model_id'] == model_id, 'rate card model does not match model id')
    require(isinstance(value['currency'], str) and re.fullmatch('[A-Z]{3}', value['currency']),
            'invalid rate card currency')
    bounded_text(value['source'], 'rate card source')
    return dict(sha256=selection[1], currency=value['currency'],
                input=decimal(value['input_per_million_tokens'], 'input rate'),
                output=decimal(value['output_per_million_tokens'], 'output rate'))


# Planning --------------------------------------------------------------------

def input_tokens(size, overhead_percent):
    base = -(-size // BYTES_PER_TOKEN)
    return -(-base * overhead_percent // 100)


def compare(state, prior, overhead_percent, max_output):
    current, before = state['files'], (prior['files'] if prior else {})
    groups = {name: [] for name in CATEGORIES}
    for path, (sha, _) in current.items():
        kind = 'new' if path not in before else 'unchanged' if before[path] == sha else 'changed'
        groups[kind].append(path)
    groups['deleted'] = [p for p in before if p not in current]
    work = groups['new'] + groups['changed']
    size = sum(current[p][1] for p in work)
    estimated_in = sum(input_tokens(current[p][1], overhead_percent) for p in work)
    since = prior['commit'] if prior else None
    if prior is None:
        catch_up = 'initial'
    elif since == state['commit']:
        catch_up = 'none'
    else:
        catch_up = 'included'
    return dict(
        repository=state['repository'],
        revision_range={'from': since, 'to': state['commit'], 'tree': state['tree']},
        catch_up=catch_up,
        counts={name: len(groups[name]) for name in CATEGORIES},
        paths={name: sorted(groups[name])[:MAX_LISTED] for name in LISTED},
        paths_truncated={name: max(0, len(groups[name]) - MAX_LISTED) for name in LISTED},
        input_bytes=size, estimated_input_tokens=estimated_in,
        estimated_output_tokens=len(work) * max_output)


def body(states, prior, card, model_id, overhead_percent, max_output, requested):
    """Every plan field except created_at/expires_at; deterministic in its inputs."""
    repositories = [compare(s, prior['repositories'].get(s['repository']) if prior else None,
                            overhead_percent, max_output)
                    for s in sorted(states, key=lambda s: s['repository'])]
    totals = {name: sum(r['counts'][name] for r in repositories) for name in CATEGORIES}
    for name in ('input_bytes', 'estimated_input_tokens', 'estimated_output_tokens'):
        totals[name] = sum(r[name] for r in repositories)
    totals['estimated_total_tokens'] = totals['estimated_input_tokens'] + totals['estimated_output_tokens']
    cost = None
    if card is not None:
        amount = (totals['estimated_input_tokens'] * card['input']
                  + totals['estimated_output_tokens'] * card['output']) / Decimal(1000000)
        cost = dict(currency=card['currency'], rate_card_sha256=card['sha256'],
                    amount=str(amount.quantize(Decimal('0.000001'), rounding=ROUND_CEILING)),
                    label=COST_LABEL)
    unselected = sorted(set(prior['repositories']) - {s['repository'] for s in states}) if prior else []
    return dict(
        schema=PLAN_SCHEMA, model_id=model_id,
        inputs=dict(build_states=[dict(repository=s['repository'], sha256=s['sha256'])
                                  for s in sorted(states, key=lambda s: s['repository'])],
                    baseline_sha256=prior['sha256'] if prior else None,
                    rate_card_sha256=card['sha256'] if card else None),
        estimate=dict(method='ceil(ceil(bytes/4) * input_overhead_percent / 100) per new or changed '
                             'file; output fixed per file',
                      bytes_per_token=BYTES_PER_TOKEN, input_overhead_percent=overhead_percent,
                      max_output_tokens_per_file=max_output, label=ESTIMATE_LABEL),
        requested_ceiling_tokens=requested, repositories=repositories, totals=totals,
        estimated_cost=cost,
        existing_semantic_outputs=dict(written=False, baseline_sha256=prior['sha256'] if prior else None,
                                       baseline_repositories_not_selected=unselected),
        authorizes='nothing', limitations=list(LIMITATIONS))


def prepare(build_states, baseline_selection, rate_selection, model_id, overhead_percent,
            max_output, requested):
    model(model_id)
    require(type(overhead_percent) is int and 100 <= overhead_percent <= 1000,
            'input overhead percent must be 100..1000')
    tokens(max_output, 'max output tokens per file', 1)
    tokens(requested, 'requested ceiling', 1)
    require(1 <= len(build_states) <= MAX_REPOSITORIES, 'one or more build states are required')
    states = [build_state(s) for s in build_states]
    require(len({s['repository'] for s in states}) == len(states), 'duplicate build state repository')
    prior = baseline(baseline_selection)
    require(prior is None or prior['model_id'] == model_id,
            'baseline model differs; plan with --baseline-none for a full batch')
    card = rate_card(rate_selection, model_id)
    plan = body(states, prior, card, model_id, overhead_percent, max_output, requested)
    if plan['totals']['estimated_total_tokens'] > requested:
        raise Refused('estimate %d exceeds requested ceiling %d'
                      % (plan['totals']['estimated_total_tokens'], requested))
    return plan


def create_only(path, data):
    """Write data to a new regular file; never replace or follow an existing entry."""
    path = Path(os.path.abspath(path))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        with os.fdopen(fd, 'wb') as handle:
            fd = None
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            require(os.fstat(handle.fileno()).st_size == len(data), 'plan write size mismatch')
    except BaseException:
        if fd is not None:
            os.close(fd)
        # Only this invocation's own new file is removed.
        os.unlink(path)
        raise


def plan(args, now=None):
    now = now or datetime.now(timezone.utc)
    require(1 <= args.valid_hours <= MAX_VALID_HOURS, 'valid hours must be 1..%d' % MAX_VALID_HOURS)
    document = prepare(args.build_state, args.baseline, args.rate_card, args.model_id,
                       args.input_overhead_percent, args.max_output_tokens_per_file,
                       args.requested_ceiling)
    created = now.replace(microsecond=0)
    document.update(created_at=stamp(created), expires_at=stamp(created + timedelta(hours=args.valid_hours)))
    closed(document, PLAN_FIELDS, 'plan')
    data = encoded(document)
    create_only(args.output, data)
    return dict(status='planned',
                plan=dict(path=str(Path(os.path.abspath(args.output))), sha256=digest(data)),
                totals=document['totals'], requested_ceiling_tokens=document['requested_ceiling_tokens'],
                expires_at=document['expires_at'], authorizes='nothing')


# Verification ----------------------------------------------------------------

def approval_record(value):
    closed(value, APPROVAL_FIELDS, 'approval record')
    require(value['schema'] == APPROVAL_SCHEMA, 'unsupported approval record')
    require(valid_hash(value['plan_sha256']), 'invalid approval plan sha256')
    bounded_text(value['approved_by'], 'approved_by')
    bounded_text(value['approval_source'], 'approval_source')
    tokens(value['token_ceiling'], 'approval token ceiling', 1)
    states = value['build_states']
    require(isinstance(states, list) and 1 <= len(states) <= MAX_REPOSITORIES,
            'invalid approval build states')
    for s in states:
        closed(s, ('repository', 'sha256'), 'approval build state')
        repository(s['repository'])
        require(valid_hash(s['sha256']), 'invalid approval build state sha256')
    require(len({s['repository'] for s in states}) == len(states), 'duplicate approval repository')
    return value


def check(args, now):
    reasons = []
    raw_plan, document = selected_input(args.plan[0], args.plan[1], MAX_INPUT)
    plan_sha = digest(raw_plan)
    closed(document, PLAN_FIELDS, 'plan')
    require(document['schema'] == PLAN_SCHEMA, 'unsupported plan')
    closed(document['estimate'], ('method', 'bytes_per_token', 'input_overhead_percent',
                                  'max_output_tokens_per_file', 'label'), 'plan estimate')
    closed(document['inputs'], ('build_states', 'baseline_sha256', 'rate_card_sha256'), 'plan inputs')
    require(isinstance(document['inputs']['build_states'], list), 'invalid plan build states')
    for s in document['inputs']['build_states']:
        closed(s, ('repository', 'sha256'), 'plan build state')
        repository(s['repository'])
        require(valid_hash(s['sha256']), 'invalid plan build state sha256')
    require(isinstance(document['totals'], dict), 'invalid plan totals')
    tokens(document['totals'].get('estimated_total_tokens'), 'plan estimated total tokens')
    tokens(document['requested_ceiling_tokens'], 'plan requested ceiling', 1)
    model(document['model_id'])
    created = utc(document['created_at'], 'plan created_at')
    expires = utc(document['expires_at'], 'plan expires_at')
    _, approval = selected_input(args.approval[0], args.approval[1], MAX_INPUT)
    approval_record(approval)
    approved_at = utc(approval['approved_at'], 'approved_at')
    approval_expires = utc(approval['expires_at'], 'approval expires_at')

    if approval['plan_sha256'] != plan_sha:
        reasons.append('approval plan_sha256 does not match the plan')
    if approval['approved_by'] != args.approver:
        reasons.append('approval approved_by does not match the expected approver')
    estimate = document['estimate']
    try:
        current = prepare(args.build_state, args.baseline, args.rate_card, document['model_id'],
                          estimate['input_overhead_percent'], estimate['max_output_tokens_per_file'],
                          document['requested_ceiling_tokens'])
    except Refused as exc:
        current = None
        reasons.append('current inputs exceed the requested ceiling: ' + str(exc))
    if current is not None and current != {k: v for k, v in document.items()
                                           if k not in ('created_at', 'expires_at')}:
        reasons.append('stale plan: current build states, baseline or rate card do not reproduce it')
    approved_states = sorted((s['repository'], s['sha256']) for s in approval['build_states'])
    planned_states = sorted((s['repository'], s['sha256']) for s in document['inputs']['build_states'])
    if approved_states != planned_states:
        reasons.append('approval build states do not match the plan')
    if not created <= approved_at <= now:
        reasons.append('approved_at is outside plan creation and now')
    if approval_expires > expires:
        reasons.append('approval expires after the plan')
    if now >= expires:
        reasons.append('plan expired')
    if now >= approval_expires:
        reasons.append('approval expired')
    needed = document['totals']['estimated_total_tokens']
    if needed > approval['token_ceiling']:
        reasons.append('estimate %d exceeds approved ceiling %d' % (needed, approval['token_ceiling']))
    if approval['token_ceiling'] > document['requested_ceiling_tokens']:
        reasons.append('approved ceiling %d exceeds requested ceiling %d'
                       % (approval['token_ceiling'], document['requested_ceiling_tokens']))
    return plan_sha, document, approval, reasons


def verify(args, now=None):
    now = now or datetime.now(timezone.utc)
    plan_sha, document, approval, reasons = check(args, now)
    return dict(schema=VERIFICATION_SCHEMA, status='refused' if reasons else 'verified',
                reasons=reasons, checked_at=stamp(now), plan_sha256=plan_sha,
                approval_sha256=args.approval[1],
                expires_at=min(document['expires_at'], approval['expires_at']),
                estimated_total_tokens=document['totals']['estimated_total_tokens'],
                approved_token_ceiling=approval['token_ceiling'],
                requested_ceiling_tokens=document['requested_ceiling_tokens'],
                authorizes='nothing', executes='nothing')


# CLI -------------------------------------------------------------------------

def parser():
    p = argparse.ArgumentParser(description='Plan a semantic batch or verify its approval; never executes.')
    sub = p.add_subparsers(dest='command', required=True)

    def inputs(command):
        command.add_argument('--build-state', nargs=2, action='append', required=True,
                             metavar=('PATH', 'SHA256'), help='current structural build-state.json')
        base = command.add_mutually_exclusive_group(required=True)
        base.add_argument('--baseline', nargs=2, metavar=('PATH', 'SHA256'))
        base.add_argument('--baseline-none', dest='baseline', action='store_const', const=None)
        command.add_argument('--rate-card', nargs=2, metavar=('PATH', 'SHA256'))

    planning = sub.add_parser('plan', help='write one create-only batch plan')
    inputs(planning)
    planning.add_argument('--model-id', required=True)
    planning.add_argument('--max-output-tokens-per-file', type=int, required=True)
    planning.add_argument('--input-overhead-percent', type=int, required=True)
    planning.add_argument('--requested-ceiling', type=int, required=True, help='total tokens')
    planning.add_argument('--valid-hours', type=int, default=24)
    planning.add_argument('--output', required=True, help='new plan file; never replaced')

    checking = sub.add_parser('verify', help='verify an approval record; writes nothing')
    inputs(checking)
    checking.add_argument('--plan', nargs=2, required=True, metavar=('PATH', 'SHA256'))
    checking.add_argument('--approval', nargs=2, required=True, metavar=('PATH', 'SHA256'))
    checking.add_argument('--approver', required=True, help='expected approved_by value')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = (plan if args.command == 'plan' else verify)(args)
    except Refused as exc:
        result = dict(status='refused', reasons=[str(exc)[:500]], authorizes='nothing')
    except (StoreError, ValueError, OSError) as exc:
        result = dict(status='failed', reasons=[(type(exc).__name__ + ': ' + str(exc))[:500]],
                      authorizes='nothing')
    sys.stdout.buffer.write(encoded(result))
    return 0 if result['status'] in ('planned', 'verified') else 1


if __name__ == '__main__':
    sys.exit(main())
