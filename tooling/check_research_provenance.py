#!/usr/bin/env python3
"""Fail-closed checks for Graphify's claim-scoped research provenance."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "research" / "positive-claims.json"
RANKING_PATH = ROOT / "research" / "RANKING.md"
RAW_ROOT = ROOT / "research" / "raw"
CHECKER_PATH = Path(__file__).resolve()
HISTORICAL_RANKING_REVISION = "e1c8b4395d135b4dad3bbbbcaef6571f5425db5f"

FULL_OID_RE = re.compile(r"[0-9a-f]{40}")
LANE_RE = re.compile(r"L(100|0?[1-9]|[1-9][0-9])")
LANE_RANGE_RE = re.compile(
    r"\bL(100|0?[1-9]|[1-9][0-9])"
    r"(?:\s*[–-]\s*L?(100|0?[1-9]|[1-9][0-9]))?\b"
)
MARKER_RE = re.compile(r"<!--\s*positive-claim:\s*([A-Z0-9-]+)\s*-->")
BOUNDARY_MARKER_RE = re.compile(
    r"<!--\s*negative-boundary:\s*([A-Z0-9-]+)\s+"
    r"status=([a-z_]+)\s+claims=([A-Z0-9,-]+|none)\s*-->"
)
NORMALIZED_RAW_REFERENCE_RE = re.compile(
    r"(?i)(?:^|[^A-Za-z0-9_-])research"
    r"(?:[\\/]+(?:\.{1,2}|research))*[\\/]+raw(?:[\\/]|\b)"
)
RAW_LANE_REFERENCE_RE = re.compile(
    r"(?i)(?:^|[^A-Za-z0-9_-])(?:research[\\/]+)?raw[\\/]+"
    r"L(100|0?[1-9]|[1-9][0-9])(?:[-.\\/]|\b)"
)
CONSTRUCTED_RAW_REFERENCE_RE = re.compile(
    r'''(?is)(?:
        \b(?:Path|PurePath)\(\s*["']research["']\s*\)
            \s*/\s*["']raw["']
      | \b(?:Path|PurePath)\s*\([^\n)]{0,160}["']research["']
            \s*,\s*["']raw["']
      | \b(?:join|joinpath)\s*\([^\n)]{0,160}["']research["']
            \s*,\s*["']raw["']
      | \b(?:Path|PurePath)\(\s*["']research["']\s*\)
            \.joinpath\(\s*["']raw["']\s*\)
      | \b(?:Path|PurePath)\(\s*["']research["']\s*\)
            \s*/\s*(?:Path|PurePath)\(\s*["']raw["']\s*\)
      | ["']research["']\s*/\s*["']raw["']
      | ["']research["']\s*\+\s*["'][\\/]["']
            \s*\+\s*["']raw["']
      | ["']research["']\s*\+\s*["'][\\/]raw["']
    )''',
    re.VERBOSE,
)
CLAIM_MAP_REFERENCE_RE = re.compile(
    r'''(?is)(?:
        research[\\/]+positive-claims\.json
      | ["']research["']\s*/\s*["']positive-claims\.json["']
      | \b(?:join|joinpath)\s*\([^\n)]{0,160}["']research["']
            \s*,\s*["']positive-claims\.json["']
    )''',
    re.VERBOSE,
)
RESERVED_POSITIVE_SECTIONS = {
    "Evidence-bound experiment order",
    "Positive claims",
    "Supported synthesis",
    "Synthesis conclusion",
}
NARRATIVE_SUFFIXES = {".md", ".rst", ".adoc"}
BOUNDARY_STATUSES = {
    "scope_limit",
    "unsupported_or_unknown",
    "no_supported_claim",
}

HISTORICAL_COMPATIBILITY: dict[int, tuple[str, str]] = {
    1: ("Stable federated node identity", "Stable federated node identity"),
    2: ("SCIP→KG symbol edges", "SCIP-to-KG symbol edges"),
    3: ("Hybrid retrieval backbone", "Hybrid retrieval backbone"),
    4: (
        "Retrieval eval harness + promotion gate",
        "Retrieval evaluation harness and promotion gate",
    ),
    5: ("Unified per-corpus SQLite store", "Unified per-corpus SQLite store"),
    6: ("Consolidated read-only MCP server", "Consolidated read-only MCP server"),
    7: (
        "Splink Fellegi-Sunter ER backbone",
        "Splink entity-resolution backbone",
    ),
    8: (
        "Content-addressed incremental refresh",
        "Content-addressed incremental refresh",
    ),
    9: ("Cross-corpus RRF scatter-gather", "Cross-corpus RRF scatter-gather"),
    10: (
        "Token-budget-ledger context packing",
        "Token-budget-ledger context packing",
    ),
    11: (
        "Entity identity governance package",
        "Entity-identity governance package",
    ),
    12: ("Offline embedding model", "Offline embedding model"),
    13: ("Parquet snapshots + SQL surface", "Parquet snapshots and SQL surface"),
    14: ("Recall-first blocking engine", "Recall-first blocking engine"),
    15: (
        "ER evaluation + promotion gates without ground truth",
        "Entity-resolution evaluation and promotion gates",
    ),
    16: (
        "SQLite freshness/validation ledger",
        "SQLite freshness and validation ledger",
    ),
    17: (
        "Layered output/truncation contract",
        "Layered output and truncation contract",
    ),
    18: (
        "Shared-server auth/isolation",
        "Shared-server authentication and isolation",
    ),
    19: ("Federate-don't-merge posture", "Federate-don't-merge posture"),
    20: ("HTTP-cache freshness envelope", "HTTP-cache freshness envelope"),
}

PARTITIONS = {
    "S-A": ("research/synthesis/S-A-t1-t3.md", 1, 21),
    "S-B": ("research/synthesis/S-B-t4-t6.md", 22, 42),
    "S-C": ("research/synthesis/S-C-t7-t10.md", 43, 70),
    "S-D": ("research/synthesis/S-D-t11-t14.md", 71, 96),
    "S-E": ("research/synthesis/S-E-t15-crosscutting.md", 97, 100),
}
GROUP_IDS = [
    "GSR-COUNTS",
    "GSR-PROVENANCE",
    "GSR-ALLOWLIST",
    "GSR-CITATIONS",
    "GSR-PARTITION",
    "GSR-COMPAT",
    "GSR-PUBLIC-SAFETY",
]


class CheckFailure(RuntimeError):
    """One deterministic contract violation."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailure(message)


def git(*args: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=not binary,
    )
    if result.returncode != 0:
        stderr = (
            result.stderr.decode("utf-8", "replace")
            if binary
            else result.stderr
        )
        raise CheckFailure(f"git {' '.join(args)} failed: {stderr.strip()}")
    stdout = result.stdout
    return stdout if binary else stdout.strip()


def tracked_text_files() -> list[tuple[str, Path, str]]:
    files: list[tuple[str, Path, str]] = []
    listing = git("ls-files")
    require(isinstance(listing, str), "git file listing was not text")
    for relative in listing.splitlines():
        path = ROOT / relative
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_symlink():
            data = str(path.readlink()).encode("utf-8")
        elif path.is_file():
            data = path.read_bytes()
        else:
            continue
        if b"\0" in data:
            continue
        try:
            value = data.decode("utf-8", "strict")
        except UnicodeDecodeError:
            continue
        files.append((relative, path, value))
    return files


UNKNOWN_PATH_COMPONENT = "<unknown>"
MAX_PATH_CANDIDATES = 64


def normalized_path_components(value: str) -> list[str]:
    components: list[str] = []
    for component in value.replace("\\", "/").split("/"):
        if component in {"", "."}:
            continue
        if component == "..":
            if components and components[-1] != UNKNOWN_PATH_COMPONENT:
                components.pop()
            continue
        components.append(component.casefold())
    return components


def candidate_has_raw_path(value: str) -> bool:
    components = normalized_path_components(value)
    return any(
        components[index:index + 2] == ["research", "raw"]
        for index in range(max(0, len(components) - 1))
    )


def candidate_raw_lane_refs(value: str) -> set[str]:
    components = normalized_path_components(value)
    lanes: set[str] = set()
    for index in range(max(0, len(components) - 2)):
        if components[index:index + 2] != ["research", "raw"]:
            continue
        match = re.match(
            r"(?i)^L(100|0?[1-9]|[1-9][0-9])(?:[-.]|$)",
            components[index + 2],
        )
        if match:
            lanes.add(canonical_lane(int(match.group(1))))
    return lanes


def join_candidate_groups(
    groups: list[set[str]], separator: str
) -> set[str]:
    candidates = {""}
    for group in groups:
        options = group or {UNKNOWN_PATH_COMPONENT}
        combined: set[str] = set()
        for prefix in sorted(candidates):
            for option in sorted(options):
                if prefix and option:
                    value = prefix + separator + option
                else:
                    value = prefix or option
                if len(value) <= 4096:
                    combined.add(value)
                if len(combined) >= MAX_PATH_CANDIDATES:
                    break
            if len(combined) >= MAX_PATH_CANDIDATES:
                break
        candidates = combined
    return candidates


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


class PythonRawPathAnalyzer(ast.NodeVisitor):
    """Small bounded dataflow evaluator for explicit path construction."""

    def __init__(self, tree: ast.AST) -> None:
        self.found = False
        self.raw_lane_refs: set[str] = set()
        self.environments: list[dict[str, set[str]]] = [{}]
        self.sequences: list[dict[str, list[set[str]]]] = [{}]
        self.mappings: list[dict[str, dict[str, set[str]]]] = [{}]
        self.bound_joiners: list[dict[str, set[str]]] = [{}]
        self.path_constructors = {"Path", "PurePath"}
        self.pathlib_modules = {"pathlib"}
        self.os_modules = {"os"}
        self.path_modules = {"posixpath", "ntpath"}
        self.join_functions: set[str] = set()
        self.normalization_functions: set[str] = set()
        self._collect_import_aliases(tree)

    @property
    def environment(self) -> dict[str, set[str]]:
        return self.environments[-1]

    @property
    def sequence_environment(self) -> dict[str, list[set[str]]]:
        return self.sequences[-1]

    @property
    def mapping_environment(self) -> dict[str, dict[str, set[str]]]:
        return self.mappings[-1]

    @property
    def bound_join_environment(self) -> dict[str, set[str]]:
        return self.bound_joiners[-1]

    def _collect_import_aliases(self, tree: ast.AST) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname or alias.name.split(".")[0]
                    if alias.name == "pathlib":
                        self.pathlib_modules.add(local)
                    elif alias.name == "os":
                        self.os_modules.add(local)
                    elif alias.name in {"os.path", "posixpath", "ntpath"}:
                        self.path_modules.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    local = alias.asname or alias.name
                    if module == "pathlib" and alias.name in {"Path", "PurePath"}:
                        self.path_constructors.add(local)
                    elif module == "os" and alias.name == "path":
                        self.path_modules.add(local)
                    elif module in {"os.path", "posixpath", "ntpath"}:
                        if alias.name == "join":
                            self.join_functions.add(local)
                        elif alias.name in {
                            "normpath", "abspath", "realpath", "relpath"
                        }:
                            self.normalization_functions.add(local)

    def _callable_kind(self, node: ast.AST) -> str | None:
        name = dotted_name(node)
        if name is None:
            return None
        if name in self.path_constructors:
            return "constructor"
        parts = name.split(".")
        if (
            len(parts) == 2
            and parts[0] in self.pathlib_modules
            and parts[1] in {"Path", "PurePath"}
        ):
            return "constructor"
        if name in self.join_functions:
            return "join"
        if name in self.normalization_functions:
            return "normalize"
        if len(parts) >= 2 and parts[-1] == "join":
            if parts[0] in self.path_modules:
                return "join"
            if len(parts) >= 3 and parts[0] in self.os_modules and parts[-2] == "path":
                return "join"
        if len(parts) >= 2 and parts[-1] in {
            "normpath", "abspath", "realpath", "relpath"
        }:
            if parts[0] in self.path_modules:
                return "normalize"
            if len(parts) >= 3 and parts[0] in self.os_modules and parts[-2] == "path":
                return "normalize"
        return None

    def _argument_groups(self, arguments: list[ast.AST]) -> list[set[str]]:
        groups: list[set[str]] = []
        for argument in arguments:
            if (
                isinstance(argument, ast.Starred)
                and isinstance(argument.value, ast.Name)
                and argument.value.id in self.sequence_environment
            ):
                groups.extend(self.sequence_environment[argument.value.id])
            else:
                groups.append(self._evaluate(argument))
        return groups

    def _evaluate(self, node: ast.AST | None) -> set[str]:
        if node is None:
            return set()
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return {node.value}
        if isinstance(node, ast.Name):
            return set(self.environment.get(node.id, set()))
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            key: str | int | None = None
            if isinstance(node.slice, ast.Constant):
                key = node.slice.value
            if isinstance(key, str):
                return set(
                    self.mapping_environment.get(node.value.id, {}).get(key, set())
                )
            if isinstance(key, int):
                sequence = self.sequence_environment.get(node.value.id, [])
                if -len(sequence) <= key < len(sequence):
                    return set(sequence[key])
            return set()
        if isinstance(node, ast.JoinedStr):
            groups: list[set[str]] = []
            for part in node.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    groups.append({part.value})
                elif isinstance(part, ast.FormattedValue):
                    groups.append(self._evaluate(part.value))
            return join_candidate_groups(groups, "")
        if isinstance(node, ast.IfExp):
            return self._evaluate(node.body) | self._evaluate(node.orelse)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return join_candidate_groups(
                [self._evaluate(node.left), self._evaluate(node.right)], "/"
            )
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return join_candidate_groups(
                [self._evaluate(node.left), self._evaluate(node.right)], ""
            )
        if isinstance(node, ast.Call):
            kind = self._callable_kind(node.func)
            if kind == "constructor":
                return join_candidate_groups(self._argument_groups(node.args), "/")
            if kind == "join":
                return join_candidate_groups(self._argument_groups(node.args), "/")
            if kind == "normalize":
                return self._evaluate(node.args[0]) if node.args else set()
            if isinstance(node.func, ast.Name) and node.func.id in self.bound_join_environment:
                return join_candidate_groups(
                    [set(self.bound_join_environment[node.func.id])]
                    + self._argument_groups(node.args),
                    "/",
                )
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == "joinpath":
                    return join_candidate_groups(
                        [self._evaluate(node.func.value)]
                        + self._argument_groups(node.args),
                        "/",
                    )
                if node.func.attr in {"resolve", "absolute"}:
                    return self._evaluate(node.func.value)
        return set()

    def _mark(self, values: set[str]) -> None:
        for value in values:
            if candidate_has_raw_path(value):
                self.found = True
                self.raw_lane_refs.update(candidate_raw_lane_refs(value))

    def _bind_name(self, name: str, value_node: ast.AST, values: set[str]) -> None:
        self.environment[name] = set(values)
        self.sequence_environment.pop(name, None)
        self.mapping_environment.pop(name, None)
        self.bound_join_environment.pop(name, None)
        self.path_constructors.discard(name)
        self.join_functions.discard(name)
        self.normalization_functions.discard(name)

        if isinstance(value_node, (ast.List, ast.Tuple)):
            self.sequence_environment[name] = [
                self._evaluate(element) for element in value_node.elts
            ]
        elif isinstance(value_node, ast.Dict):
            mapping: dict[str, set[str]] = {}
            for key_node, item_node in zip(value_node.keys, value_node.values):
                if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                    mapping[key_node.value] = self._evaluate(item_node)
            self.mapping_environment[name] = mapping

        kind = self._callable_kind(value_node)
        if kind == "constructor":
            self.path_constructors.add(name)
        elif kind == "join":
            self.join_functions.add(name)
        elif kind == "normalize":
            self.normalization_functions.add(name)
        elif isinstance(value_node, ast.Attribute) and value_node.attr == "joinpath":
            self.bound_join_environment[name] = self._evaluate(value_node.value)

    def _bind_target(self, target: ast.AST, value_node: ast.AST, values: set[str]) -> None:
        if isinstance(target, ast.Name):
            self._bind_name(target.id, value_node, values)
        elif (
            isinstance(target, (ast.Tuple, ast.List))
            and isinstance(value_node, (ast.Tuple, ast.List))
            and len(target.elts) == len(value_node.elts)
        ):
            for child_target, child_value in zip(target.elts, value_node.elts):
                self._bind_target(child_target, child_value, self._evaluate(child_value))

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        values = self._evaluate(node.value)
        self._mark(values)
        for target in node.targets:
            self._bind_target(target, node.value, values)
        self.visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
        values = self._evaluate(node.value)
        self._mark(values)
        if node.value is not None:
            self._bind_target(node.target, node.value, values)
            self.visit(node.value)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:  # noqa: N802
        values = self._evaluate(node.value)
        self._mark(values)
        self._bind_target(node.target, node.value, values)
        self.visit(node.value)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        self._mark(self._evaluate(node))
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:  # noqa: N802
        self._mark(self._evaluate(node))
        self.generic_visit(node)

    def _visit_local_scope(self, body: list[ast.stmt]) -> None:
        self.environments.append(dict(self.environment))
        self.sequences.append(dict(self.sequence_environment))
        self.mappings.append(dict(self.mapping_environment))
        self.bound_joiners.append(dict(self.bound_join_environment))
        try:
            for statement in body:
                self.visit(statement)
        finally:
            self.environments.pop()
            self.sequences.pop()
            self.mappings.pop()
            self.bound_joiners.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                self.visit(default)
        self._visit_local_scope(node.body)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self._visit_local_scope(node.body)


def python_raw_path_analysis(value: str) -> tuple[bool, set[str]]:
    try:
        tree = ast.parse(value)
    except (SyntaxError, ValueError):
        return False, set()
    analyzer = PythonRawPathAnalyzer(tree)
    analyzer.visit(tree)
    return analyzer.found, analyzer.raw_lane_refs


def python_contains_raw_path(value: str) -> bool:
    return python_raw_path_analysis(value)[0]


def contains_raw_source_reference(value: str) -> bool:
    if (
        NORMALIZED_RAW_REFERENCE_RE.search(value)
        or RAW_LANE_REFERENCE_RE.search(value)
        or CONSTRUCTED_RAW_REFERENCE_RE.search(value)
    ):
        return True
    lowered = value.casefold()
    return (
        "research" in lowered
        and "raw" in lowered
        and python_contains_raw_path(value)
    )


def literal_raw_lane_refs(value: str) -> set[str]:
    direct = {
        canonical_lane(int(match.group(1)))
        for match in RAW_LANE_REFERENCE_RE.finditer(value)
    }
    return direct | python_raw_path_analysis(value)[1]


def contains_claim_map_reference(value: str) -> bool:
    return CLAIM_MAP_REFERENCE_RE.search(value) is not None


def raw_reference_role(path: Path) -> str:
    return "reference" if path.suffix.lower() in NARRATIVE_SUFFIXES else "consumer"


def canonical_lane(number: int) -> str:
    require(1 <= number <= 100, f"lane number out of range: {number}")
    return f"L{number:02d}" if number < 100 else "L100"


def parse_lane_refs(value: str) -> list[str]:
    lanes: list[str] = []
    seen: set[str] = set()
    for match in LANE_RANGE_RE.finditer(value):
        start = int(match.group(1))
        end = int(match.group(2) or match.group(1))
        require(end >= start, f"descending lane range: {match.group(0)}")
        for number in range(start, end + 1):
            lane = canonical_lane(number)
            if lane not in seen:
                lanes.append(lane)
                seen.add(lane)
    return lanes


def markdown_cells(line: str) -> list[str]:
    stripped = line.strip()
    require(stripped.startswith("|") and stripped.endswith("|"),
            f"not a Markdown table row: {line}")
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def strip_backticks(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == "`":
        return value[1:-1]
    return value


def strip_marker(value: str) -> str:
    return MARKER_RE.sub("", value).strip()


def is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(
        re.fullmatch(r":?-{3,}:?", cell) is not None for cell in cells
    )


def boundary_records_by_id(
    manifest: dict[str, Any],
    claims: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    raw_records = manifest.get("negative_boundaries")
    require(isinstance(raw_records, list),
            "claim map must contain a negative_boundaries list")
    records: dict[str, dict[str, Any]] = {}
    for record in raw_records:
        require(isinstance(record, dict), "negative boundary record is not an object")
        boundary_id = record.get("id")
        require(
            isinstance(boundary_id, str)
            and re.fullmatch(r"BND-[A-Z0-9-]+", boundary_id) is not None,
            f"invalid negative boundary ID: {boundary_id!r}",
        )
        require(boundary_id not in records,
                f"duplicate negative boundary ID: {boundary_id}")
        require(record.get("form") in {"paragraph", "conclusion"},
                f"{boundary_id} has an unsupported boundary form")
        status = record.get("status")
        require(status in BOUNDARY_STATUSES,
                f"{boundary_id} has an unsupported status: {status!r}")
        claim_ids = record.get("claim_ids")
        require(
            isinstance(claim_ids, list)
            and len(claim_ids) == len(set(claim_ids)),
            f"{boundary_id} claim_ids must be a unique list",
        )
        for claim_id in claim_ids:
            require(claim_id in claims,
                    f"{boundary_id} names unknown positive claim {claim_id}")
            require(claims[claim_id]["consumer"] == record.get("consumer"),
                    f"{boundary_id} claim {claim_id} has another consumer")
            require(claims[claim_id]["section"] == record.get("section"),
                    f"{boundary_id} claim {claim_id} has another section")
        require(
            status != "no_supported_claim" or not claim_ids,
            f"{boundary_id} no_supported_claim status cannot name claims",
        )
        require(
            record.get("form") != "conclusion"
            or status == "unsupported_or_unknown",
            f"{boundary_id} conclusion boundary has the wrong status",
        )
        statement = record.get("statement")
        require(
            isinstance(statement, str)
            and statement.strip() == statement
            and statement
            and "\n" not in statement,
            f"{boundary_id} statement must be one canonical logical line",
        )
        require(isinstance(record.get("consumer"), str),
                f"{boundary_id} has no consumer")
        require(isinstance(record.get("section"), str),
                f"{boundary_id} has no section")
        records[boundary_id] = record
    return records


def parse_boundary_claim_ids(value: str) -> list[str]:
    return [] if value == "none" else value.split(",")


def parse_negative_boundary_blocks(
    relative: str,
    text: str,
    records: dict[str, dict[str, Any]],
) -> tuple[Counter[str], dict[int, str]]:
    lines = text.splitlines()
    expected = {
        boundary_id: record
        for boundary_id, record in records.items()
        if record["consumer"] == relative
    }
    observed: Counter[str] = Counter()
    covered_lines: dict[int, str] = {}
    section: str | None = None
    index = 0
    while index < len(lines):
        line = lines[index]
        heading = re.match(r"^## (.+)$", line)
        if heading:
            section = heading.group(1).strip()
            index += 1
            continue
        if "negative-boundary:" not in line:
            index += 1
            continue

        marker = BOUNDARY_MARKER_RE.fullmatch(line)
        require(marker is not None,
                f"{relative}:{index + 1} has a malformed boundary marker")
        boundary_id, status, marker_claims = marker.groups()
        require(boundary_id in expected,
                f"{relative}:{index + 1} has unregistered boundary {boundary_id}")
        record = expected[boundary_id]
        require(section == record["section"],
                f"{boundary_id} appears in section {section!r}, "
                f"expected {record['section']!r}")
        require(status == record["status"],
                f"{boundary_id} marker status differs from claim map")
        require(parse_boundary_claim_ids(marker_claims) == record["claim_ids"],
                f"{boundary_id} marker claim IDs differ from claim map")
        observed[boundary_id] += 1
        covered_lines[index + 1] = boundary_id

        block_index = index + 1
        require(block_index < len(lines) and lines[block_index].strip(),
                f"{boundary_id} has no governed block")
        logical_lines: list[str] = []
        if record["form"] == "conclusion":
            prefix = "- Unsupported/unknown: "
            require(lines[block_index].startswith(prefix),
                    f"{boundary_id} conclusion block lacks its exact prefix")
            logical_lines.append(lines[block_index].removeprefix(prefix).strip())
            covered_lines[block_index + 1] = boundary_id
            block_index += 1
            while block_index < len(lines):
                continuation = lines[block_index]
                if (
                    not continuation.strip()
                    or re.match(r"^## ", continuation)
                    or "negative-boundary:" in continuation
                ):
                    break
                logical_lines.append(continuation.strip())
                covered_lines[block_index + 1] = boundary_id
                block_index += 1
        else:
            while block_index < len(lines):
                continuation = lines[block_index]
                if (
                    not continuation.strip()
                    or continuation.startswith("|")
                    or re.match(r"^## ", continuation)
                    or "negative-boundary:" in continuation
                ):
                    break
                require(not continuation.startswith("- Supported: "),
                        f"{boundary_id} paragraph contains a positive claim line")
                logical_lines.append(continuation.strip())
                covered_lines[block_index + 1] = boundary_id
                block_index += 1

        require(" ".join(logical_lines) == record["statement"],
                f"{boundary_id} complete block differs from claim map")
        index = block_index
    return observed, covered_lines


def validate_positive_section_structure(
    relative: str,
    text: str,
    sections: set[str],
    covered_lines: dict[int, str],
) -> None:
    section: str | None = None
    seen_sections: set[str] = set()
    for line_number, line in enumerate(text.splitlines(), start=1):
        heading = re.match(r"^## (.+)$", line)
        if heading:
            section = heading.group(1).strip()
            if section in sections:
                seen_sections.add(section)
            continue
        if section not in sections or not line.strip():
            continue
        if line_number in covered_lines:
            continue
        require(line.startswith("|"),
                f"{relative}:{line_number} ungoverned positive-section prose")
        cells = markdown_cells(line)
        if is_separator_row(cells) or cells[0] in {"Order", "Supported statement"}:
            continue
        require(MARKER_RE.search(line) is not None,
                f"{relative}:{line_number} positive row lacks a claim marker")
    require(seen_sections == sections,
            f"{relative} positive sections differ: "
            f"missing={sorted(sections - seen_sections)}")


def validate_governed_conclusion(
    relative: str,
    text: str,
    section_name: str,
    claims: dict[str, dict[str, Any]],
    records: dict[str, dict[str, Any]],
    covered_lines: dict[int, str],
) -> None:
    body: list[tuple[int, str]] = []
    in_section = False
    heading_count = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        heading = re.match(r"^## (.+)$", line)
        if heading:
            current = heading.group(1).strip()
            in_section = current == section_name
            if in_section:
                heading_count += 1
            continue
        if in_section:
            body.append((line_number, line))

    require(heading_count == 1,
            f"{relative} must contain exactly one {section_name!r} section")
    expected_claims = {
        claim_id
        for claim_id, claim in claims.items()
        if claim["consumer"] == relative
        and claim["section"] == section_name
        and claim.get("form", "table_row") == "prose"
    }
    conclusion_records = {
        boundary_id: record
        for boundary_id, record in records.items()
        if record["consumer"] == relative
        and record["section"] == section_name
        and record["form"] == "conclusion"
    }
    require(len(conclusion_records) == 1,
            f"{relative} conclusion must have exactly one boundary record")
    bound_claims = {
        claim_id
        for record in conclusion_records.values()
        for claim_id in record["claim_ids"]
    }
    require(bound_claims == expected_claims,
            f"{relative} conclusion boundary claim IDs differ: "
            f"missing={sorted(expected_claims - bound_claims)} "
            f"extra={sorted(bound_claims - expected_claims)}")

    observed_claims: set[str] = set()
    observed_boundaries: set[str] = set()
    supported_lines = 0
    supported_none = False
    for line_number, line in body:
        if not line.strip():
            continue
        if line_number in covered_lines:
            observed_boundaries.add(covered_lines[line_number])
            continue
        if line == "- Supported: none.":
            supported_lines += 1
            supported_none = True
            continue
        if line.startswith("- Supported: "):
            supported_lines += 1
            markers = MARKER_RE.findall(line)
            require(len(markers) == 1,
                    f"{relative}:{line_number} supported conclusion must have "
                    "one registered claim marker")
            claim_id = markers[0]
            require(claim_id in claims,
                    f"{relative}:{line_number} has unknown claim {claim_id}")
            claim = claims[claim_id]
            require(claim.get("form") == "prose",
                    f"{claim_id} conclusion claim is not form=prose")
            require(claim["consumer"] == relative,
                    f"{claim_id} conclusion consumer differs")
            require(claim["section"] == section_name,
                    f"{claim_id} conclusion section differs")
            statement = strip_marker(line.removeprefix("- Supported: "))
            require(statement == claim["statement"],
                    f"{claim_id} conclusion statement differs from claim map")
            observed_claims.add(claim_id)
            continue
        raise CheckFailure(
            f"{relative}:{line_number} ungoverned conclusion prose: {line!r}"
        )

    require(supported_lines == 1,
            f"{relative} conclusion must have exactly one Supported line")
    require(observed_boundaries == set(conclusion_records),
            f"{relative} conclusion boundary coverage differs")
    require(not (supported_none and observed_claims),
            f"{relative} conclusion mixes Supported:none with positive claims")
    require(observed_claims == expected_claims,
            f"{relative} conclusion claims differ: "
            f"missing={sorted(expected_claims - observed_claims)} "
            f"extra={sorted(observed_claims - expected_claims)}")


def validate_scip_contract(pilot: str, requirements: str) -> None:
    normalized_pilot = " ".join(pilot.split())
    for required in (
        "Protocol state: unexecutable",
        "exact Graphify tool revision",
        "tooling/scip_convert.py",
        "tooling/validate.py",
        "shell and every control-plane binary",
        "dynamic loader, shared libraries, plugins, helper scripts",
        "mode `120000`",
        "mode `160000`",
        "locked `mktemp -d`",
        "cleanup trap",
        "empty destination",
        "reject every symlink",
        "credential-free filesystem sandbox",
        "no host, home, or protected-repository mounts",
        "must not be a host bind mount",
        "mount table",
        "Network access must be denied",
        "Every pilot stage and every descendant",
        "complete local, non-promisor",
        "any lazy fetch path",
        "Use a private process namespace",
        "Deny the host `/proc`",
        "Drop every capability",
        "no-new-privileges",
        "PID-count, CPU-time, memory, output-file-size",
        "pre-locked patch",
        "complete expected post-patch fixture manifest",
        "every final relative path with its entry type, mode, byte count, and cryptographic digest",
        "immediately before indexing",
        "read-only immutable snapshot",
        "Authority effect: none",
    ):
        require(required in normalized_pilot,
                f"SCIP protocol lacks required gate: {required}")
    normalized_requirements = re.sub(r"\n#[ \t]?", " ", requirements)
    require("leaves the protocol unexecutable" in normalized_requirements,
            "SCIP requirements do not fail closed on an incomplete run lock")
    for required in (
        "complete local non-promisor source-object closure",
        "pre-locked fixture patch",
        "complete expected final fixture manifest",
        "all-stage sandbox/network/mount/process/privilege",
        "finite resource-bound configuration for every descendant",
    ):
        require(required in normalized_requirements,
                f"SCIP requirements lack required gate: {required}")

    combined = pilot + "\n" + requirements
    prohibited = {
        "absolute home path": r"/home/[^\s`]+",
        "unbound archive": r"archive\s+HEAD\b",
        "remote Python bootstrap": r"get-pip\.py",
        "executable npx resolution": r"\bnpx\s+(?:-y|--yes)\b",
        "executable npm install": r"^[ \t]*(?:\$[ \t]+)?npm[ \t]+(?:install|exec)\b",
        "executable Python install": r"^[ \t]*(?:\$[ \t]+)?(?:python\S*\s+-m\s+)?pip\s+install\b",
        "network fetch recipe": r"^[ \t]*(?:\$[ \t]+)?(?:curl|wget)\s+",
        "predictable SCIP temp path": r"/tmp/scip(?:-|/)",
        "runnable shell block": r"```(?:ba|z)?sh\b",
        "recorded result table": r"^## Recorded pilot results",
        "embedded graph counts": r"\b(?:nodes|links)\s*=\s*\d+",
    }
    for label, pattern in prohibited.items():
        require(re.search(pattern, combined, re.MULTILINE) is None,
                f"SCIP protocol contains {label}")


def expect_failure(operation: Callable[[], None], label: str) -> None:
    try:
        operation()
    except CheckFailure:
        return
    raise CheckFailure(f"adversarial case did not fail closed: {label}")


def load_manifest() -> tuple[dict[str, Any], str]:
    raw = MANIFEST_PATH.read_bytes()
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as error:
        raise CheckFailure(f"invalid {MANIFEST_PATH.relative_to(ROOT)}: {error}")
    require(manifest.get("schema_version") == 1, "unsupported claim-map schema")
    require(manifest.get("authority_effect") == "none",
            "claim map must retain authority_effect=none")
    validator = manifest.get("validator", {})
    require(validator.get("path") == "tooling/check_research_provenance.py",
            "claim map names a different validator")
    require(validator.get("repository_check") == [
        "python3", "tooling/check_research_provenance.py"
    ], "claim map repository invocation differs")
    require(validator.get("self_test") == [
        "python3", "tooling/check_research_provenance.py", "--self-test"
    ], "claim map self-test invocation differs")
    require(validator.get("group_ids") == GROUP_IDS,
            "claim map affected-check group IDs differ")
    governed = manifest.get("governed_conclusion_sections", {})
    expected_consumers = {relative for relative, _, _ in PARTITIONS.values()}
    require(set(governed) == expected_consumers,
            "governed conclusion consumers differ from synthesis partitions")
    require(set(governed.values()) == {"Synthesis conclusion"},
            "every governed conclusion must use the Synthesis conclusion heading")
    for field in ("raw_consumer_files", "raw_reference_files"):
        values = manifest.get(field)
        require(isinstance(values, list) and len(values) == len(set(values)),
                f"{field} must be a unique path list")
    return manifest, hashlib.sha256(raw).hexdigest()


def parse_ranking_rows() -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for line_number, line in enumerate(
        RANKING_PATH.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not re.match(r"^\| L(?:[0-9]{2}|100) \|", line):
            continue
        cells = markdown_cells(line)
        require(len(cells) == 8,
                f"ranking source-map row {line_number} has {len(cells)} cells")
        lane = cells[0]
        require(LANE_RE.fullmatch(lane) is not None,
                f"invalid lane ID at ranking line {line_number}: {lane}")
        require(lane not in rows, f"duplicate ranking lane: {lane}")
        rows[lane] = {
            "path": strip_backticks(cells[1]),
            "class": strip_backticks(cells[3]),
            "reviewed_revision": strip_backticks(cells[4]),
            "input_blob_oid": strip_backticks(cells[5]),
            "input_sha256": strip_backticks(cells[6]),
        }
    expected = {canonical_lane(number) for number in range(1, 101)}
    require(set(rows) == expected,
            f"ranking lane set mismatch: missing={sorted(expected - set(rows))} "
            f"extra={sorted(set(rows) - expected)}")
    return rows


def check_counts(manifest: dict[str, Any], rows: dict[str, dict[str, str]]) -> str:
    expected_counts = manifest["expected_class_counts"]
    actual_counts = Counter(row["class"] for row in rows.values())
    require(dict(actual_counts) == expected_counts,
            f"class counts differ: actual={dict(actual_counts)} "
            f"expected={expected_counts}")
    require(sum(expected_counts.values()) == 100, "class counts do not total 100")

    files = sorted(RAW_ROOT.glob("L*.md"))
    file_lanes: set[str] = set()
    for path in files:
        match = re.match(r"L(100|0?[1-9]|[1-9][0-9])(?:-|\.md$)", path.name)
        require(match is not None, f"unparseable raw lane filename: {path.name}")
        lane = canonical_lane(int(match.group(1)))
        require(lane not in file_lanes, f"duplicate raw lane file for {lane}")
        file_lanes.add(lane)
    expected_files = {lane for lane, row in rows.items() if row["class"] != "missing"}
    require(file_lanes == expected_files,
            f"raw filename inventory differs: missing={sorted(expected_files - file_lanes)} "
            f"extra={sorted(file_lanes - expected_files)}")
    require(len(files) == 95, f"expected 95 raw lane files, found {len(files)}")
    return f"lanes=100 files=95 classes={dict(actual_counts)}"


def check_provenance(manifest: dict[str, Any], rows: dict[str, dict[str, str]]) -> str:
    source_revision = manifest["source_revision"]
    reviewed_revision = manifest["reviewed_revision"]
    require(FULL_OID_RE.fullmatch(source_revision) is not None,
            "source_revision is not a full commit ID")
    require(FULL_OID_RE.fullmatch(reviewed_revision) is not None,
            "reviewed_revision is not a full commit ID")
    require(git("rev-parse", f"{source_revision}^{{commit}}") == source_revision,
            "source_revision does not resolve exactly")
    require(git("rev-parse", f"{reviewed_revision}^{{commit}}") == reviewed_revision,
            "reviewed_revision does not resolve exactly")

    ranking_text = RANKING_PATH.read_text(encoding="utf-8")
    require(f"Candidate raw-input revision: `{source_revision}`." in ranking_text,
            "ranking candidate revision is not bound to the claim map")

    allowlisted = manifest["allowlisted_lanes"]
    validated = {lane for lane, row in rows.items() if row["class"] == "validated"}
    require(set(allowlisted) == validated,
            f"allowlist differs from validated rows: "
            f"missing={sorted(validated - set(allowlisted))} "
            f"extra={sorted(set(allowlisted) - validated)}")

    reviewed_blobs = 0
    excluded_blobs = 0
    for lane, row in rows.items():
        require(row["reviewed_revision"] == reviewed_revision,
                f"{lane} has a different reviewed revision")
        if row["class"] == "missing":
            require(row["input_blob_oid"] == row["input_sha256"] == "-",
                    f"{lane} missing row carries blob identity")
            continue

        path = row["path"]
        require((ROOT / path).is_file(), f"{lane} path missing: {path}")
        reviewed_oid = git("rev-parse", f"{reviewed_revision}:{path}")
        require(reviewed_oid == row["input_blob_oid"],
                f"{lane} reviewed blob OID mismatch")
        reviewed_bytes = git("show", f"{reviewed_revision}:{path}", binary=True)
        require(hashlib.sha256(reviewed_bytes).hexdigest() == row["input_sha256"],
                f"{lane} reviewed SHA-256 mismatch")
        reviewed_blobs += 1

        if row["class"] == "excluded_not_public_safe":
            working_oid = git("hash-object", "--", path)
            require(working_oid == row["input_blob_oid"],
                    f"{lane} excluded blob changed from reviewed bytes")
            excluded_blobs += 1

    for lane, entry in allowlisted.items():
        path = entry["path"]
        require(rows[lane]["path"] == path, f"{lane} allowlist path mismatch")
        source_oid = git("rev-parse", f"{source_revision}:{path}")
        require(source_oid == entry["blob_oid"],
                f"{lane} source-revision blob OID mismatch")
        require(git("hash-object", "--", path) == entry["blob_oid"],
                f"{lane} working bytes differ from the allowlisted source blob")

    for synthesis_path, _, _ in PARTITIONS.values():
        text = (ROOT / synthesis_path).read_text(encoding="utf-8")
        require(
            re.findall(r"Exact raw-input revision: `([0-9a-f]{40})`\.", text)
            == [source_revision],
            f"{synthesis_path} source binding differs from claim map",
        )
    return (
        f"source={source_revision} reviewed_blobs={reviewed_blobs} "
        f"excluded_byte_exact={excluded_blobs} allowlisted={len(allowlisted)}"
    )


def claims_by_id(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    claims: dict[str, dict[str, Any]] = {}
    for claim in manifest["claims"]:
        claim_id = claim["id"]
        require(re.fullmatch(r"(?:EXP|S[A-E])-\d{2}", claim_id) is not None,
                f"invalid claim ID: {claim_id}")
        require(claim_id not in claims, f"duplicate claim ID: {claim_id}")
        require(claim.get("form", "table_row") in {"table_row", "prose"},
                f"{claim_id} has an unsupported form")
        require(isinstance(claim.get("statement"), str) and claim["statement"],
                f"{claim_id} has no statement")
        require(isinstance(claim.get("consumer"), str),
                f"{claim_id} has no consumer")
        require(isinstance(claim.get("section"), str),
                f"{claim_id} has no section")
        claims[claim_id] = claim
    return claims


def check_allowlist(manifest: dict[str, Any], rows: dict[str, dict[str, str]]) -> str:
    claims = claims_by_id(manifest)
    allowlisted = manifest["allowlisted_lanes"]
    reciprocal: dict[str, set[str]] = defaultdict(set)
    for claim_id, claim in claims.items():
        require(claim["lanes"], f"{claim_id} has no supporting lane")
        require(len(claim["lanes"]) == len(set(claim["lanes"])),
                f"{claim_id} repeats a lane")
        for lane in claim["lanes"]:
            require(lane in allowlisted,
                    f"{claim_id} uses non-allowlisted lane {lane}")
            require(rows[lane]["class"] == "validated",
                    f"{claim_id} uses lane {lane} with class {rows[lane]['class']}")
            reciprocal[lane].add(claim_id)

    for lane, entry in allowlisted.items():
        require(set(entry["claim_ids"]) == reciprocal[lane],
                f"{lane} reciprocal claim IDs differ: "
                f"map={entry['claim_ids']} claims={sorted(reciprocal[lane])}")

    boundary_records = boundary_records_by_id(manifest, claims)
    boundary_consumers = {
        record["consumer"] for record in boundary_records.values()
    }
    marker_consumers: set[str] = set()
    for path in ROOT.rglob("*.md"):
        if ".git" in path.parts:
            continue
        if "negative-boundary:" in path.read_text(encoding="utf-8"):
            marker_consumers.add(path.relative_to(ROOT).as_posix())
    require(marker_consumers.issubset(boundary_consumers),
            f"unregistered boundary marker consumers: "
            f"{sorted(marker_consumers - boundary_consumers)}")

    found_boundaries: Counter[str] = Counter()
    boundary_coverage: dict[str, dict[int, str]] = {}
    for relative in sorted(boundary_consumers):
        path = ROOT / relative
        require(path.is_file(), f"negative boundary consumer missing: {relative}")
        observed, covered = parse_negative_boundary_blocks(
            relative,
            path.read_text(encoding="utf-8"),
            boundary_records,
        )
        found_boundaries.update(observed)
        boundary_coverage[relative] = covered
    require(set(found_boundaries) == set(boundary_records),
            f"negative boundary markers differ: "
            f"missing={sorted(set(boundary_records) - set(found_boundaries))} "
            f"extra={sorted(set(found_boundaries) - set(boundary_records))}")
    require(all(count == 1 for count in found_boundaries.values()),
            f"negative boundary markers are not unique: {dict(found_boundaries)}")

    found: Counter[str] = Counter()
    positive_sections = {
        path: set(sections)
        for path, sections in manifest["positive_sections"].items()
    }
    governed_conclusions: dict[str, str] = manifest[
        "governed_conclusion_sections"
    ]
    for path in ROOT.rglob("*.md"):
        if ".git" in path.parts:
            continue
        relative = path.relative_to(ROOT).as_posix()
        section: str | None = None
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            heading = re.match(r"^## (.+)$", line)
            if heading:
                section = heading.group(1).strip()
                if section in RESERVED_POSITIVE_SECTIONS:
                    registered = (
                        section in positive_sections.get(relative, set())
                        or governed_conclusions.get(relative) == section
                    )
                    require(
                        registered,
                        f"{relative}:{line_number} has an unregistered "
                        f"positive section {section!r}",
                    )
            markers = MARKER_RE.findall(line)
            if not markers:
                continue
            require(len(markers) == 1,
                    f"{relative}:{line_number} has multiple claim markers")
            claim_id = markers[0]
            require(claim_id in claims,
                    f"{relative}:{line_number} has unknown claim {claim_id}")
            claim = claims[claim_id]
            require(relative == claim["consumer"],
                    f"{claim_id} appears in {relative}, expected {claim['consumer']}")
            require(section == claim["section"],
                    f"{claim_id} appears in section {section!r}, "
                    f"expected {claim['section']!r}")
            form = claim.get("form", "table_row")
            if form == "prose":
                require(line.startswith("- Supported: "),
                        f"{relative}:{line_number} prose claim is outside the "
                        "governed Supported conclusion form")
                statement = strip_marker(line.removeprefix("- Supported: "))
                require(statement == claim["statement"],
                        f"{claim_id} statement differs from claim map")
            else:
                cells = markdown_cells(line)
                if relative == "research/RANKING.md":
                    statement_column, lane_column = 1, 2
                else:
                    statement_column, lane_column = 0, 1
                require(len(cells) > lane_column,
                        f"{relative}:{line_number} claim row is too short")
                require(strip_marker(cells[statement_column]) == claim["statement"],
                        f"{claim_id} statement differs from claim map")
                require(parse_lane_refs(cells[lane_column]) == claim["lanes"],
                        f"{claim_id} lane list differs from claim map")
            found[claim_id] += 1

    require(set(found) == set(claims),
            f"claim markers differ: missing={sorted(set(claims) - set(found))} "
            f"extra={sorted(set(found) - set(claims))}")
    require(all(count == 1 for count in found.values()),
            f"claim markers are not unique: {dict(found)}")

    for relative, sections in positive_sections.items():
        path = ROOT / relative
        require(path.is_file(), f"positive consumer missing: {relative}")
        validate_positive_section_structure(
            relative,
            path.read_text(encoding="utf-8"),
            sections,
            boundary_coverage.get(relative, {}),
        )

    for relative, section_name in governed_conclusions.items():
        validate_governed_conclusion(
            relative,
            (ROOT / relative).read_text(encoding="utf-8"),
            section_name,
            claims,
            boundary_records,
            boundary_coverage.get(relative, {}),
        )

    approved_raw_consumers = set(manifest["raw_consumer_files"])
    approved_raw_references = set(manifest["raw_reference_files"])
    observed_raw_consumers: set[str] = set()
    observed_raw_references: set[str] = set()
    consumer_text: dict[str, str] = {}
    for relative, path, text in tracked_text_files():
        if relative in {
            CHECKER_PATH.relative_to(ROOT).as_posix(),
            MANIFEST_PATH.relative_to(ROOT).as_posix(),
        } or RAW_ROOT in path.parents:
            continue
        if not contains_raw_source_reference(text):
            continue
        if raw_reference_role(path) == "reference":
            observed_raw_references.add(relative)
        else:
            observed_raw_consumers.add(relative)
            consumer_text[relative] = text

    require(observed_raw_consumers == approved_raw_consumers,
            f"raw consumer allowlist differs: observed={sorted(observed_raw_consumers)} "
            f"approved={sorted(approved_raw_consumers)}")
    require(observed_raw_references == approved_raw_references,
            f"raw narrative reference allowlist differs: "
            f"observed={sorted(observed_raw_references)} "
            f"approved={sorted(approved_raw_references)}")

    for relative, text in consumer_text.items():
        require(contains_claim_map_reference(text),
                f"{relative} reads raw research without positive-claims.json")
        literal_lanes = literal_raw_lane_refs(text)
        require(literal_lanes.issubset(allowlisted),
                f"{relative} names non-allowlisted raw lanes: "
                f"{sorted(literal_lanes - set(allowlisted))}")
    return (
        f"claims={len(claims)} lanes={len(allowlisted)} "
        f"raw_consumers={len(observed_raw_consumers)} "
        f"raw_references={len(observed_raw_references)} "
        f"negative_boundaries={len(boundary_records)}"
    )


def check_citations(manifest: dict[str, Any]) -> str:
    source_revision = manifest["source_revision"]
    total_links = 0
    for lane, entry in manifest["allowlisted_lanes"].items():
        content = git("show", f"{source_revision}:{entry['path']}", binary=True)
        text = content.decode("utf-8", "strict")
        links = re.findall(
            r"(?:https?://|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}/)[^\s|)>]+",
            text,
        )
        require(links, f"{lane} has no source URL in its allowlisted blob")
        total_links += len(links)
    return f"lanes={len(manifest['allowlisted_lanes'])} source_urls={total_links}"


def check_partition(manifest: dict[str, Any], rows: dict[str, dict[str, str]]) -> str:
    claims = claims_by_id(manifest)
    manifest_text = (ROOT / "research" / "RESEARCH-MANIFEST.md").read_text(
        encoding="utf-8"
    )
    covered: set[str] = set()
    ranking_coverage: dict[str, list[str]] = {}
    for line in RANKING_PATH.read_text(encoding="utf-8").splitlines():
        if re.match(r"^\| S-[A-E] \|", line):
            cells = markdown_cells(line)
            ranking_coverage[cells[0]] = cells

    for synthesis_id, (relative, start, end) in PARTITIONS.items():
        expected_lanes = {canonical_lane(number) for number in range(start, end + 1)}
        require(not covered.intersection(expected_lanes),
                f"{synthesis_id} overlaps an earlier partition")
        covered.update(expected_lanes)
        text = (ROOT / relative).read_text(encoding="utf-8")
        range_match = re.search(r"^- Lane range: L(\d+)–L(\d+)\.$", text, re.MULTILINE)
        require(range_match is not None, f"{relative} lacks a lane range")
        require((int(range_match.group(1)), int(range_match.group(2))) == (start, end),
                f"{relative} lane range is not L{start:02d}–L{end:02d}")

        consumer_claim_lanes = {
            lane
            for claim in claims.values()
            if claim["consumer"] == relative
            for lane in claim["lanes"]
        }
        consumed_count = len(consumer_claim_lanes)
        count_match = re.search(
            r"^- Content-validated and consumed inputs: (\d+) of (\d+) lanes\.$",
            text,
            re.MULTILINE,
        )
        require(count_match is not None, f"{relative} lacks a consumed count")
        require(
            (int(count_match.group(1)), int(count_match.group(2)))
            == (consumed_count, len(expected_lanes)),
            f"{relative} consumed count differs from claim map",
        )

        range_literal = f"L{start:02d}–L{end:02d} ({len(expected_lanes)}"
        require(range_literal in manifest_text,
                f"research manifest lacks exact {synthesis_id} partition")

        cells = ranking_coverage.get(synthesis_id)
        require(cells is not None and len(cells) == 6,
                f"ranking coverage row missing or malformed for {synthesis_id}")
        require(set(parse_lane_refs(cells[1])) == expected_lanes,
                f"ranking range differs for {synthesis_id}")
        qualified = sum(
            rows[lane]["class"] == "qualified_unconsumed" for lane in expected_lanes
        )
        other = len(expected_lanes) - consumed_count - qualified
        require(
            [int(cells[2]), int(cells[3]), int(cells[4])]
            == [consumed_count, qualified, other],
            f"ranking totals differ for {synthesis_id}",
        )
        require(set(parse_lane_refs(cells[5])) == expected_lanes - consumer_claim_lanes,
                f"ranking unconsumed list differs for {synthesis_id}")

    expected_all = {canonical_lane(number) for number in range(1, 101)}
    require(covered == expected_all, "synthesis partitions do not cover L01–L100")
    require(len(ranking_coverage) == 5, "ranking must contain five coverage rows")
    return "S-A=21 S-B=21 S-C=28 S-D=26 S-E=4 total=100"


def check_compatibility(_: dict[str, Any], __: dict[str, dict[str, str]]) -> str:
    text = RANKING_PATH.read_text(encoding="utf-8")
    require(
        f"{HISTORICAL_RANKING_REVISION}:research/RANKING.md" in text,
        "historical recommendation definition is not immutable-bound",
    )

    historical_text = git(
        "show", f"{HISTORICAL_RANKING_REVISION}:research/RANKING.md"
    )
    require(isinstance(historical_text, str), "historical ranking was not text")
    historical_labels: dict[int, str] = {}
    for line in historical_text.splitlines():
        if not re.match(r"^\|(?:[1-9]|1[0-9]|20)\|", line):
            continue
        match = re.match(
            r"^\|((?:[1-9]|1[0-9]|20))\|([^|\n]+?) — ", line
        )
        require(match is not None,
                "historical ranking row lacks a stable recommendation prefix")
        number = int(match.group(1))
        require(number not in historical_labels,
                f"duplicate historical ranking R{number}")
        historical_labels[number] = match.group(2)
    require(set(historical_labels) == set(range(1, 21)),
            "immutable historical ranking does not define exactly R1-R20")

    mapped: dict[int, str] = {}
    for line in text.splitlines():
        if not re.match(r"^\| R(?:[1-9]|1[0-9]|20) \|", line):
            continue
        cells = markdown_cells(line)
        require(len(cells) == 3,
                f"historical compatibility row has {len(cells)} cells")
        number = int(cells[0][1:])
        require(number not in mapped, f"duplicate historical R{number}")
        require(cells[2] == "`historical_identity_only`",
                f"R{number} compatibility status grants more than identity")
        mapped[number] = cells[1]
    require(set(mapped) == set(range(1, 21)),
            f"historical recommendation map differs: {sorted(mapped)}")

    for number, (historical_label, stable_label) in HISTORICAL_COMPATIBILITY.items():
        require(historical_labels[number] == historical_label,
                f"R{number} immutable historical label changed: "
                f"{historical_labels[number]!r}")
        require(mapped[number] == stable_label,
                f"R{number} stable label does not match its immutable "
                f"historical definition: {mapped[number]!r}")

    require("`GSR-P2-04` remains open at its original P2 severity" in text,
            "GSR-P2-04 is not retained as an open P2 residual")
    require(
        "blocks a broader claim that downstream implementations are "
        "provenance-cleared" in text,
        "GSR-P2-04 blocking effect is not explicit",
    )
    require(
        "Exact consumer-by-consumer\nprovenance remediation or an authorized "
        "owner disposition remains required" in text,
        "GSR-P2-04 required disposition is not explicit",
    )
    require("Outside this artifact set; no disposition is asserted here." not in text,
            "GSR-P2-04 retains an undisposed placeholder")

    referenced: set[int] = set()
    for relative, path, text_value in tracked_text_files():
        if relative in {
            CHECKER_PATH.relative_to(ROOT).as_posix(),
            RANKING_PATH.relative_to(ROOT).as_posix(),
        } or RAW_ROOT in path.parents:
            continue
        referenced.update(
            int(match.group(1))
            for match in re.finditer(r"\bR([1-9]|1[0-9]|20)\b", text_value)
        )
    require(referenced.issubset(mapped),
            f"downstream historical IDs lack compatibility entries: "
            f"{sorted(referenced - set(mapped))}")
    return (
        f"historical={HISTORICAL_RANKING_REVISION} mapped=R1-R20 "
        f"downstream_refs={len(referenced)} identity_only=true residual=GSR-P2-04"
    )


def check_public_safety(_: dict[str, Any], __: dict[str, dict[str, str]]) -> str:
    pilot = (ROOT / "docs" / "SCIP-PILOT.md").read_text(encoding="utf-8")
    requirements = (ROOT / "tooling" / "requirements-scip.txt").read_text(
        encoding="utf-8"
    )
    validate_scip_contract(pilot, requirements)

    l40 = (RAW_ROOT / "L40-small-model-extraction-quality.md").read_text(
        encoding="utf-8"
    )
    l42 = (RAW_ROOT / "L42-gguf-quantization-tradeoffs.md").read_text(
        encoding="utf-8"
    )
    for stale in (
        "-np 4",
        "16 threads",
        "40–60 t/s",
        "8–12 s/doc",
        "2–2.5× aggregate",
        "100-doc golden-set",
    ):
        require(stale not in l40 + l42,
                f"L40/L42 retains host-tuned value: {stale}")
    for required in (
        "declare thread count, parallel slots,",
        "Measure extraction precision/recall/F1 and abstention separately",
        "No thread count, slot count, context size, cache",
        "separately report prompt-processing rate, generation rate, p50/p95 latency",
    ):
        require(required in l40 + l42,
                f"L40/L42 lacks parameterized measurement boundary: {required}")
    return (
        "scip_protocol=unexecutable_all_stage_complete_source_final_fixture "
        "l40_l42=parameterized"
    )


def self_test() -> None:
    require(parse_lane_refs("L01–L03, L20, L98-L100") == [
        "L01", "L02", "L03", "L20", "L98", "L99", "L100"
    ], "lane range parser self-test failed")
    row = "| 1 | <!-- positive-claim: EXP-01 --> Statement. | L20, L64 | gate |"
    cells = markdown_cells(row)
    require(strip_marker(cells[1]) == "Statement.", "marker stripping self-test failed")
    require(parse_lane_refs(cells[2]) == ["L20", "L64"],
            "claim lane parser self-test failed")
    require(is_separator_row(["---:", "---", ":---:"]),
            "separator parser self-test failed")

    conclusion_claims = {
        "SA-99": {
            "id": "SA-99",
            "consumer": "research/synthesis/test.md",
            "section": "Synthesis conclusion",
            "form": "prose",
            "statement": "One bounded claim is supported.",
            "lanes": ["L20"],
        }
    }
    test_boundary_records = {
        "BND-TEST-CONCLUSION": {
            "id": "BND-TEST-CONCLUSION",
            "consumer": "research/synthesis/test.md",
            "section": "Synthesis conclusion",
            "form": "conclusion",
            "status": "unsupported_or_unknown",
            "claim_ids": ["SA-99"],
            "statement": "All other conclusions are unsupported.",
        },
        "BND-TEST-NONE": {
            "id": "BND-TEST-NONE",
            "consumer": "research/synthesis/test.md",
            "section": "Supported synthesis",
            "form": "paragraph",
            "status": "no_supported_claim",
            "claim_ids": [],
            "statement": "No additional claim is supported.",
        },
    }
    conclusion_text = (
        "## Synthesis conclusion\n\n"
        "- Supported: <!-- positive-claim: SA-99 --> One bounded claim is supported.\n"
        "<!-- negative-boundary: BND-TEST-CONCLUSION "
        "status=unsupported_or_unknown claims=SA-99 -->\n"
        "- Unsupported/unknown: All other conclusions are unsupported.\n"
    )
    _, conclusion_coverage = parse_negative_boundary_blocks(
        "research/synthesis/test.md",
        conclusion_text,
        test_boundary_records,
    )
    validate_governed_conclusion(
        "research/synthesis/test.md",
        conclusion_text,
        "Synthesis conclusion",
        conclusion_claims,
        test_boundary_records,
        conclusion_coverage,
    )

    unmarked_conclusion = (
        "## Synthesis conclusion\n\n"
        "- Supported: One unregistered positive claim.\n"
        "<!-- negative-boundary: BND-TEST-CONCLUSION "
        "status=unsupported_or_unknown claims=SA-99 -->\n"
        "- Unsupported/unknown: All other conclusions are unsupported.\n"
    )
    _, unmarked_coverage = parse_negative_boundary_blocks(
        "research/synthesis/test.md",
        unmarked_conclusion,
        test_boundary_records,
    )
    expect_failure(
        lambda: validate_governed_conclusion(
            "research/synthesis/test.md",
            unmarked_conclusion,
            "Synthesis conclusion",
            conclusion_claims,
            test_boundary_records,
            unmarked_coverage,
        ),
        "unmarked positive conclusion",
    )

    positive_section_text = (
        "## Supported synthesis\n\n"
        "<!-- negative-boundary: BND-TEST-NONE "
        "status=no_supported_claim claims=none -->\n"
        "No additional claim is supported.\n"
    )
    _, positive_coverage = parse_negative_boundary_blocks(
        "research/synthesis/test.md",
        positive_section_text,
        test_boundary_records,
    )
    validate_positive_section_structure(
        "research/synthesis/test.md",
        positive_section_text,
        {"Supported synthesis"},
        positive_coverage,
    )
    expect_failure(
        lambda: parse_negative_boundary_blocks(
            "research/synthesis/test.md",
            positive_section_text.replace(
                "No additional claim is supported.",
                "Splink remains the production-ready supported choice.",
            ),
            test_boundary_records,
        ),
        "positive prose laundered as a negative boundary",
    )
    expect_failure(
        lambda: parse_negative_boundary_blocks(
            "research/synthesis/test.md",
            positive_section_text.replace(
                "No additional claim is supported.\n",
                "No additional claim is supported.\n"
                "Splink is the production-ready supported choice.\n",
            ),
            test_boundary_records,
        ),
        "unchecked multiline boundary continuation",
    )
    expect_failure(
        lambda: validate_positive_section_structure(
            "research/synthesis/test.md",
            "## Supported synthesis\n\n"
            "Splink remains the production-ready supported choice.\n",
            {"Supported synthesis"},
            {},
        ),
        "unmarked positive-section prose",
    )
    expect_failure(
        lambda: parse_negative_boundary_blocks(
            "research/synthesis/test.md",
            positive_section_text.replace(
                "status=no_supported_claim", "status=scope_limit"
            ),
            test_boundary_records,
        ),
        "boundary status variance",
    )
    expect_failure(
        lambda: parse_negative_boundary_blocks(
            "research/synthesis/test.md",
            positive_section_text.replace("claims=none", "claims=SA-99"),
            test_boundary_records,
        ),
        "boundary claim-ID variance",
    )

    raw_reference_cases = {
        "extensionless constructed path": 'fixture = Path("research") / "raw"',
        "service normalized path": "Environment=INPUT=research/./raw/L20-item.md",
        "pathlib joinpath": 'Path("research").joinpath("raw")',
        "Path operand": 'Path("research") / Path("raw")',
        "two-step named components": (
            'base = "research"\nleaf = "raw"\nroot = Path(base) / leaf'
        ),
        "pathlib import alias": (
            'from pathlib import Path as P\nbase = "research"\n'
            'leaf = "raw"\nroot = P(base).joinpath(leaf)'
        ),
        "indirect os.path join": (
            'base = "research"\nleaf = "raw"\n'
            'root = os.path.join(ROOT, base, leaf)'
        ),
        "os.path module alias": (
            'import os.path as osp\nbase = "research"\nleaf = "raw"\n'
            'root = osp.join(base, leaf)'
        ),
        "imported join alias": (
            'from os.path import join as combine, normpath as clean\n'
            'base = "research"\nleaf = "raw"\n'
            'root = clean(combine(base, leaf))'
        ),
        "constructor alias": (
            'from pathlib import Path\nBuilder = Path\n'
            'base = "research"\nleaf = "raw"\nroot = Builder(base) / leaf'
        ),
        "mapping components": (
            'parts = {"base": "research", "leaf": "raw"}\n'
            'root = Path(parts["base"]) / parts["leaf"]'
        ),
        "bound joinpath alias": (
            'base = Path("research")\nappend = base.joinpath\nroot = append("raw")'
        ),
        "starred component sequence": (
            'parts = ["research", "raw"]\nroot = Path(*parts)'
        ),
        "tuple-unpacked components": (
            'base, leaf = "research", "raw"\nroot = Path(base) / leaf'
        ),
        "normalized parent path": "research/../research/raw/L20-item.md",
        "multi-argument path": 'Path(ROOT, "research", "raw")',
    }
    for label, value in raw_reference_cases.items():
        require(contains_raw_source_reference(value),
                f"raw reference detector missed {label}")
    raw_false_positive_cases = {
        "uncomposed list": 'labels = ["research", "raw"]',
        "separate named values": 'subject = "research"\nquality = "raw"',
        "descriptive text": 'note = "research and raw are separate labels"',
        "reassigned constructor alias": (
            'from pathlib import Path\nBuilder = Path\nBuilder = print\n'
            'root = Builder("research", "raw")'
        ),
    }
    for label, value in raw_false_positive_cases.items():
        require(not contains_raw_source_reference(value),
                f"raw reference detector produced false positive for {label}")
    require(
        literal_raw_lane_refs(
            'candidate = Path("research") / "raw" / "L01-private.md"'
        ) == {"L01"},
        "constructed raw lane extraction self-test failed",
    )
    for filename in ("runner", "pilot.service", "research.conf"):
        require(raw_reference_role(Path(filename)) == "consumer",
                f"raw reference role missed alternate format {filename}")

    pilot = (ROOT / "docs" / "SCIP-PILOT.md").read_text(encoding="utf-8")
    requirements = (ROOT / "tooling" / "requirements-scip.txt").read_text(
        encoding="utf-8"
    )
    validate_scip_contract(pilot, requirements)
    expect_failure(
        lambda: validate_scip_contract(
            pilot.replace("tooling/scip_convert.py", "tooling/converter.py"),
            requirements,
        ),
        "omitted executed converter input",
    )
    expect_failure(
        lambda: validate_scip_contract(
            pilot.replace("mode `120000`", "an unspecified file mode"),
            requirements,
        ),
        "archive symlink admission",
    )
    expect_failure(
        lambda: validate_scip_contract(
            pilot.replace("reject every symlink", "accept fixture symlinks"),
            requirements,
        ),
        "fixture symlink admission",
    )
    expect_failure(
        lambda: validate_scip_contract(
            pilot.replace(
                "no host, home, or protected-repository mounts",
                "an unspecified mount policy",
            ),
            requirements,
        ),
        "protected mount precondition",
    )
    expect_failure(
        lambda: validate_scip_contract(
            pilot + "\n```bash\necho runnable\n```\n", requirements
        ),
        "runnable shell path",
    )
    expect_failure(
        lambda: validate_scip_contract(
            pilot.replace(
                "Every pilot stage and\nevery descendant",
                "Only selected stages and descendants",
            ),
            requirements,
        ),
        "pre-indexer stage outside containment",
    )
    expect_failure(
        lambda: validate_scip_contract(
            pilot.replace("complete local, non-promisor", "possibly remote source"),
            requirements,
        ),
        "promisor or lazy source input",
    )
    expect_failure(
        lambda: validate_scip_contract(
            pilot.replace("Deny the host `/proc`", "Expose the host `/proc`"),
            requirements,
        ),
        "host process namespace exposure",
    )
    expect_failure(
        lambda: validate_scip_contract(
            pilot.replace("no-new-privileges", "privilege policy unspecified"),
            requirements,
        ),
        "missing no-new-privileges policy",
    )
    expect_failure(
        lambda: validate_scip_contract(
            pilot.replace("PID-count", "unbounded-process-count"),
            requirements,
        ),
        "missing finite process/resource bounds",
    )
    expect_failure(
        lambda: validate_scip_contract(
            pilot.replace("pre-locked patch", "operator-time patch"),
            requirements,
        ),
        "unlocked fixture preparation",
    )
    expect_failure(
        lambda: validate_scip_contract(
            pilot.replace(
                "every final relative\npath", "selected final\npaths"
            ),
            requirements,
        ),
        "incomplete final fixture manifest",
    )
    expect_failure(
        lambda: validate_scip_contract(
            pilot.replace("immediately before indexing", "at an earlier time"),
            requirements,
        ),
        "stale final fixture verification",
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="exercise deterministic parser tests instead of repository checks",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        try:
            self_test()
        except CheckFailure as error:
            print(f"FAIL GSR-SELF-TEST {error}", file=sys.stderr)
            return 1
        print(
            "PASS GSR-SELF-TEST parser_cases=4 boundary_adversarial=6 "
            "raw_path_adversarial=24 scip_adversarial=13"
        )
        return 0

    try:
        manifest, manifest_sha256 = load_manifest()
        rows = parse_ranking_rows()
    except (CheckFailure, KeyError, TypeError) as error:
        print(f"FAIL GSR-MANIFEST {error}", file=sys.stderr)
        return 1

    checks: list[
        tuple[str, Callable[[dict[str, Any], dict[str, dict[str, str]]], str]]
    ] = [
        ("GSR-COUNTS", check_counts),
        ("GSR-PROVENANCE", check_provenance),
        ("GSR-ALLOWLIST", check_allowlist),
        ("GSR-CITATIONS", lambda current_manifest, _: check_citations(current_manifest)),
        ("GSR-PARTITION", check_partition),
        ("GSR-COMPAT", check_compatibility),
        ("GSR-PUBLIC-SAFETY", check_public_safety),
    ]
    failed = False
    for group_id, check in checks:
        try:
            detail = check(manifest, rows)
        except (CheckFailure, KeyError, TypeError, UnicodeDecodeError) as error:
            failed = True
            print(f"FAIL {group_id} {error}", file=sys.stderr)
        else:
            print(f"PASS {group_id} {detail}")
    status = "FAIL" if failed else "PASS"
    print(
        f"{status} GSR-MANIFEST schema=1 sha256={manifest_sha256} "
        f"source={manifest['source_revision']}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
