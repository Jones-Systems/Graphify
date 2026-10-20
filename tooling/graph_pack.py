#!/usr/bin/env python3
"""Create one portable graph store from six explicitly selected JSON inputs.

Each --NAME path requires --NAME-sha256 (graph, validation, inventory, policy,
extractor, source). Source evidence is graphify-pack-source/v1 with exactly
source={repository,head} or {repository,head,slice}, input_sha256={the other
five names: SHA256},
build_observation=null or {head,dirty:bool|null,stable:bool|null}, and limitations
(a list of strings). Observations are caller reports, never live attestations.

Inventory is graphify-pack-inventory/v1: source, files=[{path,sha256,coverage}],
limitations. Coverage is structural, enriched, or unknown; it describes supplied
input coverage, not semantic correctness. Policy is graphify-pack-policy/v1:
source, name, rules (JSON object), limitations. Rules are retained data, not
executed admission logic. Extractor is graphify-pack-extractor/v1: source, name,
version (string|null), artifact_sha256 (SHA256|null), limitations. These four
schemas are closed. Graph and validation retain the existing consumer formats
and exact bytes. Source evidence binds every selected input's exact bytes.

A slice is one part of a multi-slice repository packed alone; every input must
declare the same source, including its slice. A single-slice repository omits
slice and packs exactly as before. Graph links stay closed within the slice. A
reference into another slice is a validation.cross_slice_references record
{source, source_file, type, target, line, target_path, target_id, target_slice}:
source_file is admitted here, target_path is a safe path not admitted here,
target_slice is another slice, and both ids are structural-v1 shaped. Records
are sorted by (source_file, type, target, line, target_path) without duplicates.
A slice holds at most MAX_SLICE_RECORDS nodes, links, hyperedges and cross-slice
records combined. Targets in other slices are not verified here. Source-byte
admission bounds belong upstream; the inventory carries no file sizes. A sliced
package's catalog is catalog v2.

No source files are opened from inventory entries. Admission, extraction, policy
enforcement, and source observations must occur upstream. This command validates
structure and content binding; it cannot establish truthful provenance, canonical
latest source, or freshness. Missing evidence stays explicitly qualified.

Output is create-only: download-catalog.json, package.json, archives/<hash>.tar.gz.
package_sha256 identifies package.json, whose hashes bind catalog and archive.
Handled cancellation removes only this invocation's tracked output entries.
Unhandleable termination or ownership changes require explicit reconciliation;
there is no recovery cleanup of an existing destination.
"""

import argparse
from contextlib import contextmanager
import gzip
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
import tarfile

from graph_read import (CATALOG_SCHEMA, CATALOG_SCHEMA_V2, digest, identity, load_catalog,
                        open_nofollow, read_graph, require, signature, slice_name, valid_hash)

NAMES = ('graph', 'validation', 'inventory', 'policy', 'extractor', 'source')
MAX_INPUT = 16 * 1024**2
MAX_GRAPH = 64 * 1024**2
MAX_ARCHIVE = 160 * 1024**2
MAX_RECORDS = 100000
MAX_SLICE_RECORDS = 100000
MAX_ITEMS = 1000000
MAX_DEPTH = 48
CANCEL_SIGNALS = {signal.SIGINT, signal.SIGTERM}


class UnknownOutputError(ValueError):
    """A created output could not be safely removed; reconcile its exact path."""


def link_refusal(info):
    """Why a verified archive may not be shared by hard link, or None.

    A link shares one inode with its source, so a write through either name
    changes both. Only regular files of this user with no write bit qualify;
    another user's file would also keep its blocks charged to that user. Nothing
    is chmodded here. The owner can still add a write bit later.
    """
    if not stat.S_ISREG(info.st_mode):
        return 'not_regular'
    if info.st_uid != os.geteuid():
        return 'foreign_owner'
    if info.st_mode & 0o222:
        return 'write_bits_present'
    return None


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True,
                       separators=(',', ':'), allow_nan=False) + '\n').encode()


def closed(value, keys, label):
    require(isinstance(value, dict) and set(value) == set(keys),
            f'invalid {label} fields')


def bounded_text(value, label):
    require(isinstance(value, str) and 0 < len(value) <= 4096 and '\x00' not in value,
            f'invalid {label}')


def limitations(value):
    require(isinstance(value, list) and len(value) <= 1000, 'invalid limitations')
    for item in value:
        bounded_text(item, 'limitation')


def source_identity(value):
    closed(value, ('repository', 'head', *(('slice',) if isinstance(value, dict) and 'slice' in value
                                           else ())), 'source identity')
    identity(value)
    slice_name(value)
    for part in value['repository'].split('/'):
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', part) is not None
                and not part.endswith('.git'), 'noncanonical repository identity')
    return value


def file_path(value):
    bounded_text(value, 'inventory path')
    path = PurePosixPath(value)
    require(not path.is_absolute() and str(path) == value and value != '.'
            and '..' not in path.parts and '\\' not in value
            and not any(ord(c) < 32 for c in value), 'unsafe inventory path')
    return value


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result

    def constant(_):
        raise ValueError('nonfinite JSON number')

    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    stack = [(value, 0)]
    count = 0
    while stack:
        item, depth = stack.pop()
        count += 1
        require(count <= MAX_ITEMS and depth <= MAX_DEPTH, 'JSON resource limit exceeded')
        if isinstance(item, dict):
            stack.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            stack.extend((v, depth + 1) for v in item)
        elif isinstance(item, float):
            require(float('-inf') < item < float('inf'), 'nonfinite JSON number')
    require(isinstance(value, dict), 'input must be a JSON object')
    return value


def selected_input(path, expected, limit):
    require(valid_hash(expected), 'invalid input checksum')
    with open_nofollow(path) as handle:
        before = signature(handle)
        require(before[2] <= limit, 'input too large')
        raw = handle.read(limit + 1)
        require(before == signature(handle), 'input changed during read')
    require(len(raw) <= limit, 'input too large')
    require(digest(raw) == expected, 'input checksum mismatch')
    return raw, strict_json(raw)


def validate_inputs(values, hashes):
    source = values['source']
    closed(source, ('schema', 'source', 'input_sha256', 'build_observation', 'limitations'),
           'source evidence')
    require(source['schema'] == 'graphify-pack-source/v1', 'unsupported source schema')
    selected = source_identity(source['source'])
    limitations(source['limitations'])
    require(source['input_sha256'] == {k: hashes[k] for k in NAMES if k != 'source'},
            'source evidence input checksum mismatch')
    missing = []
    observation = source['build_observation']
    if observation is None:
        missing.append('build_observation')
    else:
        closed(observation, ('head', 'dirty', 'stable'), 'build observation')
        require(observation['head'] == selected['head'], 'build observation head mismatch')
        for key in ('dirty', 'stable'):
            require(observation[key] is None or type(observation[key]) is bool,
                    f'invalid build observation {key}')
            if observation[key] is None:
                missing.append('build_observation.' + key)

    fields = {
        'inventory': ('files',), 'policy': ('name', 'rules'),
        'extractor': ('name', 'version', 'artifact_sha256'),
    }
    for name, extra in fields.items():
        value = values[name]
        closed(value, ('schema', 'source', 'limitations', *extra), name)
        require(value['schema'] == f'graphify-pack-{name}/v1', f'unsupported {name} schema')
        require(source_identity(value['source']) == selected, f'{name} source mismatch')
        limitations(value['limitations'])
    bounded_text(values['policy']['name'], 'policy name')
    require(isinstance(values['policy']['rules'], dict), 'invalid policy rules')
    extractor = values['extractor']
    bounded_text(extractor['name'], 'extractor name')
    if extractor['version'] is None:
        missing.append('extractor.version')
    else:
        bounded_text(extractor['version'], 'extractor version')
    if extractor['artifact_sha256'] is None:
        missing.append('extractor.artifact_sha256')
    else:
        require(valid_hash(extractor['artifact_sha256']), 'invalid extractor artifact checksum')

    files = values['inventory']['files']
    require(isinstance(files, list) and len(files) <= MAX_RECORDS, 'invalid inventory files')
    admitted = set()
    coverage = dict(structural=0, enriched=0, unknown=0)
    for record in files:
        closed(record, ('path', 'sha256', 'coverage'), 'inventory file')
        path = file_path(record['path'])
        require(path not in admitted, 'duplicate inventory path')
        require(valid_hash(record['sha256']), 'invalid inventory content checksum')
        require(isinstance(record['coverage'], str) and record['coverage'] in coverage,
                'invalid inventory coverage')
        admitted.add(path)
        coverage[record['coverage']] += 1

    graph, validation = values['graph'], values['validation']
    for name in ('graph', 'validation'):
        value = values[name]
        if 'source' in value:
            require(source_identity(value['source']) == selected, f'{name} source mismatch')
        else:
            missing.append(name + '.source')
        if 'repository' in value:
            require(value['repository'] == selected['repository'], f'{name} repository mismatch')
        if 'built_at_commit' in value:
            require(value['built_at_commit'] == selected['head'], f'{name} source head mismatch')
    require(graph.get('built_at_commit') == selected['head'], 'graph source head mismatch')
    require(graph.get('directed') is True and isinstance(graph.get('nodes'), list)
            and isinstance(graph.get('links'), list), 'malformed directed graph')
    require(len(graph['nodes']) <= MAX_RECORDS and len(graph['links']) <= MAX_RECORDS,
            'graph record limit exceeded')
    nodes = set()
    for node in graph['nodes']:
        require(isinstance(node, dict), 'invalid node')
        bounded_text(node.get('id'), 'node id')
        require(node['id'] not in nodes, 'duplicate node id')
        nodes.add(node['id'])
    for edge in graph['links']:
        require(isinstance(edge, dict) and isinstance(edge.get('source'), str)
                and isinstance(edge.get('target'), str) and edge['source'] in nodes
                and edge['target'] in nodes, 'invalid graph endpoint')
    metadata = graph.get('graph', {})
    require(isinstance(metadata, dict), 'invalid graph metadata')
    records = list(graph['nodes']) + graph['links']
    for collection in (graph.get('hyperedges', []), metadata.get('hyperedges', [])):
        require(isinstance(collection, list) and len(collection) <= MAX_RECORDS,
                'invalid hyperedge collection')
        for hyperedge in collection:
            require(isinstance(hyperedge, dict) and isinstance(hyperedge.get('nodes'), list)
                    and all(isinstance(n, str) and n in nodes for n in hyperedge['nodes']),
                    'invalid hyperedge endpoint')
        records.extend(collection)
    sliced = 'slice' in selected
    references = cross_slice_references(validation, selected, admitted)
    if sliced:
        require(len(records) + len(references) <= MAX_SLICE_RECORDS, 'slice record limit exceeded')
    unbound = 0
    for record in records:
        if 'source_file' in record:
            require(file_path(record['source_file']) in admitted, 'graph file not admitted')
        else:
            unbound += 1
    segments = validation.get('covered_segments_by_file')
    if segments is not None:
        require(isinstance(segments, dict), 'invalid covered segments')
        for path in segments:
            require(file_path(path) in admitted, 'validation file not admitted')
    else:
        missing.append('validation.covered_segments_by_file')
    if coverage['unknown']:
        missing.append('inventory.coverage')
    if unbound:
        missing.append('graph.record_source_files')
    result = dict(source=selected, provenance_status='caller_supplied_not_attested',
                  freshness='unknown', missing_provenance=sorted(missing),
                  build_observation=observation, inventory_coverage=coverage,
                  records_without_source_file=unbound,
                  coverage_meaning='Caller-reported file coverage; structural is not semantic enrichment',
                  limitations=['Policy admission and extraction were not executed or attested',
                               'No source checkout or canonical target was observed'])
    if sliced:
        # Unsliced qualification stays byte-identical; only slices gain these fields.
        result['cross_slice_references'] = dict(count=len(references),
                                                target_verification='not_verified_in_package')
        result['limitations'] = result['limitations'] + [
            'One repository slice; cross-slice reference targets are not verified by this package']
    return result


def cross_slice_references(validation, selected, admitted):
    """Validate validation.cross_slice_references for one slice; return the records."""
    if 'cross_slice_references' not in validation:
        return []
    own = selected.get('slice')
    require(own is not None, 'cross-slice references require a sliced source')
    references = validation['cross_slice_references']
    require(isinstance(references, list) and len(references) <= MAX_RECORDS,
            'invalid cross-slice references')
    previous = None
    for record in references:
        closed(record, ('source', 'source_file', 'type', 'target', 'line', 'target_path',
                        'target_id', 'target_slice'), 'cross-slice reference')
        require(file_path(record['source_file']) in admitted, 'cross-slice source file not admitted')
        require(file_path(record['target_path']) not in admitted,
                'cross-slice target is admitted in this slice')
        require(slice_name(dict(slice=record['target_slice'])) != own,
                'cross-slice target is this slice')
        for key in ('source', 'target_id'):
            require(isinstance(record[key], str)
                    and re.fullmatch('structural-v1:[0-9a-f]{64}', record[key]) is not None,
                    'invalid cross-slice reference id')
        bounded_text(record['type'], 'cross-slice reference type')
        bounded_text(record['target'], 'cross-slice reference target')
        require(type(record['line']) is int and record['line'] >= 1, 'invalid cross-slice reference line')
        key = (record['source_file'], record['type'], record['target'], record['line'],
               record['target_path'])
        require(previous is None or previous < key, 'cross-slice references unsorted or duplicated')
        previous = key
    return references


@contextmanager
def directory_fd(path):
    path = Path(os.path.abspath(path))
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def inode(value):
    return value.st_dev, value.st_ino


class OwnedOutput:
    """Track only entries created here, relative to pinned directory descriptors."""

    def __init__(self, parent, name):
        self.parent, self.name = parent, name
        self.created = False
        self.root = None
        self.directories = []
        self.files = []

    def create(self):
        mask = signal.pthread_sigmask(signal.SIG_BLOCK, CANCEL_SIGNALS)
        try:
            os.mkdir(self.name, mode=0o700, dir_fd=self.parent)
            self.created = True
            self.root = os.stat(self.name, dir_fd=self.parent, follow_symlinks=False)
            fd = os.open(self.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                         dir_fd=self.parent)
            self.directories.append((self.parent, self.name, fd, inode(self.root)))
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        return fd

    def mkdir(self, parent, name):
        mask = signal.pthread_sigmask(signal.SIG_BLOCK, CANCEL_SIGNALS)
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent)
            created = os.stat(name, dir_fd=parent, follow_symlinks=False)
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            self.directories.append((parent, name, fd, inode(created)))
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        return fd

    @contextmanager
    def file(self, parent, name):
        mask = signal.pthread_sigmask(signal.SIG_BLOCK, CANCEL_SIGNALS)
        fd = None
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=parent)
            self.files.append((parent, name, inode(os.fstat(fd))))
        finally:
            try:
                signal.pthread_sigmask(signal.SIG_SETMASK, mask)
            except BaseException:
                if fd is not None:
                    os.close(fd)
                raise
        with os.fdopen(fd, 'wb') as handle:
            yield handle

    def link(self, parent, name, source_parent, source_name, expected):
        """Hard-link one verified file as a create-only owned entry.

        expected is the (st_dev, st_ino) the caller verified through an open
        descriptor. A name swapped before linking yields another inode; that link
        is removed and the caller falls back or fails.
        """
        mask = signal.pthread_sigmask(signal.SIG_BLOCK, CANCEL_SIGNALS)
        try:
            os.link(source_name, name, src_dir_fd=source_parent, dst_dir_fd=parent,
                    follow_symlinks=False)
            created = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if inode(created) != expected or not stat.S_ISREG(created.st_mode):
                os.unlink(name, dir_fd=parent)
                raise ValueError('linked archive identity changed')
            self.files.append((parent, name, expected))
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, mask)

    def verify_ownership(self):
        # Inspect the complete closure before unlinking anything. Unexpected
        # children or replaced entries preserve an unknown effect for the caller.
        if not self.created:
            return
        require(self.directories, 'created destination could not be pinned; cleanup refused')
        for parent, name, _, expected in self.directories:
            require(inode(os.stat(name, dir_fd=parent, follow_symlinks=False)) == expected,
                    'destination ownership changed; cleanup refused')
        for parent, name, expected in self.files:
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            require(inode(current) == expected and stat.S_ISREG(current.st_mode),
                    'output ownership changed; cleanup refused')
        for _, _, fd, _ in self.directories:
            expected = {n for p, n, _ in self.files if p == fd}
            expected.update(n for p, n, _, _ in self.directories if p == fd)
            require(set(os.listdir(fd)) == expected, 'unowned output entries; cleanup refused')

    def cleanup(self):
        self.verify_ownership()
        for parent, name, _ in reversed(self.files):
            os.unlink(name, dir_fd=parent)
        for parent, name, _, _ in reversed(self.directories):
            os.rmdir(name, dir_fd=parent)

    def close(self):
        for _, _, fd, _ in reversed(self.directories):
            os.close(fd)


def archive_bytes(members):
    buffer = io.BytesIO()
    # Filename, clock, owners, modes and member order cannot depend on this host.
    with gzip.GzipFile(filename='', mode='wb', fileobj=buffer, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w|', format=tarfile.USTAR_FORMAT) as archive:
            for name, raw in sorted(members.items()):
                entry = tarfile.TarInfo(name)
                entry.mode = 0o600
                entry.size = len(raw)
                archive.addfile(entry, io.BytesIO(raw))
    result = buffer.getvalue()
    require(len(result) <= MAX_ARCHIVE, 'output archive too large')
    return result


def pack(inputs, destination):
    """inputs maps all six names to (explicit path, SHA256); never discovers files."""
    closed(inputs, NAMES, 'input selection')
    destination = Path(os.path.abspath(destination))
    require(destination.name not in ('', '.', '..'), 'invalid destination')
    require(not os.path.lexists(destination), 'destination exists')
    raw, values, hashes = {}, {}, {}
    for name in NAMES:
        path, expected = inputs[name]
        raw[name], values[name] = selected_input(path, expected,
                                               MAX_GRAPH if name == 'graph' else MAX_INPUT)
        hashes[name] = expected
    evidence = validate_inputs(values, hashes)
    members = {'enriched/graph.json': raw['graph'],
               'enriched/validation.json': raw['validation']}
    members['enriched/hashes.json'] = encoded({n.split('/')[-1]: digest(b)
                                             for n, b in members.items()})
    members.update({f'provenance/{name}.json': raw[name] for name in NAMES[2:]})
    members['provenance/qualification.json'] = encoded(evidence)
    members['archive-manifest.json'] = encoded(dict(
        schema='portable-graph-archive/v1', source=evidence['source'],
        files={name: digest(data) for name, data in members.items()}))
    archive = archive_bytes(members)
    archive_sha = digest(archive)
    archive_name = archive_sha + '.tar.gz'
    entry = dict(source=evidence['source'], archive=archive_name,
                 sha256=archive_sha, bytes=len(archive))
    catalog = encoded(dict(schema=CATALOG_SCHEMA_V2 if 'slice' in evidence['source'] else CATALOG_SCHEMA,
                           status='complete', archive_directory='archives', archives=[entry],
                           empty_repositories=[]))
    package = encoded(dict(schema='graphify-pack-package/v1', source=evidence['source'],
                           input_sha256=hashes, catalog_sha256=digest(catalog), archive=entry,
                           graph_sha256=hashes['graph'], validation_sha256=hashes['validation'],
                           qualification=evidence))
    with directory_fd(destination.parent) as parent:
        owned = OwnedOutput(parent, destination.name)
        try:
            root = owned.create()
            archives = owned.mkdir(root, 'archives')
            for fd, name, data in ((archives, archive_name, archive),
                                   (root, 'download-catalog.json', catalog),
                                   (root, 'package.json', package)):
                with owned.file(fd, name) as handle:
                    handle.write(data)
            # These are the unchanged validation routines also used by graph_pull.
            verified, _ = load_catalog(destination / 'download-catalog.json', digest(catalog))
            _, _, graph_sha, _ = read_graph(destination / 'download-catalog.json',
                                             verified['archives'][0])
            require(graph_sha == hashes['graph'], 'completed graph checksum mismatch')
            selected_input(destination / 'package.json', digest(package), MAX_INPUT)
            owned.verify_ownership()
            require(inode(destination.stat(follow_symlinks=False)) == inode(owned.root),
                    'destination ownership changed')
            return dict(schema='graphify-pack-result/v1', status='ok',
                        destination=str(destination), source=evidence['source'],
                        package_sha256=digest(package), catalog_sha256=digest(catalog),
                        archive_sha256=archive_sha, graph_sha256=graph_sha,
                        validation_sha256=hashes['validation'],
                        validation='unchanged_reader_and_pull_validators', qualification=evidence)
        except BaseException as original:
            mask = signal.pthread_sigmask(signal.SIG_BLOCK, CANCEL_SIGNALS)
            try:
                owned.cleanup()
            except (ValueError, OSError) as cleanup_error:
                raise UnknownOutputError(
                    f'{original}; cleanup refused or failed; effect unknown at '
                    f'{destination}: {cleanup_error}') from original
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, mask)
            raise
        finally:
            owned.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in NAMES:
        parser.add_argument('--' + name, required=True)
        parser.add_argument('--' + name + '-sha256', required=True)
    parser.add_argument('--destination', required=True)
    args = parser.parse_args(argv)
    old = {}

    def cancel(signum, frame):
        raise KeyboardInterrupt('cancelled')

    for sig in CANCEL_SIGNALS:
        old[sig] = signal.signal(sig, cancel)
    try:
        result = pack({name: (getattr(args, name), getattr(args, name + '_sha256'))
                       for name in NAMES}, args.destination)
        code = 0
    except (ValueError, OSError, tarfile.TarError, RecursionError, KeyboardInterrupt,
            KeyError, TypeError, OverflowError) as exc:
        result = dict(schema='graphify-pack-result/v1', status='error',
                      destination=str(Path(os.path.abspath(args.destination))),
                      effect='unknown' if isinstance(exc, UnknownOutputError) else 'not_completed',
                      error=str(exc)[:2000])
        code = 1
    finally:
        for sig, handler in old.items():
            signal.signal(sig, handler)
    print(json.dumps(result, ensure_ascii=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
