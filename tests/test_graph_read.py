from contextlib import contextmanager
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tooling'))
import graph_read as reader
HEAD='a'*40
REPO='Owner/Repo'
@contextmanager
def store(graph=None,mutate=None):
    with tempfile.TemporaryDirectory(prefix='graphify-fixture-') as directory:
        root=Path(directory);(root/'archives').mkdir()
        graph=graph or dict(built_at_commit=HEAD,directed=True,nodes=[dict(id='a',label='Ambiguous'),dict(id='b',label='Ambiguous'),dict(id='c')],links=[dict(source='a',target='b',key=0,relation='calls',provenance='ast'),dict(source='a',target='b',key=1,relation='documents',provenance='semantic'),dict(source='b',target='c',key=0)])
        content={'enriched/graph.json':json.dumps(graph).encode(),'enriched/validation.json':b'{"coverage_meaning":"Partial fixture","structural_parser_errors":1,"structural_warnings_present":true,"semantic_coverage":"complete_assigned_input_review","runtime_qualification":"not_assessed"}'}
        content['enriched/hashes.json']=json.dumps({n.split('/')[-1]:reader.digest(v) for n,v in content.items()}).encode()
        content['archive-manifest.json']=json.dumps(dict(schema='portable-graph-archive/v1',source=dict(repository=REPO,head=HEAD),files={n:reader.digest(v) for n,v in content.items()})).encode()
        if mutate:mutate(content)
        archive=root/'archives'/'repo.tar.gz'
        with tarfile.open(archive,'w:gz') as t:
            for name,data in content.items():
                m=tarfile.TarInfo(name);m.size=len(data);t.addfile(m,io.BytesIO(data))
        c=dict(schema=reader.CATALOG_SCHEMA,status='complete',archive_directory='archives',archives=[dict(source=dict(repository=REPO,head=HEAD),archive=archive.name,sha256=reader.digest(archive.read_bytes()),bytes=archive.stat().st_size)],empty_repositories=[dict(repository='Owner/Empty',status='empty_repository')])
        path=root/'download-catalog.json';path.write_text(json.dumps(c));yield root,path,c

def query(path,*args):return reader.query(reader.parser().parse_args(['--catalog',str(path),'--repo',REPO,*args]))

class GraphReadTests(unittest.TestCase):
    def test_list_and_no_writes(self):
        with store() as (root,path,c):
            before={p.relative_to(root):p.stat().st_mtime_ns for p in root.rglob('*')}
            self.assertEqual(len(query(path,'list')['results']),2);query(path,'node','--id','a')
            self.assertEqual(before,{p.relative_to(root):p.stat().st_mtime_ns for p in root.rglob('*')})
    def test_search_absent_and_freshness(self):
        with store() as (_,path,c):
            self.assertEqual(len(query(path,'search','--text','Ambiguous')['results']),2)
            self.assertEqual(query(path,'node','--id','missing')['status'],'node_absent')
            self.assertEqual(query(path,'node','--id','a')['freshness']['status'],'unknown')
            self.assertEqual(query(path,'--source-head',HEAD,'node','--id','a')['freshness']['status'],'head_matches_cleanliness_unknown')
            self.assertEqual(query(path,'--source-head',HEAD,'--source-dirty','true','node','--id','a')['freshness']['status'],'head_matches_dirty_reported')
            self.assertEqual(query(path,'--source-head','b'*40,'node','--id','a')['freshness']['status'],'head_mismatch')
    def test_search_scans_late_nodes_and_reports_coverage(self):
        with store() as (_,path,c):
            r=query(path,'--max-explored','1','search','--text','c')
            self.assertEqual([n['id'] for n in r['results']],['c'])
            self.assertIsNone(r['truncation_reason'])
            self.assertEqual(r['validation_coverage']['structural_parser_errors'],1)
            self.assertTrue(r['validation_coverage']['structural_warnings_present'])
            self.assertEqual(r['validation_coverage']['runtime_qualification'],'not_assessed')
            self.assertIsNone(r['validation_coverage']['covered_files'])
            self.assertEqual(r['validation_coverage']['exclusions'],'not_reported')
    def test_duplicate_and_nonregular_archive_members(self):
        with store() as (root,path,c):
            archive=root/'archives'/'repo.tar.gz'
            for duplicate in (True,False):
                with tarfile.open(archive,'w:gz') as t:
                    m=tarfile.TarInfo('enriched/graph.json');m.size=2;t.addfile(m,io.BytesIO(b'{}'))
                    m=tarfile.TarInfo('enriched/graph.json' if duplicate else 'linked')
                    if duplicate:
                        m.size=2;t.addfile(m,io.BytesIO(b'{}'))
                    else:
                        m.type=tarfile.SYMTYPE;m.linkname='enriched/graph.json';t.addfile(m)
                c['archives'][0].update(sha256=reader.digest(archive.read_bytes()),bytes=archive.stat().st_size);path.write_text(json.dumps(c))
                with self.assertRaises(reader.StoreError):query(path,'node','--id','a')
    def test_parallel_directed_reverse_and_path(self):
        with store() as (_,path,c):
            self.assertEqual([x['edge']['key'] for x in query(path,'neighbors','--id','b','--direction','in')['results']],[0,1])
            self.assertEqual(len(query(path,'path','--from-id','a','--to-id','c')['results'][0]['hops'][0]['relationships']),2)
            self.assertEqual(query(path,'path','--from-id','c','--to-id','a')['status'],'no_path')
    def test_limits(self):
        with store() as (_,path,c):
            self.assertEqual(query(path,'path','--from-id','a','--to-id','c','--max-hops','1')['status'],'no_path_within_hop_limit')
            self.assertEqual(query(path,'--max-explored','1','path','--from-id','a','--to-id','c')['status'],'exploration_exhausted')
            self.assertEqual(query(path,'--limit','1','neighbors','--id','a')['truncation_reason'],'record_limit')
    def test_budget_all_fields(self):
        r=reader.envelope();r.update(results=[dict(field='ü'*10000)],validation_coverage={'meaning':'x'*10000},hints=['x'*10000],repository='x'*10000)
        raw=reader.bounded_output(r,2048);self.assertLessEqual(len(raw.encode()),2048);self.assertEqual(json.loads(raw)['truncation_reason'],'byte_budget')
    def test_catalog_hash_identity_and_filename_rejection(self):
        with store() as (_,path,c):
            with self.assertRaises(reader.StoreError):reader.load_catalog(path,'0'*64)
            for key,value in [('archive','../repo.tar.gz'),('sha256',None)]:
                old=c['archives'][0][key];c['archives'][0][key]=value;path.write_text(json.dumps(c))
                with self.assertRaises(reader.StoreError):reader.load_catalog(path)
                c['archives'][0][key]=old
            c['archives'][0]['source']['head']='';path.write_text(json.dumps(c))
            with self.assertRaises(reader.StoreError):reader.load_catalog(path)
    def test_symlink_components_rejected(self):
        with store() as (root,path,c):
            link=root/'linked';link.symlink_to(root/'archives',target_is_directory=True)
            with self.assertRaises(OSError):
                with reader.open_nofollow(link/'repo.tar.gz'):pass
            archive=root/'archives'/'repo.tar.gz';archive.rename(root/'real.tar.gz');archive.symlink_to(root/'real.tar.gz')
            with self.assertRaises(OSError):query(path,'node','--id','a')
    def test_changed_descriptor_and_corruption(self):
        with store() as (root,path,c):
            with self.assertRaises(reader.StoreError):
                with reader.verified_archive(path,c['archives'][0]):
                    with (root/'archives'/'repo.tar.gz').open('ab') as f:f.write(b'x')
            with self.assertRaises(reader.StoreError):query(path,'node','--id','a')
    def test_missing_hash_member_and_wrong_manifest_identity(self):
        for mutate in (lambda x:x.pop('enriched/hashes.json'),lambda x:x.__setitem__('enriched/graph.json',b'{}'),lambda x:x.__setitem__('archive-manifest.json',json.dumps(dict(schema='portable-graph-archive/v1',source=dict(repository='Wrong/Repo',head=HEAD),files={})).encode())):
            with store(mutate=mutate) as (_,path,c):
                with self.assertRaises(reader.StoreError):query(path,'node','--id','a')
    def test_malformed_endpoints_duplicate_nodes_and_hyperedges(self):
        for graph in (dict(built_at_commit=HEAD,directed=True,nodes=[dict(id='a')],links=[dict(source='a',target='missing')]),dict(built_at_commit=HEAD,directed=True,nodes=[dict(id='a'),dict(id='a')],links=[]),dict(built_at_commit=HEAD,directed=True,nodes=[],links=[],hyperedges=[dict(nodes=['missing'])])):
            with store(graph=graph) as (_,path,c):
                with self.assertRaises(reader.StoreError):query(path,'node','--id','a')
if __name__=='__main__':unittest.main()
