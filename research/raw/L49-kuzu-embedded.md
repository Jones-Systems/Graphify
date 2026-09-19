# L49 — Kùzu embedded graph database

Status recorded 2026-08-25; no later upstream currentness is claimed.

## Critical upstream finding (verified)
Upstream **Kùzu is dead**: `kuzudb/kuzu` was archived read-only on **2025-10-10**; final release **v0.11.3** published to PyPI the same day (wheel upload timestamps 2025-10-10T13:35–13:36Z). Official notice confirms: prior releases remain usable; official extension server discontinued; docs/blog moved to kuzudb.github.io. (Apple-acquisition rumors circulate but are **reported, not established** — irrelevant to adoption decision either way.) The live continuation is **LadybugDB** (repo `LadybugDB/ladybug`, "formerly known as Kuzu", maintained by Ladybug Inc., MIT retained), plus a niche fork `Vela-Engineering/kuzu`.

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|kuzu==0.11.3 (frozen upstream)|tool|https://github.com/kuzudb/kuzu|MIT|EOL-frozen (archived 2025-10-10)|4|2|2|2|2|H|cp313 and cp313t free-threaded manylinux_2_27_x86_64 wheels were recorded for 0.11.3; the repository was archived on the recorded date. Future maintenance and wheel availability are not established.|
|ladybug==0.19.1 (LadybugDB successor)|tool|https://github.com/LadybugDB/ladybug|MIT|Active 0.x (0.19.1 2026-08-04; steady cadence 0.15→0.19 through 2026)|5|3|3|3|2|M|requires_python >=3.10,<3.15 with cp313 manylinux x86_64 + musllinux wheels (PyPI project page); kuzu-API-compatible (`import ladybug; ladybug.Database(...)`) per migration blog 2026-03-01; NEW: direct attach/query of Arrow/DuckDB/Parquet (`CREATE NODE TABLE ... WITH (storage='arrow://...')`), subgraphs (`CREATE GRAPH`/`USE`), schema-free node creation; repo read 2026-08-25: 6,288 commits, 1.6k stars, non-fork re-seeded repo; stewardship by newly-formed Ladybug Inc. — longevity unproven|
|Vela-Engineering/kuzu fork|tool|https://github.com/Vela-Engineering/kuzu|MIT|Early-active (updated Jul 2026)|2|1|1|1|3|L|Adds concurrent multi-writer support (removes upstream single-writer limit); positioned for AI-agent memory workloads; much smaller community/evidence base than LadybugDB (cmu-db/dbdb.io issue #162)|
|Parquet-source-of-truth + rebuild-on-format-change|strategy|https://kuzudb.github.io/docs/migrate/|n/a|Proven (this IS the sanctioned kuzu upgrade path)|5|2|1|4|1|H|Native on-disk format is NOT cross-version stable: storage-version check rejects mismatches ("Database file version: 34, Current build storage version: 36", issue #5254) and 0.11.0 collapsed the DB dir to single-file data.kz; documented migration = EXPORT DATABASE (parquet) → IMPORT DATABASE into fresh DB; maps 1:1 onto an existing DuckDB/Parquet snapshot layer|
|node-link → DDL + COPY FROM adapter|technique|https://docs.ladybugdb.com/client-apis/python/|n/a|Documented API surface|5|2|1|2|1|M|Group node-link records by label, create node and relationship tables, and load DataFrame/Arrow inputs with `COPY FROM`. The public API exposes buffer-pool and thread controls; both must be derived from deployment measurements. The algorithm extension provides PageRank, not necessarily personalized PageRank.|

**Recorded conclusion:** The dated comparison favored evaluating LadybugDB's
continuation before the archived Kùzu release. Any embedded graph database
should be evaluated as a rebuildable derived index over portable snapshots
because the native storage format is version-sensitive. Package availability,
maintenance status, migration mechanics, and compatibility require fresh
verification.

Integration candidate: load immutable node/link snapshots through `COPY FROM`
or a documented Arrow/Parquet attachment, open serving connections read-only,
and select buffer-pool and thread limits from measurements. The report does
not establish a migration, replacement query path, resource budget, or
deployment choice.
