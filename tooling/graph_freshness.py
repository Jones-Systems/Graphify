#!/usr/bin/env python3
"""Observe one explicit checkout against a validated portable graph snapshot."""
import argparse
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import tarfile
import time

# Importing this CLI must not create caches in the bound reader checkout either.
sys.dont_write_bytecode = True
import graph_read as reader

VERSION = '1.0'
MAX_GIT_BYTES = 1024 * 1024
GIT_TIMEOUT = 10


class ObservationError(ValueError):
    pass


def _git(root, *arguments):
    """Bound local Git reads; never write the index or lazily fetch objects."""
    env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    env.update(GIT_OPTIONAL_LOCKS='0', GIT_NO_LAZY_FETCH='1', GIT_TERMINAL_PROMPT='0')
    command = ['git', '--no-optional-locks', '-c', 'core.fsmonitor=false',
               '-c', 'core.untrackedCache=false', '-c', 'status.submoduleSummary=false',
               '-C', str(root), *arguments]
    try:
        with subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
            try:
                data = bytearray()
                deadline = time.monotonic() + GIT_TIMEOUT
                with selectors.DefaultSelector() as poll:
                    poll.register(process.stdout, selectors.EVENT_READ)
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0 or not poll.select(remaining):
                            raise ObservationError('Git observation timed out')
                        block = os.read(process.stdout.fileno(), 65536)
                        if not block:
                            break
                        data.extend(block)
                        if len(data) > MAX_GIT_BYTES:
                            raise ObservationError('Git observation output limit exceeded')
                code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
                if code:
                    raise ObservationError('Git observation failed (missing HEAD or unavailable checkout)')
                return bytes(data)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ObservationError('Git unavailable or observation failed') from exc


def _oid(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', value) is not None


def _require_safe_status(root):
    """Reject extension execution before Git can revalidate tracked contents."""
    # Query names only, across the same effective scopes (including includes and
    # worktree config) as status. Attributes from any source can select a driver;
    # disabling drivers would change cleanliness semantics, so fail closed even
    # for unused/empty filter definitions instead of attempting attribute matching.
    keys = _git(root, 'config', '--includes', '--null', '--list', '--name-only')
    if any(key.lower().startswith(b'filter.') for key in keys.split(b'\0')):
        raise ObservationError('source observation unavailable: Git filter configuration')
    # A submodule has independent configuration. Do not enter it or report a
    # clean parent while suppressing its dirty state. ls-files reads index entries
    # without content conversion; status also disables recursion defensively.
    entries = _git(root, 'ls-files', '--stage', '-z')
    if any(entry.startswith(b'160000 ') for entry in entries.split(b'\0')):
        raise ObservationError('source observation unavailable: indexed submodules')


def _observe_source(source_root):
    """Reusable read-only sample; equal samples cannot exclude intervening edits."""
    try:
        root = Path(source_root).resolve(strict=True)
    except OSError as exc:
        raise ObservationError('source root unavailable') from exc
    if not root.is_dir():
        raise ObservationError('source root is not a directory')
    top = os.fsdecode(_git(root, 'rev-parse', '--show-toplevel')).rstrip('\n')
    if Path(top).resolve() != root:
        raise ObservationError('source root must be the exact Git worktree root')
    head = _git(root, 'rev-parse', '--verify', 'HEAD^{commit}').decode('ascii').strip()
    _require_safe_status(root)
    status = _git(root, 'status', '--porcelain=v1', '-z', '--untracked-files=all',
                  '--ignore-submodules=all')
    after = _git(root, 'rev-parse', '--verify', 'HEAD^{commit}').decode('ascii').strip()
    if not _oid(head) or not _oid(after):
        raise ObservationError('invalid observed Git HEAD')
    return dict(root=str(root), head=head, head_after=after, cleanliness='dirty' if status else 'clean',
                status_sha256=hashlib.sha256(status).hexdigest(), stable=head == after)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _envelope(repository, expected, target):
    return dict(
        schema='graphify-freshness-result/v1', observer_version=VERSION,
        status='error', repository=repository, catalog_sha256=None,
        expected_catalog_sha256=expected, archive_sha256=None, graph_sha256=None,
        snapshot_head=None, source={'before': None, 'after': None},
        observation={'started_at_utc': _now(), 'finished_at_utc': None,
                     'stability': 'unknown', 'basis': 'bounded before/after Git samples'},
        target={'oid': target, 'authority_basis': 'caller_supplied' if target else 'not_supplied',
                'snapshot_matches': None, 'source_matches': None},
        canonical_currentness='unknown',
        validation={'status': 'not_completed', 'coverage': None,
                    'build_provenance': {'status': 'not_verified',
                                         'missing_or_unverified': ['build_time_inventory', 'build_time_cleanliness']}},
        comparison={'outcome': 'unavailable', 'local_clean_match': False, 'qualified': False,
                    'scope': 'observed_local_checkout_and_optional_caller_target'},
        limitations=['Equal samples cannot exclude intervening changes.',
                     'Git cleanliness excludes ignored files and is not build-input inventory proof.',
                     'Filter-configured checkouts and indexed submodules cannot be qualified.',
                     'Git configuration must remain unchanged during observation.',
                     'Repository-to-root binding and optional target authority are caller supplied.',
                     'Canonical latest source and build-time provenance are not established.'],
        truncation_reason=None,
    )


def observe(catalog_path, catalog_sha256, repository, source_root, target_oid=None):
    """Return a bounded-observation envelope; reader failures retain their type."""
    result = _envelope(repository, catalog_sha256, target_oid)
    try:
        reader.require(isinstance(repository, str) and len(repository) <= 256 and
                       re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository),
                       'invalid repository identity')
        reader.require(reader.valid_hash(catalog_sha256), 'catalog SHA256 required')
        reader.require(target_oid is None or _oid(target_oid), 'target must be an exact full Git OID')
        reader.require(bool(catalog_path) and bool(source_root), 'catalog and source root required')
        before = result['source']['before'] = _observe_source(source_root)
        try:
            catalog, result['catalog_sha256'] = reader.load_catalog(catalog_path, catalog_sha256)
            entries = [entry for entry in catalog['archives'] if entry['source']['repository'] == repository]
            reader.require(len(entries) == 1, 'repository has no selected graph')
            entry = entries[0]
            result.update(snapshot_head=entry['source']['head'], archive_sha256=entry['sha256'])
            _, _, result['graph_sha256'], coverage = reader.read_graph(catalog_path, entry)
            result['validation'].update(status='validated', coverage=coverage)
        finally:
            # A failing recheck cannot erase an earlier reader validation failure.
            try:
                result['source']['after'] = _observe_source(source_root)
            except (ValueError, OSError) as exc:
                result['source']['recheck_error'] = dict(type=type(exc).__name__, message=str(exc)[:500])
            after = result['source']['after']
            stable = after is not None and before['stable'] and after['stable'] and before == after
            result['observation']['stability'] = 'stable_samples' if stable else 'unstable'
        comparison = result['comparison']
        if not stable:
            comparison['outcome'] = 'unstable_source'
        elif before['cleanliness'] != 'clean':
            comparison['outcome'] = 'dirty_source'
        elif result['snapshot_head'] != before['head']:
            comparison['outcome'] = 'head_mismatch'
        else:
            comparison.update(outcome='clean_head_match', local_clean_match=True)
        if target_oid is not None:
            result['target'].update(snapshot_matches=result['snapshot_head'] == target_oid,
                                    source_matches=stable and after['head'] == target_oid)
            if comparison['local_clean_match'] and not result['target']['snapshot_matches']:
                comparison['outcome'] = 'target_mismatch'
        comparison['qualified'] = comparison['outcome'] == 'clean_head_match'
        result['status'] = 'qualified' if comparison['qualified'] else 'not_qualified'
    except (ValueError, OSError, tarfile.TarError, KeyError, TypeError, RecursionError) as exc:
        result['error'] = dict(type=type(exc).__name__, message=str(exc)[:500])
        result['comparison']['outcome'] = 'observation_error' if isinstance(exc, ObservationError) else 'validation_error'
    finally:
        result['observation']['finished_at_utc'] = _now()
    return result


def bounded_output(result, budget):
    if len(reader.serialize(result)) + 1 > budget:
        result['validation']['coverage'] = {'status': 'omitted_for_byte_budget'}
        result['truncation_reason'] = 'byte_budget'
    if len(reader.serialize(result)) + 1 > budget:
        # Fail closed if even identity/error metadata cannot fit; never trim a claim
        # into an apparently successful qualification with missing evidence.
        result.clear()
        result.update(schema='graphify-freshness-result/v1', observer_version=VERSION,
                      status='error', comparison={'qualified': False, 'outcome': 'output_limit'},
                      error={'type': 'OutputLimitError', 'message': 'observation exceeds byte budget'},
                      truncation_reason='byte_budget')
    return reader.serialize(result).decode() + '\n'


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--catalog', required=True)
    p.add_argument('--catalog-sha256', required=True)
    p.add_argument('--repo', required=True)
    p.add_argument('--source-root', required=True)
    p.add_argument('--target-oid')
    p.add_argument('--max-bytes', type=reader.bounded_int(4096, 1024 * 1024), default=32768)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    result = observe(args.catalog, args.catalog_sha256, args.repo, args.source_root, args.target_oid)
    sys.stdout.write(bounded_output(result, args.max_bytes))
    return 0 if result['status'] == 'qualified' else 1 if result['status'] == 'error' else 2


if __name__ == '__main__':
    raise SystemExit(main())
