# L57 — OpenCypher ergonomics through an embedded Kùzu-lineage database

Date recorded: 2026-08-25. Public-source claims are retained as recorded and were not independently revalidated during remediation.

## Recorded upstream status

 kuzudb/kuzu GitHub repo was archived read-only on 2025-10-10; final release kuzu==0.11.3 (PyPI, 2025-10-10) bundles algo/fts/json/vector extensions since the hosted extension server was discontinued. Community continuation is ACTIVE: LadybugDB (github.com/LadybugDB/ladybug, MIT, 'formerly known as Kuzu', 6,288 commits) released v0.16.x->v0.19.1 (latest 2026-08-04), carrying over docs, CLI binaries, multi-language bindings, and an MCP server.

## Recorded Python packaging

The recorded package metadata showed CPython 3.13 manylinux wheels for both kuzu 0.11.3 and ladybug 0.19.1. The recorded download count and version constraints require fresh verification before adoption.

## Ergonomics

 canonical pattern is ONE generic query(cypher) MCP tool — mcp-server-ladybug (MIT, pip/uvx/Docker) exposes exactly that with context-protection caps (1024 rows / 50k chars, --max-rows/--max-chars) and stdio/sse/stream transports. Cypher beats bespoke CLI verbs for agents: a widely represented query language (openCypher in-distribution for LLMs), deterministic self-correctable engine errors, arbitrary multi-hop shapes without verb explosion; keep only 3-5 canned verbs for hot paths (top-k neighbors, A-to-B path). Safety: Database(path, read_only=True) rejects writes at engine level (in-memory DBs cannot be read-only); mcp-server-ladybug documents NO read-only flag, so wrap/enforce at DB level. MEMORY: buffer_pool_size defaults to ~80% of system RAM — MUST set explicitly (512 MiB-1 GiB) to respect the stated target memory floor (cross-ref L49).

## Recorded integration estimate

 ~150-250 LOC, 0.5-1 day, no daemon, fully offline: (1) refresh-time exporter dumps graphifyy KG to Parquet/CSV and COPY FROM into .lbdb via short-lived RW connection; (2) embed lb.Database(read_only=True, buffer_pool_size=512MiB) + Connection.execute in a query server, rows_as_dict()/get_as_df()->JSON with LIMIT clamps; (3) schema-DDL + 5 example queries in bootstrap prompt. Sync+async APIs, UDFs, Pandas/Polars/Arrow results all supported.

## Findings table
|Item|Type|URL|License|Maturity|StackFit|EffGain|EffectGain|QualGain|AdoptCost|Conf|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|LadybugDB ladybug 0.19.1 (Kùzu continuation)|tool|github.com/LadybugDB/ladybug; pypi.org/project/ladybug|MIT|Active: v0.16-v0.19.1, 2026-08-04; cp313 wheel verified|5|4|4|3|1|H|PyPI JSON 2026-08-04; releases.atom v0.19.1..v0.16.0; README 'formerly known as Kuzu'; 90k weekly dl|
|mcp-server-ladybug|tool|github.com/LadybugDB/mcp-server-ladybug|MIT|Shipped with fork; pip/uvx/Docker|4|5|3|3|1|H|README: single query Cypher tool, 1024-row/50k-char caps, stdio/sse/stream; no read-only flag (gap)|
|Generic openCypher-over-MCP vs custom CLI verbs|strategy|pattern per mcp-server-ladybug + kuzudb MCP lineage|n/a|Proven in both upstream and fork|5|4|4|4|1|M|Agents know Cypher natively; read_only=True confines injection to reads; verbs reserved for <=5 hot paths|
|kuzu 0.11.3 (frozen upstream)|tool|pypi.org/project/kuzu/0.11.3|MIT|Frozen: archived 2025-10-10, no future fixes|4|4|3|2|1|H|PyPI upload 2025-10-10; GitHub archived/read-only banner; extension server discontinued (self-host ghcr.io/kuzudb/extension-repo)|
|Ladybug CLI binary (REPL)|tool|github.com/LadybugDB/ladybug/releases/latest|MIT|Precompiled per release|2|2|2|1|1|H|README install table; human debugging aid, weak structured output vs Python/MCP|

## Verdict

Recorded candidate: Adopt ladybug==0.19.1 (not frozen kuzu) — identical embedded openCypher ergonomics with live maintenance and verified cp313 wheels. Integrate as read-only .lbdb built from graphifyy KG via COPY FROM Parquet, served through one query(cypher,params) MCP tool with row/char caps, explicit buffer_pool_size, and schema-DDL bootstrap prompt; skip Apache AGE (server ops overhead).
