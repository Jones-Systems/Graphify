#!/usr/bin/env python3
"""Structural-only python-json/v1 and v2 adapter; stdin request, stdout response.

Reads only explicit staged inputs. No execution/import of source, file writes,
subprocesses, environment lookup or network. This family is not legacy parity.
Both protocols extract file-local fragments and assemble them over the whole
admitted set; v2 also accepts verified reusable fragments and returns new ones.
A v2 request whose extractor version is '2' selects family version 2: lexical
extractors from the SHA256-pinned sibling structural_languages.py, a
forbidden-marker check, closed record/output limits and optional slicing with a
staged repository path index. Family version 1 never loads that module.
"""
import ast
from contextlib import contextmanager
import fnmatch
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import stat
import sys

NAME = 'graphify-stdlib-structural'
VERSION = '1'
MAX_REQUEST = 512 * 1024
MAX_RECORDS = 20000
MAX_AST_NODES = 100000
LIMITS = dict(file_bytes=4 * 1024**2, input_bytes=16 * 1024**2,
              output_bytes=8 * 1024**2, seconds=300)
REQUEST_V1, REQUEST_V2 = 'graphify-refresh-request/v1', 'graphify-refresh-request/v2'
FRAGMENT = 'graphify-structural-fragment/v1'
GIT_LIMITATION = 'Git-object input; checkout cleanliness not observed.'

VERSION_V2 = '2'
FRAGMENT_V2 = 'graphify-structural-fragment/v2'
PATH_INDEX = 'graphify-path-index/v1'
# Family 2 bounds: one slice (D5) of at most 2048 files and 100000 assembled records.
MAX_REQUEST_V2 = 2 * 1024**2
MAX_ITEMS_V2 = 32768
MAX_FILES_V2 = 2048
MAX_RECORDS_V2 = 100000
MAX_INDEX_PATHS = 32768
MAX_INDEX_BYTES = 8 * 1024**2
MAX_CANDIDATES = 32
FRAGMENT_BYTES = 8 * 1024**2
LIMITS_V2 = dict(file_bytes=4 * 1024**2, input_bytes=112 * 1024**2,
                 output_bytes=64 * 1024**2, seconds=300)
LANGUAGES_MODULE = 'structural_languages.py'
LANGUAGES_SHA256 = '5f541b26d749777acab9590ba2102b788cb81ac434492f5a4c670a0112d6fd6f'
MAX_LANGUAGES = 1024**2
NODE_TYPES_V2 = frozenset(('class', 'function', 'method', 'interface', 'type', 'enum', 'variable',
                           'namespace', 'export', 'struct', 'protocol', 'actor', 'extension',
                           'package', 'heading', 'dependency', 'go_module', 'action'))
EDGE_TYPES_V2 = frozenset(('contains', 'exports', 'depends_on', 'uses'))
REFERENCE_KINDS_V2 = frozenset(('imports', 'links_to', 'sources', 'uses'))
RESOLUTIONS_V2 = frozenset(('unique', 'first'))
SLICE_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}')
LANGUAGES = None


class Limit(ValueError):
    """A per-file bound; v1 fails the request, v2 records the file as unknown."""


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode() + b'\n'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def closed(value, keys):
    require(isinstance(value, dict) and set(value) == set(keys), 'invalid fields')


def text(value):
    require(isinstance(value, str) and 0 < len(value) <= 4096
            and not any(ord(c) < 32 for c in value), 'invalid text')
    return value


def checksum(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'invalid hash')


def path(value, absolute=False):
    text(value)
    p = PurePosixPath(value)
    require(p.is_absolute() == absolute and str(p) == value and value not in ('.', '/')
            and '..' not in p.parts and '.git' not in p.parts and '\\' not in value,
            'unsafe path')
    return p


def strict_json(raw, max_items=10000):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate key')
            result[key] = value
        return result
    def invalid(_):
        raise ValueError('nonfinite number')
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    pending, count = [(value, 0)], 0
    while pending:
        item, depth = pending.pop()
        count += 1
        require(count <= max_items and depth <= 24, 'request complexity limit')
        if isinstance(item, dict):
            pending.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            pending.extend((v, depth + 1) for v in item)
        elif isinstance(item, float):
            require(float('-inf') < item < float('inf'), 'nonfinite number')
    return value


def overlaps(p, taken):
    return p in taken or any(p.startswith(q + '/') or q.startswith(p + '/') for q in taken)


def validate_common(request, keys, schema, bounds=LIMITS, max_files=256):
    closed(request, keys)
    require(request['schema'] == schema, 'unsupported request')
    checksum(request['manifest_sha256'])
    source = request['source']
    closed(source, ('repository', 'head'))
    text(source['repository'])
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}',
                         source['repository']) and not any(
        p.endswith('.git') for p in source['repository'].split('/')), 'invalid repository')
    require(isinstance(source['head'], str) and re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}',
                                                           source['head']), 'invalid head')
    path(request['stage'], absolute=True)
    limits = request['limits']
    closed(limits, bounds)
    for key, maximum in bounds.items():
        require(type(limits[key]) is int and 1 <= limits[key] <= maximum, 'invalid limit')
    files = request['files']
    require(isinstance(files, list) and 1 <= len(files) <= max_files, 'invalid files')
    return source, files


def validate_extractor(extractor, protocol, version=VERSION):
    closed(extractor, ('protocol', 'name', 'version', 'executable', 'script'))
    require(extractor['protocol'] == protocol and extractor['name'] == NAME
            and extractor['version'] == version, 'wrong extractor family')
    for key in ('executable', 'script'):
        closed(extractor[key], ('path', 'sha256'))
        path(extractor[key]['path'], absolute=True)
        checksum(extractor[key]['sha256'])


def validate(request):
    source, files = validate_common(
        request, ('schema', 'manifest_sha256', 'source', 'stage', 'files',
                  'policy', 'extractor', 'samples', 'limits'), REQUEST_V1)
    admitted = set()
    for entry in files:
        closed(entry, ('path', 'sha256'))
        p = str(path(entry['path']))
        checksum(entry['sha256'])
        require(not overlaps(p, admitted), 'overlapping admission')
        admitted.add(p)
    policy = request['policy']
    closed(policy, ('schema', 'source', 'name', 'rules', 'limitations'))
    require(policy['schema'] == 'graphify-pack-policy/v1' and policy['source'] == source
            and policy['name'] == 'refresh-explicit-selection' and policy['limitations'] == [],
            'invalid policy identity')
    rules = policy['rules']
    closed(rules, ('allow', 'deny', 'no_follow', 'git_metadata_denied'))
    require(rules['allow'] == files and rules['no_follow'] is True
            and rules['git_metadata_denied'] is True, 'invalid admission policy')
    require(isinstance(rules['deny'], list) and len(rules['deny']) <= 128, 'invalid denies')
    for pattern in rules['deny']:
        text(pattern)
        require(not any(fnmatch.fnmatchcase(p, pattern) for p in admitted), 'denied file')
    validate_extractor(request['extractor'], 'python-json/v1')
    samples = request['samples']
    closed(samples, ('before', 'after_capture'))
    require(samples['before'] == samples['after_capture'], 'unstable samples')
    sample = samples['before']
    closed(sample, ('root', 'head', 'head_after', 'cleanliness', 'status_sha256', 'stable'))
    path(sample['root'], absolute=True)
    require(sample['head'] == sample['head_after'] == source['head']
            and sample['cleanliness'] == 'clean' and sample['stable'] is True
            and sample['status_sha256'] == digest(b''), 'unqualified samples')
    return admitted


def patterns(value):
    require(isinstance(value, list) and len(value) <= 128, 'invalid patterns')
    for pattern in value:
        text(pattern)
    return value


def validate_v2(request):
    source, files = validate_common(
        request, ('schema', 'manifest_sha256', 'source', 'input_basis', 'stage', 'files',
                  'policy', 'extractor', 'limits'), REQUEST_V2)
    require(request['input_basis'] == 'git_blob', 'unsupported input basis')
    admitted, staged = set(), set()
    for entry in files:
        closed(entry, ('path', 'sha256', 'action', 'fragment'))
        p = str(path(entry['path']))
        checksum(entry['sha256'])
        require(not overlaps(p, admitted), 'overlapping admission')
        admitted.add(p)
        if entry['action'] == 'extract':
            require(entry['fragment'] is None, 'unexpected fragment')
        else:
            require(entry['action'] == 'reuse', 'invalid action')
            closed(entry['fragment'], ('stage_path', 'sha256'))
            q = str(path(entry['fragment']['stage_path']))
            checksum(entry['fragment']['sha256'])
            require(not overlaps(q, staged), 'overlapping fragment')
            staged.add(q)
    require(not any(overlaps(q, admitted) for q in staged), 'fragment overlaps admission')
    policy = request['policy']
    closed(policy, ('schema', 'source', 'name', 'rules', 'limitations'))
    require(policy['schema'] == 'graphify-pack-policy/v1' and policy['source'] == source
            and policy['name'] == 'incremental-admission' and policy['limitations'] == [],
            'invalid policy identity')
    # The admission policy object is owned by the driver; only include/deny are checked here.
    rules = policy['rules']
    require(isinstance(rules, dict), 'invalid admission policy')
    include, deny = patterns(rules.get('include')), patterns(rules.get('deny'))
    for p in admitted:
        require(any(fnmatch.fnmatchcase(p, x) for x in include)
                and not any(fnmatch.fnmatchcase(p, x) for x in deny), 'denied file')
    validate_extractor(request['extractor'], 'python-json/v2')
    return admitted


@contextmanager
def directory(parts):
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def signature(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_staged(stage, entry, limit):
    parts = PurePosixPath(stage, entry['path']).parts
    with directory(parts[1:-1]) as parent:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                    and before.st_size <= limit, 'unsafe or oversized staged file')
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                raw = stream.read(limit + 1)
            require(len(raw) <= limit and signature(before) == signature(os.fstat(fd))
                    == signature(os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)),
                    'staged file changed')
        finally:
            os.close(fd)
    require(digest(raw) == entry['sha256'], 'staged hash mismatch')
    return raw


def record_id(*parts):
    return 'structural-v1:' + digest(encoded(parts))


def file_id(file):
    return record_id(file, 'file', file)


def file_node(file):
    return dict(id=file_id(file), type='file', label=text(file), source_file=file)


def candidate(value):
    # Only a valid relative path can equal an admitted path; others never resolve.
    try:
        return str(path(value))
    except ValueError:
        return None


def resolve(file, reference, admitted):
    """Return (kind, v1 dedup key, record) for one reference over the admitted set."""
    found = [c for c in reference['candidates'] if c in admitted]
    if len(found) == 1:
        record = dict(source=file_id(file), target=file_id(found[0]),
                      type=reference['kind'], source_file=file)
        return 'edge', (file, record['source'], record['target'], record['type']), record
    text(reference['target'])
    record = dict(source_file=file, type=reference['kind'], target=reference['target'],
                  line=reference['line'])
    return 'unresolved', (file, record['type'], record['target'], record['line']), record


class Extraction:
    """File-local records of one file. Without an admitted set (v2), each distinct
    reference is counted; with one (v1), the record it becomes is counted instead."""

    def __init__(self, file, limits, admitted=None):
        self.file, self.file_id, self.admitted = file, file_id(file), admitted
        self.byte_limit, self.bytes = limits['output_bytes'], 0
        self.nodes, self.edges, self.references, self.accounted = [], {}, {}, set()

    def account(self, record):
        self.bytes += len(encoded(record))
        if len(self.nodes) + len(self.edges) + len(self.accounted) > MAX_RECORDS:
            raise Limit('record limit')
        if self.bytes > self.byte_limit:
            raise Limit('output byte limit')

    def node(self, kind, label, *location):
        text(label)
        identity = record_id(self.file, kind, label, *location)
        record = dict(id=identity, type=kind, label=label, source_file=self.file)
        self.nodes.append(record)
        self.account(record)
        return identity

    def edge(self, source, target, kind):
        key = source, target, kind
        if key in self.edges:
            return
        record = self.edges[key] = dict(source=source, target=target, type=kind, source_file=self.file)
        self.account(record)

    def reference(self, kind, target, line, candidates):
        key = kind, target, line
        if key in self.references:
            return
        record = self.references[key] = dict(
            kind=kind, target=target, line=line,
            candidates=[c for c in map(candidate, candidates) if c is not None])
        if self.admitted is not None:
            _, key, record = resolve(self.file, record, self.admitted)
        if key not in self.accounted:
            self.accounted.add(key)
            self.account(record)


def python_structure(raw, file, records):
    # ast.parse never imports or executes admitted source. Parser failure is coverage loss.
    tree = ast.parse(raw, filename=file)
    pending = [(tree, records.file_id, '')]
    count = 0
    while pending:
        item, parent, scope = pending.pop()
        count += 1
        if count > MAX_AST_NODES:
            raise Limit('AST node limit')
        if isinstance(item, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            scope = scope + '.' + item.name if scope else item.name
            kind = 'class' if isinstance(item, ast.ClassDef) else 'function'
            child = records.node(kind, scope, item.lineno, item.col_offset)
            records.edge(parent, child, 'contains')
            parent = child
        if isinstance(item, (ast.Import, ast.ImportFrom)):
            modules = [a.name for a in item.names] if isinstance(item, ast.Import) else []
            if isinstance(item, ast.ImportFrom):
                package = list(PurePosixPath(file).parts[:-1])
                if item.level:
                    if item.level > len(package):
                        records.reference('imports', '.' * item.level + (item.module or ''), item.lineno, [])
                    else:
                        base = package[:len(package) - item.level + 1]
                        modules = ['.'.join(base + ([item.module] if item.module else []))]
                else:
                    modules = [item.module or '']
            for module in modules:
                stem = module.replace('.', '/')
                records.reference('imports', module, item.lineno, [stem + '.py', stem + '/__init__.py'])
        pending.extend((child, parent, scope) for child in reversed(list(ast.iter_child_nodes(item))))


INLINE_LINK = re.compile(r'(?<!!)\[[^\]\n]*\]\(([^\s()]+)\)')


def markdown_structure(raw, file, records):
    content = raw.decode('utf-8')
    fence = None
    for number, line in enumerate(content.splitlines(), 1):
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence is not None or line.startswith(('    ', '\t')):
            continue
        # This intentionally covers plain inline links only, not full CommonMark.
        line = re.sub(r'(`+).*?\1', '', line)
        for match in INLINE_LINK.finditer(line):
            link = match.group(1)
            if link.startswith(('/', '#')) or re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', link):
                continue
            target = link.split('#', 1)[0].split('?', 1)[0]
            parts = list(PurePosixPath(file).parts[:-1])
            safe = bool(target) and '\\' not in target and '%' not in target
            for part in target.split('/'):
                if part == '..':
                    if parts:
                        parts.pop()
                    else:
                        safe = False
                elif part not in ('', '.'):
                    parts.append(part)
            normalized = '/'.join(parts)
            records.reference('links_to', link, number, [normalized] if safe else [])


def document(file, raw, outcome, reason, records=None):
    return dict(schema=FRAGMENT, family=dict(name=NAME, version=VERSION), path=file,
                content_sha256=digest(raw), outcome=outcome, reason=reason, file_node=file_node(file),
                nodes=sorted(records.nodes, key=lambda n: n['id']) if records else [],
                edges=[records.edges[k] for k in sorted(records.edges)] if records else [],
                references=[records.references[k] for k in sorted(records.references)] if records else [])


def extract(file, raw, limits, admitted=None):
    records = Extraction(file, limits, admitted)
    try:
        if file.endswith('.py'):
            python_structure(raw, file, records)
        elif file.endswith('.md'):
            markdown_structure(raw, file, records)
        else:
            raise NotImplementedError('unsupported file type')
    except (SyntaxError, RecursionError, UnicodeError, NotImplementedError) as exc:
        # Failed files keep no local records; the reason is the concrete exception name.
        return document(file, raw, 'unknown', type(exc).__name__)
    return document(file, raw, 'structural', None, records)


def fragment(file, raw, limits):
    """Return the file-local v2 fragment; a per-file bound gives outcome unknown, reason limit."""
    path(file)
    try:
        result = extract(file, raw, limits)
        if len(encoded(result)) > limits['output_bytes']:
            raise Limit('output byte limit')
    except Limit:
        return document(file, raw, 'unknown', 'limit')
    return result


def check_fragment(item, file, content_sha256):
    closed(item, ('schema', 'family', 'path', 'content_sha256', 'outcome', 'reason',
                  'file_node', 'nodes', 'edges', 'references'))
    require(item['schema'] == FRAGMENT and item['family'] == dict(name=NAME, version=VERSION)
            and item['path'] == file and item['content_sha256'] == content_sha256
            and item['file_node'] == file_node(file), 'fragment identity mismatch')
    nodes, edges, references = item['nodes'], item['edges'], item['references']
    require(all(isinstance(x, list) for x in (nodes, edges, references))
            and len(nodes) + len(edges) + len(references) <= MAX_RECORDS, 'invalid fragment records')
    if item['outcome'] == 'unknown':
        require(isinstance(item['reason'], str) and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,63}', item['reason'])
                and not nodes and not edges and not references, 'invalid unknown fragment')
        return
    require(item['outcome'] == 'structural' and item['reason'] is None, 'invalid fragment outcome')
    ids = {item['file_node']['id']}
    for node in nodes:
        closed(node, ('id', 'type', 'label', 'source_file'))
        require(isinstance(node['id'], str) and re.fullmatch('structural-v1:[0-9a-f]{64}', node['id'])
                and node['id'] not in ids and node['type'] in ('class', 'function')
                and node['source_file'] == file, 'invalid fragment node')
        text(node['label'])
        ids.add(node['id'])
    seen = set()
    for edge in edges:
        closed(edge, ('source', 'target', 'type', 'source_file'))
        require(edge['type'] == 'contains' and edge['source_file'] == file and edge['source'] in ids
                and edge['target'] in ids and (edge['source'], edge['target']) not in seen,
                'invalid fragment edge')
        seen.add((edge['source'], edge['target']))
    seen = set()
    for reference in references:
        closed(reference, ('kind', 'target', 'line', 'candidates'))
        require(reference['kind'] in ('imports', 'links_to') and isinstance(reference['target'], str)
                and type(reference['line']) is int and reference['line'] >= 1
                and isinstance(reference['candidates'], list) and len(reference['candidates']) <= 2
                and all(candidate(c) == c for c in reference['candidates'])
                and (reference['kind'], reference['target'], reference['line']) not in seen,
                'invalid fragment reference')
        seen.add((reference['kind'], reference['target'], reference['line']))


def assemble(fragments, source, request_sha256, limits):
    """Resolve every reference over the given admitted set; global bounds fail the run."""
    admitted = set(fragments)
    nodes, edges, unresolved, errors, coverage = [], {}, {}, [], {}
    size = 0

    def bound(record=None):
        nonlocal size
        size += len(encoded(record)) if record is not None else 0
        require(len(nodes) + len(edges) + len(unresolved) + len(errors) <= MAX_RECORDS, 'record limit')
        require(size <= limits['output_bytes'], 'output byte limit')

    for file in sorted(admitted):
        require(fragments[file]['path'] == file, 'fragment path mismatch')
        nodes.append(file_node(file))
        bound(nodes[-1])
    for file in sorted(admitted):
        item = fragments[file]
        coverage[file] = item['outcome']
        if item['outcome'] != 'structural':
            errors.append(dict(source_file=file, reason=item['reason']))
            bound()
            continue
        for node in item['nodes']:
            nodes.append(node)
            bound(node)
        for edge in item['edges']:
            key = file, edge['source'], edge['target'], edge['type']
            if key not in edges:
                edges[key] = edge
                bound(edge)
        for reference in item['references']:
            kind, key, record = resolve(file, reference, admitted)
            records = edges if kind == 'edge' else unresolved
            if key not in records:
                records[key] = record
                bound(record)
    common = dict(source=source, built_at_commit=source['head'],
                  refresh_request_sha256=request_sha256, extractor_family=dict(name=NAME, version=VERSION))
    graph = dict(common, directed=True, nodes=sorted(nodes, key=lambda n: n['id']),
                 links=[edges[k] for k in sorted(edges)])
    validation = dict(common, status='partial', semantic_coverage='none',
                      covered_segments_by_file={p: [] for p in sorted(admitted)},
                      structural_parser_errors=len(errors), parser_errors=errors,
                      unresolved_references=[unresolved[k] for k in sorted(unresolved)],
                      limitations=['Structural syntax only; no execution, type/call resolution or semantic enrichment.',
                                   'Imports resolve exact admitted root-relative modules only; source roots are not inferred.',
                                   'Markdown supports plain inline relative links, not full CommonMark.',
                                   'Source identity and observations are caller supplied, not independently attested.'])
    return graph, validation, coverage


def respond_v1(raw, request):
    admitted = validate(request)
    limits = request['limits']
    fragments, total = {}, 0
    for entry in sorted(request['files'], key=lambda f: f['path']):
        data = read_staged(request['stage'], entry, min(limits['file_bytes'], limits['input_bytes'] - total))
        total += len(data)
        require(total <= limits['input_bytes'], 'total input limit')
        # v1 keeps per-file bounds fatal: Limit propagates and the whole request fails.
        fragments[entry['path']] = extract(entry['path'], data, limits, admitted)
    sha = digest(raw)
    graph, validation, coverage = assemble(fragments, request['source'], sha, limits)
    response = encoded(dict(schema='graphify-refresh-response/v1', request_sha256=sha,
                            graph=graph, validation=validation, coverage=coverage))
    require(len(response) <= limits['output_bytes'], 'output byte limit')
    return response


def respond_v2(raw, request):
    validate_v2(request)
    limits, stage = request['limits'], request['stage']
    fragments, extracted, total = {}, {}, 0
    for entry in sorted(request['files'], key=lambda f: f['path']):
        file, remaining = entry['path'], limits['input_bytes'] - total
        if entry['action'] == 'extract':
            data = read_staged(stage, entry, min(limits['file_bytes'], remaining))
            item = extracted[file] = fragment(file, data, limits)
        else:
            staged = dict(path=entry['fragment']['stage_path'], sha256=entry['fragment']['sha256'])
            data = read_staged(stage, staged, min(limits['output_bytes'], remaining))
            item = strict_json(data, 8 * MAX_RECORDS + 64)
            check_fragment(item, file, entry['sha256'])
        # input_bytes bounds every staged byte read: content and reused fragments.
        total += len(data)
        require(total <= limits['input_bytes'], 'total input limit')
        fragments[file] = item
    sha = digest(raw)
    graph, validation, coverage = assemble(fragments, request['source'], sha, limits)
    validation['limitations'].append(GIT_LIMITATION)
    response = encoded(dict(schema='graphify-refresh-response/v2', request_sha256=sha, graph=graph,
                            validation=validation, coverage=coverage, fragments=extracted))
    require(len(response) <= limits['output_bytes'], 'output byte limit')
    return response


# Family version 2 -----------------------------------------------------------

def load_languages():
    """Load the sibling extractor module once, only from bytes matching LANGUAGES_SHA256."""
    global LANGUAGES
    if LANGUAGES is None:
        location = PurePosixPath(os.path.realpath(__file__)).with_name(LANGUAGES_MODULE)
        with directory(location.parts[1:-1]) as parent:
            fd = os.open(location.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(fd, 'rb') as stream:
                require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'unsafe languages module')
                raw = stream.read(MAX_LANGUAGES + 1)
        require(len(raw) <= MAX_LANGUAGES and digest(raw) == LANGUAGES_SHA256,
                'languages module mismatch')
        namespace = dict(__name__='structural_languages', __file__=str(location))
        try:
            exec(compile(raw, str(location), 'exec', dont_inherit=True), namespace)
        except SyntaxError as exc:
            raise ValueError('languages module invalid') from exc
        LANGUAGES = Languages(namespace)
    return LANGUAGES


class Languages:
    """Attribute view of the executed languages module namespace."""

    def __init__(self, namespace):
        self.__dict__.update(namespace)


def usable(value):
    return (isinstance(value, str) and 0 < len(value) <= 4096
            and not any(ord(c) < 32 for c in value))


class ExtractionV2(Extraction):
    """Family 2 sink: invalid labels or targets are a per-file limit; ids stay unique."""

    def __init__(self, file, limits):
        super().__init__(file, limits)
        self.ids = {self.file_id}

    def node(self, kind, label, *location):
        if not usable(label):
            raise Limit('invalid label')
        identity = record_id(self.file, kind, label, *location)
        if identity not in self.ids:
            self.ids.add(identity)
            super().node(kind, label, *location)
        return identity

    def reference(self, kind, target, line, candidates, resolution='unique'):
        if not usable(target):
            raise Limit('invalid reference')
        key = kind, target, line
        if key in self.references:
            return
        found = list(dict.fromkeys(c for c in map(candidate, candidates) if c is not None))
        if len(found) > MAX_CANDIDATES:
            raise Limit('candidate limit')
        record = self.references[key] = dict(kind=kind, target=target, line=line,
                                              candidates=found, resolution=resolution)
        self.accounted.add(key)
        self.account(record)


def document_v2(file, raw, outcome, reason, records=None):
    item = document(file, raw, outcome, reason, records)
    item.update(schema=FRAGMENT_V2, family=dict(name=NAME, version=VERSION_V2))
    return item


def fragment_v2(file, raw, limits, languages):
    """File-local family 2 fragment; marker, unsupported, parse and bound failures are unknown."""
    path(file)
    if languages.forbidden(raw):
        return document_v2(file, raw, 'unknown', 'forbidden_marker')
    records = ExtractionV2(file, limits)
    try:
        if file.endswith('.py'):
            python_structure(raw, file, records)
        else:
            languages.extract(file, raw, records)
        result = document_v2(file, raw, 'structural', None, records)
        if len(encoded(result)) > limits['output_bytes']:
            raise Limit('output byte limit')
    except NotImplementedError:
        return document_v2(file, raw, 'unknown', 'unsupported')
    except (SyntaxError, RecursionError, UnicodeError) as exc:
        return document_v2(file, raw, 'unknown', type(exc).__name__)
    except Limit:
        return document_v2(file, raw, 'unknown', 'limit')
    return result


def check_fragment_v2(item, file, content_sha256):
    closed(item, ('schema', 'family', 'path', 'content_sha256', 'outcome', 'reason',
                  'file_node', 'nodes', 'edges', 'references'))
    require(item['schema'] == FRAGMENT_V2 and item['family'] == dict(name=NAME, version=VERSION_V2)
            and item['path'] == file and item['content_sha256'] == content_sha256
            and item['file_node'] == file_node(file), 'fragment identity mismatch')
    nodes, edges, references = item['nodes'], item['edges'], item['references']
    require(all(isinstance(x, list) for x in (nodes, edges, references))
            and len(nodes) + len(edges) + len(references) <= MAX_RECORDS, 'invalid fragment records')
    if item['outcome'] == 'unknown':
        require(isinstance(item['reason'], str) and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,63}', item['reason'])
                and not nodes and not edges and not references, 'invalid unknown fragment')
        return
    require(item['outcome'] == 'structural' and item['reason'] is None, 'invalid fragment outcome')
    ids = {item['file_node']['id']}
    for node in nodes:
        closed(node, ('id', 'type', 'label', 'source_file'))
        require(isinstance(node['id'], str) and re.fullmatch('structural-v1:[0-9a-f]{64}', node['id'])
                and node['id'] not in ids and node['type'] in NODE_TYPES_V2
                and node['source_file'] == file and usable(node['label']), 'invalid fragment node')
        ids.add(node['id'])
    seen = set()
    for edge in edges:
        closed(edge, ('source', 'target', 'type', 'source_file'))
        key = edge['source'], edge['target'], edge['type']
        require(edge['type'] in EDGE_TYPES_V2 and edge['source_file'] == file and edge['source'] in ids
                and edge['target'] in ids and key not in seen, 'invalid fragment edge')
        seen.add(key)
    seen = set()
    for reference in references:
        closed(reference, ('kind', 'target', 'line', 'candidates', 'resolution'))
        key = reference['kind'], reference['target'], reference['line']
        found = reference['candidates']
        require(reference['kind'] in REFERENCE_KINDS_V2 and usable(reference['target'])
                and type(reference['line']) is int and reference['line'] >= 1
                and reference['resolution'] in RESOLUTIONS_V2
                and isinstance(found, list) and len(found) <= MAX_CANDIDATES
                and len(set(found)) == len(found) and all(candidate(c) == c for c in found)
                and key not in seen, 'invalid fragment reference')
        seen.add(key)


def disjoint(paths):
    """True when no path repeats or is an ancestor of another; linear in total depth."""
    seen, ancestors = set(), set()
    for p in paths:
        parts = p.split('/')
        prefixes = ['/'.join(parts[:k]) for k in range(1, len(parts))]
        if p in seen or p in ancestors or any(q in seen for q in prefixes):
            return False
        seen.add(p)
        ancestors.update(prefixes)
    return True


def validate_family_v2(request):
    """Return (admitted paths, slice name or None, staged index entry or None)."""
    optional = tuple(k for k in ('slice', 'path_index') if isinstance(request, dict) and k in request)
    limits = request.get('limits') if isinstance(request, dict) else None
    bounds = dict(LIMITS_V2, records=MAX_RECORDS_V2) if isinstance(limits, dict) and 'records' in limits else LIMITS_V2
    source, files = validate_common(
        request, ('schema', 'manifest_sha256', 'source', 'input_basis', 'stage', 'files',
                  'policy', 'extractor', 'limits') + optional, REQUEST_V2, bounds, MAX_FILES_V2)
    require(request['input_basis'] == 'git_blob', 'unsupported input basis')
    # Slicing is all or nothing: a slice name needs the index that resolves against other slices.
    require(len(optional) in (0, 2), 'slice and path index must be given together')
    admitted, staged = [], []
    for entry in files:
        closed(entry, ('path', 'sha256', 'action', 'fragment'))
        admitted.append(str(path(entry['path'])))
        checksum(entry['sha256'])
        if entry['action'] == 'extract':
            require(entry['fragment'] is None, 'unexpected fragment')
        else:
            require(entry['action'] == 'reuse', 'invalid action')
            closed(entry['fragment'], ('stage_path', 'sha256'))
            staged.append(str(path(entry['fragment']['stage_path'])))
            checksum(entry['fragment']['sha256'])
    name = index = None
    if optional:
        closed(request['slice'], ('name',))
        name = request['slice']['name']
        require(isinstance(name, str) and SLICE_NAME.fullmatch(name), 'invalid slice name')
        index = request['path_index']
        closed(index, ('stage_path', 'sha256'))
        staged.append(str(path(index['stage_path'])))
        checksum(index['sha256'])
    require(disjoint(admitted) and disjoint(staged) and disjoint(admitted + staged),
            'overlapping admission or staged input')
    policy = request['policy']
    closed(policy, ('schema', 'source', 'name', 'rules', 'limitations'))
    require(policy['schema'] == 'graphify-pack-policy/v1' and policy['source'] == source
            and policy['name'] == 'incremental-admission' and policy['limitations'] == [],
            'invalid policy identity')
    rules = policy['rules']
    require(isinstance(rules, dict), 'invalid admission policy')
    include, deny = patterns(rules.get('include')), patterns(rules.get('deny'))
    for p in admitted:
        require(any(fnmatch.fnmatchcase(p, x) for x in include)
                and not any(fnmatch.fnmatchcase(p, x) for x in deny), 'denied file')
    validate_extractor(request['extractor'], 'python-json/v2', VERSION_V2)
    return set(admitted), name, index


def read_path_index(raw, admitted, name):
    """Return {path: slice}; it must map every own file to this request's slice."""
    value = strict_json(raw, 2 * MAX_INDEX_PATHS + 16)
    closed(value, ('schema', 'paths'))
    require(value['schema'] == PATH_INDEX, 'unsupported path index')
    paths = value['paths']
    require(isinstance(paths, dict) and len(admitted) <= len(paths) <= MAX_INDEX_PATHS,
            'invalid path index')
    keys = list(paths)
    require(keys == sorted(keys) and disjoint(keys), 'unsorted or overlapping path index')
    for p, owner in paths.items():
        require(candidate(p) == p and isinstance(owner, str) and SLICE_NAME.fullmatch(owner),
                'invalid path index entry')
    for p in admitted:
        require(paths.get(p) == name, 'path index omits or misassigns an admitted file')
    require(not any(owner == name and p not in admitted for p, owner in paths.items()),
            'path index assigns an unadmitted file to this slice')
    return paths


def assemble_v2(fragments, source, request_sha256, limits, index=None):
    """Resolve over the whole repository: the index when sliced, else the admitted set.
    The same candidate set and test decide both, so slicing never changes a decision."""
    admitted = set(fragments)
    universe = admitted if index is None else index
    maximum = limits.get('records', MAX_RECORDS)
    nodes, edges, crossing, unresolved, errors, coverage = [], {}, {}, {}, [], {}
    size = 0

    def bound(record=None):
        nonlocal size
        size += len(encoded(record)) if record is not None else 0
        require(len(nodes) + len(edges) + len(crossing) + len(unresolved) + len(errors) <= maximum,
                'record limit')
        require(size <= limits['output_bytes'], 'output byte limit')

    for file in sorted(admitted):
        require(fragments[file]['path'] == file, 'fragment path mismatch')
        nodes.append(file_node(file))
        bound(nodes[-1])
    for file in sorted(admitted):
        item = fragments[file]
        coverage[file] = item['outcome']
        if item['outcome'] != 'structural':
            errors.append(dict(source_file=file, reason=item['reason']))
            bound()
            continue
        for node in item['nodes']:
            nodes.append(node)
            bound(node)
        for edge in item['edges']:
            key = file, edge['source'], edge['target'], edge['type']
            if key not in edges:
                edges[key] = edge
                bound(edge)
        for reference in item['references']:
            found = [c for c in reference['candidates'] if c in universe]
            if reference['resolution'] == 'first':
                found = found[:1]
            if len(found) != 1:
                record = dict(source_file=file, type=reference['kind'], target=reference['target'],
                              line=reference['line'])
                key, records = (file, record['type'], record['target'], record['line']), unresolved
            elif found[0] in admitted:
                record = dict(source=file_id(file), target=file_id(found[0]),
                              type=reference['kind'], source_file=file)
                key, records = (file, record['source'], record['target'], record['type']), edges
            else:
                record = dict(source=file_id(file), source_file=file, type=reference['kind'],
                              target=reference['target'], line=reference['line'],
                              target_path=found[0], target_id=file_id(found[0]),
                              target_slice=index[found[0]])
                key = file, record['type'], record['target'], record['line'], found[0]
                records = crossing
            if key not in records:
                records[key] = record
                bound(record)
    family = dict(name=NAME, version=VERSION_V2)
    common = dict(source=source, built_at_commit=source['head'],
                  refresh_request_sha256=request_sha256, extractor_family=family)
    graph = dict(common, directed=True, nodes=sorted(nodes, key=lambda n: n['id']),
                 links=[edges[k] for k in sorted(edges)])
    validation = dict(common, status='partial', semantic_coverage='none',
                      covered_segments_by_file={p: [] for p in sorted(admitted)},
                      structural_parser_errors=len(errors), parser_errors=errors,
                      unresolved_references=[unresolved[k] for k in sorted(unresolved)],
                      limitations=['Lexical structure only; no execution, compiler, type or call resolution, or semantic enrichment.',
                                   'Imports resolve exact root-relative or relative paths only; aliases, packages, Go modules and Swift modules stay unresolved.',
                                   'TS/JS relative imports and workflow uses resolve to the first present candidate in a declared order; alternatives are not reported.',
                                   'Markdown covers headings and inline and reference-definition links, not full CommonMark.',
                                   'Files containing a forbidden marker carry no records.',
                                   'Source identity and observations are caller supplied, not independently attested.'])
    if index is not None:
        validation['cross_slice_references'] = [crossing[k] for k in sorted(crossing)]
        validation['limitations'].append(
            'Cross-slice references resolve against a caller-supplied path index; their targets are in other slices.')
    return graph, validation, coverage


def respond_family_v2(raw, request):
    admitted, name, index_entry = validate_family_v2(request)
    languages = load_languages()
    limits, stage = request['limits'], request['stage']
    per_file = dict(limits, output_bytes=min(limits['output_bytes'], FRAGMENT_BYTES))
    total, index = 0, None
    if index_entry is not None:
        staged = dict(path=index_entry['stage_path'], sha256=index_entry['sha256'])
        data = read_staged(stage, staged, min(MAX_INDEX_BYTES, limits['input_bytes']))
        total = len(data)
        index = read_path_index(data, admitted, name)
    fragments, extracted = {}, {}
    for entry in sorted(request['files'], key=lambda f: f['path']):
        file, remaining = entry['path'], limits['input_bytes'] - total
        if entry['action'] == 'extract':
            data = read_staged(stage, entry, min(limits['file_bytes'], remaining))
            item = extracted[file] = fragment_v2(file, data, per_file, languages)
        else:
            staged = dict(path=entry['fragment']['stage_path'], sha256=entry['fragment']['sha256'])
            data = read_staged(stage, staged, min(FRAGMENT_BYTES, remaining))
            item = strict_json(data, 40 * MAX_RECORDS + 64)
            check_fragment_v2(item, file, entry['sha256'])
        total += len(data)
        require(total <= limits['input_bytes'], 'total input limit')
        fragments[file] = item
    sha = digest(raw)
    # The adapter alone binds the slice into graph.source and validation.source; request.source
    # stays {repository, head} and fragments stay slice-independent.
    source = request['source'] if name is None else dict(request['source'], slice=name)
    graph, validation, coverage = assemble_v2(fragments, source, sha, limits, index)
    validation['limitations'].append(GIT_LIMITATION)
    response = encoded(dict(schema='graphify-refresh-response/v2', request_sha256=sha, graph=graph,
                            validation=validation, coverage=coverage, fragments=extracted))
    require(len(response) <= limits['output_bytes'], 'output byte limit')
    return response


def family_v2(request):
    extractor = request.get('extractor') if isinstance(request, dict) else None
    return (request.get('schema') == REQUEST_V2 and isinstance(extractor, dict)
            and extractor.get('version') == VERSION_V2)


def respond(raw):
    require(len(raw) <= MAX_REQUEST_V2, 'request byte limit')
    request = strict_json(raw, MAX_ITEMS_V2)
    if family_v2(request):
        return respond_family_v2(raw, request)
    # Every other request keeps the original bounds, parse and dispatch unchanged.
    require(len(raw) <= MAX_REQUEST, 'request byte limit')
    request = strict_json(raw)
    if isinstance(request, dict) and request.get('schema') == REQUEST_V2:
        return respond_v2(raw, request)
    return respond_v1(raw, request)


def main():
    try:
        response = respond(sys.stdin.buffer.read(MAX_REQUEST_V2 + 1))
    except (ValueError, TypeError, KeyError, OSError, RecursionError, OverflowError, MemoryError):
        # No partial JSON can be mistaken for success; stderr contains no source contents.
        sys.stderr.write('structural adapter rejected request or resource bound\n')
        return 1
    sys.stdout.buffer.write(response)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
