# L46 — T7 Storage: Parquet-Backed Graph Snapshots (NetworkX node-link JSON → Parquet)

*Researched 2026-08-25. Environment: Debian VPS, 16 CPU, no GPU, Python 3.13, MemAvailable floor 3 GiB. All versions/dates verified against primary sources today.*

## Context & current-state fit

Repos serialize structural graphs (graphifyy==0.9.16 output, NetworkX in-memory) as node-link JSON. Node-link JSON repeats `"source"`/`"target"`/`"nodes"` keys per element and boxes every attribute as a dict entry — worst case for size and for query access (whole-document parse to answer one predicate). A two-table Parquet snapshot (`nodes.parquet`, `edges.parquet`) is columnar, dictionary-encoded, splittable, directly queryable by DuckDB with zero load step, and is now the de-facto interchange convention even at billion-edge scale: **LDBC Graphalytics began publishing `-v.parquet`/`-e.parquet` vertex/edge files alongside tar.zst text packages in February 2026** (cit-Patents 3M n/16M e; kgs 832k n/17M e).

NetworkX conversion is mechanical: `nx.node_link_data(G)` (v3.6.1; kwargs `source/target/name/key/edges/nodes`; multigraph `key` support; verified from networkx/readwrite/json_graph/node_link.py source) returns exactly the two flat lists (`data["nodes"]`, `data["edges"]`) that map 1:1 onto the two tables; `nx.node_link_graph()` stays the round-trip when a live NX object is needed.

## Candidate items

|Item|Type|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|Two-table Parquet snapshot layout (`nodes.parquet` id64+attrs; `edges.parquet` src/dst/type/weight) replacing node-link JSON|technique|https://ldbcouncil.org/benchmarks/graphalytics/datasets/|n/a (format Apache-2.0)|High (convention shipped by LDBC at B-edge scale since 2026-02)|5|4|4|4|1|H|Graphalytics datasets page: "February 2026. Vertex and edge files are now available in Parquet format"; NX node_link_data returns exactly two flat lists|
|pyarrow 25.0.1 writer (`compression="zstd"`, per-column levels, dictionary encoding; Py 3.10–3.14 covers our 3.13)|tool|https://arrow.apache.org/docs/python/parquet.html|Apache-2.0|Very high|5|3|3|3|1|H|PyPI 25.0.1 rel 2026-08-10; docs: ZSTD supported but default remains Snappy (opt in required)|
|DuckDB 1.5.x direct Parquet queries (`FROM 'nodes.parquet'`, views, joins, recursive CTE traversal)|tool|https://duckdb.org/docs/current/data/parquet/overview|MIT|Very high|5|4|3|4|1|H|Stable v1.5.5 (2026-07-22); zero-copy read_parquet, hive partitioning, views|
|DuckDB v2.0 recursive-CTE rewrite (preview "Cyanoptera", stable fall 2026)|tool|https://www.duckdb.org/2026/08/17/duckdb-20-highlights|MIT|Preview|4|2|5|3|2|H|Official blog 2026-08-17: 1M-edge reachability CTE 4.90 s (v1.5.4) → **0.12 s** (v2.0 preview, ~40×); partition-aware planner; async Parquet I/O|
|DuckPGQ v1.2.2 SQL/PGQ (`CREATE PROPERTY GRAPH`, `GRAPH_TABLE`, paths, pagerank, WCC)|tool|https://github.com/cwida/duckpgq-extension|MIT|Medium (research-grade)|3|2|4|3|4|H|duckdb.org graph_queries guide: **unavailable on DuckDB 1.5.x; requires v1.4.4** — conflicts with DuckLake (≥1.5.2)|
|Apache GraphAr (Incubating) 0.13.0 — standardized chunked property-graph format over Parquet payload|repo/spec|https://graphar.apache.org/docs/specification/format/|Apache-2.0|Early-mid (incubating since 2024-03; rel 0.13.0 Aug 2025; format v1.0.0)|3|2|2|3|4|H|Apache clutch page + implementation-status doc (Parquet r/w in C++/Python/Spark)|
|Immutable dated snapshot dirs + Hive partitioning + MANIFEST.json (sha256, counts, rev) + `latest` pointer; cross-snapshot diffs via partition filter|strategy|https://duckdb.org/docs/current/data/partitioning/hive_partitioning|n/a (DIY)|n/a|5|4|3|4|1|H|DuckDB first-class hive-partitioned reads/writes; each snapshot ≈ tens of MB at our scale|
|DuckLake v1.0 — SQL-catalog lakehouse over Parquet; per-commit snapshots; `AT (VERSION⇒…)`/`AT (TIMESTAMP⇒…)` time travel; `ducklake_expire_snapshots`|tool|https://ducklake.select/docs/stable/duckdb/usage/snapshots|MIT (Stichting DuckDB Foundation)|New-but-stable (v1.0 Apr 2026; requires DuckDB ≥1.5.2)|4|3|3|4|2|H|Docs: snapshot metadata tables, attach-at-snapshot, append-only files, destructive-expiration caveat|
|Delta Lake time travel via deltalake 1.6.2 (delta-rs, Py ≥3.10): `DeltaTable(uri, version=N)`, `load_as_version`, VACUUM limits history|tool|https://delta-io.github.io/delta-rs/python/usage.html|Apache-2.0|Very high|2|2|2|3|3|H|PyPI 1.6.2 (2026-07-08); open scan-regression issue delta-rs#4623 (Jul 2026)|
|Kùzu embedded graph DB **archived 2025-10-10** (final v0.11.3; forks LadybugDB/Bighorn unproven)|repo/cautionary|https://github.com/kuzudb/kuzu|MIT (archived)|Dead upstream|1|0|0|2|0|H|README archive notice; The Register 2025-10-14; validates plain-files+query-engine over embedded GDB|
|CSR adjacency export from src-sorted edge table (`scipy.sparse.csgraph`) feeding PPR-over-KG fusion|technique|https://docs.scipy.org/doc/scipy/reference/sparse.csgraph.html|BSD-3|Very high|5|3|4|3|2|M|Sorted-by-src edges compress better and load straight into csr_matrix for CPU PPR, dropping NetworkX from the hot path|
|DuckDB VARIANT (GA v1.5) for ragged node attributes instead of NULL-sparse column zoo|technique|https://www.duckdb.org/2026/08/17/duckdb-20-highlights|MIT|New (v2.0 adds shredded Parquet r/w)|4|2|2|3|1|M|v2.0 blog: VARIANT auto-shreds semi-structured data; compressed storage; Parquet shredded write coming in v2.0|

## Compression ratios at ~200k-node scale

- Planning ranges (dictionary/RLE/delta encodings then ZSTD pages, per parquet.apache.org compression docs): vs uncompressed JSONL — nodes 3–10×, numeric-heavy edges 5–15× (to ~20×); vs already-compressed JSON only ~2–4× survives.
- Extrapolation to our scale [INFERENCE]: 200k nodes + ~1M edges ≈ 100–220 MB node-link JSON → **~5–20 MB Parquet-zstd(level 3, dictionary, src-sorted edges)** ⇒ ~8–15× vs raw JSON, ~2–4× vs gzip JSON; projected-column reads skip attribute bytes entirely. Unique-string-heavy payloads reduce the gap.
- Query-side anchor: DuckDB blog 1M-edge reachability 0.12 s (v2.0 preview) vs 4.90 s (v1.5.4).
- **Gap:** no measured on-repo number — lane is read-only; run a 15-min benchmark (real repo graph → both formats, `du -b`) before publishing ratios.

## Verdict

Top pick: items 1+7+3 — `node_link_data(G)` lists → pyarrow-zstd `nodes.parquet`/`edges.parquet` under immutable `snapshots/{date}+sha256/` + MANIFEST.json + `latest` symlink, queried by pinned duckdb==1.5.* views/recursive CTEs (`SET memory_limit='2GB'; SET threads=8` — DuckDB defaults to 80% of RAM, which would breach the 3 GiB MemAvailable floor).
Skip DuckPGQ (forces DuckDB 1.4.4 pin, blocks DuckLake) and Delta/Iceberg (overkill at tens-of-MB snapshots); revisit DuckLake once on ≥1.5.2 if catalog/time-travel beats symlinks; treat DuckDB 2.0's 40× CTE rewrite as trigger to re-benchmark.
Snapshot sha256 doubles as the rebuild-cache key for tantivy/LanceDB/graphifyy artifacts.