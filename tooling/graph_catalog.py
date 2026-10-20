#!/usr/bin/env python3
"""Assemble explicitly selected graph packages into one new download catalog.

Each --package PATH SHA256 names one graphify-pack-package/v1 package.json by
its exact raw SHA256. The caller selects exactly one package per repository, or
one per repository slice (source.slice); a repository is never both sliced and
unsliced. Nothing is discovered from directories, corpora, or stores. Every
package must sit beside the download-catalog.json and archives/<sha>.tar.gz it
declares.

Before any output is created, each package, its declared single-entry catalog,
archive bytes, archive manifest, provenance member digests, and graph are
validated with the unchanged graph_read validators. Repository and slice
identities (compared exactly and case-insensitively) and archive names must not
collide.

Output is create-only: download-catalog.json (private-graph-download-catalog/v1,
or v2 when any entry is sliced; entries ordered by repository, then slice),
archives/<sha>.tar.gz copied byte-exactly, and assembly.json recording each
selected package's identities, qualification, and limitations.

--link-existing (off by default) hard-links a verified package archive instead
of copying it only when it is on the destination filesystem, a regular file of
this user, and has no write bit. Otherwise it is copied, with the reason in the
result. Nothing is chmodded; pack writes archives 0600, so they are copied
unless their owner removed the write bits. Linking saves physical disk only:
quota accounting counts every path. Output bytes do not depend on the mode.

--slice-set PATH SHA256 (repeatable, one per repository) names a producer
graphify-slice-set/v1 record {schema, repository, accepted_head, tree, slices:
[{name, package_sha256, built_head, input_digest, resolution_digest,
build_state_sha256}]}. tree is a full Git object id of accepted_head's length.
Its slices must be exactly that repository's selected slice packages. Each entry
then gains slice={name, built_head, equivalent_head: accepted_head}, and
assembly.json keeps the record. Equivalence is the producer's digest claim;
this command checks only consistency with the selected packages.

Graph nodes, source identities, freshness, and cleanliness are neither merged
nor upgraded; assembly attests consistency, not provenance.
Handled failure or cancellation removes only this invocation's tracked output.
Unprovable ownership or cleanup failure reports an unknown effect for explicit
reconciliation; there is no retry or recovery cleanup of existing paths.
"""

import argparse
import errno
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
import signal
import tarfile
import zlib

from graph_pack import (MAX_ARCHIVE, MAX_INPUT, NAMES, CANCEL_SIGNALS, OwnedOutput,
                        UnknownOutputError, closed, directory_fd, encoded, inode,
                        link_refusal, selected_input, source_identity, strict_json)
from graph_read import (CATALOG_SCHEMA, CATALOG_SCHEMA_V2, MAX_METADATA, digest, load_catalog,
                        read_graph, require, slice_name, valid_hash, verified_archive)

PACKAGE_SCHEMA = 'graphify-pack-package/v1'
SLICE_SET_SCHEMA = 'graphify-slice-set/v1'
ASSEMBLY_SCHEMA = 'graphify-catalog-assembly/v1'
RESULT_SCHEMA = 'graphify-catalog-result/v1'
MAX_PACKAGES = 128
MAX_TOTAL_ARCHIVE = 4 * 1024**3
MAX_ARCHIVE_EXPANDED = 256 * 1024**2
MAX_ARCHIVE_MEMBERS = 64
BLOCK = 1024**2
PACKAGE_FIELDS = ('schema', 'source', 'input_sha256', 'catalog_sha256', 'archive',
                  'graph_sha256', 'validation_sha256', 'qualification')
ENTRY_FIELDS = ('source', 'archive', 'sha256', 'bytes')
MANIFEST_FILES = frozenset(['enriched/graph.json', 'enriched/validation.json',
                            'enriched/hashes.json', 'provenance/qualification.json']
                           + [f'provenance/{name}.json' for name in NAMES[2:]])
# Link failures that leave no entry and fall back to a copy.
LINK_FALLBACK = {errno.EXDEV: 'cross_device', errno.EPERM: 'link_not_permitted',
                 errno.EMLINK: 'link_count_limit', errno.ENOTSUP: 'link_unsupported'}
ERRORS = (ValueError, OSError, EOFError, zlib.error, tarfile.TarError, RecursionError,
          KeyError, TypeError, OverflowError)


def archive_members(catalog_path, entry):
    """Digest every member of the checksum-verified archive without buffering it."""
    members, manifest, total = {}, None, 0
    with verified_archive(catalog_path, entry) as handle:
        with tarfile.open(fileobj=handle, mode='r|gz') as archive:
            for member in archive:
                require(member.name not in members and len(members) < MAX_ARCHIVE_MEMBERS,
                        'duplicate or excess archive member')
                require(member.isfile() and not member.name.startswith('/')
                        and '..' not in PurePosixPath(member.name).parts,
                        'unsafe archive member')
                total += member.size
                require(total <= MAX_ARCHIVE_EXPANDED, 'archive expanded size limit exceeded')
                stream, sha, size = archive.extractfile(member), hashlib.sha256(), 0
                kept = bytearray() if member.name == 'archive-manifest.json' else None
                while block := stream.read(BLOCK):
                    sha.update(block)
                    size += len(block)
                    if kept is not None:
                        require(len(kept) + len(block) <= MAX_INPUT, 'archive manifest too large')
                        kept.extend(block)
                require(size == member.size, 'archive member size mismatch')
                members[member.name] = sha.hexdigest()
                if kept is not None:
                    manifest = bytes(kept)
    require(manifest is not None, 'missing archive manifest')
    return members, strict_json(manifest)


def inspect_package(path, expected):
    """Validate one selected package closure; return its exact catalog record."""
    path = Path(os.path.abspath(path))
    require(path.name == 'package.json', 'selected package must be named package.json')
    raw, package = selected_input(path, expected, MAX_INPUT)
    closed(package, PACKAGE_FIELDS, 'package')
    require(package['schema'] == PACKAGE_SCHEMA, 'unsupported package schema')
    source = source_identity(package['source'])
    hashes = package['input_sha256']
    closed(hashes, NAMES, 'package input checksums')
    require(all(valid_hash(value) for value in hashes.values()), 'invalid package input checksum')
    require(package['graph_sha256'] == hashes['graph']
            and package['validation_sha256'] == hashes['validation'],
            'contradictory package graph or validation checksum')
    require(valid_hash(package['catalog_sha256']), 'invalid package catalog checksum')
    entry = package['archive']
    closed(entry, ENTRY_FIELDS, 'package archive')
    require(source_identity(entry['source']) == source, 'package archive source mismatch')
    require(valid_hash(entry['sha256']) and entry['archive'] == entry['sha256'] + '.tar.gz',
            'invalid package archive identity')
    require(type(entry['bytes']) is int and 0 < entry['bytes'] <= MAX_ARCHIVE,
            'invalid package archive size')
    qualification = package['qualification']
    require(isinstance(qualification, dict) and qualification.get('source') == source,
            'package qualification source mismatch')

    catalog_path = path.parent / 'download-catalog.json'
    _, declared = selected_input(catalog_path, package['catalog_sha256'], MAX_METADATA)
    schema = CATALOG_SCHEMA_V2 if 'slice' in source else CATALOG_SCHEMA
    require(declared == dict(schema=schema, status='complete', archive_directory='archives',
                             archives=[entry], empty_repositories=[]),
            'package catalog contradicts package declaration')
    # Unchanged reader validation of the declared catalog and its selected graph.
    catalog, _ = load_catalog(catalog_path, package['catalog_sha256'])
    _, _, graph_sha, _ = read_graph(catalog_path, catalog['archives'][0])
    require(graph_sha == package['graph_sha256'], 'package graph checksum mismatch')

    members, manifest = archive_members(catalog_path, entry)
    closed(manifest, ('schema', 'source', 'files'), 'archive manifest')
    require(manifest['schema'] == 'portable-graph-archive/v1', 'invalid archive manifest')
    require(source_identity(manifest['source']) == source, 'archive manifest source mismatch')
    files = manifest['files']
    require(isinstance(files, dict) and set(files) == MANIFEST_FILES
            and set(members) == MANIFEST_FILES | {'archive-manifest.json'},
            'archive member set mismatch')
    require(all(members[name] == files[name] for name in MANIFEST_FILES),
            'archive member checksum mismatch')
    bound = {'enriched/graph.json': hashes['graph'],
             'enriched/validation.json': hashes['validation'],
             'provenance/qualification.json': digest(encoded(qualification))}
    bound.update({f'provenance/{name}.json': hashes[name] for name in NAMES[2:]})
    require(all(files[name] == value for name, value in bound.items()),
            'archive provenance contradicts package declaration')
    return dict(path=path, catalog_path=catalog_path, entry=entry, package=package,
                package_sha256=digest(raw))


def select(packages):
    require(isinstance(packages, (list, tuple)) and 0 < len(packages) <= MAX_PACKAGES,
            f'select 1..{MAX_PACKAGES} packages')
    for item in packages:
        require(isinstance(item, (list, tuple)) and len(item) == 2
                and isinstance(item[0], (str, os.PathLike)) and valid_hash(item[1]),
                'invalid package selection')
    paths = [os.path.abspath(path) for path, _ in packages]
    require(len(set(paths)) == len(paths), 'duplicate package path')
    require(len({sha for _, sha in packages}) == len(packages), 'duplicate package checksum')
    records = [inspect_package(path, sha) for path, sha in packages]
    sliced = {}
    for record in records:
        source = record['entry']['source']
        part = 'slice' in source
        require(sliced.setdefault(source['repository'].casefold(), part) == part,
                'repository mixes sliced and unsliced packages')
    keys = {(r['entry']['source']['repository'].casefold(),
             r['entry']['source'].get('slice', '').casefold()) for r in records}
    require(len(keys) == len(records), 'duplicate repository selection'
            if not any(sliced.values()) else 'duplicate repository slice selection')
    require(len({r['entry']['archive'] for r in records}) == len(records),
            'colliding archive name')
    require(sum(r['entry']['bytes'] for r in records) <= MAX_TOTAL_ARCHIVE,
            'aggregate archive size limit exceeded')
    return sorted(records, key=lambda r: (r['entry']['source']['repository'],
                                          r['entry']['source'].get('slice', '')))


def slice_metadata(records, slice_sets):
    """Bind each slice-set record to the selected packages; set each record's catalog entry."""
    for record in records:
        record['catalog_entry'] = record['entry']
    require(isinstance(slice_sets, (list, tuple)), 'invalid slice-set selection')
    kept, seen = [], set()
    for item in slice_sets:
        require(isinstance(item, (list, tuple)) and len(item) == 2
                and isinstance(item[0], (str, os.PathLike)) and valid_hash(item[1]),
                'invalid slice-set selection')
        _, value = selected_input(item[0], item[1], MAX_INPUT)
        closed(value, ('schema', 'repository', 'accepted_head', 'tree', 'slices'), 'slice set')
        require(value['schema'] == SLICE_SET_SCHEMA, 'unsupported slice-set schema')
        repository = value['repository']
        source_identity(dict(repository=repository, head=value['accepted_head']))
        require(isinstance(value['tree'], str) and len(value['tree']) == len(value['accepted_head'])
                and re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', value['tree']) is not None,
                'invalid slice-set tree')
        require(repository.casefold() not in seen, 'duplicate slice set for repository')
        seen.add(repository.casefold())
        slices = value['slices']
        require(isinstance(slices, list) and 0 < len(slices) <= MAX_PACKAGES, 'invalid slice-set slices')
        listed = {}
        for part in slices:
            closed(part, ('name', 'package_sha256', 'built_head', 'input_digest',
                          'resolution_digest', 'build_state_sha256'), 'slice-set slice')
            name = slice_name(dict(slice=part['name']))
            require(name not in listed, 'duplicate slice-set slice')
            source_identity(dict(repository=repository, head=part['built_head']))
            require(all(valid_hash(part[k]) for k in ('package_sha256', 'input_digest',
                                                     'resolution_digest', 'build_state_sha256')),
                    'invalid slice-set digest')
            listed[name] = part
        selected = {r['entry']['source'].get('slice'): r for r in records
                    if r['entry']['source']['repository'] == repository}
        require(set(selected) == set(listed),
                'slice set contradicts selected slice packages')
        for name, record in selected.items():
            part = listed[name]
            require(part['package_sha256'] == record['package_sha256']
                    and part['built_head'] == record['entry']['source']['head'],
                    'slice set contradicts selected slice packages')
            record['catalog_entry'] = dict(record['entry'], slice=dict(
                name=name, built_head=part['built_head'], equivalent_head=value['accepted_head']))
        kept.append(dict(sha256=item[1], record=value))
    return sorted(kept, key=lambda k: k['record']['repository'])


def copy_archive(owned, directory, record):
    entry, sha, size = record['entry'], hashlib.sha256(), 0
    with owned.file(directory, entry['archive']) as target:
        with verified_archive(record['catalog_path'], entry) as source:
            while block := source.read(BLOCK):
                size += len(block)
                require(size <= entry['bytes'], 'archive grew while copying')
                sha.update(block)
                target.write(block)
    require(size == entry['bytes'] and sha.hexdigest() == entry['sha256'],
            'archive changed while copying')


def link_archive(owned, directory, record):
    """Hard-link one verified package archive; return None, or the reason it was not linked."""
    entry = record['entry']
    name = entry['archive']
    with directory_fd(record['path'].parent / 'archives') as source:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=source)
        with os.fdopen(fd, 'rb') as handle:
            info = os.fstat(fd)
            reason = link_refusal(info)
            if reason is None and info.st_dev != os.fstat(directory).st_dev:
                reason = 'cross_device'
            if reason is not None:
                return reason
            state = (info.st_size, info.st_mtime_ns)
            require(info.st_size == entry['bytes'], 'archive size mismatch')
            require(stream_sha(handle) == entry['sha256'], 'archive checksum mismatch')
            try:
                owned.link(directory, name, source, name, inode(info))
            except OSError as error:
                if error.errno in LINK_FALLBACK:
                    return LINK_FALLBACK[error.errno]
                raise
            # The shared inode must still hold the verified bytes once linked.
            handle.seek(0)
            after = os.fstat(fd)
            require((after.st_size, after.st_mtime_ns) == state
                    and stream_sha(handle) == entry['sha256'], 'archive changed while linking')
    return None


def stream_sha(handle):
    sha = hashlib.sha256()
    while block := handle.read(BLOCK):
        sha.update(block)
    return sha.hexdigest()


def verify_assembled(destination, catalog_sha, records):
    """Validate the completed catalog and every selected graph with unchanged readers."""
    catalog_path = destination / 'download-catalog.json'
    catalog, _ = load_catalog(catalog_path, catalog_sha)
    require(catalog['archives'] == [r['catalog_entry'] for r in records], 'assembled catalog mismatch')
    for record, entry in zip(records, catalog['archives']):
        _, _, graph_sha, _ = read_graph(catalog_path, entry)
        require(graph_sha == record['package']['graph_sha256'], 'assembled graph checksum mismatch')


def assemble(packages, destination, link_existing=False, slice_sets=()):
    """packages and slice_sets: sequences of (path, raw SHA256); destination must be new."""
    require(type(link_existing) is bool, 'invalid link mode')
    require(isinstance(destination, (str, os.PathLike)) and os.path.isabs(destination),
            'destination must be absolute')
    destination = Path(os.path.abspath(destination))
    require(destination.name not in ('', '.', '..'), 'invalid destination')
    require(not os.path.lexists(destination), 'destination exists')
    records = select(packages)
    slice_records = slice_metadata(records, slice_sets)
    entries = [r['catalog_entry'] for r in records]
    schema = CATALOG_SCHEMA_V2 if any('slice' in e['source'] for e in entries) else CATALOG_SCHEMA
    catalog = encoded(dict(schema=schema, status='complete', archive_directory='archives',
                           archives=entries, empty_repositories=[]))
    require(len(catalog) <= MAX_METADATA, 'assembled catalog too large')
    catalog_sha = digest(catalog)
    selected = [dict(source=r['package']['source'], package_sha256=r['package_sha256'],
                     source_catalog_sha256=r['package']['catalog_sha256'],
                     archive=r['entry']['archive'], archive_sha256=r['entry']['sha256'],
                     bytes=r['entry']['bytes'], graph_sha256=r['package']['graph_sha256'],
                     validation_sha256=r['package']['validation_sha256'],
                     input_sha256=r['package']['input_sha256'],
                     qualification=r['package']['qualification']) for r in records]
    summary = dict(
        schema=ASSEMBLY_SCHEMA, catalog_sha256=catalog_sha, packages=selected,
        freshness='unknown',
        limitations=['Assembly validates selected package consistency, not provenance truth',
                     'Per-repository graphs are not merged; freshness and cleanliness are unknown'])
    if slice_records:
        # Absent without --slice-set, so earlier assemblies keep their exact bytes.
        summary['slice_sets'] = slice_records
        summary['limitations'] = summary['limitations'] + [
            'Slice equivalent heads are producer digest claims checked only for consistency']
    assembly = encoded(summary)
    require(len(assembly) <= MAX_METADATA, 'assembly record too large')
    with directory_fd(destination.parent) as parent:
        owned = OwnedOutput(parent, destination.name)
        try:
            root = owned.create()
            archives = owned.mkdir(root, 'archives')
            transfers = []
            for record in records:
                reason = link_archive(owned, archives, record) if link_existing else None
                if not link_existing or reason is not None:
                    copy_archive(owned, archives, record)
                transfers.append(dict(archive=record['entry']['archive'],
                                      transfer='copied' if reason else 'linked', reason=reason))
            for name, data in (('download-catalog.json', catalog), ('assembly.json', assembly)):
                with owned.file(root, name) as handle:
                    handle.write(data)
            verify_assembled(destination, catalog_sha, records)
            selected_input(destination / 'assembly.json', digest(assembly), MAX_METADATA)
            owned.verify_ownership()
            require(inode(destination.stat(follow_symlinks=False)) == inode(owned.root),
                    'destination ownership changed')
            result = dict(schema=RESULT_SCHEMA, status='ok', destination=str(destination),
                          catalog_sha256=catalog_sha, assembly_sha256=digest(assembly),
                          repositories=sorted({e['source']['repository'] for e in entries}),
                          packages=[{k: v for k, v in item.items()
                                     if k not in ('input_sha256', 'qualification')}
                                    for item in selected],
                          validation='unchanged_reader_validators', freshness='unknown')
            if link_existing:
                result['archive_transfer'] = transfers
                result['link_limitations'] = [
                    'Linked archives share an inode with their package; nothing prevents a later write bit',
                    'Links save physical disk only; quota accounting counts every path']
            return result
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
    parser.add_argument('--package', nargs=2, action='append', required=True,
                        metavar=('PATH', 'SHA256'))
    parser.add_argument('--destination', required=True)
    parser.add_argument('--link-existing', action='store_true',
                        help='hard-link verified no-write-bit package archives on the same filesystem')
    parser.add_argument('--slice-set', nargs=2, action='append', default=[],
                        metavar=('PATH', 'SHA256'))
    args = parser.parse_args(argv)
    old = {}

    def cancel(signum, frame):
        raise KeyboardInterrupt('cancelled')

    for sig in CANCEL_SIGNALS:
        old[sig] = signal.signal(sig, cancel)
    try:
        result = assemble([tuple(item) for item in args.package], args.destination,
                          args.link_existing, [tuple(item) for item in args.slice_set])
        code = 0
    except ERRORS + (KeyboardInterrupt,) as exc:
        result = dict(schema=RESULT_SCHEMA, status='error',
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
