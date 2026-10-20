from contextlib import contextmanager, redirect_stdout
import errno
import io
import itertools
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tooling'))
import graph_catalog as catalogs
import graph_freshness as freshness
import graph_pack as packer
import graph_pull as puller
import graph_read as reader

HEAD = 'a' * 40
ACCEPTED = 'b' * 40
TREE = 'd' * 40
# The last commit before slices; its reader is the installed consumer behavior.
LEGACY_READER_COMMIT = 'd63f45e31f06760f2a1b052a53b5113017b9f29c'
SLICED = [('Owner/R%02d' % n, part) for n in range(11) for part in ('core', 'rest')]
QUALIFICATION_V1 = {'source', 'provenance_status', 'freshness', 'missing_provenance',
                    'build_observation', 'inventory_coverage', 'records_without_source_file',
                    'coverage_meaning', 'limitations'}
COUNTER = itertools.count()


def file_id(name):
    return 'structural-v1:' + reader.digest(name.encode())


def reference(source_file='a.py', target='lib.b', line=3, target_path='lib/b.py',
              target_slice='lib', **changes):
    return dict(dict(source=file_id(source_file), source_file=source_file, type='imports',
                     target=target, line=line, target_path=target_path,
                     target_id=file_id(target_path), target_slice=target_slice), **changes)


@contextmanager
def workspace():
    # Synthetic packages only, under this checkout (or a caller-selected task root),
    # never /tmp: hard links need one filesystem. TemporaryDirectory removes its own
    # children, including read-only files, on every exit path.
    parent = os.environ.get('GRAPHIFY_PACK_TEST_ROOT', str(ROOT))
    with tempfile.TemporaryDirectory(prefix='slice-catalog-test-', dir=parent) as directory:
        yield Path(directory)


def build(root, repository, head=HEAD, part=None, label='node', references=None):
    """Create one real pack() output from synthetic inputs; return (package path, sha)."""
    source = dict(repository=repository, head=head)
    if part is not None:
        source['slice'] = part
    validation = dict(source=source, status='partial', limitations=['synthetic'],
                      covered_segments_by_file={'a.py': [[1, 2]]})
    if references is not None:
        validation['cross_slice_references'] = references
    documents = dict(
        graph=dict(built_at_commit=head, directed=True, source=source,
                   nodes=[dict(id='a', source_file='a.py', label=label), dict(id='b')],
                   links=[dict(source='a', target='b', relation='calls')]),
        validation=validation,
        inventory=dict(schema='graphify-pack-inventory/v1', source=source,
                       files=[dict(path='a.py', sha256='1' * 64, coverage='structural')],
                       limitations=['synthetic']),
        policy=dict(schema='graphify-pack-policy/v1', source=source, name='policy',
                    rules={}, limitations=[]),
        extractor=dict(schema='graphify-pack-extractor/v1', source=source, name='synthetic',
                       version=None, artifact_sha256=None, limitations=['no extraction']),
    )
    documents['source'] = dict(
        schema='graphify-pack-source/v1', source=source, build_observation=None,
        limitations=['caller supplied'],
        input_sha256={n: reader.digest(packer.encoded(v)) for n, v in documents.items()})
    directory = root / ('inputs-%03d' % next(COUNTER))
    directory.mkdir()
    inputs = {}
    for name, value in documents.items():
        raw = packer.encoded(value)
        (directory / (name + '.json')).write_bytes(raw)
        inputs[name] = (directory / (name + '.json'), reader.digest(raw))
    store = directory.with_name(directory.name.replace('inputs-', 'package-'))
    result = packer.pack(inputs, store)
    return store / 'package.json', result['package_sha256']


def archive_of(package_path):
    entry = json.loads(package_path.read_bytes())['archive']
    return package_path.parent / 'archives' / entry['archive']


def read_only(*selection):
    # The test owner, not the tool, removes write bits from its own fixture archives.
    for path, _ in selection:
        archive_of(path).chmod(0o444)


def inodes(*directories):
    found = set()
    for directory in directories:
        for path in directory.rglob('*.tar.gz'):
            info = path.lstat()
            if stat.S_ISREG(info.st_mode):
                found.add((info.st_dev, info.st_ino))
    return found


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob('*'))
            if p.is_file()}


def query(catalog, *args):
    return reader.query(reader.parser().parse_args(['--catalog', str(catalog), *args]))


def slice_set(root, repository, accepted, slices, tree=TREE):
    raw = packer.encoded(dict(schema='graphify-slice-set/v1', repository=repository,
                              accepted_head=accepted, tree=tree, slices=slices))
    path = root / ('slice-set-%03d.json' % next(COUNTER))
    path.write_bytes(raw)
    return path, reader.digest(raw)


def slice_record(name, selection, built_head, **changes):
    return dict(dict(name=name, package_sha256=selection[1], built_head=built_head,
                     input_digest='3' * 64, resolution_digest='4' * 64,
                     build_state_sha256='5' * 64), **changes)


def flip_last_byte(path):
    mode = stat.S_IMODE(path.stat().st_mode)
    path.chmod(0o600)
    with path.open('r+b') as handle:
        handle.seek(-1, os.SEEK_END)
        last = handle.read(1)
        handle.seek(-1, os.SEEK_END)
        handle.write(bytes([last[0] ^ 1]))
    path.chmod(mode)


class Edge3CrossSliceTests(unittest.TestCase):
    def test_edge3_valid_cross_slice_references_pack_and_read(self):
        references = [reference(), reference(target='lib.c', target_path='lib/c.py', line=9)]
        with workspace() as root:
            src = build(root, 'Owner/Mono', part='src', references=references)
            docs = build(root, 'Owner/Mono', part='docs')
            package = json.loads(src[0].read_bytes())
            self.assertEqual(package['qualification']['cross_slice_references'],
                             dict(count=2, target_verification='not_verified_in_package'))
            self.assertEqual(json.loads(docs[0].read_bytes())['qualification']
                             ['cross_slice_references']['count'], 0)
            result = catalogs.assemble([src, docs], root / 'catalog')
            path = root / 'catalog' / 'download-catalog.json'
            found = query(path, '--repo', 'Owner/Mono', '--slice', 'src', 'node', '--id', 'a')
            self.assertEqual(found['validation_coverage']['cross_slice_references'],
                             dict(count=2, references=references, truncated=False, followed=False))
            self.assertIn('not followed', found['hints'][-1])
            # Links stay closed within the slice.
            self.assertEqual(query(path, '--repo', 'Owner/Mono', '--slice', 'src', 'path',
                                   '--from-id', 'a', '--to-id', 'b')['status'], 'ok')
            other = query(path, '--repo', 'Owner/Mono', '--slice', 'docs', 'node', '--id', 'a')
            self.assertNotIn('cross_slice_references', other['validation_coverage'])
            with patch.object(reader, 'MAX_LISTED_REFERENCES', 1):
                listed = query(path, '--repo', 'Owner/Mono', '--slice', 'src', 'node', '--id', 'a')
            self.assertEqual(listed['validation_coverage']['cross_slice_references'],
                             dict(count=2, references=references[:1], truncated=True, followed=False))
            self.assertEqual(result['catalog_sha256'], reader.digest(path.read_bytes()))

    def test_edge3_invalid_cross_slice_references_refused(self):
        cases = [
            ('target-admitted', 'src', [reference(target_path='a.py')], 'target is admitted in this slice'),
            ('target-own-slice', 'src', [reference(target_slice='src')], 'target is this slice'),
            ('source-not-admitted', 'src', [reference(source_file='z.py')], 'source file not admitted'),
            ('unsafe-target', 'src', [reference(target_path='../x.py')], 'unsafe inventory path'),
            ('bad-id', 'src', [reference(target_id='file:lib/b.py')], 'reference id'),
            ('bad-source-id', 'src', [reference(source='structural-v1:' + 'A' * 64)], 'reference id'),
            ('bad-line', 'src', [reference(line=0)], 'reference line'),
            ('bool-line', 'src', [reference(line=True)], 'reference line'),
            ('bad-slice', 'src', [reference(target_slice='../lib')], 'slice identity'),
            ('extra-field', 'src', [reference(cross_slice=True)], 'cross-slice reference fields'),
            ('missing-field', 'src', [{k: v for k, v in reference().items() if k != 'line'}],
             'cross-slice reference fields'),
            ('unsorted', 'src', [reference(line=9), reference(line=3)], 'unsorted or duplicated'),
            ('duplicate', 'src', [reference(), reference()], 'unsorted or duplicated'),
            ('not-list', 'src', {}, 'invalid cross-slice references'),
            ('unsliced', None, [reference()], 'require a sliced source'),
        ]
        with workspace() as root:
            for name, part, references, message in cases:
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, message):
                    build(root, 'Owner/Mono', part=part, references=references)
            # Cross-slice records count toward the per-slice record bound (3 graph records).
            with patch.object(packer, 'MAX_SLICE_RECORDS', 4), \
                    self.assertRaisesRegex(ValueError, 'slice record limit exceeded'):
                build(root, 'Owner/Mono', part='src',
                      references=[reference(), reference(line=4)])
            with patch.object(packer, 'MAX_SLICE_RECORDS', 4):
                build(root, 'Owner/Mono', part='src', references=[reference()])
            # The slice bound never applies to an unsliced package.
            with patch.object(packer, 'MAX_SLICE_RECORDS', 1):
                build(root, 'Owner/Mono')

    def test_edge3_single_slice_catalog_byte_identical(self):
        with workspace() as root:
            selection = [build(root, 'Owner/Beta'), build(root, 'Owner/Alpha')]
            packages = [json.loads(path.read_bytes()) for path, _ in selection]
            for (path, _), package in zip(selection, packages):
                self.assertEqual(set(package['qualification']), QUALIFICATION_V1)
                self.assertEqual(set(package['source']), {'repository', 'head'})
                self.assertEqual(json.loads((path.parent / 'download-catalog.json').read_bytes())
                                 ['schema'], reader.CATALOG_SCHEMA)
            result = catalogs.assemble(selection, root / 'catalog')
            self.assertNotIn('archive_transfer', result)
            expected = packer.encoded(dict(
                schema=reader.CATALOG_SCHEMA, status='complete', archive_directory='archives',
                archives=sorted((p['archive'] for p in packages),
                                key=lambda e: e['source']['repository']),
                empty_repositories=[]))
            self.assertEqual((root / 'catalog' / 'download-catalog.json').read_bytes(), expected)
            assembly = json.loads((root / 'catalog' / 'assembly.json').read_bytes())
            self.assertEqual(set(assembly), {'schema', 'catalog_sha256', 'packages', 'freshness',
                                             'limitations'})
            listing = query(root / 'catalog' / 'download-catalog.json', 'list')['results']
            self.assertTrue(all('slice' not in item for item in listing))

    def test_edge3_multi_slice_catalog_current_reader_rejects_new_accepts(self):
        with workspace() as root:
            selection = [build(root, 'Owner/Mono', part=part, label=part)
                         for part in ('docs', 'src')] + [build(root, 'Owner/Legacy')]
            catalogs.assemble(selection, root / 'catalog')
            path = root / 'catalog' / 'download-catalog.json'
            catalog = json.loads(path.read_bytes())
            self.assertEqual(catalog['schema'], reader.CATALOG_SCHEMA_V2)
            repositories = [e['source']['repository'] for e in catalog['archives']]
            self.assertEqual(repositories, ['Owner/Legacy', 'Owner/Mono', 'Owner/Mono'])
            listing = query(path, 'list')['results']
            self.assertEqual([item.get('slice') for item in listing], [None, 'docs', 'src'])
            with self.assertRaisesRegex(ValueError, 'repository is sliced; select --slice from: docs,src'):
                query(path, '--repo', 'Owner/Mono', 'node', '--id', 'a')
            with self.assertRaisesRegex(ValueError, 'repository is not sliced'):
                query(path, '--repo', 'Owner/Legacy', '--slice', 'docs', 'node', '--id', 'a')
            found = query(path, '--repo', 'Owner/Mono', '--slice', 'src', 'node', '--id', 'a')
            self.assertEqual((found['slice'], found['built_head'], found['equivalent_head'],
                              found['results'][0]['label']), ('src', HEAD, None, 'src'))
            self.assertNotIn('slice', query(path, '--repo', 'Owner/Legacy', 'node', '--id', 'a'))
            pulled = puller.pull(path, root / 'pulled', ['Owner/Mono'])
            self.assertEqual(pulled['repositories'], ['Owner/Mono'])
            self.assertEqual(len(reader.load_catalog(root / 'pulled' / 'download-catalog.json')[0]
                                 ['archives']), 2)

    def test_edge3_legacy_reader_refuses_multi_slice_catalog(self):
        # Compatibility fact: the installed reader refuses the v2 catalog instead of
        # silently reading one slice as the whole repository. The reader is pinned by
        # commit; a shallow checkout without that commit skips only this check.
        shown = subprocess.run(['git', '-C', str(ROOT), 'show',
                                LEGACY_READER_COMMIT + ':tooling/graph_read.py'],
                               capture_output=True, check=False)
        if shown.returncode:
            self.skipTest('legacy reader commit %s unavailable in this checkout'
                          % LEGACY_READER_COMMIT)
        with workspace() as root:
            selection = [build(root, 'Owner/Mono', part=part) for part in ('docs', 'src')]
            selection.append(build(root, 'Owner/Legacy'))
            catalogs.assemble(selection, root / 'catalog')
            path = root / 'catalog' / 'download-catalog.json'
            legacy = types.ModuleType('legacy_graph_read')
            exec(compile(shown.stdout, 'legacy_graph_read.py', 'exec'), legacy.__dict__)
            with self.assertRaisesRegex(ValueError, 'unsupported or incomplete catalog'):
                legacy.load_catalog(path)
            unsliced = root / 'unsliced'
            catalogs.assemble(selection[2:], unsliced)
            self.assertEqual(legacy.load_catalog(unsliced / 'download-catalog.json'),
                             reader.load_catalog(unsliced / 'download-catalog.json'))

    def test_edge3_slice_identity_uniqueness_and_mixing_rejected(self):
        with workspace() as root:
            docs = build(root, 'Owner/Mono', part='docs')
            again = build(root, 'Owner/Mono', head=ACCEPTED, part='docs')
            case = build(root, 'owner/mono', part='DOCS')
            whole = build(root, 'Owner/Mono')
            for selection, message in (([docs, again], 'duplicate repository slice selection'),
                                       ([docs, case], 'duplicate repository slice selection'),
                                       ([docs, whole], 'mixes sliced and unsliced')):
                with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                    catalogs.assemble(selection, root / 'out')
            self.assertFalse((root / 'out').exists())
            entry = json.loads(docs[0].read_bytes())['archive']
            other = json.loads(whole[0].read_bytes())['archive']
            meta = dict(name='docs', built_head=HEAD)
            for schema, archives, message in (
                    (reader.CATALOG_SCHEMA, [entry], 'slice requires catalog v2'),
                    (reader.CATALOG_SCHEMA_V2, [entry, other], 'mixes sliced and unsliced'),
                    (reader.CATALOG_SCHEMA_V2, [entry, dict(entry, archive='x' + entry['archive'])],
                     'duplicate catalog identity'),
                    (reader.CATALOG_SCHEMA_V2, [dict(entry, source=dict(entry['source'], slice='../x'))],
                     'invalid slice identity'),
                    (reader.CATALOG_SCHEMA_V2, [dict(other, slice=meta)], 'invalid slice metadata'),
                    (reader.CATALOG_SCHEMA_V2, [dict(entry, slice=dict(meta, extra=1))],
                     'invalid slice metadata'),
                    (reader.CATALOG_SCHEMA_V2, [dict(entry, slice=dict(meta, name='src'))],
                     'contradicts source'),
                    (reader.CATALOG_SCHEMA_V2, [dict(entry, slice=dict(meta, built_head=ACCEPTED))],
                     'contradicts source'),
                    (reader.CATALOG_SCHEMA_V2, [dict(entry, slice=dict(meta, equivalent_head='main'))],
                     'invalid equivalent head')):
                with self.subTest(schema=schema, message=message):
                    path = root / 'manual.json'
                    path.write_text(json.dumps(dict(schema=schema, status='complete',
                                                    archive_directory='archives',
                                                    archives=archives, empty_repositories=[])))
                    with self.assertRaisesRegex(ValueError, message):
                        reader.load_catalog(path)
            # The package cap is retained: excess selections are refused, never raised.
            with patch.object(catalogs, 'MAX_PACKAGES', 1), \
                    self.assertRaisesRegex(ValueError, 'select 1..1 packages'):
                catalogs.assemble([docs, build(root, 'Owner/Mono', part='src')], root / 'out')
            self.assertEqual(catalogs.MAX_PACKAGES, 128)
            for bad in ('', '-x', 'a/b', 'x' * 101, 1):
                with self.subTest(slice=bad), self.assertRaises(ValueError):
                    packer.source_identity(dict(repository='Owner/Mono', head=HEAD, slice=bad))


class SliceSetEquivalenceTests(unittest.TestCase):
    def test_slice_set_equivalent_head_shown_only_with_record(self):
        with workspace() as root:
            docs = build(root, 'Owner/Mono', part='docs')
            src = build(root, 'Owner/Mono', head=ACCEPTED, part='src')
            legacy = build(root, 'Owner/Legacy')
            record = slice_set(root, 'Owner/Mono', ACCEPTED,
                               [slice_record('docs', docs, HEAD), slice_record('src', src, ACCEPTED)])
            result = catalogs.assemble([docs, src, legacy], root / 'catalog', slice_sets=[record])
            path = root / 'catalog' / 'download-catalog.json'
            catalog, _ = reader.load_catalog(path, result['catalog_sha256'])
            self.assertEqual([e.get('slice') for e in catalog['archives']], [
                None, dict(name='docs', built_head=HEAD, equivalent_head=ACCEPTED),
                dict(name='src', built_head=ACCEPTED, equivalent_head=ACCEPTED)])
            assembly = json.loads((root / 'catalog' / 'assembly.json').read_bytes())
            self.assertEqual(assembly['slice_sets'], [dict(sha256=record[1], record=json.loads(
                record[0].read_bytes()))])
            common = ('--repo', 'Owner/Mono', '--slice', 'docs')
            found = query(path, *common, '--source-head', ACCEPTED, 'node', '--id', 'a')
            self.assertEqual((found['built_head'], found['equivalent_head']), (HEAD, ACCEPTED))
            self.assertEqual(found['freshness']['status'], 'equivalent_head_matches_cleanliness_unknown')
            self.assertEqual(found['freshness']['equivalence_basis'], 'producer_slice_set_digest_claim')
            self.assertEqual(query(path, *common, '--source-head', HEAD, '--source-dirty', 'false',
                                   'node', '--id', 'a')['freshness']['status'],
                             'head_matches_clean_reported')
            self.assertEqual(query(path, *common, '--source-head', 'c' * 40, 'node', '--id', 'a')
                             ['freshness']['status'], 'head_mismatch')
            pulled = puller.pull(path, root / 'pulled', ['Owner/Mono'], result['catalog_sha256'])
            local = root / 'pulled' / 'download-catalog.json'
            self.assertEqual(query(local, *common, 'node', '--id', 'a')['equivalent_head'], ACCEPTED)
            self.assertEqual(pulled['upstream_catalog_sha256'], result['catalog_sha256'])
            # Without the record, no equivalence is shown or used.
            catalogs.assemble([docs, src], root / 'plain')
            plain = root / 'plain' / 'download-catalog.json'
            self.assertNotIn('slice', reader.load_catalog(plain)[0]['archives'][0])
            unproved = query(plain, *common, '--source-head', ACCEPTED, 'node', '--id', 'a')
            self.assertEqual((unproved['equivalent_head'], unproved['freshness']['status']),
                             (None, 'head_mismatch'))
            self.assertNotIn('slice_sets', json.loads((root / 'plain' / 'assembly.json').read_bytes()))

    def test_slice_set_contradictions_refused(self):
        with workspace() as root:
            docs = build(root, 'Owner/Mono', part='docs')
            src = build(root, 'Owner/Mono', part='src')
            legacy = build(root, 'Owner/Legacy')
            good = [slice_record('docs', docs, HEAD), slice_record('src', src, HEAD)]
            cases = [
                ('wrong-package', [good[0], slice_record('src', docs, HEAD)], 'contradicts selected'),
                ('missing-slice', good[:1], 'contradicts selected'),
                ('extra-slice', good + [slice_record('more', src, HEAD)], 'contradicts selected'),
                ('wrong-built-head', [good[0], slice_record('src', src, ACCEPTED)], 'contradicts selected'),
                ('duplicate-slice', good + good[:1], 'duplicate slice-set slice'),
                ('bad-digest', [good[0], slice_record('src', src, HEAD, input_digest='x')],
                 'invalid slice-set digest'),
                ('bad-build-state', [good[0], slice_record('src', src, HEAD,
                                                           build_state_sha256='F' * 64)],
                 'invalid slice-set digest'),
                ('missing-build-state', [good[0], {k: v for k, v in good[1].items()
                                                   if k != 'build_state_sha256'}],
                 'slice-set slice fields'),
                ('extra-field', [dict(good[0], proved=True), good[1]], 'slice-set slice fields'),
                ('empty', [], 'invalid slice-set slices'),
            ]
            for name, slices, message in cases:
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, message):
                    catalogs.assemble([docs, src], root / 'out',
                                      slice_sets=[slice_set(root, 'Owner/Mono', ACCEPTED, slices)])
            record = slice_set(root, 'Owner/Mono', ACCEPTED, good)
            for name, selection, sets, message in (
                    ('unsliced-repository', [docs, src, legacy],
                     [record, slice_set(root, 'Owner/Legacy', ACCEPTED, [slice_record('x', legacy, HEAD)])],
                     'contradicts selected'),
                    ('absent-repository', [legacy], [record], 'contradicts selected'),
                    ('duplicate-record', [docs, src], [record, slice_set(root, 'owner/mono', ACCEPTED, good)],
                     'duplicate slice set'),
                    ('checksum', [docs, src], [(record[0], '0' * 64)], 'checksum mismatch'),
                    ('bad-head', [docs, src], [slice_set(root, 'Owner/Mono', 'main', good)],
                     'invalid source head'),
                    ('bad-tree', [docs, src], [slice_set(root, 'Owner/Mono', ACCEPTED, good,
                                                         tree='main')], 'invalid slice-set tree'),
                    ('tree-length', [docs, src], [slice_set(root, 'Owner/Mono', ACCEPTED, good,
                                                            tree='d' * 64)], 'invalid slice-set tree'),
                    ('tree-type', [docs, src], [slice_set(root, 'Owner/Mono', ACCEPTED, good,
                                                          tree=None)], 'invalid slice-set tree')):
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, message):
                    catalogs.assemble(selection, root / 'out', slice_sets=sets)
            raw = packer.encoded(dict(schema='graphify-slice-set/v2', repository='Owner/Mono',
                                      accepted_head=ACCEPTED, tree=TREE, slices=good))
            (root / 'no-tree.json').write_bytes(packer.encoded(dict(
                schema='graphify-slice-set/v1', repository='Owner/Mono', accepted_head=ACCEPTED,
                slices=good)))
            with self.assertRaisesRegex(ValueError, 'invalid slice set fields'):
                catalogs.assemble([docs, src], root / 'out', slice_sets=[(
                    root / 'no-tree.json', reader.digest((root / 'no-tree.json').read_bytes()))])
            (root / 'v2.json').write_bytes(raw)
            with self.assertRaisesRegex(ValueError, 'unsupported slice-set schema'):
                catalogs.assemble([docs, src], root / 'out',
                                  slice_sets=[(root / 'v2.json', reader.digest(raw))])
            self.assertFalse((root / 'out').exists())


class FreshnessSliceTests(unittest.TestCase):
    def test_freshness_refuses_sliced_repository(self):
        with workspace() as root:
            selection = [build(root, 'Owner/Mono', part=part) for part in ('docs', 'src')]
            selection.append(build(root, 'Owner/Legacy'))
            result = catalogs.assemble(selection, root / 'catalog')
            path = root / 'catalog' / 'download-catalog.json'
            sample = dict(root=str(root), head=HEAD, head_after=HEAD, cleanliness='clean',
                          status_sha256='0' * 64, stable=True)
            with patch.object(freshness, '_observe_source', return_value=sample):
                sliced = freshness.observe(path, result['catalog_sha256'], 'Owner/Mono', root)
                whole = freshness.observe(path, result['catalog_sha256'], 'Owner/Legacy', root)
            self.assertEqual((sliced['status'], sliced['comparison']['outcome']),
                             ('error', 'validation_error'))
            self.assertIn('repository is sliced', sliced['error']['message'])
            self.assertIsNone(sliced['snapshot_head'])
            self.assertFalse(sliced['comparison']['qualified'])
            self.assertEqual((whole['status'], whole['snapshot_head']), ('qualified', HEAD))


class ProducerLinkTests(unittest.TestCase):
    def test_link_existing_is_off_by_default_and_copies_writable_archives(self):
        with workspace() as root:
            selection = [build(root, 'Owner/Mono', part=part) for part in ('docs', 'src')]
            plain = catalogs.assemble(selection, root / 'plain')
            self.assertNotIn('archive_transfer', plain)
            self.assertEqual(inodes(root / 'plain') & inodes(*(p.parent for p, _ in selection)), set())
            linked = catalogs.assemble(selection, root / 'requested', link_existing=True)
            self.assertEqual({(t['transfer'], t['reason']) for t in linked['archive_transfer']},
                             {('copied', 'write_bits_present')})
            for path, _ in selection:
                self.assertEqual(stat.S_IMODE(archive_of(path).stat().st_mode), 0o600)
                self.assertEqual(archive_of(path).stat().st_nlink, 1)
            self.assertEqual(snapshot(root / 'requested'), snapshot(root / 'plain'))
            with self.assertRaisesRegex(ValueError, 'invalid link mode'):
                catalogs.assemble(selection, root / 'bad', link_existing='yes')
            # Consumer store links are deferred: graph_pull has no reuse option.
            with redirect_stdout(io.StringIO()), patch('sys.stderr', io.StringIO()), \
                    self.assertRaises(SystemExit):
                puller.main(['--catalog', str(root / 'plain' / 'download-catalog.json'),
                             '--destination', str(root / 'store'), '--repo', 'Owner/Mono',
                             '--reuse-store', str(root / 'plain')])
            self.assertFalse((root / 'store').exists())

    def test_second_catalog_adds_only_changed_archive_inodes(self):
        with workspace() as root:
            first = {key: build(root, key[0], part=key[1]) for key in SLICED}
            read_only(*first.values())
            catalog_a = catalogs.assemble(list(first.values()), root / 'catalog-a', link_existing=True)
            self.assertEqual([t['transfer'] for t in catalog_a['archive_transfer']], ['linked'] * 22)
            self.assertEqual(inodes(root / 'catalog-a'),
                             inodes(*(path.parent for path, _ in first.values())))
            changed = [('Owner/R00', 'core'), ('Owner/R07', 'rest')]
            before = inodes(root)
            second = dict(first)
            for repo, part in changed:
                second[(repo, part)] = build(root, repo, head=ACCEPTED, part=part, label='changed')
                read_only(second[(repo, part)])
            catalog_b = catalogs.assemble(list(second.values()), root / 'catalog-b', link_existing=True)
            self.assertEqual(len(inodes(root) - before), 2)
            self.assertEqual(inodes(root / 'catalog-b') - inodes(*(p.parent for p, _ in second.values())),
                             set())
            for repo, part in changed:
                self.assertEqual(archive_of(first[(repo, part)][0]).stat().st_nlink, 2)
                self.assertEqual(archive_of(second[(repo, part)][0]).stat().st_nlink, 2)
            self.assertEqual(archive_of(first[('Owner/R05', 'core')][0]).stat().st_nlink, 3)
            copied = catalogs.assemble(list(second.values()), root / 'catalog-b-copy')
            self.assertEqual(copied['catalog_sha256'], catalog_b['catalog_sha256'])
            self.assertEqual(snapshot(root / 'catalog-b-copy'), snapshot(root / 'catalog-b'))
            # Consumer pull keeps its legacy copy behavior.
            repos = sorted({repo for repo, _ in SLICED})
            store = puller.pull(root / 'catalog-b' / 'download-catalog.json', root / 'store',
                                repos, catalog_b['catalog_sha256'])
            self.assertNotIn('archive_transfer', store)
            self.assertEqual(inodes(root / 'store') & inodes(root / 'catalog-b'), set())
            local = root / 'store' / 'download-catalog.json'
            for repo, part in SLICED:
                self.assertEqual(query(local, '--repo', repo, '--slice', part, 'node', '--id', 'a')
                                 ['results'][0]['label'], 'changed' if (repo, part) in changed else 'node')

    def test_tampered_swapped_or_changed_link_source_refused(self):
        with workspace() as root:
            selection = [build(root, 'Owner/Mono', part=part) for part in ('docs', 'src')]
            read_only(*selection)
            archive = archive_of(selection[0][0])
            real_link = os.link

            def swap_then_link(source, destination, **kwargs):
                folder = kwargs['src_dir_fd']
                os.rename(source, source + '.moved', src_dir_fd=folder, dst_dir_fd=folder)
                os.close(os.open(source, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400, dir_fd=folder))
                real_link(source, destination, **kwargs)

            with patch.object(packer.os, 'link', swap_then_link), \
                    self.assertRaisesRegex(ValueError, 'linked archive identity changed'):
                catalogs.assemble(selection, root / 'out', link_existing=True)
            self.assertFalse((root / 'out').exists())
            archive.unlink()
            archive.with_name(archive.name + '.moved').rename(archive)

            def link_then_change(source, destination, **kwargs):
                real_link(source, destination, **kwargs)
                folder = kwargs['dst_dir_fd']
                os.chmod(destination, 0o600, dir_fd=folder)
                fd = os.open(destination, os.O_WRONLY | os.O_APPEND, dir_fd=folder)
                os.write(fd, b'x')
                os.close(fd)

            with patch.object(packer.os, 'link', link_then_change), \
                    self.assertRaisesRegex(ValueError, 'changed while linking'):
                catalogs.assemble(selection, root / 'out', link_existing=True)
            self.assertFalse((root / 'out').exists())
            # The appended source now fails verification before any output.
            with self.assertRaisesRegex(ValueError, 'archive (size|checksum) mismatch'):
                catalogs.assemble(selection, root / 'out', link_existing=True)
            self.assertFalse((root / 'out').exists())

    def test_tamper_cleanup_and_cross_device_fallback(self):
        with workspace() as root:
            selection = [build(root, 'Owner/Mono', part=part) for part in ('docs', 'src')]
            read_only(*selection)
            archive = archive_of(selection[0][0])
            for error in (OSError('verification failed'), KeyboardInterrupt('cancelled')):
                with patch.object(catalogs, 'verify_assembled', side_effect=error), \
                        self.assertRaises(type(error)):
                    catalogs.assemble(selection, root / 'out', link_existing=True)
                self.assertFalse((root / 'out').exists())
                self.assertEqual(archive.stat().st_nlink, 1)
            with patch.object(packer.os, 'link', side_effect=OSError(errno.EXDEV, 'cross-device')):
                fallback = catalogs.assemble(selection, root / 'fallback', link_existing=True)
            self.assertEqual({(t['transfer'], t['reason']) for t in fallback['archive_transfer']},
                             {('copied', 'cross_device')})
            self.assertEqual(archive.stat().st_nlink, 1)
            flip_last_byte(archive)
            with self.assertRaisesRegex(ValueError, 'archive checksum mismatch'):
                catalogs.assemble(selection, root / 'out', link_existing=True)
            self.assertFalse((root / 'out').exists())

    def test_cli_link_existing_and_slice_set(self):
        with workspace() as root:
            selection = [build(root, 'Owner/Mono', part=part) for part in ('docs', 'src')]
            read_only(*selection)
            record = slice_set(root, 'Owner/Mono', ACCEPTED,
                               [slice_record('docs', selection[0], HEAD),
                                slice_record('src', selection[1], HEAD)])
            args = ['--destination', str(root / 'catalog'), '--link-existing',
                    '--slice-set', str(record[0]), record[1]]
            for path, sha in selection:
                args.extend(['--package', str(path), sha])
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(catalogs.main(args), 0)
            result = json.loads(output.getvalue())
            self.assertEqual({t['transfer'] for t in result['archive_transfer']}, {'linked'})
            self.assertEqual(result['repositories'], ['Owner/Mono'])
            catalog, _ = reader.load_catalog(root / 'catalog' / 'download-catalog.json',
                                             result['catalog_sha256'])
            self.assertEqual({e['slice']['equivalent_head'] for e in catalog['archives']}, {ACCEPTED})
            bad = ['--destination', str(root / 'bad'), '--slice-set', str(record[0]), '0' * 64]
            for path, sha in selection:
                bad.extend(['--package', str(path), sha])
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(catalogs.main(bad), 1)
            self.assertEqual(json.loads(output.getvalue())['effect'], 'not_completed')
            self.assertFalse((root / 'bad').exists())


if __name__ == '__main__':
    unittest.main()
