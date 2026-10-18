#!/usr/bin/env python3
"""Structural-only python-json/v1 adapter; stdin request, stdout response.

Reads only explicit staged inputs. No execution/import of source, file writes,
subprocesses, environment lookup or network. This family is not legacy parity.
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


def strict_json(raw):
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
        require(count <= 10000 and depth <= 24, 'request complexity limit')
        if isinstance(item, dict):
            pending.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            pending.extend((v, depth + 1) for v in item)
        elif isinstance(item, float):
            require(float('-inf') < item < float('inf'), 'nonfinite number')
    return value


def validate(request):
    closed(request, ('schema', 'manifest_sha256', 'source', 'stage', 'files',
                     'policy', 'extractor', 'samples', 'limits'))
    require(request['schema'] == 'graphify-refresh-request/v1', 'unsupported request')
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
    closed(limits, LIMITS)
    for key, maximum in LIMITS.items():
        require(type(limits[key]) is int and 1 <= limits[key] <= maximum, 'invalid limit')
    files = request['files']
    require(isinstance(files, list) and 1 <= len(files) <= 256, 'invalid files')
    admitted = set()
    for entry in files:
        closed(entry, ('path', 'sha256'))
        p = str(path(entry['path']))
        checksum(entry['sha256'])
        require(p not in admitted and not any(p.startswith(q + '/') or q.startswith(p + '/')
                                              for q in admitted), 'overlapping admission')
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
    extractor = request['extractor']
    closed(extractor, ('protocol', 'name', 'version', 'executable', 'script'))
    require(extractor['protocol'] == 'python-json/v1' and extractor['name'] == NAME
            and extractor['version'] == VERSION, 'wrong extractor family')
    for key in ('executable', 'script'):
        closed(extractor[key], ('path', 'sha256'))
        path(extractor[key]['path'], absolute=True)
        checksum(extractor[key]['sha256'])
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


class Records:
    def __init__(self, byte_limit):
        self.nodes, self.edges, self.unresolved, self.errors = [], {}, {}, []
        self.byte_limit, self.bytes = byte_limit, 0

    def bound(self):
        require(len(self.nodes) + len(self.edges) + len(self.unresolved) + len(self.errors)
                <= MAX_RECORDS, 'record limit')
        require(self.bytes <= self.byte_limit, 'output byte limit')

    def account(self, record):
        self.bytes += len(encoded(record))
        self.bound()

    def node(self, file, kind, label, *location):
        text(label)
        identity = record_id(file, kind, label, *location)
        record = dict(id=identity, type=kind, label=label, source_file=file)
        self.account(record)
        self.nodes.append(record)
        self.bound()
        return identity

    def edge(self, file, source, target, kind):
        key = file, source, target, kind
        if key in self.edges:
            return
        record = dict(source=source, target=target, type=kind, source_file=file)
        self.account(record)
        self.edges[key] = record
        self.bound()

    def unresolved_reference(self, file, kind, target, line):
        text(target)
        key = file, kind, target, line
        if key in self.unresolved:
            return
        record = dict(source_file=file, type=kind, target=target, line=line)
        self.account(record)
        self.unresolved[key] = record
        self.bound()


def python_structure(raw, file, files, records):
    # ast.parse never imports or executes admitted source. Parser failure is coverage loss.
    tree = ast.parse(raw, filename=file)
    pending = [(tree, files[file], '')]
    count = 0
    while pending:
        item, parent, scope = pending.pop()
        count += 1
        require(count <= MAX_AST_NODES, 'AST node limit')
        if isinstance(item, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            scope = scope + '.' + item.name if scope else item.name
            kind = 'class' if isinstance(item, ast.ClassDef) else 'function'
            child = records.node(file, kind, scope, item.lineno, item.col_offset)
            records.edge(file, parent, child, 'contains')
            parent = child
        if isinstance(item, (ast.Import, ast.ImportFrom)):
            modules = [a.name for a in item.names] if isinstance(item, ast.Import) else []
            if isinstance(item, ast.ImportFrom):
                package = list(PurePosixPath(file).parts[:-1])
                if item.level:
                    if item.level > len(package):
                        records.unresolved_reference(file, 'imports', '.' * item.level + (item.module or ''), item.lineno)
                    else:
                        base = package[:len(package) - item.level + 1]
                        modules = ['.'.join(base + ([item.module] if item.module else []))]
                else:
                    modules = [item.module or '']
            for module in modules:
                stem = module.replace('.', '/')
                candidates = [p for p in (stem + '.py', stem + '/__init__.py') if p in files]
                if len(candidates) == 1:
                    records.edge(file, files[file], files[candidates[0]], 'imports')
                else:
                    records.unresolved_reference(file, 'imports', module, item.lineno)
        pending.extend((child, parent, scope) for child in reversed(list(ast.iter_child_nodes(item))))


INLINE_LINK = re.compile(r'(?<!!)\[[^\]\n]*\]\(([^\s()]+)\)')


def markdown_structure(raw, file, files, records):
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
            if safe and normalized in files:
                records.edge(file, files[file], files[normalized], 'links_to')
            else:
                records.unresolved_reference(file, 'links_to', link, number)


def respond(raw):
    require(len(raw) <= MAX_REQUEST, 'request byte limit')
    request = strict_json(raw)
    admitted = validate(request)
    limits = request['limits']
    records, coverage = Records(limits['output_bytes']), {}
    files = {p: records.node(p, 'file', p) for p in sorted(admitted)}
    total = 0
    for entry in sorted(request['files'], key=lambda f: f['path']):
        data = read_staged(request['stage'], entry, min(limits['file_bytes'], limits['input_bytes'] - total))
        total += len(data)
        require(total <= limits['input_bytes'], 'total input limit')
        file = entry['path']
        local = Records(limits['output_bytes'] - records.bytes)
        try:
            if file.endswith('.py'):
                python_structure(data, file, files, local)
            elif file.endswith('.md'):
                markdown_structure(data, file, files, local)
            else:
                raise NotImplementedError('unsupported file type')
        except (SyntaxError, RecursionError, UnicodeError, NotImplementedError) as exc:
            coverage[file] = 'unknown'
            records.errors.append(dict(source_file=file, reason=type(exc).__name__))
        else:
            coverage[file] = 'structural'
            records.bytes += local.bytes
            records.nodes.extend(local.nodes)
            records.edges.update(local.edges)
            records.unresolved.update(local.unresolved)
        records.bound()
    sha = digest(raw)
    common = dict(source=request['source'], built_at_commit=request['source']['head'],
                  refresh_request_sha256=sha, extractor_family=dict(name=NAME, version=VERSION))
    graph = dict(common, directed=True, nodes=sorted(records.nodes, key=lambda n: n['id']),
                 links=[records.edges[k] for k in sorted(records.edges)])
    validation = dict(common, status='partial', semantic_coverage='none',
                      covered_segments_by_file={p: [] for p in sorted(admitted)},
                      structural_parser_errors=len(records.errors), parser_errors=records.errors,
                      unresolved_references=[records.unresolved[k] for k in sorted(records.unresolved)],
                      limitations=['Structural syntax only; no execution, type/call resolution or semantic enrichment.',
                                   'Imports resolve exact admitted root-relative modules only; source roots are not inferred.',
                                   'Markdown supports plain inline relative links, not full CommonMark.',
                                   'Source identity and observations are caller supplied, not independently attested.'])
    response = encoded(dict(schema='graphify-refresh-response/v1', request_sha256=sha,
                            graph=graph, validation=validation, coverage=coverage))
    require(len(response) <= limits['output_bytes'], 'output byte limit')
    return response


def main():
    try:
        response = respond(sys.stdin.buffer.read(MAX_REQUEST + 1))
    except (ValueError, TypeError, KeyError, OSError, RecursionError, OverflowError, MemoryError):
        # No partial JSON can be mistaken for success; stderr contains no source contents.
        sys.stderr.write('structural adapter rejected request or resource bound\n')
        return 1
    sys.stdout.buffer.write(response)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
