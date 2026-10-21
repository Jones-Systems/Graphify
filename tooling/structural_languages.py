"""Conservative lexical extractors for graphify-stdlib-structural version 2.

refresh_adapter_structural.py loads this file by path after checking its
SHA256, so a change here must update LANGUAGES_SHA256 there. It is not an
import-path module and has no side effects.

Each extractor reads one decoded file and reports to a record sink with
node(kind, label, *location), edge(source, target, kind) and
reference(kind, target, line, candidates, resolution). Nothing is executed,
imported or installed. This is lexical structure, not compiler semantics:
path aliases, bare packages, Go module imports, Swift modules, conditional
compilation, macros and generated names are not resolved. Records carry identifiers, headings, import
specifiers, link targets and manifest dependency names only; other string
contents are replaced before matching. Empty, overlong or control-character
specifiers and headings are not recorded. A lexer that loses structure raises
SyntaxError, and the adapter then records the file as unknown.
"""
import json
from pathlib import PurePosixPath
import re

try:
    import tomllib
except ImportError:  # Python < 3.11: pyproject.toml stays unsupported.
    tomllib = None

# Mirrors preflight.FORBIDDEN_MARKERS; assembled so this file does not match itself.
FORBIDDEN_MARKERS = (
    'BEGIN ' + 'PRIVATE ' + 'KEY',
    'BEGIN ' + 'RSA PRIVATE ' + 'KEY',
    'AWS_ACCESS_KEY_' + 'ID=',
    'api_' + 'key =',
)
MARKDOWN = ('.md', '.markdown')
JS_EXTENSIONS = ('.ts', '.tsx', '.mts', '.cts', '.js', '.jsx', '.mjs', '.cjs')
SHELL = ('.sh', '.bash', '.zsh')
LOOKAHEAD = 4096


def forbidden(raw):
    return any(marker.encode() in raw for marker in FORBIDDEN_MARKERS)


def usable(value):
    return (isinstance(value, str) and 0 < len(value) <= 4096
            and not any(ord(c) < 32 for c in value))


def directory_parts(file):
    return list(PurePosixPath(file).parts[:-1])


def relative(base, target):
    """Normalize target against base parts; None when empty, unsafe or escaping."""
    if not target or '\\' in target or '%' in target:
        return None
    parts = list(base)
    for part in target.split('/'):
        if part == '..':
            if not parts:
                return None
            parts.pop()
        elif part not in ('', '.'):
            parts.append(part)
    return '/'.join(parts) or None


def blank(segment):
    """Replace skipped text, keeping its line breaks so later line numbers hold."""
    return '\n' * segment.count('\n') or ' '


# Tokens over sanitized code: string placeholders, identifiers, numbers, punctuation.
TOKEN = re.compile(r'"(?:\d+|!)"|`[^`\n]+`|(?:[^\W\d]|\$)[\w$]*|\d[\w.]*|\S')
IDENTIFIER = re.compile(r'(?:[^\W\d]|\$)[\w$]*\Z')


class Tokens:
    def __init__(self, code, strings=()):
        self.items, self.strings = [], strings
        line, last = 1, 0
        for match in TOKEN.finditer(code):
            breaks = code.count('\n', last, match.start())
            line += breaks
            self.items.append((match.group(), line, match.start(), breaks > 0))
            last = match.end()

    def value(self, k):
        return self.items[k][0] if 0 <= k < len(self.items) else None

    def name(self, k):
        value = self.value(k)
        if value is not None and value.startswith('`') and len(value) > 2:
            value = value[1:-1]
        return value if value is not None and IDENTIFIER.match(value) else None

    def string(self, k):
        """Literal value of a string placeholder token, else None."""
        value = self.value(k)
        if value is None or not value.startswith('"') or value == '"!"':
            return None
        return self.strings[int(value[1:-1])]


def literal(out, strings, value, segment):
    if value is None:
        out.append(' "!" ')
    else:
        out.append(' "%d" ' % len(strings))
        strings.append(value)
    out.append('\n' * segment.count('\n'))


def balance(scopes, paren):
    if scopes or paren:
        raise SyntaxError('unbalanced brackets')


# TypeScript / JavaScript -------------------------------------------------------

JS_CHUNK = re.compile(r'[^\'"`/{}]+')
JS_REGEX_KEYWORDS = frozenset('return typeof instanceof in of new delete void throw case do '
                              'else yield await'.split())


def last_token(chunk, prev):
    s = chunk.rstrip()
    if not s:
        return prev
    k = len(s)
    while k and (s[k - 1].isalnum() or s[k - 1] in '_$'):
        k -= 1
    word = s[k:]
    if not word:
        return s[-1]
    return '0' if word[0].isdigit() else word


def regex_allowed(prev):
    # Heuristic only: '/' after an operand is division. '<' covers JSX closing tags.
    if prev is None:
        return True
    if prev[0].isalnum() or prev[0] in '_$':
        return prev in JS_REGEX_KEYWORDS
    return prev not in (')', ']', '}', '<')


def regex_end(content, i):
    j, klass, n = i + 1, False, len(content)
    while j < n and content[j] != '\n':
        c = content[j]
        if c == '\\':
            if j + 1 < n and content[j + 1] == '\n':
                return None
            j += 2
            continue
        if c == '[':
            klass = True
        elif c == ']':
            klass = False
        elif c == '/' and not klass:
            j += 1
            while j < n and (content[j].isalnum() or content[j] in '_$'):
                j += 1
            return j
        j += 1
    return None


def template_scan(content, i):
    """Return (index after the part, ended) from inside a template literal."""
    j, n = i, len(content)
    while j < n:
        c = content[j]
        if c == '\\':
            j += 2
            continue
        if c == '`':
            return j + 1, True
        if c == '$' and content.startswith('${', j):
            return j + 2, False
        j += 1
    raise SyntaxError('unterminated template literal')


def sanitize_js(content):
    """Drop comments, regex and string contents; keep literal specifiers aside."""
    out, strings, templates = [], [], []
    i, n, prev = 0, len(content), None
    if content.startswith('#!'):
        i = content.find('\n')
        i = n if i < 0 else i
    while i < n:
        match = JS_CHUNK.match(content, i)
        if match:
            out.append(match.group())
            prev = last_token(match.group(), prev)
            i = match.end()
            continue
        c = content[i]
        if c == '/':
            if content.startswith('//', i):
                j = content.find('\n', i)
                i = n if j < 0 else j
                out.append(' ')
                continue
            if content.startswith('/*', i):
                j = content.find('*/', i + 2)
                if j < 0:
                    raise SyntaxError('unterminated comment')
                out.append(blank(content[i:j + 2]))
                i = j + 2
                continue
            j = regex_end(content, i) if regex_allowed(prev) else None
            if j is not None:
                out.append(' 0 ')
                prev, i = '0', j
                continue
            out.append('/')
            prev, i = '/', i + 1
        elif c in '\'"':
            j, escaped = i + 1, False
            while j < n and content[j] not in (c, '\n'):
                if content[j] == '\\':
                    escaped = True
                    j += 1
                j += 1
            if j < n and content[j] == c:
                literal(out, strings, None if escaped else content[i + 1:j], content[i:j + 1])
                i = j + 1
            else:
                # Unterminated on its line (often JSX text): recovery drops the rest of the line.
                out.append(blank(content[i:j]))
                i = j
            prev = '0'
        elif c == '`':
            j, ended = template_scan(content, i + 1)
            if ended:
                inner = content[i + 1:j - 1]
                literal(out, strings, None if '\\' in inner else inner, content[i:j])
                prev = '0'
            else:
                out.append(blank(content[i:j]))
                templates.append(0)
                prev = '('
            i = j
        elif c == '{':
            if templates:
                templates[-1] += 1
            out.append('{')
            prev, i = '{', i + 1
        else:  # '}'
            if templates and templates[-1] == 0:
                templates.pop()
                j, ended = template_scan(content, i + 1)
                out.append(blank(content[i:j]))
                if ended:
                    prev = '0'
                else:
                    templates.append(0)
                    prev = '('
                i = j
                continue
            if templates:
                templates[-1] -= 1
            out.append('}')
            prev, i = '}', i + 1
    if templates:
        raise SyntaxError('unterminated template literal')
    return ''.join(out), strings


JS_SWAP = {'.js': ('.ts', '.tsx'), '.jsx': ('.tsx',), '.mjs': ('.mts',), '.cjs': ('.cts',)}


def js_candidates(file, specifier):
    """Ordered relative-resolution candidates; bare names and aliases have none."""
    if not (specifier.startswith(('./', '../')) or specifier in ('.', '..')):
        return []
    base = relative(directory_parts(file), specifier.split('?', 1)[0])
    if base is None:
        return []
    suffix = PurePosixPath(base).suffix
    if suffix in JS_EXTENSIONS:
        return [base] + [base[:-len(suffix)] + s for s in JS_SWAP.get(suffix, ())]
    return ([base] + [base + s for s in JS_EXTENSIONS]
            + [base + '/index' + s for s in JS_EXTENSIONS])


JS_KINDS = {'function': 'function', 'class': 'class', 'interface': 'interface', 'type': 'type',
            'enum': 'enum', 'const': 'variable', 'let': 'variable', 'var': 'variable',
            'namespace': 'namespace', 'module': 'namespace'}
JS_MODIFIERS = frozenset(('export', 'default', 'declare', 'abstract', 'async'))
JS_MEMBER_MODIFIERS = frozenset(('static', 'async', 'get', 'set', 'public', 'private', 'protected',
                                 'readonly', 'override', 'abstract', 'declare', 'accessor', '*'))
JS_NOT_NAMES = frozenset(('extends', 'implements', 'from', 'of', 'in'))
CONTINUES = frozenset('.,=([+-*/%&|^!?:<>~')


def js_structure(file, content, records):
    code, strings = sanitize_js(content)
    t = Tokens(code, strings)
    scopes, paren, pending, prev = [], 0, None, None

    def imports(k):
        value = t.string(k)
        if usable(value):
            records.reference('imports', value, t.items[k][1], js_candidates(file, value), 'first')

    def export(name, k):
        if usable(name):
            identity = records.node('export', name, t.items[k][1], t.items[k][2])
            records.edge(records.file_id, identity, 'exports')

    def clause(k):
        # import/export clause: names, commas, '*' and braces up to `from "x"`.
        for j in range(k + 1, min(len(t.items), k + LOOKAHEAD)):
            value = t.value(j)
            if value == 'from' and t.string(j + 1) is not None:
                imports(j + 1)
                return
            if not (value in (',', '*', '{', '}')
                    or (t.name(j) and value not in ('import', 'export'))):
                return

    def export_list(j):
        entry = []
        for m in range(j + 1, min(len(t.items), j + LOOKAHEAD)):
            value = t.value(m)
            if value in (',', '}'):
                if entry and entry[0][0] == 'type' and len(entry) > 1:
                    entry = entry[1:]
                names = [x for x in entry if t.name(x[1])]
                if names:
                    alias = [x for i, x in enumerate(entry[:-1]) if x[0] == 'as']
                    chosen = entry[-1] if alias else names[0]
                    export(chosen[0], chosen[1])
                entry = []
                if value == '}':
                    return
            else:
                entry.append((value, m))

    def declaration(k):
        nonlocal pending
        tok = t.value(k)
        if tok == 'module' and t.value(k + 1) == '.' and t.value(k + 2) == 'exports':
            if t.value(k + 3) == '=' and t.value(k + 4) != '=':
                export('default', k)
            elif t.value(k + 3) == '.' and t.name(k + 4) and t.value(k + 5) == '=':
                export(t.name(k + 4), k + 4)
            return
        if tok == 'exports' and t.value(k + 1) == '.' and t.name(k + 2) and t.value(k + 3) == '=':
            export(t.name(k + 2), k + 2)
            return
        j, exported, default = k, False, False
        while t.value(j) in JS_MODIFIERS:
            exported = exported or t.value(j) == 'export'
            default = default or (exported and t.value(j) == 'default')
            j += 1
        if exported and j == k + 1:
            if t.value(j) == '{':
                export_list(j)
                return
            if t.value(j) == '*':
                if t.value(j + 1) == 'as' and t.name(j + 2):
                    export(t.name(j + 2), j + 2)
                return
        if default:
            export('default', k)
        keyword = t.value(j)
        if keyword == 'const' and t.value(j + 1) == 'enum':
            keyword, j = 'enum', j + 1
        kind = JS_KINDS.get(keyword)
        if kind is None:
            return
        j += 1
        if keyword == 'function' and t.value(j) == '*':
            j += 1
        name = t.name(j)
        follow = t.value(j + 1)
        if (name is None or name in JS_NOT_NAMES
                or (keyword == 'type' and follow not in ('=', '<'))
                or (kind == 'variable' and follow not in ('=', ':', ';', ',', '!', None)
                    and not t.items[j + 1][3])
                or (kind == 'namespace' and follow not in ('{', '.'))):
            return
        identity = records.node(kind, name, t.items[j][1], t.items[j][2])
        records.edge(records.file_id, identity, 'contains')
        if exported and not default:
            export(name, j)
        if kind == 'class':
            pending = (name, identity, paren, len(scopes))

    def member(k, owner):
        j, modifiers = k, []
        while t.value(j) in JS_MEMBER_MODIFIERS:
            modifiers.append(t.value(j))
            j += 1
        if t.value(j) == '#' and t.name(j + 1):
            name, after = '#' + t.name(j + 1), j + 2
        elif t.name(j):
            name, after = t.name(j), j + 1
        elif modifiers and modifiers[-1] != '*' and t.value(j) in ('(', '<'):
            name, after, j = modifiers[-1], j, j - 1
        else:
            return
        if t.value(after) in ('?', '!'):
            after += 1
        if t.value(after) in ('(', '<'):
            identity = records.node('method', owner[0] + '.' + name, t.items[j][1], t.items[j][2])
            records.edge(owner[1], identity, 'contains')

    for k, (tok, line, offset, newline) in enumerate(t.items):
        if prev != '.':
            if tok == 'import' and t.value(k + 1) == '(':
                if t.value(k + 3) in (')', ','):
                    imports(k + 2)
            elif tok == 'import' and t.string(k + 1) is not None:
                imports(k + 1)
            elif tok in ('import', 'export'):
                clause(k)
            elif tok == 'require' and t.value(k + 1) == '(' and t.value(k + 3) in (')', ','):
                imports(k + 2)
        start = prev is None or prev in (';', '{', '}') or (newline and prev not in CONTINUES)
        if start and not scopes and paren == 0:
            declaration(k)
        elif start and scopes and scopes[-1][0] is not None and paren == scopes[-1][2]:
            member(k, (scopes[-1][0], scopes[-1][1]))
        if tok == '{':
            if pending and pending[2] == paren and pending[3] == len(scopes):
                scopes.append((pending[0], pending[1], paren))
                pending = None
            else:
                scopes.append((None, None, paren))
        elif tok == '}':
            if not scopes:
                raise SyntaxError('unbalanced braces')
            scopes.pop()
        elif tok == ';' and pending and pending[2] == paren and pending[3] == len(scopes):
            pending = None
        elif tok in '([':
            paren += 1
        elif tok in ')]':
            paren -= 1
            if paren < 0:
                raise SyntaxError('unbalanced brackets')
        prev = tok
    balance(scopes, paren)


# Swift ---------------------------------------------------------------------------

SWIFT_CHUNK = re.compile(r'[^"#/()]+')
SWIFT_KINDS = {'class': 'class', 'struct': 'struct', 'enum': 'enum', 'protocol': 'protocol',
               'actor': 'actor', 'extension': 'extension', 'func': 'function'}
SWIFT_MODIFIED = frozenset(('func', 'var', 'let', 'subscript', 'init', 'deinit', 'static', 'final',
                            'override', 'required', 'convenience', 'public', 'private',
                            'fileprivate', 'internal', 'open', 'dynamic', 'mutating',
                            'nonmutating', 'lazy', 'weak', 'unowned', 'class', 'typealias',
                            'indirect'))
SWIFT_CANCEL = frozenset(SWIFT_KINDS) | frozenset(('var', 'let', 'case', 'subscript', 'init',
                                                   'deinit', 'typealias', 'associatedtype',
                                                   'import'))
SWIFT_IMPORT_KINDS = frozenset(('typealias', 'struct', 'class', 'enum', 'protocol', 'let', 'var',
                                'func'))


def swift_string(content, i, hashes, multiline):
    """Return (index after the part, ended) from inside a string literal."""
    close = ('"""' if multiline else '"') + '#' * hashes
    escape = '\\' + '#' * hashes
    j, n = i, len(content)
    while j < n:
        if content.startswith(escape, j):
            after = j + len(escape)
            if after < n and content[after] == '(':
                return after + 1, False
            j = after + 1
            continue
        if content.startswith(close, j):
            return j + len(close), True
        if content[j] == '\n' and not multiline:
            return j, True  # Unterminated single-line literal: recover at the line end.
        j += 1
    raise SyntaxError('unterminated string literal')


def sanitize_swift(content):
    out, interpolations, i, n = [], [], 0, len(content)
    while i < n:
        match = SWIFT_CHUNK.match(content, i)
        if match:
            out.append(match.group())
            i = match.end()
            continue
        c = content[i]
        if c == '/':
            if content.startswith('//', i):
                j = content.find('\n', i)
                i = n if j < 0 else j
                out.append(' ')
            elif content.startswith('/*', i):
                depth, j = 1, i + 2
                while depth:
                    opening, closing = content.find('/*', j), content.find('*/', j)
                    if closing < 0:
                        raise SyntaxError('unterminated comment')
                    if 0 <= opening < closing:
                        depth, j = depth + 1, opening + 2
                    else:
                        depth, j = depth - 1, closing + 2
                out.append(blank(content[i:j]))
                i = j
            else:
                out.append('/')
                i += 1
        elif c in '#"':
            j = i
            while j < n and content[j] == '#':
                j += 1
            if j < n and content[j] == '"':
                multiline = content.startswith('"""', j)
                hashes = j - i
                k, ended = swift_string(content, j + (3 if multiline else 1), hashes, multiline)
                out.append(blank(content[i:k]))
                out.append(' 0 ' if ended else ' ')
                if not ended:
                    interpolations.append([0, hashes, multiline])
                i = k
            else:
                out.append(content[i:j])
                i = j
        elif c == '(':
            if interpolations:
                interpolations[-1][0] += 1
            out.append('(')
            i += 1
        else:  # ')'
            if interpolations and interpolations[-1][0] == 0:
                _, hashes, multiline = interpolations.pop()
                k, ended = swift_string(content, i + 1, hashes, multiline)
                out.append(blank(content[i:k]))
                out.append(' 0 ' if ended else ' ')
                if not ended:
                    interpolations.append([0, hashes, multiline])
                i = k
                continue
            if interpolations:
                interpolations[-1][0] -= 1
            out.append(')')
            i += 1
    if interpolations:
        raise SyntaxError('unterminated string interpolation')
    return ''.join(out)


def swift_structure(file, content, records):
    t = Tokens(sanitize_swift(content))
    scopes, paren, pending, prev = [], 0, None, None  # scope: (label|None, id|None, paren)
    for k, (tok, line, offset, newline) in enumerate(t.items):
        if prev not in ('.', '\\'):
            if tok in SWIFT_CANCEL and pending and pending[2] == paren and pending[3] == len(scopes):
                pending = None
            if tok == 'import':
                j = k + 1 + (t.value(k + 1) in SWIFT_IMPORT_KINDS)
                parts = []
                while t.name(j):
                    parts.append(t.name(j))
                    if t.value(j + 1) != '.':
                        break
                    j += 2
                if parts and usable('.'.join(parts)):
                    records.reference('imports', '.'.join(parts), line, [], 'unique')
            elif (tok in SWIFT_KINDS and prev != 'import'
                  and not (tok == 'class' and t.value(k + 1) in SWIFT_MODIFIED)):
                j, parts = k + 1, []
                while t.name(j):
                    parts.append(t.name(j))
                    if tok != 'extension' or t.value(j + 1) != '.':
                        break
                    j += 2
                recordable = (all(s[0] is not None for s in scopes)
                              and paren == (scopes[-1][2] if scopes else 0))
                if parts and recordable:
                    label = '.'.join(([scopes[-1][0]] if scopes else []) + parts)
                    identity = records.node(SWIFT_KINDS[tok], label, line, offset)
                    records.edge(scopes[-1][1] if scopes else records.file_id, identity, 'contains')
                    pending = (label, identity, paren, len(scopes))
        if tok == '{':
            if pending and pending[2] == paren and pending[3] == len(scopes):
                scopes.append((pending[0], pending[1], paren))
                pending = None
            else:
                scopes.append((None, None, paren))
        elif tok == '}':
            if not scopes:
                raise SyntaxError('unbalanced braces')
            scopes.pop()
            if pending and pending[2] == paren:
                pending = None
        elif tok == ';' and pending and pending[2] == paren:
            pending = None
        elif tok in '([':
            paren += 1
        elif tok in ')]':
            paren -= 1
            if paren < 0:
                raise SyntaxError('unbalanced brackets')
        prev = tok
    balance(scopes, paren)


# Go --------------------------------------------------------------------------------

GO_CHUNK = re.compile(r'[^"`\'/]+')


def sanitize_go(content):
    out, strings, i, n = [], [], 0, len(content)
    while i < n:
        match = GO_CHUNK.match(content, i)
        if match:
            out.append(match.group())
            i = match.end()
            continue
        c = content[i]
        if c == '/':
            if content.startswith('//', i):
                j = content.find('\n', i)
                i = n if j < 0 else j
                out.append(' ')
            elif content.startswith('/*', i):
                j = content.find('*/', i + 2)
                if j < 0:
                    raise SyntaxError('unterminated comment')
                out.append(blank(content[i:j + 2]))
                i = j + 2
            else:
                out.append('/')
                i += 1
        elif c == '`':
            j = content.find('`', i + 1)
            if j < 0:
                raise SyntaxError('unterminated raw string')
            literal(out, strings, content[i + 1:j], content[i:j + 1])
            i = j + 1
        else:  # interpreted string or rune
            j, escaped = i + 1, False
            while j < n and content[j] not in (c, '\n'):
                if content[j] == '\\':
                    escaped = True
                    j += 1
                j += 1
            if j >= n or content[j] != c:
                raise SyntaxError('unterminated literal')
            if c == '"':
                literal(out, strings, None if escaped else content[i + 1:j], content[i:j + 1])
            else:
                out.append(' 0 ')
            i = j + 1
    return ''.join(out), strings


def go_structure(file, content, records):
    code, strings = sanitize_go(content)
    t = Tokens(code, strings)
    depth, paren, prev, package = 0, 0, None, False

    def imports(k):
        value = t.string(k)
        if usable(value):
            # Unresolved by design: go.mod content is not in the path index, so module-prefix
            # resolution would differ between sliced and unsliced assembly.
            records.reference('imports', value, t.items[k][1], [], 'unique')

    def declare(kind, label, k):
        if usable(label):
            identity = records.node(kind, label, t.items[k][1], t.items[k][2])
            records.edge(records.file_id, identity, 'contains')

    def group(k):
        """Yield token indexes inside a parenthesized group starting at k, with entry flags."""
        level, inner, entry = 0, 0, True
        for j in range(k, min(len(t.items), k + 64 * LOOKAHEAD)):
            value = t.value(j)
            if value in ('(', '['):
                level += 1
                if level == 1:
                    continue
            elif value in (')', ']'):
                level -= 1
                if level == 0:
                    return
            elif value == '{':
                inner += 1
            elif value == '}':
                inner -= 1
            if level == 1 and inner == 0:
                yield j, entry or t.items[j][3] or t.value(j - 1) == ';'
                entry = False

    for k, (tok, line, offset, newline) in enumerate(t.items):
        top = depth == 0 and paren == 0 and (prev is None or newline or prev == ';')
        if top and tok == 'package' and not package and t.name(k + 1):
            package = True
            declare('package', t.name(k + 1), k + 1)
        elif top and tok == 'import':
            if t.value(k + 1) == '(':
                for j, _ in group(k + 1):
                    if t.string(j) is not None:
                        imports(j)
            elif t.string(k + 1) is not None:
                imports(k + 1)
            elif t.string(k + 2) is not None and (t.name(k + 1) or t.value(k + 1) in ('.', '_')):
                imports(k + 2)
        elif top and tok == 'func':
            j, receiver = k + 1, None
            if t.value(j) == '(':
                names, level = [], 0
                while j < len(t.items):
                    value = t.value(j)
                    level += value in ('(', '[')
                    level -= value in (')', ']')
                    if value == '[' or (level == 1 and value == ','):
                        names.append(None)  # generic arguments and extra receivers end the type
                    elif level == 1 and t.name(j) and (not names or names[-1] is not None):
                        names.append(t.name(j))
                    j += 1
                    if level == 0:
                        break
                names = [x for x in names[:names.index(None)] if x] if None in names else names
                receiver = names[-1] if names else None
            name = t.name(j)
            if name and (receiver or t.value(k + 1) != '('):
                declare('method' if receiver else 'function',
                        receiver + '.' + name if receiver else name, j)
        elif top and tok == 'type':
            if t.value(k + 1) == '(':
                for j, entry in group(k + 1):
                    if entry and t.name(j):
                        declare('type', t.name(j), j)
            elif t.name(k + 1):
                declare('type', t.name(k + 1), k + 1)
        if tok == '{':
            depth += 1
        elif tok == '}':
            depth -= 1
            if depth < 0:
                raise SyntaxError('unbalanced braces')
        elif tok in '([':
            paren += 1
        elif tok in ')]':
            paren -= 1
            if paren < 0:
                raise SyntaxError('unbalanced brackets')
        prev = tok
    if depth or paren:
        raise SyntaxError('unbalanced brackets')


# Shell -----------------------------------------------------------------------------

SHELL_SOURCE = re.compile(
    r'(?:^|[;&|(]|\b(?:then|do|else|elif)\b)[ \t]*(?:source|\.)[ \t]+'
    r'((?:"[^"\n]*"|\'[^\'\n]*\'|\$\([^()\n]*(?:\([^()\n]*\)[^()\n]*)*\)|[^\s;&|()\'"])+)')
SHELL_FUNCTION = re.compile(
    r'[ \t]*(?:function[ \t]+([A-Za-z_][\w:.-]*)[ \t]*(?:\([ \t]*\))?|([A-Za-z_][\w:.-]*)[ \t]*'
    r'\([ \t]*\))[ \t]*(?:\{|\(|$)')
HEREDOC = re.compile(r'(?<!<)<<(-?)[ \t]*(["\']?)([A-Za-z_][\w.-]*)\2')
SCRIPT_DIRECTORY = re.compile(
    r'(?:\$\(\s*dirname\s+(?:\$0|\$\{0\}|\$\{BASH_SOURCE(?:\[0\])?\}|\$BASH_SOURCE)\s*\)'
    r'|\$\{BASH_SOURCE(?:\[0\])?%/\*\}|\$\{0%/\*\})/')


def shell_code(line, quote):
    """Return (line before an unquoted comment, quote state at the line end)."""
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        if quote == "'":
            if c == "'":
                quote = None
        elif quote == '"':
            if c == '\\':
                i += 1
            elif c == '"':
                quote = None
        elif c == '\\':
            i += 1
        elif c in '\'"':
            quote = c
        elif c == '#' and (i == 0 or line[i - 1] in ' \t;&|('):
            return line[:i], quote
        i += 1
    return line, quote


def shell_candidates(file, word):
    base = directory_parts(file)
    expansion = re.compile(r'[$`*?\[~{]')
    script = SCRIPT_DIRECTORY.match(word)
    if script:
        rest = word[script.end():]
        found = [] if expansion.search(rest) else [relative(base, rest)]
    elif expansion.search(word) or word.startswith('/'):
        found = []
    else:
        # `source` resolves against the caller's directory; script-relative and root-relative
        # both stay candidates, so a path present in both places is left unresolved.
        found = [relative(base, word), relative([], word)]
    return list(dict.fromkeys(x for x in found if x))


def shell_structure(file, content, records):
    quote, heredoc = None, None
    for number, line in enumerate(content.splitlines(), 1):
        if heredoc is not None:
            if (line.lstrip('\t') if heredoc[1] else line) == heredoc[0]:
                heredoc = None
            continue
        quoted = quote is not None
        code, quote = shell_code(line, quote)
        if quoted:
            continue  # The line starts inside a multi-line string.
        for match in SHELL_SOURCE.finditer(code):
            word = match.group(1).replace('"', '').replace("'", '')
            if usable(word):
                records.reference('sources', word, number, shell_candidates(file, word), 'unique')
        function = SHELL_FUNCTION.match(code)
        if function:
            name = function.group(1) or function.group(2)
            identity = records.node('function', name, number)
            records.edge(records.file_id, identity, 'contains')
        here = HEREDOC.search(code)
        if here:
            heredoc = (here.group(3), bool(here.group(1)))


# Markdown --------------------------------------------------------------------------

FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})')
ATX = re.compile(r'^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$')
SETEXT = re.compile(r'^ {0,3}(=+|-+)[ \t]*$')
DEFINITION = re.compile(r'^ {0,3}\[([^\]\n]+)\]:[ \t]*<?([^\s<>]+)>?')
INLINE = re.compile(r'(?<!!)\[[^\]\n]*\]\([ \t]*<?([^\s()<>]+)>?'
                    r'(?:[ \t]+(?:"[^"\n]*"|\'[^\'\n]*\'|\([^()\n]*\)))?[ \t]*\)')
CODE_SPAN = re.compile(r'(`+).*?\1')
LINK_TEXT = re.compile(r'!?\[([^\]\n]*)\]\([^)\n]*\)')
BLOCK_START = re.compile(r' {0,3}(?:[-*+>|]|\d+[.)])(?:\s|$)')
SCHEME = re.compile(r'^[A-Za-z][A-Za-z0-9+.-]*:')


def front_matter(lines):
    if lines and lines[0].strip() == '---':
        for number, line in enumerate(lines[1:], 2):
            if line.strip() in ('---', '...'):
                return number
    return 0


def markdown_structure(file, content, records):
    base, lines = directory_parts(file), content.splitlines()
    skip = front_matter(lines)
    fence, comment, stack, paragraph, boundary = None, False, [], None, True

    def link(target, number):
        if not usable(target) or target.startswith(('/', '#')) or SCHEME.match(target):
            return
        normalized = relative(base, target.split('#', 1)[0].split('?', 1)[0])
        records.reference('links_to', target, number, [normalized] if normalized else [], 'unique')

    def heading(level, title, number):
        label = ' '.join(LINK_TEXT.sub(r'\1', title or '').replace('`', '').split())
        if not usable(label):
            return
        while stack and stack[-1][0] >= level:
            stack.pop()
        identity = records.node('heading', label, number)
        records.edge(stack[-1][1] if stack else records.file_id, identity, 'contains')
        stack.append((level, identity))

    for number, line in enumerate(lines, 1):
        if number <= skip:
            continue
        if not comment:
            marker = FENCE.match(line)
            if marker:
                token = marker.group(1)
                if fence is None:
                    fence = token
                elif token[0] == fence[0] and len(token) >= len(fence):
                    fence = None
                paragraph, boundary = None, True
                continue
        if fence is not None:
            continue
        if comment:
            end = line.find('-->')
            if end < 0:
                continue
            comment, line = False, line[end + 3:]
        line = re.sub(r'<!--.*?-->', ' ', line)
        if '<!--' in line:
            comment, line = True, line[:line.index('<!--')]
        if not line.strip():
            paragraph, boundary = None, True
            continue
        if line.startswith(('    ', '\t')):
            paragraph, boundary = None, False
            continue
        text = CODE_SPAN.sub('', line)
        atx, underline = ATX.match(line), SETEXT.match(line)
        if atx:
            heading(len(atx.group(1)), atx.group(2), number)
            paragraph, boundary = None, True
        elif underline:
            if paragraph is not None:
                heading(1 if underline.group(1)[0] == '=' else 2, paragraph[1], paragraph[0])
            paragraph, boundary = None, True
            continue
        else:
            definition = DEFINITION.match(text)
            if definition and not definition.group(1).startswith('^'):
                link(definition.group(2), number)
                paragraph = None
            else:
                eligible = boundary and not BLOCK_START.match(line)
                paragraph = (number, line) if eligible else None
            boundary = False
        for match in INLINE.finditer(text):
            link(match.group(1), number)


# Manifests -------------------------------------------------------------------------

NPM_NAME = re.compile(r'(?:@[A-Za-z0-9~][\w.~-]*/)?[A-Za-z0-9~][\w.~-]*\Z')
PEP508_NAME = re.compile(r'\s*([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)')
GO_PATH = re.compile(r'[A-Za-z0-9][\w.~+/-]*\Z')
ACTION = re.compile(r'[A-Za-z0-9][\w.-]*(?:/[\w.-]+)+\Z')
USES = re.compile(r'^\s*(?:-\s+)?uses:\s*(["\']?)([^\s"\'#]+)\1\s*(?:#.*)?$')
BLOCK_SCALAR = re.compile(r'^(\s*)(?:-\s+)?[^#\s][^#]*?:\s*[|>][-+0-9]*\s*(?:#.*)?$')


def dependencies(records, names, pattern):
    for name in dict.fromkeys(names):
        if isinstance(name, str) and pattern.match(name) and usable(name):
            identity = records.node('dependency', name)
            records.edge(records.file_id, identity, 'depends_on')


def package_json(file, content, records):
    try:
        data = json.loads(content)
    except ValueError as exc:
        raise SyntaxError('invalid package.json') from exc
    if not isinstance(data, dict):
        raise SyntaxError('invalid package.json')
    names = []
    for section in ('dependencies', 'devDependencies', 'peerDependencies', 'optionalDependencies'):
        if isinstance(data.get(section), dict):
            names.extend(data[section])
    dependencies(records, names, NPM_NAME)


def requirement_names(values):
    for value in values if isinstance(values, list) else []:
        match = PEP508_NAME.match(value) if isinstance(value, str) else None
        if match:
            yield match.group(1)


def pyproject(file, content, records):
    if tomllib is None:
        raise NotImplementedError('tomllib unavailable')
    try:
        data = tomllib.loads(content)
    except ValueError as exc:
        raise SyntaxError('invalid pyproject.toml') from exc

    def table(value, *keys):
        for key in keys:
            value = value.get(key) if isinstance(value, dict) else None
        return value if isinstance(value, dict) else {}

    project, poetry = table(data, 'project'), table(data, 'tool', 'poetry')
    names = list(requirement_names(project.get('dependencies')))
    for values in table(project, 'optional-dependencies').values():
        names.extend(requirement_names(values))
    for values in table(data, 'dependency-groups').values():
        names.extend(requirement_names(values))
    names.extend(requirement_names(table(data, 'build-system').get('requires')))
    sections = [table(poetry, 'dependencies'), table(poetry, 'dev-dependencies')]
    sections += [table(group, 'dependencies') for group in table(poetry, 'group').values()]
    names.extend(name for section in sections for name in section if name != 'python')
    dependencies(records, names, PEP508_NAME)


def go_mod(file, content, records):
    module, names, block = None, [], None
    for number, raw_line in enumerate(content.splitlines(), 1):
        words = raw_line.split('//', 1)[0].replace('(', ' ( ').replace(')', ' ) ').split()
        if not words:
            continue
        if block is not None:
            if words[0] == ')':
                block = None
            elif block == 'require':
                names.append(words[0].strip('"`'))
            continue
        if words[0] == 'module' and len(words) == 2 and module is None:
            module = (words[1].strip('"`'), number)
        elif len(words) >= 2 and words[1] == '(':
            block = words[0]
        elif words[0] == 'require' and len(words) >= 3:
            names.append(words[1].strip('"`'))
    if module and GO_PATH.match(module[0]) and usable(module[0]):
        identity = records.node('go_module', module[0], module[1])
        records.edge(records.file_id, identity, 'contains')
    dependencies(records, names, GO_PATH)


def workflow(file, content, records):
    block = None
    for number, line in enumerate(content.splitlines(), 1):
        if block is not None:
            if not line.strip() or len(line) - len(line.lstrip(' ')) > block:
                continue
            block = None
        scalar = BLOCK_SCALAR.match(line)
        if scalar:
            block = len(scalar.group(1))
            continue
        uses = USES.match(line)
        if not uses or not usable(uses.group(2)):
            continue
        value = uses.group(2)
        if value.startswith('./'):
            # Local actions and reusable workflows resolve from the repository root.
            target = relative([], value[2:])
            if target is None:
                candidates = []
            elif target.endswith(('.yml', '.yaml')):
                candidates = [target]
            else:
                candidates = [target + '/action.yml', target + '/action.yaml']
            records.reference('uses', value, number, candidates, 'first')
            continue
        label = value if value.startswith('docker://') else value.split('@', 1)[0]
        if value.startswith('docker://') or ACTION.match(label):
            identity = records.node('action', label, number)
            records.edge(records.file_id, identity, 'uses')


def is_workflow(p):
    if p.name in ('action.yml', 'action.yaml'):
        return True
    parts = p.parts
    return (p.suffix in ('.yml', '.yaml') and len(parts) >= 3
            and parts[-3:-1] == ('.github', 'workflows'))


def handler(file):
    p = PurePosixPath(file)
    suffix = p.suffix.lower()
    if p.name == 'package.json':
        return package_json
    if p.name == 'pyproject.toml':
        return pyproject
    if p.name == 'go.mod':
        return go_mod
    if is_workflow(p):
        return workflow
    if suffix in MARKDOWN:
        return markdown_structure
    if suffix in JS_EXTENSIONS:
        return js_structure
    if suffix == '.swift':
        return swift_structure
    if suffix == '.go':
        return go_structure
    if suffix in SHELL:
        return shell_structure
    return None


def extract(file, raw, records):
    """Extract one non-Python file; unsupported types raise NotImplementedError."""
    selected = handler(file)
    if selected is None:
        raise NotImplementedError('unsupported file type')
    content = raw.decode('utf-8')
    if content.startswith('﻿'):
        content = content[1:]
    selected(file, content, records)
