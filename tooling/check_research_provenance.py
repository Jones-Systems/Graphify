#!/usr/bin/env python3
"""Fail-closed checks for Graphify's claim-scoped research provenance."""

from __future__ import annotations

import argparse
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

FULL_OID_RE = re.compile(r"[0-9a-f]{40}")
LANE_RE = re.compile(r"L(100|0?[1-9]|[1-9][0-9])")
LANE_RANGE_RE = re.compile(
    r"\bL(100|0?[1-9]|[1-9][0-9])"
    r"(?:\s*[–-]\s*L?(100|0?[1-9]|[1-9][0-9]))?\b"
)
MARKER_RE = re.compile(r"<!--\s*positive-claim:\s*([A-Z0-9-]+)\s*-->")
SOURCE_CODE_REFERENCE_RE = re.compile(
    r"research/(?:raw(?:/|\b)|positive-claims\.json\b)"
)
RESERVED_POSITIVE_SECTIONS = {
    "Evidence-bound experiment order",
    "Positive claims",
    "Supported synthesis",
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

    found: Counter[str] = Counter()
    positive_sections = {
        path: set(sections)
        for path, sections in manifest["positive_sections"].items()
    }
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
                    require(
                        section in positive_sections.get(relative, set()),
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
        section: str | None = None
        seen_sections: set[str] = set()
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            heading = re.match(r"^## (.+)$", line)
            if heading:
                section = heading.group(1).strip()
                if section in sections:
                    seen_sections.add(section)
                continue
            if section not in sections or not line.startswith("|"):
                continue
            cells = markdown_cells(line)
            if is_separator_row(cells):
                continue
            if cells[0] in {"Order", "Supported statement"}:
                continue
            require(MARKER_RE.search(line) is not None,
                    f"{relative}:{line_number} positive row lacks a claim marker")
        require(seen_sections == sections,
                f"{relative} positive sections differ: "
                f"missing={sorted(sections - seen_sections)}")

    approved_raw_consumers = set(manifest["raw_consumer_files"])
    code_suffixes = {".py", ".sh", ".js", ".mjs", ".cjs", ".ts", ".tsx"}
    observed_raw_consumers: set[str] = set()
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or path.suffix not in code_suffixes:
            continue
        if path.resolve() == CHECKER_PATH or RAW_ROOT in path.parents:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if SOURCE_CODE_REFERENCE_RE.search(text):
            observed_raw_consumers.add(path.relative_to(ROOT).as_posix())
    require(observed_raw_consumers == approved_raw_consumers,
            f"raw consumer allowlist differs: observed={sorted(observed_raw_consumers)} "
            f"approved={sorted(approved_raw_consumers)}")

    observed_raw_references: set[str] = set()
    for path in ROOT.rglob("*.md"):
        if ".git" in path.parts or RAW_ROOT in path.parents:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "research/raw/" in text:
            observed_raw_references.add(path.relative_to(ROOT).as_posix())
    approved_raw_references = set(manifest["raw_reference_files"])
    require(observed_raw_references == approved_raw_references,
            f"raw Markdown reference allowlist differs: "
            f"observed={sorted(observed_raw_references)} "
            f"approved={sorted(approved_raw_references)}")
    return f"claims={len(claims)} lanes={len(allowlisted)} raw_consumers=0"


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
        "e1c8b4395d135b4dad3bbbbcaef6571f5425db5f:research/RANKING.md" in text,
        "historical recommendation definition is not immutable-bound",
    )
    mapped: dict[int, str] = {}
    for line in text.splitlines():
        if not re.match(r"^\| R(?:[1-9]|1[0-9]|20) \|", line):
            continue
        cells = markdown_cells(line)
        number = int(cells[0][1:])
        require(number not in mapped, f"duplicate historical R{number}")
        require(cells[2] == "`historical_identity_only`",
                f"R{number} compatibility status grants more than identity")
        mapped[number] = cells[1]
    require(set(mapped) == set(range(1, 21)),
            f"historical recommendation map differs: {sorted(mapped)}")

    referenced: set[int] = set()
    text_suffixes = {".md", ".py", ".txt", ".sh"}
    for base in (ROOT / "docs", ROOT / "tooling"):
        for path in base.rglob("*"):
            if (
                not path.is_file()
                or path.resolve() == CHECKER_PATH
                or "__pycache__" in path.parts
                or path.suffix not in text_suffixes
            ):
                continue
            text_value = path.read_text(encoding="utf-8", errors="replace")
            referenced.update(
                int(match.group(1))
                for match in re.finditer(r"\bR([1-9]|1[0-9]|20)\b", text_value)
            )
    require(referenced.issubset(mapped),
            f"downstream historical IDs lack compatibility entries: "
            f"{sorted(referenced - set(mapped))}")
    return f"mapped=R1-R20 downstream_refs={len(referenced)} identity_only=true"


def check_public_safety(_: dict[str, Any], __: dict[str, dict[str, str]]) -> str:
    pilot = (ROOT / "docs" / "SCIP-PILOT.md").read_text(encoding="utf-8")
    requirements = (ROOT / "tooling" / "requirements-scip.txt").read_text(
        encoding="utf-8"
    )
    for required in (
        "mktemp -d",
        "trap cleanup EXIT HUP INT TERM",
        'archive --format=tar "$resolved_commit"',
        "pilot destination is not empty",
        "network-denied sandbox",
        "immutable lock record",
        "Authority effect: none",
    ):
        require(required in pilot, f"SCIP protocol lacks required gate: {required}")

    prohibited = {
        "absolute home path": r"/home/[^\s`]+",
        "unbound archive": r"archive\s+HEAD\b",
        "remote Python bootstrap": r"get-pip\.py",
        "executable npx resolution": r"\bnpx\s+(?:-y|--yes)\b",
        "executable npm install": r"^[ \t]*(?:\$[ \t]+)?npm[ \t]+(?:install|exec)\b",
        "predictable SCIP temp path": r"/tmp/scip(?:-|/)",
        "recorded result table": r"^## Recorded pilot results",
        "embedded graph counts": r"\b(?:nodes|links)\s*=\s*\d+",
    }
    combined = pilot + "\n" + requirements
    for label, pattern in prohibited.items():
        require(re.search(pattern, combined, re.MULTILINE) is None,
                f"SCIP protocol contains {label}")
    require("mktemp -d" in requirements,
            "pinned Go CLI example must use a fresh temporary directory")

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
    return "scip_protocol=public_fixture_fail_closed l40_l42=parameterized"


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
        print("PASS GSR-SELF-TEST parser_cases=4")
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
