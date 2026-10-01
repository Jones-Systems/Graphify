from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
import signal
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tooling'))
from test_graph_read import store, REPO, query
import graph_pull as puller
import graph_read as reader
class GraphPullTests(unittest.TestCase):
    def test_portable_identity_and_create_only(self):
        with store() as (root,path,c):
            dest=root/'new';result=puller.pull(path,dest,[REPO]);before=query(path,'node','--id','a');after=query(dest/'download-catalog.json','node','--id','a')
            for key in ('repository','source_head','archive_sha256','graph_sha256','results'):self.assertEqual(before[key],after[key])
            self.assertEqual(result['upstream_catalog_sha256'],reader.digest(path.read_bytes()))
            with self.assertRaises(FileExistsError):puller.pull(path,dest,[REPO])
            self.assertTrue((dest/'download-catalog.json').exists())
    def test_corrupt_source_cleanup(self):
        with store() as (root,path,c):
            (root/'archives'/'repo.tar.gz').write_bytes(b'bad')
            with self.assertRaises(reader.StoreError):puller.pull(path,root/'failed',[REPO])
            self.assertFalse((root/'failed').exists());self.assertTrue(path.exists())
    def test_failure_cancel_cleanup(self):
        with store() as (root,path,c):
            for error in (OSError('failure'),KeyboardInterrupt('cancelled')):
                with patch.object(puller,'read_graph',side_effect=error):
                    with self.assertRaises(type(error)):puller.pull(path,root/'failed',[REPO])
                self.assertFalse((root/'failed').exists())
    def test_partial_copy_failure_cleans_destination(self):
        with store() as (root,path,c):
            original=puller.verified_archive
            @contextmanager
            def fail_copy(*args):
                with original(*args) as src:
                    class FailingStream:
                        reads=0
                        def read(self,size):
                            self.reads+=1
                            if self.reads>1:raise OSError('copy failure')
                            return src.read(size)
                    yield FailingStream()
            with patch.object(puller,'verified_archive',fail_copy):
                with self.assertRaisesRegex(OSError,'copy failure'):puller.pull(path,root/'partial',[REPO])
            self.assertFalse((root/'partial').exists())
    def test_cleanup_failure_preserves_original_error(self):
        with store() as (root,path,c):
            with patch.object(puller,'read_graph',side_effect=OSError('original failure')), patch.object(puller.shutil,'rmtree',side_effect=OSError('cleanup denied')):
                with self.assertRaisesRegex(ValueError,'original failure; cleanup failed: cleanup denied'):puller.pull(path,root/'failed',[REPO])
            self.assertTrue((root/'failed').exists())
    def test_handled_signal_cleanup(self):
        with store() as (root,path,c):
            def cancel(*args):signal.raise_signal(signal.SIGTERM)
            with patch.object(puller,'read_graph',side_effect=cancel):self.assertEqual(puller.main(['--catalog',str(path),'--destination',str(root/'cancelled'),'--repo',REPO]),1)
            self.assertFalse((root/'cancelled').exists())
    def test_signal_at_creation_boundary_cleanup(self):
        with store() as (root,path,c):
            destination=root/'boundary'; original=Path.mkdir
            def create_then_cancel(target,*args,**kwargs):
                result=original(target,*args,**kwargs)
                if target==destination:signal.raise_signal(signal.SIGTERM)
                return result
            with patch.object(Path,'mkdir',create_then_cancel):
                self.assertEqual(puller.main(['--catalog',str(path),'--destination',str(destination),'--repo',REPO]),1)
            self.assertFalse(destination.exists())
    def test_concurrent_distinct_destinations(self):
        with store() as (root,path,c):
            with ThreadPoolExecutor(max_workers=2) as pool:
                jobs=[pool.submit(puller.pull,path,root/name,[REPO]) for name in ('first','second')]
                self.assertEqual([j.result()['status'] for j in jobs],['ok','ok'])
            for name in ('first','second'):self.assertTrue((root/name/'download-catalog.json').exists())
    def test_unknown_selection_no_creation(self):
        with store() as (root,path,c):
            with self.assertRaises(reader.StoreError):puller.pull(path,root/'unknown',['Other/Repo'])
            self.assertFalse((root/'unknown').exists())
if __name__=='__main__':unittest.main()
