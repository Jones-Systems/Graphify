#!/usr/bin/env python3
"""Read one catalog-selected graph without extraction or persistent state."""
import argparse
from collections import deque
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tarfile

VERSION = '1.0'
CATALOG_SCHEMA = 'private-graph-download-catalog/v1'
MAX_ARCHIVE = 2 * 1024**3
MAX_MEMBER = 1024**3
MAX_TOTAL = 8 * 1024**3
MAX_METADATA = 16 * 1024**2

class StoreError(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise StoreError(message)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def valid_hash(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None

def identity(source):
    require(isinstance(source, dict), 'missing source identity')
    repo, head = source.get('repository'), source.get('head')
    require(isinstance(repo, str) and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo), 'invalid repository identity')
    require(isinstance(head, str) and re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', head), 'invalid source head')
    return repo, head

@contextmanager
def open_nofollow(path):
    path = Path(os.path.abspath(path))
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        file_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(file_fd, 'rb') as handle:
            require(stat.S_ISREG(os.fstat(handle.fileno()).st_mode), 'not a regular file')
            yield handle
    finally:
        os.close(fd)

def signature(handle):
    s = os.fstat(handle.fileno())
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)

def load_catalog(path, expected=None):
    with open_nofollow(path) as f:
        before = signature(f)
        raw = f.read(MAX_METADATA + 1)
        require(signature(f) == before, 'catalog changed during read')
    require(len(raw) <= MAX_METADATA, 'catalog too large')
    sha = digest(raw)
    require(expected is None or sha == expected, 'catalog checksum mismatch')
    c = json.loads(raw)
    require(isinstance(c, dict) and c.get('schema') == CATALOG_SCHEMA and c.get('status') == 'complete', 'unsupported or incomplete catalog')
    require(c.get('archive_directory') == 'archives', 'archive directory must be archives')
    require(isinstance(c.get('archives'), list), 'missing archive selections')
    names, repos = set(), set()
    for e in c['archives']:
        require(isinstance(e, dict), 'invalid archive selection')
        repo, _ = identity(e.get('source'))
        name = e.get('archive')
        require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_.-]+\.tar\.gz', name), 'invalid archive filename')
        require(repo not in repos and name not in names, 'duplicate catalog identity')
        require(valid_hash(e.get('sha256')), 'missing archive checksum')
        require(type(e.get('bytes')) is int and 0 < e['bytes'] <= MAX_ARCHIVE, 'invalid archive size')
        repos.add(repo); names.add(name)
    empty = c.get('empty_repositories', [])
    require(isinstance(empty, list), 'invalid empty repositories')
    for e in empty:
        require(isinstance(e, dict) and isinstance(e.get('repository'), str) and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', e['repository']), 'invalid empty identity')
        require(e['repository'] not in repos, 'duplicate repository identity')
        repos.add(e['repository'])
    return c, sha

@contextmanager
def verified_archive(catalog_path, entry):
    with open_nofollow(Path(catalog_path).parent / 'archives' / entry['archive']) as f:
        before = signature(f)
        require(before[2] == entry['bytes'], 'archive size mismatch')
        sha = hashlib.sha256()
        while block := f.read(1024**2):
            sha.update(block)
        require(sha.hexdigest() == entry['sha256'], 'archive checksum mismatch')
        require(signature(f) == before, 'archive changed during verification')
        f.seek(0)
        yield f
        require(signature(f) == before, 'archive changed during reading')

def read_graph(catalog_path, entry):
    wanted = {'archive-manifest.json', 'enriched/hashes.json', 'enriched/validation.json', 'enriched/graph.json'}
    content = {}; seen = set(); total = 0
    with verified_archive(catalog_path, entry) as f:
        with tarfile.open(fileobj=f, mode='r|gz') as archive:
            for m in archive:
                require(m.name not in seen, 'duplicate archive member')
                seen.add(m.name)
                require(len(seen) <= 100000 and 0 <= m.size <= MAX_MEMBER, 'archive member limit exceeded')
                require(m.isfile(), 'archive has nonregular member')
                require(not m.name.startswith('/') and '..' not in Path(m.name).parts, 'unsafe archive member')
                total += m.size
                require(total <= MAX_TOTAL, 'archive expanded size limit exceeded')
                if m.name in wanted:
                    require(m.name == 'enriched/graph.json' or m.size <= MAX_METADATA, 'metadata too large')
                    content[m.name] = archive.extractfile(m).read()
    require(wanted == content.keys(), 'missing required graph members')
    manifest = json.loads(content['archive-manifest.json'])
    require(isinstance(manifest, dict) and manifest.get('schema') == 'portable-graph-archive/v1', 'invalid archive manifest')
    require(identity(manifest.get('source')) == identity(entry['source']), 'archive source identity mismatch')
    hashes = json.loads(content['enriched/hashes.json'])
    require(isinstance(hashes, dict) and isinstance(manifest.get('files'), dict), 'invalid hash manifests')
    for name in wanted - {'archive-manifest.json'}:
        require(valid_hash(manifest['files'].get(name)) and digest(content[name]) == manifest['files'][name], 'member checksum mismatch')
        if name != 'enriched/hashes.json':
            require(valid_hash(hashes.get(name.removeprefix('enriched/'))) and digest(content[name]) == hashes[name.removeprefix('enriched/')], 'enriched checksum mismatch')
    graph = json.loads(content['enriched/graph.json'])
    require(isinstance(graph, dict) and graph.get('built_at_commit') == entry['source']['head'], 'graph source head mismatch')
    require(graph.get('directed') is True and isinstance(graph.get('nodes'), list) and isinstance(graph.get('links'), list), 'malformed directed graph')
    nodes = {}
    for n in graph['nodes']:
        require(isinstance(n, dict) and isinstance(n.get('id'), str) and n['id'] and n['id'] not in nodes, 'invalid or duplicate node id')
        nodes[n['id']] = n
    for edge in graph['links']:
        require(isinstance(edge, dict) and isinstance(edge.get('source'), str) and isinstance(edge.get('target'), str) and edge['source'] in nodes and edge['target'] in nodes, 'invalid graph endpoint')
    metadata = graph.get('graph', {})
    require(isinstance(metadata, dict), 'invalid graph metadata')
    for hyperedges in (graph.get('hyperedges', []), metadata.get('hyperedges', [])):
        require(isinstance(hyperedges, list), 'invalid hyperedge collection')
        for h in hyperedges:
            require(isinstance(h, dict) and isinstance(h.get('nodes'), list) and all(isinstance(n, str) and n in nodes for n in h['nodes']), 'invalid hyperedge endpoint')
    validation = json.loads(content['enriched/validation.json'])
    require(isinstance(validation, dict), 'malformed validation')
    coverage = {k: validation[k] for k in (
        'coverage_meaning', 'limitations', 'exclusions', 'unresolved_references',
        'source', 'status', 'semantic_coverage', 'structural_parser_errors',
        'structural_rejected_edges', 'structural_warnings_present', 'included_files',
        'accepted_batches', 'expected_batches', 'missing_batches',
        'runtime_qualification', 'model_execution_evidence',
    ) if k in validation}
    segments = validation.get('covered_segments_by_file')
    coverage['covered_files'] = len(segments) if isinstance(segments, dict) else None
    coverage['exclusions'] = validation.get('exclusions', 'not_reported')
    coverage['verification'] = 'archive, required member hashes, source identity, all graph endpoints'
    return graph, nodes, digest(content['enriched/graph.json']), coverage

def envelope():
    return dict(schema='graphify-reader-result/v1', reader_version=VERSION, status='ok', catalog_sha256=None, repository=None, source_head=None, archive_sha256=None, graph_sha256=None, validation_coverage=None, freshness={'status': 'unknown'}, results=[], truncation_reason=None, hints=['Confirm consequential claims in current canonical sources.'])

def serialize(result):
    return json.dumps(result, ensure_ascii=True, separators=(',', ':')).encode('utf-8')

def bounded_output(result, budget):
    while len(serialize(result)) + 1 > budget and result['results']:
        result['results'].pop()
        result['truncation_reason'] = 'byte_budget'
    if len(serialize(result)) + 1 > budget:
        result['validation_coverage'] = {'status': 'omitted_for_byte_budget'}
        result['hints'] = ['Metadata omitted to fit byte budget.']
        result['truncation_reason'] = 'byte_budget'
    if len(serialize(result)) + 1 > budget:
        for key in ('repository', 'source_head', 'freshness', 'error'):
            if key in result:
                result[key] = None
    return serialize(result).decode() + '\n'

def bounded_int(low, high):
    def parse(value):
        n = int(value)
        if not low <= n <= high:
            raise argparse.ArgumentTypeError(f'must be {low}..{high}')
        return n
    return parse

def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--catalog', required=True); p.add_argument('--catalog-sha256')
    p.add_argument('--repo'); p.add_argument('--source-head'); p.add_argument('--source-dirty', choices=('true','false','unknown'), default='unknown')
    p.add_argument('--limit', type=bounded_int(1,1000), default=50)
    p.add_argument('--max-bytes', type=bounded_int(2048,1024**2), default=32768)
    p.add_argument('--max-explored', type=bounded_int(1,100000), default=10000)
    commands = p.add_subparsers(dest='command', required=True)
    commands.add_parser('list')
    commands.add_parser('search').add_argument('--text', required=True)
    commands.add_parser('node').add_argument('--id', required=True)
    n=commands.add_parser('neighbors'); n.add_argument('--id', required=True); n.add_argument('--direction', choices=('in','out','both'), default='both'); n.add_argument('--depth',type=bounded_int(1,2),default=1)
    q=commands.add_parser('path'); q.add_argument('--from-id', required=True); q.add_argument('--to-id',required=True); q.add_argument('--max-hops',type=bounded_int(0,12),default=6)
    return p

def query(args):
    result = envelope()
    catalog, result['catalog_sha256'] = load_catalog(args.catalog, args.catalog_sha256)
    if args.command == 'list':
        result['results'] = [dict(repository=e['source']['repository'],source_head=e['source']['head'],archive_sha256=e['sha256'],status='selected') for e in catalog['archives']] + catalog.get('empty_repositories', [])
    else:
        require(args.repo is not None, '--repo required for graph query')
        matches = [e for e in catalog['archives'] if e['source']['repository'] == args.repo]
        require(len(matches) == 1, 'repository has no selected graph')
        e=matches[0]; result.update(repository=args.repo, source_head=e['source']['head'],archive_sha256=e['sha256'])
        graph, nodes, result['graph_sha256'], result['validation_coverage'] = read_graph(args.catalog,e)
        result['freshness'] = dict(status='unknown', caller_source_head=args.source_head, caller_dirty=args.source_dirty, comparison_basis='caller observation')
        if args.source_head:
            result['freshness']['status'] = 'head_mismatch' if args.source_head != result['source_head'] else ('head_matches_clean_reported' if args.source_dirty == 'false' else 'head_matches_dirty_reported' if args.source_dirty == 'true' else 'head_matches_cleanliness_unknown')
        if args.command == 'search':
            text=args.text.casefold()
            for n in nodes.values():
                if any(text in str(n.get(k,'')).casefold() for k in ('id','label','name','source_file','type')):
                    result['results'].append(n)
                    if len(result['results']) > args.limit:
                        break
        elif args.command == 'node':
            result['results'] = [nodes[args.id]] if args.id in nodes else []
            if not result['results']: result['status']='node_absent'
        else:
            start = args.id if args.command == 'neighbors' else args.from_id
            require(start in nodes, 'start node absent')
            if args.command == 'path': require(args.to_id in nodes, 'target node absent')
            adjacency={}
            direction = args.direction if args.command == 'neighbors' else 'out'
            for edge in graph['links']:
                if direction in ('out','both'): adjacency.setdefault(edge['source'],[]).append((edge['target'],edge))
                if direction in ('in','both'): adjacency.setdefault(edge['target'],[]).append((edge['source'],edge))
            depth = args.depth if args.command=='neighbors' else args.max_hops
            queue=deque([(start,0)]); visited={start}; predecessor={}; examined=0; found=start == getattr(args,'to_id',None); hit_hop=False
            while queue and not found:
                current,level=queue.popleft()
                if level == depth:
                    hit_hop = hit_hop or any(n not in visited for n,_ in adjacency.get(current,[])); continue
                for nxt, edge in adjacency.get(current,[]):
                    if examined >= args.max_explored:
                        result['truncation_reason']='exploration_limit'; queue.clear(); break
                    examined+=1
                    if args.command=='neighbors': result['results'].append(dict(node=nodes[nxt],edge=edge,depth=level+1))
                    if nxt not in visited:
                        visited.add(nxt); predecessor[nxt]=current; queue.append((nxt,level+1))
                    if args.command=='path' and nxt==args.to_id:
                        found=True; break
                if args.command=='neighbors' and len(result['results']) > args.limit: break
            if args.command=='path':
                if found:
                    ids=[args.to_id]
                    while ids[-1] != start: ids.append(predecessor[ids[-1]])
                    ids.reverse()
                    result['results']=[dict(nodes=[nodes[n] for n in ids],hops=[dict(source=a,target=b,relationships=[edge for n,edge in adjacency.get(a,[]) if n==b]) for a,b in zip(ids,ids[1:])])]
                else:
                    result['status']='exploration_exhausted' if result['truncation_reason'] else 'no_path_within_hop_limit' if hit_hop else 'no_path'
            result['explored_relationships']=examined
    if len(result['results']) > args.limit:
        result['results']=result['results'][:args.limit]; result['truncation_reason']=result['truncation_reason'] or 'record_limit'
    return result

def main(argv=None):
    args=parser().parse_args(argv)
    try:
        result=query(args); code=0
    except (ValueError, OSError, tarfile.TarError, KeyError, TypeError, RecursionError) as exc:
        result=envelope(); result.update(status='error', error=str(exc)[:500],hints=['Check the explicit catalog, selected identity, and verified archive.']); code=1
    sys.stdout.write(bounded_output(result,args.max_bytes))
    return code

if __name__ == '__main__':
    raise SystemExit(main())
