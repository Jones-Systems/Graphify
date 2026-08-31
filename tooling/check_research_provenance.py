#!/usr/bin/env python3
"""Fail-closed checks for Graphify's claim-scoped research provenance."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import warnings
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path, PurePosixPath
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
BOUNDARY_ASSERTIONS: dict[str, tuple[str, str]] = {
    "experiment_scope_only": ("paragraph", "scope_limit"),
    "unregistered_evidence_excluded": ("paragraph", "unsupported_or_unknown"),
    "no_registered_positive_claim": ("paragraph", "no_supported_claim"),
    "unregistered_conclusions_unsupported": (
        "conclusion",
        "unsupported_or_unknown",
    ),
}
SUPPORTED_RAW_CONSUMER_TYPES = {
    ".py": "python",
    ".js": "javascript",
    ".cjs": "javascript",
    ".mjs": "javascript",
}

HISTORICAL_FINDING_TUPLES: tuple[dict[str, str], ...] = (
    {
        "id": "GSR-P1-01",
        "reviewed_revision": "d1dbac36208b0066fc8907bd9fe9408fc5c51a60",
        "severity": "P1",
        "original_blocking_effect": "Public-safety blocker.",
        "original_outcome": (
            "Only the exact 21-lane positive selection is eligible; 46 inherited "
            "mixed-context blobs remain byte-identical and are explicitly excluded. "
            "Other inputs are qualified but unconsumed, incomplete, origin-unbound, "
            "misrouted, or missing."
        ),
    },
    {
        "id": "GSR-P2-01",
        "reviewed_revision": "d1dbac36208b0066fc8907bd9fe9408fc5c51a60",
        "severity": "P2",
        "original_blocking_effect": "Corpus provenance and completeness blocker.",
        "original_outcome": (
            "Public research was separated from non-research wrappers; incomplete "
            "and misrouted inputs are explicit gaps or excluded. Missing canonical "
            "content was not invented."
        ),
    },
    {
        "id": "GSR-P2-02",
        "reviewed_revision": "d1dbac36208b0066fc8907bd9fe9408fc5c51a60",
        "severity": "P2",
        "original_blocking_effect": "Reviewed-revision acceptance blocker.",
        "original_outcome": (
            "L20 is limited to public evidence. L13/L19 are bound to the reviewed "
            "input and clean derivative, but their earlier origins remain unknown "
            "and they are excluded."
        ),
    },
    {
        "id": "GSR-P2-03",
        "reviewed_revision": "d1dbac36208b0066fc8907bd9fe9408fc5c51a60",
        "severity": "P2",
        "original_blocking_effect": "Research-completeness blocker.",
        "original_outcome": (
            "Content classification now records 21 validated/consumed, 3 "
            "qualified/unconsumed, 46 excluded-not-public-safe, 14 gap/incomplete, "
            "2 origin-unbound, 9 misrouted, and 5 missing lanes."
        ),
    },
    {
        "id": "GSR-P2-04",
        "reviewed_revision": "d1dbac36208b0066fc8907bd9fe9408fc5c51a60",
        "severity": "P2",
        "original_blocking_effect": "Unresolved-prior-effect blocker.",
        "original_outcome": (
            "Retained residual: historical R1–R20 downstream implementations may "
            "still encode conclusions from the pre-repair mixed-context synthesis. "
            "This identity bridge does not revalidate their implementation provenance."
        ),
    },
    {
        "id": "GSR-P3-01",
        "reviewed_revision": "d1dbac36208b0066fc8907bd9fe9408fc5c51a60",
        "severity": "P3",
        "original_blocking_effect": "Candidate-validity blocker.",
        "original_outcome": (
            "Known whitespace defects are repaired; verification must bind its "
            "result to the exact candidate revision."
        ),
    },
)

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


@lru_cache(maxsize=1)
def repository_tracked_paths() -> frozenset[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    require(result.returncode == 0, "tracked path inventory failed")
    try:
        listing = result.stdout.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        raise CheckFailure("tracked path inventory is not UTF-8") from error
    paths = listing.split("\0")
    require(paths and paths[-1] == "", "tracked path inventory is malformed")
    return frozenset(paths[:-1])


def canonical_relative_path(relative: str) -> str:
    require(isinstance(relative, str), "tracked read rejected (non-string path)")
    require(relative and "\0" not in relative,
            "tracked read rejected (empty or invalid path)")
    require("\\" not in relative,
            "tracked read rejected (non-canonical separator)")
    candidate = PurePosixPath(relative)
    require(
        not candidate.is_absolute()
        and candidate.as_posix() == relative
        and all(part not in {"", ".", ".."} for part in candidate.parts),
        "tracked read rejected (non-canonical repository-relative path)",
    )
    return candidate.as_posix()


def require_resolved_within_root(root_resolved: Path, resolved: Path) -> None:
    require(resolved.is_relative_to(root_resolved),
            "tracked read rejected (resolved outside repository)")


def resolve_tracked_regular_path(
    relative: str,
    *,
    root: Path = ROOT,
    tracked: frozenset[str] | set[str] | None = None,
) -> Path:
    canonical = canonical_relative_path(relative)
    tracked_paths = repository_tracked_paths() if tracked is None else tracked
    require(canonical in tracked_paths,
            "tracked read rejected (untracked path)")

    try:
        root_resolved = root.resolve(strict=True)
    except OSError as error:
        raise CheckFailure("tracked read rejected (repository root unavailable)") from error
    require(root_resolved.is_dir(),
            "tracked read rejected (repository root is not a directory)")

    current = root_resolved
    parts = PurePosixPath(canonical).parts
    for index, part in enumerate(parts):
        current = current / part
        try:
            metadata = current.lstat()
        except OSError as error:
            raise CheckFailure("tracked read rejected (path unavailable)") from error
        require(not stat.S_ISLNK(metadata.st_mode),
                "tracked read rejected (symlink path)")
        if index < len(parts) - 1:
            require(stat.S_ISDIR(metadata.st_mode),
                    "tracked read rejected (non-directory parent)")
        else:
            require(stat.S_ISREG(metadata.st_mode),
                    "tracked read rejected (non-regular file)")

    try:
        resolved = current.resolve(strict=True)
    except OSError as error:
        raise CheckFailure("tracked read rejected (path resolution failed)") from error
    require_resolved_within_root(root_resolved, resolved)
    return current


def read_tracked_bytes(
    relative: str,
    *,
    root: Path = ROOT,
    tracked: frozenset[str] | set[str] | None = None,
) -> bytes:
    path = resolve_tracked_regular_path(relative, root=root, tracked=tracked)
    expected = path.lstat()
    no_follow = getattr(os, "O_NOFOLLOW", None)
    require(no_follow is not None,
            "tracked read rejected (no no-follow support)")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | no_follow)
    except OSError as error:
        raise CheckFailure("tracked read rejected (open failed)") from error
    try:
        actual = os.fstat(descriptor)
        require(stat.S_ISREG(actual.st_mode),
                "tracked read rejected (opened object is non-regular)")
        require(
            (actual.st_dev, actual.st_ino, actual.st_mode)
            == (expected.st_dev, expected.st_ino, expected.st_mode),
            "tracked read rejected (identity changed before read)",
        )
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            return handle.read()
    finally:
        os.close(descriptor)


def read_tracked_text(
    relative: str,
    *,
    root: Path = ROOT,
    tracked: frozenset[str] | set[str] | None = None,
) -> str:
    try:
        return read_tracked_bytes(relative, root=root, tracked=tracked).decode(
            "utf-8", "strict"
        )
    except UnicodeDecodeError as error:
        raise CheckFailure("tracked read rejected (non-UTF-8 text)") from error


def tracked_text_files(
    *,
    root: Path = ROOT,
    tracked: frozenset[str] | set[str] | None = None,
) -> list[tuple[str, Path, str]]:
    tracked_paths = repository_tracked_paths() if tracked is None else tracked
    files: list[tuple[str, Path, str]] = []
    for relative in sorted(tracked_paths):
        data = read_tracked_bytes(relative, root=root, tracked=tracked_paths)
        if b"\0" in data:
            continue
        try:
            value = data.decode("utf-8", "strict")
        except UnicodeDecodeError:
            continue
        files.append((relative, root / relative, value))
    return files


def tracked_markdown_texts(
    *,
    root: Path = ROOT,
    tracked: frozenset[str] | set[str] | None = None,
) -> list[tuple[str, str]]:
    tracked_paths = repository_tracked_paths() if tracked is None else tracked
    return [
        (
            relative,
            read_tracked_text(relative, root=root, tracked=tracked_paths),
        )
        for relative in sorted(tracked_paths)
        if PurePosixPath(relative).suffix.casefold() == ".md"
    ]


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
        components.append(component)
    return components


def candidate_has_raw_path(value: str) -> bool:
    components = normalized_path_components(value)
    return any(
        [part.casefold() for part in components[index:index + 2]]
        == ["research", "raw"]
        for index in range(max(0, len(components) - 1))
    )


def candidate_raw_lane_refs(value: str) -> set[str]:
    components = normalized_path_components(value)
    lanes: set[str] = set()
    for index in range(max(0, len(components) - 2)):
        if [part.casefold() for part in components[index:index + 2]] != [
            "research", "raw"
        ]:
            continue
        match = re.match(
            r"(?i)^L(100|0?[1-9]|[1-9][0-9])(?:[-.]|$)",
            components[index + 2],
        )
        if match:
            lanes.add(canonical_lane(int(match.group(1))))
    return lanes


@dataclass
class RawPathAnalysis:
    found: bool = False
    unresolved: bool = False
    concrete_paths: set[str] = field(default_factory=set)
    raw_lane_refs: set[str] = field(default_factory=set)
    issue_codes: set[str] = field(default_factory=set)


def record_raw_candidates(analysis: RawPathAnalysis, values: set[str]) -> None:
    for value in values:
        components = normalized_path_components(value)
        folded = [component.casefold() for component in components]
        raw_indexes = [
            index
            for index in range(max(0, len(components) - 1))
            if folded[index:index + 2] == ["research", "raw"]
        ]
        potential = any(
            folded[index:index + 2]
            in ([UNKNOWN_PATH_COMPONENT, "raw"], ["research", UNKNOWN_PATH_COMPONENT])
            for index in range(max(0, len(components) - 1))
        )
        if not raw_indexes and not potential:
            continue
        analysis.found = True
        if potential:
            analysis.unresolved = True
            analysis.issue_codes.add("dynamic_raw_root")
        for index in raw_indexes:
            canonical = "/".join(components)
            analysis.raw_lane_refs.update(candidate_raw_lane_refs(value))
            if (
                UNKNOWN_PATH_COMPONENT in components
                or index != 0
                or len(components) != 3
            ):
                analysis.unresolved = True
                analysis.issue_codes.add("non_exact_raw_path")
            else:
                analysis.concrete_paths.add(canonical)


def join_candidate_groups(
    groups: list[set[str]], separator: str
) -> set[str]:
    candidates = {""}
    truncated = False
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
                    truncated = True
                    break
            if len(combined) >= MAX_PATH_CANDIDATES:
                break
        candidates = combined
    if truncated:
        folded_values = {
            component.casefold()
            for group in groups
            for value in group
            for component in normalized_path_components(value)
        }
        if {"research", "raw"}.issubset(folded_values) or any(
            candidate_has_raw_path(candidate) for candidate in candidates
        ):
            if len(candidates) >= MAX_PATH_CANDIDATES:
                candidates.remove(sorted(candidates)[-1])
            candidates.add(f"research/raw/{UNKNOWN_PATH_COMPONENT}")
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
        self.analysis = RawPathAnalysis()
        self.environments: list[dict[str, set[str]]] = [{}]
        self.sequences: list[dict[str, list[set[str]]]] = [{}]
        self.mappings: list[dict[str, dict[str, set[str]]]] = [{}]
        self.bound_joiners: list[dict[str, set[str]]] = [{}]
        self.callables: list[dict[str, set[str]]] = [{}]
        self.path_constructors = {"Path", "PurePath"}
        self.pathlib_modules = {"pathlib"}
        self.os_modules = {"os"}
        self.path_modules = {"posixpath", "ntpath"}
        self.join_functions: set[str] = set()
        self.normalization_functions: set[str] = set()
        self.helper_functions = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.helper_stack: set[str] = set()
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

    @property
    def callable_environment(self) -> dict[str, set[str]]:
        return self.callables[-1]

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

    def _intrinsic_callable_kinds(self, name: str) -> set[str]:
        kinds: set[str] = set()
        if name in self.path_constructors:
            kinds.add("constructor")
        if name in self.join_functions:
            kinds.add("join")
        if name in self.normalization_functions:
            kinds.add("normalize")
        return kinds

    def _callable_kinds(self, node: ast.AST) -> set[str]:
        name = dotted_name(node)
        if name is None:
            return set()
        if isinstance(node, ast.Name) and name in self.callable_environment:
            return set(self.callable_environment[name])
        kinds = self._intrinsic_callable_kinds(name)
        parts = name.split(".")
        if (
            len(parts) == 2
            and parts[0] in self.pathlib_modules
            and parts[1] in {"Path", "PurePath"}
        ):
            kinds.add("constructor")
        if len(parts) >= 2 and parts[-1] == "join":
            if parts[0] in self.path_modules:
                kinds.add("join")
            if len(parts) >= 3 and parts[0] in self.os_modules and parts[-2] == "path":
                kinds.add("join")
        if len(parts) >= 2 and parts[-1] in {
            "normpath", "abspath", "realpath", "relpath"
        }:
            if parts[0] in self.path_modules:
                kinds.add("normalize")
            if len(parts) >= 3 and parts[0] in self.os_modules and parts[-2] == "path":
                kinds.add("normalize")
        return kinds

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

    def _evaluate_sequence(self, node: ast.AST) -> list[set[str]] | None:
        if isinstance(node, (ast.List, ast.Tuple)):
            return [self._evaluate(element) for element in node.elts]
        if isinstance(node, ast.Name) and node.id in self.sequence_environment:
            return [set(group) for group in self.sequence_environment[node.id]]
        return None

    def _evaluate_helper_call(self, node: ast.Call) -> set[str]:
        if not isinstance(node.func, ast.Name):
            return set()
        name = node.func.id
        function = self.helper_functions.get(name)
        if function is None or name in self.helper_stack:
            return set()
        if len(function.body) != 1 or not isinstance(function.body[0], ast.Return):
            return set()
        parameters = [*function.args.posonlyargs, *function.args.args]
        if function.args.kwarg:
            return set()

        self.helper_stack.add(name)
        self.environments.append(dict(self.environment))
        self.sequences.append(dict(self.sequence_environment))
        self.mappings.append(dict(self.mapping_environment))
        self.bound_joiners.append(dict(self.bound_join_environment))
        self.callables.append(dict(self.callable_environment))
        try:
            for parameter in parameters:
                self.environment[parameter.arg] = {UNKNOWN_PATH_COMPONENT}
                self.sequence_environment.pop(parameter.arg, None)
                self.mapping_environment.pop(parameter.arg, None)
                self.bound_join_environment.pop(parameter.arg, None)
                self.callable_environment[parameter.arg] = set()
            for parameter, argument in zip(parameters, node.args):
                self._bind_name(parameter.arg, argument, self._evaluate(argument))
            if function.args.vararg:
                vararg = function.args.vararg.arg
                self.environment[vararg] = set()
                self.sequence_environment[vararg] = [
                    self._evaluate(argument)
                    for argument in node.args[len(parameters):]
                ]
                self.mapping_environment.pop(vararg, None)
                self.bound_join_environment.pop(vararg, None)
                self.callable_environment[vararg] = set()
            parameter_names = {parameter.arg for parameter in parameters}
            for keyword in node.keywords:
                if keyword.arg in parameter_names:
                    self._bind_name(
                        keyword.arg, keyword.value, self._evaluate(keyword.value)
                    )
            return self._evaluate(function.body[0].value)
        finally:
            self.environments.pop()
            self.sequences.pop()
            self.mappings.pop()
            self.bound_joiners.pop()
            self.callables.pop()
            self.helper_stack.remove(name)

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
            values: set[str] = set()
            for kind in self._callable_kinds(node.func):
                if kind in {"constructor", "join"}:
                    values.update(
                        join_candidate_groups(self._argument_groups(node.args), "/")
                    )
                elif kind == "normalize" and node.args:
                    values.update(self._evaluate(node.args[0]))
            if values:
                return values
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
                if node.func.attr == "join" and len(node.args) == 1:
                    sequence = self._evaluate_sequence(node.func.value)
                    separators = self._evaluate(node.args[0])
                    if sequence is not None and separators:
                        joined: set[str] = set()
                        for separator in separators:
                            joined.update(join_candidate_groups(sequence, separator))
                        return joined
                if node.func.attr in {"resolve", "absolute"}:
                    return self._evaluate(node.func.value)
            helper_values = self._evaluate_helper_call(node)
            if helper_values:
                return helper_values
            groups = self._argument_groups(node.args)
            if groups:
                uncertain = {UNKNOWN_PATH_COMPONENT}
                for group in groups:
                    uncertain.update(group)
                uncertain.update(join_candidate_groups(groups, ""))
                return uncertain
        return set()

    def _mark(self, values: set[str]) -> None:
        record_raw_candidates(self.analysis, values)

    def _bind_name(self, name: str, value_node: ast.AST, values: set[str]) -> None:
        alias_sequence: list[set[str]] | None = None
        alias_mapping: dict[str, set[str]] | None = None
        alias_bound_join: set[str] | None = None
        if isinstance(value_node, ast.Name):
            if value_node.id in self.sequence_environment:
                alias_sequence = [
                    set(group) for group in self.sequence_environment[value_node.id]
                ]
            if value_node.id in self.mapping_environment:
                alias_mapping = {
                    key: set(group)
                    for key, group in self.mapping_environment[value_node.id].items()
                }
            if value_node.id in self.bound_join_environment:
                alias_bound_join = set(
                    self.bound_join_environment[value_node.id]
                )
        callable_kinds = self._callable_kinds(value_node)
        self.environment[name] = set(values)
        self.sequence_environment.pop(name, None)
        self.mapping_environment.pop(name, None)
        self.bound_join_environment.pop(name, None)
        self.callable_environment[name] = set(callable_kinds)

        if isinstance(value_node, (ast.List, ast.Tuple)):
            self.sequence_environment[name] = [
                self._evaluate(element) for element in value_node.elts
            ]
        elif alias_sequence is not None:
            self.sequence_environment[name] = alias_sequence
        elif isinstance(value_node, ast.Dict):
            mapping: dict[str, set[str]] = {}
            for key_node, item_node in zip(value_node.keys, value_node.values):
                if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                    mapping[key_node.value] = self._evaluate(item_node)
            self.mapping_environment[name] = mapping
        elif alias_mapping is not None:
            self.mapping_environment[name] = alias_mapping

        if alias_bound_join is not None:
            self.bound_join_environment[name] = alias_bound_join
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

    def _snapshot_state(self) -> tuple[
        dict[str, set[str]],
        dict[str, list[set[str]]],
        dict[str, dict[str, set[str]]],
        dict[str, set[str]],
        dict[str, set[str]],
    ]:
        return (
            {name: set(values) for name, values in self.environment.items()},
            {
                name: [set(group) for group in groups]
                for name, groups in self.sequence_environment.items()
            },
            {
                name: {key: set(group) for key, group in mapping.items()}
                for name, mapping in self.mapping_environment.items()
            },
            {
                name: set(values)
                for name, values in self.bound_join_environment.items()
            },
            {
                name: set(values)
                for name, values in self.callable_environment.items()
            },
        )

    def _restore_state(self, state: tuple[Any, ...]) -> None:
        environment, sequences, mappings, bound_joiners, callables = state
        self.environments[-1] = {
            name: set(values) for name, values in environment.items()
        }
        self.sequences[-1] = {
            name: [set(group) for group in groups]
            for name, groups in sequences.items()
        }
        self.mappings[-1] = {
            name: {key: set(group) for key, group in mapping.items()}
            for name, mapping in mappings.items()
        }
        self.bound_joiners[-1] = {
            name: set(values) for name, values in bound_joiners.items()
        }
        self.callables[-1] = {
            name: set(values) for name, values in callables.items()
        }

    def _merge_states(self, states: list[tuple[Any, ...]]) -> tuple[Any, ...]:
        require(states, "raw-path state merge requires at least one state")
        environments, sequences, mappings, bound_joiners, callables = zip(*states)

        merged_environment: dict[str, set[str]] = {}
        for name in set().union(*(set(values) for values in environments)):
            merged_environment[name] = set().union(
                *(values.get(name, set()) for values in environments)
            )

        merged_sequences: dict[str, list[set[str]]] = {}
        for name in set().union(*(set(values) for values in sequences)):
            alternatives = [values[name] for values in sequences if name in values]
            width = max(len(groups) for groups in alternatives)
            merged_sequences[name] = [
                set().union(*(
                    groups[index] if index < len(groups) else {UNKNOWN_PATH_COMPONENT}
                    for groups in alternatives
                ))
                for index in range(width)
            ]

        merged_mappings: dict[str, dict[str, set[str]]] = {}
        for name in set().union(*(set(values) for values in mappings)):
            alternatives = [values[name] for values in mappings if name in values]
            keys = set().union(*(set(mapping) for mapping in alternatives))
            merged_mappings[name] = {
                key: set().union(*(mapping.get(key, set()) for mapping in alternatives))
                for key in keys
            }

        merged_bound_joiners: dict[str, set[str]] = {}
        for name in set().union(*(set(values) for values in bound_joiners)):
            merged_bound_joiners[name] = set().union(
                *(values.get(name, set()) for values in bound_joiners)
            )

        merged_callables: dict[str, set[str]] = {}
        for name in set().union(*(set(values) for values in callables)):
            kinds: set[str] = set()
            for values in callables:
                if name in values:
                    kinds.update(values[name])
                else:
                    kinds.update(self._intrinsic_callable_kinds(name))
            merged_callables[name] = kinds

        return (
            merged_environment,
            merged_sequences,
            merged_mappings,
            merged_bound_joiners,
            merged_callables,
        )

    def _visit_branch(
        self, state: tuple[Any, ...], body: list[ast.stmt]
    ) -> tuple[Any, ...]:
        self._restore_state(state)
        for statement in body:
            self.visit(statement)
        return self._snapshot_state()

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
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> None:  # noqa: N802
        self._mark(self._evaluate(node.value))
        self.visit(node.value)

    def visit_Return(self, node: ast.Return) -> None:  # noqa: N802
        self._mark(self._evaluate(node.value))
        if node.value is not None:
            self.visit(node.value)

    def visit_If(self, node: ast.If) -> None:  # noqa: N802
        self.visit(node.test)
        before = self._snapshot_state()
        body_state = self._visit_branch(before, node.body)
        else_state = self._visit_branch(before, node.orelse) if node.orelse else before
        self._restore_state(self._merge_states([body_state, else_state]))

    def _visit_optional_loop(
        self,
        body: list[ast.stmt],
        orelse: list[ast.stmt],
    ) -> None:
        before = self._snapshot_state()
        body_state = self._visit_branch(before, body)
        merged = self._merge_states([before, body_state])
        if orelse:
            else_state = self._visit_branch(merged, orelse)
            merged = self._merge_states([merged, else_state])
        self._restore_state(merged)

    def visit_For(self, node: ast.For) -> None:  # noqa: N802
        self.visit(node.iter)
        self._visit_optional_loop(node.body, node.orelse)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:  # noqa: N802
        self.visit_For(node)

    def visit_While(self, node: ast.While) -> None:  # noqa: N802
        self.visit(node.test)
        self._visit_optional_loop(node.body, node.orelse)

    def visit_Try(self, node: ast.Try) -> None:  # noqa: N802
        before = self._snapshot_state()
        body_state = self._visit_branch(before, node.body)
        branch_states = [before, body_state]
        handler_base = self._merge_states(branch_states)
        for handler in node.handlers:
            if handler.type is not None:
                self.visit(handler.type)
            branch_states.append(self._visit_branch(handler_base, handler.body))
        if node.orelse:
            branch_states.append(self._visit_branch(body_state, node.orelse))
        merged = self._merge_states(branch_states)
        if node.finalbody:
            merged = self._visit_branch(merged, node.finalbody)
        self._restore_state(merged)

    def visit_TryStar(self, node: ast.TryStar) -> None:  # noqa: N802
        self.visit_Try(node)

    def visit_Match(self, node: ast.Match) -> None:  # noqa: N802
        self.visit(node.subject)
        before = self._snapshot_state()
        states = [before]
        for case in node.cases:
            self._restore_state(before)
            if case.guard is not None:
                self.visit(case.guard)
            states.append(self._visit_branch(self._snapshot_state(), case.body))
        self._restore_state(self._merge_states(states))

    def _visit_local_scope(
        self, body: list[ast.stmt], shadow_names: set[str] | None = None
    ) -> None:
        self.environments.append(dict(self.environment))
        self.sequences.append(dict(self.sequence_environment))
        self.mappings.append(dict(self.mapping_environment))
        self.bound_joiners.append(dict(self.bound_join_environment))
        self.callables.append(dict(self.callable_environment))
        try:
            for name in shadow_names or set():
                self.environment[name] = {UNKNOWN_PATH_COMPONENT}
                self.sequence_environment.pop(name, None)
                self.mapping_environment.pop(name, None)
                self.bound_join_environment.pop(name, None)
                self.callable_environment[name] = set()
            for statement in body:
                self.visit(statement)
        finally:
            self.environments.pop()
            self.sequences.pop()
            self.mappings.pop()
            self.bound_joiners.pop()
            self.callables.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                self.visit(default)
        parameters = {
            argument.arg
            for argument in [
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            ]
        }
        if node.args.vararg:
            parameters.add(node.args.vararg.arg)
        if node.args.kwarg:
            parameters.add(node.args.kwarg.arg)
        self._visit_local_scope(node.body, parameters)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self._visit_local_scope(node.body)


def split_js_top_level(value: str, delimiter: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escaped = False
    for index, character in enumerate(value):
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {'"', "'", "`"}:
            quote = character
        elif character in "([{":
            depth += 1
        elif character in ")]}":
            depth = max(0, depth - 1)
        elif character == delimiter and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1
    parts.append(value[start:].strip())
    return parts


def split_js_statements(value: str) -> list[str]:
    statements: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escaped = False
    for index, character in enumerate(value):
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {'"', "'", "`"}:
            quote = character
        elif character in "([{":
            depth += 1
        elif character in ")]}":
            depth = max(0, depth - 1)
        elif character in {";", "\n"} and depth == 0:
            statement = value[start:index].strip()
            if statement:
                statements.append(statement)
            start = index + 1
    final = value[start:].strip()
    if final:
        statements.append(final)
    return statements


def strip_balanced_parentheses(value: str) -> str:
    result = value.strip()
    while result.startswith("(") and result.endswith(")"):
        depth = 0
        quote: str | None = None
        escaped = False
        closes_at_end = False
        for index, character in enumerate(result):
            if quote is not None:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
                continue
            if character in {'"', "'", "`"}:
                quote = character
            elif character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    closes_at_end = index == len(result) - 1
                    break
        if not closes_at_end:
            break
        result = result[1:-1].strip()
    return result


def decode_js_string(value: str) -> str | None:
    candidate = value.strip()
    if len(candidate) < 2 or candidate[0] != candidate[-1]:
        return None
    if candidate[0] == "`":
        return None if "${" in candidate else candidate[1:-1]
    if candidate[0] not in {'"', "'"}:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            decoded = ast.literal_eval(candidate)
    except (SyntaxError, ValueError):
        return None
    return decoded if isinstance(decoded, str) else None


class JavaScriptRawPathAnalyzer:
    """Bounded evaluator for explicit JavaScript path/array composition."""

    def __init__(self) -> None:
        self.analysis = RawPathAnalysis()
        self.environment: dict[str, set[str]] = {}
        self.sequences: dict[str, list[set[str]]] = {}

    def _evaluate_sequence(self, expression: str) -> list[set[str]] | None:
        value = strip_balanced_parentheses(expression)
        if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", value):
            groups = self.sequences.get(value)
            return [set(group) for group in groups] if groups is not None else None
        if not (value.startswith("[") and value.endswith("]")):
            return None
        return [
            self._evaluate(item)
            for item in split_js_top_level(value[1:-1], ",")
            if item
        ]

    def _evaluate(self, expression: str) -> set[str]:
        value = strip_balanced_parentheses(expression.strip().removesuffix(";"))
        decoded = decode_js_string(value)
        if decoded is not None:
            return {decoded}
        if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", value):
            return set(self.environment.get(value, set()))

        plus_parts = split_js_top_level(value, "+")
        if len(plus_parts) > 1:
            return join_candidate_groups(
                [self._evaluate(part) for part in plus_parts], ""
            )

        join_match = re.fullmatch(r"(.+)\.join\s*\((.*)\)", value, re.DOTALL)
        if join_match:
            sequence = self._evaluate_sequence(join_match.group(1))
            separators = self._evaluate(join_match.group(2))
            if sequence is not None and separators:
                joined: set[str] = set()
                for separator in separators:
                    joined.update(join_candidate_groups(sequence, separator))
                return joined

        call_match = re.fullmatch(
            r"(?:[A-Za-z_$][A-Za-z0-9_$]*\.)?(?:join|resolve)\s*\((.*)\)",
            value,
            re.DOTALL,
        )
        if call_match:
            groups = [
                self._evaluate(argument)
                for argument in split_js_top_level(call_match.group(1), ",")
            ]
            return join_candidate_groups(groups, "/")

        unknown_call = re.fullmatch(
            r"[A-Za-z_$][A-Za-z0-9_$.]*\s*\((.*)\)", value, re.DOTALL
        )
        if unknown_call:
            groups = [
                self._evaluate(argument)
                for argument in split_js_top_level(unknown_call.group(1), ",")
            ]
            uncertain = {UNKNOWN_PATH_COMPONENT}
            for group in groups:
                uncertain.update(group)
            if groups:
                uncertain.update(join_candidate_groups(groups, ""))
            return uncertain
        return set()

    def _bind(self, name: str, expression: str) -> None:
        alias_sequence = None
        stripped = strip_balanced_parentheses(expression)
        if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", stripped):
            groups = self.sequences.get(stripped)
            if groups is not None:
                alias_sequence = [set(group) for group in groups]
        sequence = self._evaluate_sequence(expression)
        self.environment[name] = self._evaluate(expression)
        self.sequences.pop(name, None)
        if sequence is not None:
            self.sequences[name] = sequence
        elif alias_sequence is not None:
            self.sequences[name] = alias_sequence

    def analyze(self, value: str) -> RawPathAnalysis:
        for statement in split_js_statements(value):
            assignment = re.fullmatch(
                r"(?:(?:const|let|var)\s+)?"
                r"([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(.+)",
                statement,
                re.DOTALL,
            )
            if assignment:
                expression = assignment.group(2)
                evaluated = self._evaluate(expression)
                record_raw_candidates(self.analysis, evaluated)
                self._bind(assignment.group(1), expression)
            else:
                record_raw_candidates(self.analysis, self._evaluate(statement))
        return self.analysis


def python_raw_path_analysis(value: str) -> RawPathAnalysis:
    try:
        tree = ast.parse(value)
    except (SyntaxError, ValueError):
        return RawPathAnalysis(issue_codes={"python_parse_failed"})
    analyzer = PythonRawPathAnalyzer(tree)
    analyzer.visit(tree)
    return analyzer.analysis


def javascript_raw_path_analysis(value: str) -> RawPathAnalysis:
    return JavaScriptRawPathAnalyzer().analyze(value)


def direct_raw_reference_present(value: str) -> bool:
    return bool(
        NORMALIZED_RAW_REFERENCE_RE.search(value)
        or RAW_LANE_REFERENCE_RE.search(value)
        or CONSTRUCTED_RAW_REFERENCE_RE.search(value)
    )


def lexical_path_components(value: str) -> tuple[set[str], set[str]]:
    decoded: list[str] = []
    for match in re.finditer(r'''(?s)(["'])(.*?)(?<!\\)\1''', value):
        literal = match.group(0)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                parsed = ast.literal_eval(literal)
        except (SyntaxError, ValueError):
            continue
        if isinstance(parsed, str):
            decoded.append(parsed)
    components: set[str] = set()
    lanes: set[str] = set()
    for start in range(len(decoded)):
        for width in range(1, min(3, len(decoded) - start) + 1):
            candidate = "".join(decoded[start:start + width])
            components.add(candidate.casefold())
            match = re.fullmatch(
                r"(?i)L(100|0?[1-9]|[1-9][0-9])(?:[-.].*)?", candidate
            )
            if match:
                lanes.add(canonical_lane(int(match.group(1))))
    return components, lanes


def lexically_suspicious_raw_construction(value: str) -> tuple[bool, set[str]]:
    components, lanes = lexical_path_components(value)
    path_operator = re.search(
        r"(?i)(?:\b(?:Path|PurePath)\s*\(|\.joinpath\s*\(|\bjoin\s*\(|"
        r"\b(?:os\.)?path\.join\b|\.join\s*\(|\s/\s)",
        value,
    )
    return {"research", "raw"}.issubset(components) and path_operator is not None, lanes


def executable_raw_path_analysis(value: str, file_type: str) -> RawPathAnalysis:
    if file_type == "python":
        analysis = python_raw_path_analysis(value)
    elif file_type == "javascript":
        analysis = javascript_raw_path_analysis(value)
    else:
        analysis = RawPathAnalysis(issue_codes={"unsupported_file_type"})
    if direct_raw_reference_present(value) and not analysis.found:
        analysis.found = True
        analysis.unresolved = True
        analysis.issue_codes.add("unanalyzed_raw_reference")
    suspicious, lanes = lexically_suspicious_raw_construction(value)
    if suspicious and not analysis.found:
        analysis.found = True
        analysis.unresolved = True
        analysis.raw_lane_refs.update(lanes)
        analysis.issue_codes.add("unsupported_raw_construction")
    return analysis


def contains_raw_source_reference(value: str) -> bool:
    if direct_raw_reference_present(value):
        return True
    lexical_suspicion, _ = lexically_suspicious_raw_construction(value)
    return (
        python_raw_path_analysis(value).found
        or javascript_raw_path_analysis(value).found
        or lexical_suspicion
    )


def literal_raw_lane_refs(value: str) -> set[str]:
    direct = {
        canonical_lane(int(match.group(1)))
        for match in RAW_LANE_REFERENCE_RE.finditer(value)
    }
    return (
        direct
        | python_raw_path_analysis(value).raw_lane_refs
        | javascript_raw_path_analysis(value).raw_lane_refs
    )


def contains_claim_map_reference(value: str) -> bool:
    return CLAIM_MAP_REFERENCE_RE.search(value) is not None


def raw_reference_role(path: Path) -> str:
    return "reference" if path.suffix.lower() in NARRATIVE_SUFFIXES else "consumer"


def validate_executable_raw_consumer(
    relative: str,
    text: str,
    declaration: dict[str, Any],
    eligible_raw_paths: set[str],
) -> RawPathAnalysis:
    canonical_relative_path(relative)
    suffix = PurePosixPath(relative).suffix.casefold()
    require(suffix in SUPPORTED_RAW_CONSUMER_TYPES,
            "executable raw consumer uses an unsupported file type")
    file_type = SUPPORTED_RAW_CONSUMER_TYPES[suffix]
    require(declaration.get("file_type") == file_type,
            "executable raw consumer file type differs from declaration")
    analysis = executable_raw_path_analysis(text, file_type)
    require(analysis.found, "declared executable raw consumer has no raw access")
    require(not analysis.unresolved,
            "executable raw consumer has dynamic or unanalyzable raw access")
    declared_paths = declaration.get("raw_paths")
    require(
        isinstance(declared_paths, list)
        and len(declared_paths) == len(set(declared_paths)),
        "executable raw consumer path declaration is malformed",
    )
    require(analysis.concrete_paths == set(declared_paths),
            "executable raw consumer paths differ from exact declaration")
    require(analysis.concrete_paths.issubset(eligible_raw_paths),
            "executable raw consumer reaches a non-allowlisted path")
    require(contains_claim_map_reference(text),
            "executable raw consumer lacks the claim-map gate")
    return analysis


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
            "not a Markdown table row")
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
        require(
            set(record) == {
                "id",
                "consumer",
                "section",
                "form",
                "status",
                "claim_ids",
                "assertion",
            },
            "negative boundary record fields differ from the structured schema",
        )
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
        assertion = record.get("assertion")
        require(assertion in BOUNDARY_ASSERTIONS,
                f"{boundary_id} has an unsupported structured assertion")
        require(
            BOUNDARY_ASSERTIONS[assertion]
            == (record.get("form"), status),
            f"{boundary_id} assertion/form/status tuple differs",
        )
        require(
            assertion not in {
                "experiment_scope_only", "unregistered_evidence_excluded"
            } or bool(claim_ids),
            f"{boundary_id} structured assertion requires registered claims",
        )
        require(
            assertion != "no_registered_positive_claim" or not claim_ids,
            f"{boundary_id} no-claim assertion names a positive claim",
        )
        require(isinstance(record.get("consumer"), str),
                f"{boundary_id} has no consumer")
        require(isinstance(record.get("section"), str),
                f"{boundary_id} has no section")
        records[boundary_id] = record
    return records


def render_negative_boundary_statement(record: dict[str, Any]) -> str:
    assertion = record["assertion"]
    if assertion == "experiment_scope_only":
        return (
            "This section orders research only; it does not establish adoption, "
            "deployment, production readiness, or support beyond the registered "
            "positive claims."
        )
    if assertion == "unregistered_evidence_excluded":
        return (
            "Only the registered positive claims may support this section; every "
            "excluded, incomplete, unconsumed, missing, misrouted, origin-unbound, "
            "or otherwise unregistered input contributes no positive support."
        )
    if assertion == "no_registered_positive_claim":
        return "This section contains no registered positive claim."
    require(assertion == "unregistered_conclusions_unsupported",
            "unknown structured negative assertion")
    claim_ids = record["claim_ids"]
    if claim_ids:
        return (
            f"Only the registered conclusion claim {','.join(claim_ids)} is "
            "supported; every other conclusion in this section is unsupported or "
            "unknown."
        )
    return (
        "No conclusion in this section is supported; every conclusion is "
        "unsupported or unknown."
    )


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

        require(" ".join(logical_lines) == render_negative_boundary_statement(record),
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
            f"{relative}:{line_number} contains ungoverned conclusion prose"
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
    raw = read_tracked_bytes(MANIFEST_PATH.relative_to(ROOT).as_posix())
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as error:
        raise CheckFailure(f"invalid {MANIFEST_PATH.relative_to(ROOT)}: {error}")
    require(manifest.get("schema_version") == 2, "unsupported claim-map schema")
    require(manifest.get("authority_effect") == "none",
            "claim map must retain authority_effect=none")
    require(
        manifest.get("historical_findings") == list(HISTORICAL_FINDING_TUPLES),
        "canonical historical finding tuples differ",
    )
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
    consumers = manifest.get("raw_consumer_files")
    require(isinstance(consumers, dict),
            "raw_consumer_files must be a path-keyed object")
    for relative, declaration in consumers.items():
        canonical_relative_path(relative)
        require(
            isinstance(declaration, dict)
            and set(declaration) == {"file_type", "raw_paths"},
            "raw consumer declaration fields differ",
        )
        suffix = PurePosixPath(relative).suffix.casefold()
        require(
            suffix in SUPPORTED_RAW_CONSUMER_TYPES
            and declaration["file_type"] == SUPPORTED_RAW_CONSUMER_TYPES[suffix],
            "raw consumer uses an unsupported or mismatched file type",
        )
        raw_paths = declaration["raw_paths"]
        require(
            isinstance(raw_paths, list)
            and raw_paths
            and len(raw_paths) == len(set(raw_paths)),
            "raw consumer must declare a non-empty unique raw-path list",
        )
        for raw_path in raw_paths:
            canonical_relative_path(raw_path)
    references = manifest.get("raw_reference_files")
    require(
        isinstance(references, list) and len(references) == len(set(references)),
        "raw_reference_files must be a unique path list",
    )
    for relative in references:
        canonical_relative_path(relative)
    return manifest, hashlib.sha256(raw).hexdigest()


def parse_ranking_rows() -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for line_number, line in enumerate(
        read_tracked_text(RANKING_PATH.relative_to(ROOT).as_posix()).splitlines(),
        start=1,
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

    ranking_text = read_tracked_text(RANKING_PATH.relative_to(ROOT).as_posix())
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
        resolve_tracked_regular_path(path)
        reviewed_oid = git("rev-parse", f"{reviewed_revision}:{path}")
        require(reviewed_oid == row["input_blob_oid"],
                f"{lane} reviewed blob OID mismatch")
        reviewed_bytes = git("show", f"{reviewed_revision}:{path}", binary=True)
        require(hashlib.sha256(reviewed_bytes).hexdigest() == row["input_sha256"],
                f"{lane} reviewed SHA-256 mismatch")
        reviewed_blobs += 1

        if row["class"] == "excluded_not_public_safe":
            resolve_tracked_regular_path(path)
            working_oid = git("hash-object", "--", path)
            require(working_oid == row["input_blob_oid"],
                    f"{lane} excluded blob changed from reviewed bytes")
            excluded_blobs += 1

    for lane, entry in allowlisted.items():
        path = entry["path"]
        resolve_tracked_regular_path(path)
        require(rows[lane]["path"] == path, f"{lane} allowlist path mismatch")
        source_oid = git("rev-parse", f"{source_revision}:{path}")
        require(source_oid == entry["blob_oid"],
                f"{lane} source-revision blob OID mismatch")
        require(git("hash-object", "--", path) == entry["blob_oid"],
                f"{lane} working bytes differ from the allowlisted source blob")

    for synthesis_path, _, _ in PARTITIONS.values():
        text = read_tracked_text(synthesis_path)
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
    markdown_texts = tracked_markdown_texts()
    for relative, markdown_text in markdown_texts:
        if "negative-boundary:" in markdown_text:
            marker_consumers.add(relative)
    require(marker_consumers.issubset(boundary_consumers),
            f"unregistered boundary marker consumers: "
            f"{sorted(marker_consumers - boundary_consumers)}")

    found_boundaries: Counter[str] = Counter()
    boundary_coverage: dict[str, dict[int, str]] = {}
    for relative in sorted(boundary_consumers):
        resolve_tracked_regular_path(relative)
        observed, covered = parse_negative_boundary_blocks(
            relative,
            read_tracked_text(relative),
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
    for relative, markdown_text in markdown_texts:
        section: str | None = None
        for line_number, line in enumerate(
            markdown_text.splitlines(), start=1
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
        resolve_tracked_regular_path(relative)
        validate_positive_section_structure(
            relative,
            read_tracked_text(relative),
            sections,
            boundary_coverage.get(relative, {}),
        )

    for relative, section_name in governed_conclusions.items():
        validate_governed_conclusion(
            relative,
            read_tracked_text(relative),
            section_name,
            claims,
            boundary_records,
            boundary_coverage.get(relative, {}),
        )

    approved_raw_consumers: dict[str, dict[str, Any]] = manifest[
        "raw_consumer_files"
    ]
    approved_raw_references = set(manifest["raw_reference_files"])
    observed_raw_consumers: set[str] = set()
    observed_raw_references: set[str] = set()
    eligible_raw_paths = {entry["path"] for entry in allowlisted.values()}
    for relative, declaration in approved_raw_consumers.items():
        require(set(declaration["raw_paths"]).issubset(eligible_raw_paths),
                f"{relative} declares a non-allowlisted raw path")
        for raw_path in declaration["raw_paths"]:
            resolve_tracked_regular_path(raw_path)

    for relative, path, text in tracked_text_files():
        if relative in {
            CHECKER_PATH.relative_to(ROOT).as_posix(),
            MANIFEST_PATH.relative_to(ROOT).as_posix(),
        } or RAW_ROOT in path.parents:
            continue
        if raw_reference_role(path) == "reference":
            if contains_raw_source_reference(text):
                observed_raw_references.add(relative)
            continue

        suffix = path.suffix.casefold()
        file_type = SUPPORTED_RAW_CONSUMER_TYPES.get(suffix)
        if file_type is None:
            require(not contains_raw_source_reference(text),
                    f"{relative} has raw access in an unsupported file type")
            continue
        analysis = executable_raw_path_analysis(text, file_type)
        if not analysis.found:
            continue
        observed_raw_consumers.add(relative)
        require(relative in approved_raw_consumers,
                f"{relative} is an undeclared executable raw consumer")
        validate_executable_raw_consumer(
            relative,
            text,
            approved_raw_consumers[relative],
            eligible_raw_paths,
        )

    require(observed_raw_consumers == set(approved_raw_consumers),
            f"raw consumer allowlist differs: observed={sorted(observed_raw_consumers)} "
            f"approved={sorted(approved_raw_consumers)}")
    require(observed_raw_references == approved_raw_references,
            f"raw narrative reference allowlist differs: "
            f"observed={sorted(observed_raw_references)} "
            f"approved={sorted(approved_raw_references)}")

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
    manifest_text = read_tracked_text("research/RESEARCH-MANIFEST.md")
    covered: set[str] = set()
    ranking_coverage: dict[str, list[str]] = {}
    for line in read_tracked_text(
        RANKING_PATH.relative_to(ROOT).as_posix()
    ).splitlines():
        if re.match(r"^\| S-[A-E] \|", line):
            cells = markdown_cells(line)
            ranking_coverage[cells[0]] = cells

    for synthesis_id, (relative, start, end) in PARTITIONS.items():
        expected_lanes = {canonical_lane(number) for number in range(start, end + 1)}
        require(not covered.intersection(expected_lanes),
                f"{synthesis_id} overlaps an earlier partition")
        covered.update(expected_lanes)
        text = read_tracked_text(relative)
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


def parse_historical_finding_tuples(text: str) -> dict[str, dict[str, str]]:
    expected_findings = {
        record["id"]: record for record in HISTORICAL_FINDING_TUPLES
    }
    observed_findings: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        if not re.match(r"^\| GSR-P[0-9]-[0-9]{2} \|", line):
            continue
        cells = markdown_cells(line)
        require(len(cells) == 5, "historical finding row has the wrong shape")
        finding_id = cells[0]
        require(finding_id not in observed_findings,
                f"duplicate historical finding tuple {finding_id}")
        observed_findings[finding_id] = {
            "id": finding_id,
            "reviewed_revision": strip_backticks(cells[1]),
            "severity": cells[2],
            "original_blocking_effect": cells[3],
            "original_outcome": cells[4],
        }
    require(observed_findings == expected_findings,
            "RANKING historical finding tuples differ from canonical identity")
    return observed_findings


def check_compatibility(manifest: dict[str, Any], _: dict[str, dict[str, str]]) -> str:
    text = read_tracked_text(RANKING_PATH.relative_to(ROOT).as_posix())
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

    expected_findings = {
        record["id"]: record for record in HISTORICAL_FINDING_TUPLES
    }
    require(
        {record["id"]: record for record in manifest["historical_findings"]}
        == expected_findings,
        "manifest historical finding tuples differ from the canonical tuples",
    )
    observed_findings = parse_historical_finding_tuples(text)

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
            MANIFEST_PATH.relative_to(ROOT).as_posix(),
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
        f"findings={len(observed_findings)} downstream_refs={len(referenced)} "
        "identity_only=true residual=GSR-P2-04"
    )


def check_public_safety(_: dict[str, Any], __: dict[str, dict[str, str]]) -> str:
    pilot = read_tracked_text("docs/SCIP-PILOT.md")
    requirements = read_tracked_text("tooling/requirements-scip.txt")
    validate_scip_contract(pilot, requirements)

    l40 = read_tracked_text("research/raw/L40-small-model-extraction-quality.md")
    l42 = read_tracked_text("research/raw/L42-gguf-quantization-tradeoffs.md")
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

    with tempfile.TemporaryDirectory(prefix="gsr-read-guard-") as temporary:
        container = Path(temporary)
        test_root = container / "repository"
        test_root.mkdir()
        (test_root / "positive.md").write_text(
            "registered positive consumer", encoding="utf-8"
        )
        (test_root / "untracked.md").write_text(
            "untracked content", encoding="utf-8"
        )
        (test_root / "directory.md").mkdir()
        outside = container / "outside.md"
        outside.write_text("CONTENT-MUST-NOT-ENTER-DIAGNOSTICS", encoding="utf-8")
        (test_root / "link.md").symlink_to("positive.md")
        (test_root / "escape.md").symlink_to("../outside.md")
        tracked_paths = {
            "positive.md",
            "directory.md",
            "link.md",
            "escape.md",
        }
        require(
            read_tracked_text(
                "positive.md", root=test_root, tracked=tracked_paths
            ) == "registered positive consumer",
            "tracked positive-consumer read failed",
        )
        path_rejections = {
            "absolute path": str(test_root / "positive.md"),
            "parent traversal": "../outside.md",
            "symlink consumer": "link.md",
            "non-regular consumer": "directory.md",
            "untracked consumer": "untracked.md",
            "outside-root resolution": "escape.md",
        }
        for label, relative in path_rejections.items():
            expect_failure(
                lambda relative=relative: read_tracked_text(
                    relative, root=test_root, tracked=tracked_paths
                ),
                label,
            )
        try:
            read_tracked_text("escape.md", root=test_root, tracked=tracked_paths)
        except CheckFailure as error:
            require(
                "CONTENT-MUST-NOT-ENTER-DIAGNOSTICS" not in str(error),
                "tracked-read diagnostic exposed file content",
            )
        else:
            raise CheckFailure("outside-root diagnostic probe did not fail")
        expect_failure(
            lambda: tracked_markdown_texts(
                root=test_root, tracked={"positive.md", "link.md"}
            ),
            "repository-wide Markdown symlink scan",
        )
        expect_failure(
            lambda: require_resolved_within_root(
                test_root.resolve(strict=True), outside.resolve(strict=True)
            ),
            "resolved path outside repository root",
        )

    ranking_for_tuple_test = read_tracked_text("research/RANKING.md")
    parse_historical_finding_tuples(ranking_for_tuple_test)
    expect_failure(
        lambda: parse_historical_finding_tuples(
            ranking_for_tuple_test.replace(
                "| GSR-P2-04 | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | P2 |",
                "| GSR-P2-04 | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | P3 |",
            )
        ),
        "historical finding severity mutation",
    )
    expect_failure(
        lambda: parse_historical_finding_tuples(
            ranking_for_tuple_test.replace(
                "Unresolved-prior-effect blocker.", "Resolved prior effect."
            )
        ),
        "historical finding blocking-effect mutation",
    )

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
            "assertion": "unregistered_conclusions_unsupported",
        },
        "BND-TEST-NONE": {
            "id": "BND-TEST-NONE",
            "consumer": "research/synthesis/test.md",
            "section": "Supported synthesis",
            "form": "paragraph",
            "status": "no_supported_claim",
            "claim_ids": [],
            "assertion": "no_registered_positive_claim",
        },
    }
    test_boundary_records = boundary_records_by_id(
        {"negative_boundaries": list(test_boundary_records.values())},
        conclusion_claims,
    )
    conclusion_text = (
        "## Synthesis conclusion\n\n"
        "- Supported: <!-- positive-claim: SA-99 --> One bounded claim is supported.\n"
        "<!-- negative-boundary: BND-TEST-CONCLUSION "
        "status=unsupported_or_unknown claims=SA-99 -->\n"
        "- Unsupported/unknown: Only the registered conclusion claim SA-99 is "
        "supported; every other conclusion in this section is unsupported or "
        "unknown.\n"
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
        "- Unsupported/unknown: Only the registered conclusion claim SA-99 is "
        "supported; every other conclusion in this section is unsupported or "
        "unknown.\n"
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
        "This section contains no registered positive claim.\n"
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
                "This section contains no registered positive claim.",
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
                "This section contains no registered positive claim.\n",
                "This section contains no registered positive claim.\n"
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

    def synchronized_laundering_probe() -> None:
        laundered = [dict(record) for record in test_boundary_records.values()]
        for record in laundered:
            if record["id"] == "BND-TEST-NONE":
                record["statement"] = (
                    "Splink remains the production-ready supported choice."
                )
        records = boundary_records_by_id(
            {"negative_boundaries": laundered}, conclusion_claims
        )
        parse_negative_boundary_blocks(
            "research/synthesis/test.md",
            positive_section_text.replace(
                "This section contains no registered positive claim.",
                "Splink remains the production-ready supported choice.",
            ),
            records,
        )

    expect_failure(
        synchronized_laundering_probe,
        "synchronized no-supported-claim manifest and prose laundering",
    )

    raw_reference_cases = {
        "extensionless constructed path": 'fixture = Path("research") / "raw"',
        "unsupported split join": (
            'fixture = join("rese" + "arch", "ra" + "w", '
            '"L01-private.md")'
        ),
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
    raw_positive_probes = {
        "split literals": (
            "python",
            'candidate = Path("rese" + "arch") / ("ra" + "w") / '
            '"L01-private.md"',
        ),
        "helper-function composition": (
            "python",
            'def base():\n    return "rese" + "arch"\n'
            'def leaf():\n    return "ra" + "w"\n'
            'candidate = Path(base()) / leaf() / "L01-private.md"',
        ),
        "vararg helper composition": (
            "python",
            'def compose(*parts):\n    return Path(*parts)\n'
            'candidate = compose("research", "raw", "L01-private.md")',
        ),
        "JavaScript array join": (
            "javascript",
            'const parts = ["rese" + "arch", "ra" + "w", '
            '"L01-private.md"]; const candidate = parts.join("/");',
        ),
        "JavaScript alias and reassignment": (
            "javascript",
            'let parts = ["safe"]; parts = ["research", "raw", '
            '"L01-private.md"]; const first = parts; const second = first; '
            'const candidate = second.join("/");',
        ),
        "conditional base": (
            "python",
            'base = "safe"\nif flag:\n    base = "research"\n'
            'candidate = Path(base) / "raw" / "L01-private.md"',
        ),
        "conditional Path or os.path.join alias": (
            "python",
            'Builder = Path\nif flag:\n    Builder = os.path.join\n'
            'candidate = Builder("research", "raw", "L01-private.md")',
        ),
        "Path starred sequence alias": (
            "python",
            'parts = ["research", "raw", "L01-private.md"]\n'
            'alias = parts\ncandidate = Path(*alias)',
        ),
        "second bound joinpath alias": (
            "python",
            'base = Path("research")\nfirst = base.joinpath\nsecond = first\n'
            'candidate = second("raw", "L01-private.md")',
        ),
        "optional loop merge": (
            "python",
            'base = "safe"\nfor item in items:\n    base = "research"\n'
            'candidate = Path(base) / "raw" / "L01-private.md"',
        ),
        "try-handler merge": (
            "python",
            'base = "safe"\ntry:\n    base = "research"\n'
            'except Exception:\n    base = "safe"\n'
            'candidate = Path(base) / "raw" / "L01-private.md"',
        ),
        "match-case merge": (
            "python",
            'base = "safe"\nmatch selector:\n    case 1:\n'
            '        base = "research"\n    case _:\n        base = "safe"\n'
            'candidate = Path(base) / "raw" / "L01-private.md"',
        ),
    }
    for label, (file_type, value) in raw_positive_probes.items():
        analysis = executable_raw_path_analysis(value, file_type)
        require(analysis.found, f"raw analysis missed {label}")
        require("L01" in analysis.raw_lane_refs,
                f"raw analysis missed L01 extraction for {label}")
        require(
            not analysis.unresolved
            and "research/raw/L01-private.md" in analysis.concrete_paths,
            f"raw analysis did not retain an exact path for {label}",
        )

    raw_dynamic_probes = {
        "unsupported Python helper": (
            "python",
            'candidate = Path(build("rese", "arch")) / ("ra" + "w") / '
            '"L01-private.md"',
        ),
        "dynamic Python lane": (
            "python",
            'lane = choose("L01-private.md")\n'
            'candidate = Path("research") / "raw" / lane',
        ),
        "unsupported JavaScript helper": (
            "javascript",
            'const candidate = [make("rese", "arch"), "raw", '
            '"L01-private.md"].join("/");',
        ),
        "JavaScript join alias reassignment": (
            "javascript",
            'let joiner = noop; joiner = path.join; const candidate = '
            'joiner("research", "raw", "L01-private.md");',
        ),
    }
    for label, (file_type, value) in raw_dynamic_probes.items():
        analysis = executable_raw_path_analysis(value, file_type)
        require(analysis.found and analysis.unresolved,
                f"dynamic raw analysis did not fail closed for {label}")
        require("L01" in analysis.raw_lane_refs,
                f"dynamic raw analysis missed L01 extraction for {label}")
    overflow_analysis = RawPathAnalysis()
    record_raw_candidates(
        overflow_analysis,
        join_candidate_groups(
            [
                {"research"},
                {"raw"},
                {f"L{number:02d}-item.md" for number in range(1, 71)},
            ],
            "/",
        ),
    )
    require(
        overflow_analysis.found and overflow_analysis.unresolved,
        "bounded candidate overflow did not fail closed",
    )

    raw_false_positive_cases = {
        "uncomposed list": 'labels = ["research", "raw"]',
        "separate named values": 'subject = "research"\nquality = "raw"',
        "descriptive text": 'note = "research and raw are separate labels"',
        "reassigned constructor alias": (
            'from pathlib import Path\nBuilder = Path\nBuilder = print\n'
            'root = Builder("research", "raw")'
        ),
        "JavaScript unjoined labels": (
            'const labels = ["research", "raw", "L01-private.md"];'
        ),
        "JavaScript descriptive values": (
            'const subject = "research"; const quality = "raw";'
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

    exact_consumer = (
        'CLAIM_MAP = "research/positive-claims.json"\n'
        'RAW_INPUT = Path("research") / "raw" / '
        '"L20-pg17-hybrid-search.md"\n'
    )
    validate_executable_raw_consumer(
        "consumer.py",
        exact_consumer,
        {
            "file_type": "python",
            "raw_paths": ["research/raw/L20-pg17-hybrid-search.md"],
        },
        {"research/raw/L20-pg17-hybrid-search.md"},
    )
    validate_executable_raw_consumer(
        "consumer.js",
        'const CLAIM_MAP = "research/positive-claims.json"; '
        'const parts = ["research", "raw", '
        '"L20-pg17-hybrid-search.md"]; const RAW_INPUT = parts.join("/");',
        {
            "file_type": "javascript",
            "raw_paths": ["research/raw/L20-pg17-hybrid-search.md"],
        },
        {"research/raw/L20-pg17-hybrid-search.md"},
    )
    expect_failure(
        lambda: validate_executable_raw_consumer(
            "consumer.py",
            'CLAIM_MAP = "research/positive-claims.json"\n'
            'name = choose("L01-private.md")\n'
            'RAW_INPUT = Path("research") / "raw" / name',
            {
                "file_type": "python",
                "raw_paths": ["research/raw/L20-pg17-hybrid-search.md"],
            },
            {"research/raw/L20-pg17-hybrid-search.md"},
        ),
        "dynamic raw consumer",
    )
    expect_failure(
        lambda: validate_executable_raw_consumer(
            "consumer.py",
            'CLAIM_MAP = "research/positive-claims.json"\n'
            'RAW_INPUT = Path("research") / "raw" / "L01-private.md"',
            {
                "file_type": "python",
                "raw_paths": ["research/raw/L01-private.md"],
            },
            {"research/raw/L20-pg17-hybrid-search.md"},
        ),
        "non-allowlisted exact raw consumer",
    )
    expect_failure(
        lambda: validate_executable_raw_consumer(
            "consumer.sh",
            'RAW_INPUT="research/raw/L20-pg17-hybrid-search.md"',
            {
                "file_type": "shell",
                "raw_paths": ["research/raw/L20-pg17-hybrid-search.md"],
            },
            {"research/raw/L20-pg17-hybrid-search.md"},
        ),
        "unsupported executable raw consumer type",
    )

    pilot = read_tracked_text("docs/SCIP-PILOT.md")
    requirements = read_tracked_text("tooling/requirements-scip.txt")
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
            "PASS GSR-SELF-TEST parser_cases=4 path_identity_adversarial=9 "
            "historical_tuple_adversarial=2 boundary_adversarial=7 "
            "raw_path_adversarial=49 scip_adversarial=13"
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
        f"{status} GSR-MANIFEST schema={manifest['schema_version']} "
        f"sha256={manifest_sha256} "
        f"source={manifest['source_revision']}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
