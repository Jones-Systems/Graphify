#!/usr/bin/env python3
"""Assemble explicitly selected graph packages into one new download catalog.

Each --package PATH SHA256 names one graphify-pack-package/v1 package.json by
its exact raw SHA256. The caller selects exactly one package per repository;
nothing is discovered from directories, corpora, or stores. Every package must
sit beside the download-catalog.json and archives/<sha>.tar.gz it declares.

Before any output is created, each package, its declared single-entry catalog,
archive bytes, archive manifest, provenance member digests, and graph are
validated with the unchanged graph_read validators. Repository identities
(compared exactly and case-insensitively) and archive names must not collide.

Output is create-only: download-catalog.json (private-graph-download-catalog/v1,
entries ordered by repository), archives/<sha>.tar.gz copied byte-exactly, and
assembly.json recording each selected package's identities, qualification, and
limitations. Graph nodes, source identities, freshness, and cleanliness are
neither merged nor upgraded; assembly attests consistency, not provenance.
Handled failure or cancellation removes only this invocation's tracked output.
Unprovable ownership or cleanup failure reports an unknown effect for explicit
reconciliation; there is no retry or recovery cleanup of existing paths.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import signal
import tarfile
import zlib

from graph_pack import (MAX_ARCHIVE, MAX_INPUT, NAMES, CANCEL_SIGNALS, OwnedOutput,
                        UnknownOutputError, closed, directory_fd, encoded, inode,
                        selected_input, source_identity, strict_json)
from graph_read import (CATALOG_SCHEMA, MAX_METADATA, digest, load_catalog, read_graph,
                        require, valid_hash, verified_archive)

PACKAGE_SCHEMA = 'graphify-pack-package/v1'
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
    require(declared == dict(schema=CATALOG_SCHEMA, status='complete', archive_directory='archives',
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
    repositories = [r['entry']['source']['repository'] for r in records]
    require(len({repo.casefold() for repo in repositories}) == len(records),
            'duplicate repository selection')
    require(len({r['entry']['archive'] for r in records}) == len(records),
            'colliding archive name')
    require(sum(r['entry']['bytes'] for r in records) <= MAX_TOTAL_ARCHIVE,
            'aggregate archive size limit exceeded')
    return sorted(records, key=lambda r: r['entry']['source']['repository'])


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


def verify_assembled(destination, catalog_sha, records):
    """Validate the completed catalog and every selected graph with unchanged readers."""
    catalog_path = destination / 'download-catalog.json'
    catalog, _ = load_catalog(catalog_path, catalog_sha)
    require(catalog['archives'] == [r['entry'] for r in records], 'assembled catalog mismatch')
    for record, entry in zip(records, catalog['archives']):
        _, _, graph_sha, _ = read_graph(catalog_path, entry)
        require(graph_sha == record['package']['graph_sha256'], 'assembled graph checksum mismatch')


def assemble(packages, destination):
    """packages: sequence of (package.json path, raw SHA256); destination must be new."""
    require(isinstance(destination, (str, os.PathLike)) and os.path.isabs(destination),
            'destination must be absolute')
    destination = Path(os.path.abspath(destination))
    require(destination.name not in ('', '.', '..'), 'invalid destination')
    require(not os.path.lexists(destination), 'destination exists')
    records = select(packages)
    entries = [r['entry'] for r in records]
    catalog = encoded(dict(schema=CATALOG_SCHEMA, status='complete', archive_directory='archives',
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
    assembly = encoded(dict(
        schema=ASSEMBLY_SCHEMA, catalog_sha256=catalog_sha, packages=selected,
        freshness='unknown',
        limitations=['Assembly validates selected package consistency, not provenance truth',
                     'Per-repository graphs are not merged; freshness and cleanliness are unknown']))
    require(len(assembly) <= MAX_METADATA, 'assembly record too large')
    with directory_fd(destination.parent) as parent:
        owned = OwnedOutput(parent, destination.name)
        try:
            root = owned.create()
            archives = owned.mkdir(root, 'archives')
            for record in records:
                copy_archive(owned, archives, record)
            for name, data in (('download-catalog.json', catalog), ('assembly.json', assembly)):
                with owned.file(root, name) as handle:
                    handle.write(data)
            verify_assembled(destination, catalog_sha, records)
            selected_input(destination / 'assembly.json', digest(assembly), MAX_METADATA)
            owned.verify_ownership()
            require(inode(destination.stat(follow_symlinks=False)) == inode(owned.root),
                    'destination ownership changed')
            return dict(schema=RESULT_SCHEMA, status='ok', destination=str(destination),
                        catalog_sha256=catalog_sha, assembly_sha256=digest(assembly),
                        repositories=[e['source']['repository'] for e in entries],
                        packages=[{k: v for k, v in item.items()
                                   if k not in ('input_sha256', 'qualification')}
                                  for item in selected],
                        validation='unchanged_reader_validators', freshness='unknown')
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
    args = parser.parse_args(argv)
    old = {}

    def cancel(signum, frame):
        raise KeyboardInterrupt('cancelled')

    for sig in CANCEL_SIGNALS:
        old[sig] = signal.signal(sig, cancel)
    try:
        result = assemble([tuple(item) for item in args.package], args.destination)
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
