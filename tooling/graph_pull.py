#!/usr/bin/env python3
"""Copy selected verified archives into a new portable store."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import tarfile

from graph_read import load_catalog, verified_archive, read_graph, require

def pull(catalog_path, destination, repos, expected=None):
    catalog, upstream=load_catalog(catalog_path,expected)
    require(bool(repos), 'at least one repository required')
    entries=[e for e in catalog['archives'] if e['source']['repository'] in set(repos)]
    require({e['source']['repository'] for e in entries} == set(repos), 'repository has no selected archive')
    destination=Path(os.path.abspath(destination))
    mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
    owned = None
    unmasked = False
    try:
        destination.mkdir(mode=0o700)
        owned=destination.lstat()
        signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        unmasked = True
        (destination/'archives').mkdir(mode=0o700)
        for entry in entries:
            read_graph(catalog_path,entry)
            with verified_archive(catalog_path,entry) as src:
                sha=hashlib.sha256()
                with (destination/'archives'/entry['archive']).open('xb') as dst:
                    while block := src.read(1024**2):
                        sha.update(block); dst.write(block)
                require(sha.hexdigest()==entry['sha256'], 'archive changed while copying')
        selected={k:v for k,v in catalog.items() if k not in ('archives','empty_repositories')}
        selected.update(archives=entries,empty_repositories=[],upstream_catalog_sha256=upstream)
        raw=(json.dumps(selected,indent=2)+'\n').encode()
        with (destination/'download-catalog.json').open('xb') as f: f.write(raw)
        return dict(schema='graphify-pull-result/v1',status='ok',catalog_sha256=hashlib.sha256(raw).hexdigest(),upstream_catalog_sha256=upstream,repositories=[e['source']['repository'] for e in entries])
    except BaseException as original:
        if owned is not None:
            cleanup_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
            try:
                current=destination.lstat()
                require((current.st_dev,current.st_ino)==(owned.st_dev,owned.st_ino), 'destination ownership changed; cleanup refused')
                shutil.rmtree(destination)
            except (ValueError, OSError) as cleanup_error:
                raise ValueError(f'{original}; cleanup failed: {cleanup_error}') from original
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, cleanup_mask)
        raise
    finally:
        if not unmasked:
            signal.pthread_sigmask(signal.SIG_SETMASK, mask)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--catalog',required=True);p.add_argument('--catalog-sha256');p.add_argument('--destination',required=True);p.add_argument('--repo',action='append',required=True)
    args=p.parse_args(argv)
    old={}
    def cancel(signum,frame): raise KeyboardInterrupt('cancelled')
    for sig in (signal.SIGTERM,signal.SIGINT): old[sig]=signal.signal(sig,cancel)
    try:
        result=pull(args.catalog,args.destination,args.repo,args.catalog_sha256);code=0
    except (ValueError,OSError,tarfile.TarError,KeyboardInterrupt,KeyError,TypeError) as exc:
        result=dict(schema='graphify-pull-result/v1',status='error',error=str(exc)[:500]);code=1
    finally:
        for sig,handler in old.items():signal.signal(sig,handler)
    print(json.dumps(result))
    return code

if __name__=='__main__':raise SystemExit(main())
