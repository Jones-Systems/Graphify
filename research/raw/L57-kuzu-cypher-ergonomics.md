# L57 — OpenCypher ergonomics through an embedded Kùzu-lineage database

Date recorded: 2026-08-25. Public-source claims are retained as recorded; no
later currentness or deployment fit is claimed.

## Recorded upstream status

 kuzudb/kuzu GitHub repo was archived read-only on 2025-10-10; final release kuzu==0.11.3 (PyPI, 2025-10-10) bundles algo/fts/json/vector extensions since the hosted extension server was discontinued. Community continuation is ACTIVE: LadybugDB (github.com/LadybugDB/ladybug, MIT, 'formerly known as Kuzu', 6,288 commits) released v0.16.x->v0.19.1 (latest 2026-08-04), carrying over docs, CLI binaries, multi-language bindings, and an MCP server.

## Recorded Python packaging

The recorded package metadata showed CPython 3.13 manylinux wheels for both kuzu 0.11.3 and ladybug 0.19.1. The recorded download count and version constraints require fresh verification before adoption.

## Ergonomics

The public `mcp-server-ladybug` project exposes a generic Cypher query tool
with row and character caps and multiple transports. A general query language
supports arbitrary multi-hop shapes without a large verb surface, while a few
bounded canned queries can still cover common paths. Safety must be enforced
at the database boundary with `Database(path, read_only=True)` because the
recorded server documentation did not expose a read-only switch. The public
API also exposes a buffer-pool limit; its value must be measured rather than
copied from this report.

## Non-authoritative integration outline

A candidate shape is to build an immutable database from Parquet or CSV with
a short-lived writer, then serve bounded queries through a read-only
connection. The original effort, buffer-size, and example-count estimates are
not retained as evidence.

## Findings table
|Item|Type|URL|License|Maturity|StackFit|EffGain|EffectGain|QualGain|AdoptCost|Conf|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|LadybugDB ladybug 0.19.1 (Kùzu continuation)|tool|github.com/LadybugDB/ladybug; pypi.org/project/ladybug|MIT|Active: v0.16-v0.19.1, 2026-08-04; cp313 wheel verified|5|4|4|3|1|H|PyPI JSON 2026-08-04; releases.atom v0.19.1..v0.16.0; README 'formerly known as Kuzu'; 90k weekly dl|
|mcp-server-ladybug|tool|github.com/LadybugDB/mcp-server-ladybug|MIT|Shipped with fork; pip/uvx/Docker|4|5|3|3|1|H|README: single query Cypher tool, 1024-row/50k-char caps, stdio/sse/stream; no read-only flag (gap)|
|Generic openCypher-over-MCP vs custom CLI verbs|strategy|pattern per mcp-server-ladybug + kuzudb MCP lineage|n/a|Implemented in both upstream and continuation|5|4|4|4|1|M|A generic query surface avoids verb proliferation; read_only=True confines database effects, while a small bounded verb set can cover common paths.|
|kuzu 0.11.3 (frozen upstream)|tool|pypi.org/project/kuzu/0.11.3|MIT|Frozen: archived 2025-10-10, no future fixes|4|4|3|2|1|H|PyPI upload 2025-10-10; GitHub archived/read-only banner; extension server discontinued (self-host ghcr.io/kuzudb/extension-repo)|
|Ladybug CLI binary (REPL)|tool|github.com/LadybugDB/ladybug/releases/latest|MIT|Precompiled per release|2|2|2|1|1|H|README install table; human debugging aid, weak structured output vs Python/MCP|

## Verdict

The recorded comparison preferred evaluating the LadybugDB continuation over
the archived Kùzu release. That is source-dated, not an adoption decision.
Version and wheel availability, read-only enforcement, output caps,
buffer-pool behavior, storage migration, and query ergonomics all require
fresh verification and target measurements.
