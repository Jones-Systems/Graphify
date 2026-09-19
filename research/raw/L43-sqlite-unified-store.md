# L43 — SQLite unified store beside structural graphs

Investigated 2026-08-25. Only public-source findings are retained as
recorded; no installed library version, compile option, or deployment state is
established.

FINDINGS TABLE:

| Item | Type | URL | License | Maturity | StackFit | EffGain | EffectGain | QualGain | AdoptCost | Conf | KeyEvidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Unified single-file store: chunks row + FTS5 external-content + vec0 + JSONB payload in one .db beside graphs | strategy | github.com/asg017/sqlite-vec/issues/48 ; github.com/liamca/sqlite-hybrid-search | components MIT/Apache-2.0/public-domain | proven pattern (basic-memory KG-MCP, liamca template) | 5 | 4 | 3 | 3 | 2 | H | Maintainer-endorsed same-rowid design; one transaction makes lexical, vector, and payload updates atomic, avoiding cross-store drift |
| sqlite-vec stable v0.1.9 (brute-force exact KNN) | tool | github.com/asg017/sqlite-vec/releases.atom | MIT OR Apache-2.0 (both files in tree) | pre-1.0, 8k stars, wide deployment; loads via stdlib sqlite3 enable_load_extension | 5 | 4 | 2 | 3 | 2 | H | releases.atom ordering confirms v0.1.9 stable line above v0.1.8/v0.1.7; exact scan gives recall 1.0 (>= LanceDB ANN recall) |
| Upstream ANN alpha v0.1.10-alpha.4 (Rescore/DiskANN/experimental IVF) | tool | github.com/asg017/sqlite-vec/releases/tag/v0.1.10-alpha.4 | MIT OR Apache-2.0 | alpha, 2026-05-18; IVF disabled by default | 4 | 3 | 4 | 3 | 3 | M | Release notes: DiskANN neighbor-leak fix, ALTER TABLE RENAME fix; only needed if corpus >~1M chunks or latency SLO fails |
| vlasky/sqlite-vec fork v0.2.6-alpha: MMR rerank, AVX2/NEON Hamming SIMD, KNN distance filters, INSERT OR REPLACE | tool | github.com/vlasky/sqlite-vec/blob/main/CHANGELOG.md | inherits upstream dual [INFERENCE] | very active (2025-11 to 2026-08-22); fork-governance risk | 4 | 3 | 4 | 4 | 3 | M | Dated changelog; base = upstream v0.1.7-alpha.2 |
| FTS5 external-content table + triggers synced to chunks | technique | sqlite.org/fts5.html | public domain | core since 2015 | 5 | 3 | 2 | 2 | 1 | H | The public FTS5 documentation defines external-content tables, synchronization triggers, and built-in bm25(); availability must be checked on the selected SQLite build. |
| JSONB/JSON core + generated columns for structured payloads and node properties | technique | sqlite.org/json1.html | public domain | JSON core since 3.38, JSONB since 3.45 | 5 | 3 | 2 | 2 | 1 | H | The public JSON documentation defines JSON functions and JSONB; generated columns can expose selected values, but availability and schema fit require a selected SQLite build. |
| RRF fusion in pure SQL (k=60) over rowid-aligned fts/vec CTEs | strategy | github.com/liamca/sqlite-hybrid-search | n/a (SQL pattern) | documented copy-ready implementation | 5 | 3 | 3 | 3 | 1 | H | Issue #48 guidance; ROW_NUMBER ranks -> SUM(1/(k+r)). Any later reranking stage and constant require separate evaluation. |
| WAL concurrent-reader config: journal_mode=WAL, read-only readers, one writer, bounded busy timeout, explicit transactions, and measured checkpoint policy | strategy | sqlite.org/wal.html (recorded update 2026-08-24) | public domain | canonical concurrent-reader pattern | 5 | 3 | 2 | 2 | 1 | H | The recorded WAL documentation describes reader/writer concurrency and checkpoint constraints. The report also records a WAL-reset bug and fixes in 3.51.3 with backports; every version and fix must be reverified before selection. |
| VACUUM INTO snapshot + Connection.backup() page-stepped live copy; auto_vacuum=INCREMENTAL + incremental_vacuum(N) for routine reclamation | strategy | sqlite.org/lang_vacuum.html ; sqlite.org/backup.html | public domain | core since 3.27/3.11 | 5 | 2 | 1 | 2 | 1 | H | Docs describe destination-space, source-readability, and page-stepped backup behavior. Dataset size, step size, duration, and cadence require target measurements. |
| Litestream continuous WAL-shipping DR | tool | github.com/benbjohnson/litestream | Apache-2.0 (GPLv3->Apache at v0.3.4) | mature v0.3.14; v0.5+ LTX format non-drop-in | 3 | 2 | 1 | 2 | 2 | M | Release history verified 2026-08; local-dir targets offline-safe; S3/object targets = requires separate cloud-service review |
| vec0 knobs: INT8[768]/BIT[768] via vec_quantize_binary(), repo_id TEXT PARTITION KEY, indexed metadata filters, +content auxiliary col | technique | alexgarcia.xyz/blog/2024/sqlite-vec-metadata-release/index.html | part of sqlite-vec (MIT/Apache) | shipped v0.1.6 (2024-11) | 5 | 3 | 2 | 2 | 1 | M | BIT[384]=48B vs FLOAT[384]=1536B (32x smaller); partition key prunes scan per repo; brute force stays O(n) without it |

VERDICT: The recorded candidate is a rowid-aligned SQLite store combining
FTS5, sqlite-vec, and structured payload columns in one transaction. It is a
bake-off candidate, not a selected store: exact SQLite and extension versions,
compile options, recall, latency, concurrency, durability, backup behavior,
and migration thresholds require target measurements. Readers should open the
store read-only and a single writer should own updates; concrete timeouts,
checkpoint settings, quantization, and backup cadence remain deployment
parameters.
