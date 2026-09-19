# L20 — PostgreSQL 17 tsvector+pgvector hybrid-search comparison

Investigated 2026-08-25 by lane L20 (T3 hybrid). Question: when should a
multi-repository research corpus use a central PostgreSQL 17 search service
instead of per-repository file-local stores?

> **Evidence boundary:** the comparison below retains only public-source
> material. No PostgreSQL deployment, suitability, workload binding, or
> operating authority is established.

## Findings

|Item|Type|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|pgvector extension|tool|https://github.com/pgvector/pgvector|PostgreSQL License|High|5|3|4|3|1|H|v0.8.6 released 2026-07-29; steady fix cadence 0.8.2-0.8.6 Feb-Jul 2026; 22.7k GitHub stars; packaged in Debian trixie (0.8.0-1) and PGDG pool (0.8.6-1.pgdg+1)|
|HNSW index params + iterative scans|technique|https://github.com/pgvector/pgvector#iterative-index-scans|(part of pgvector)|High|5|4|4|3|1|H|m=16, ef_construction=64, hnsw.ef_search=40 defaults; iterative_scan strict_order/relaxed_order shipped 0.8.0 (2024-10-30) fixes filtered-recall cliff (10% selectivity x ef_search 40 = ~4 hits otherwise); hnsw.scan_mem_multiplier=2; builds fastest when graph fits maintenance_work_mem (NOTICE warns when exceeded)|
|halfvec fp16 + binary_quantize rerank|technique|https://github.com/pgvector/pgvector#half-precision-indexing|(part of pgvector)|High|5|3|3|2|1|H|halfvec up to 4000 dims halves index/table bytes; documented pattern: binary HNSW prefilter then rerank by original vectors for recall; README scaling advice names halfvec + binary quantization as the two levers|
|PG17 tsvector FTS core|technique|https://www.postgresql.org/docs/current/textsearch-controls.html|PostgreSQL License (built-in)|Very High|5|2|3|3|1|H|setweight A-D + concatenated tsvector + GIN + websearch_to_tsquery (never raises syntax errors on user input); ts_rank_cd = cover-density ranking with NO corpus statistics - docs state ranking functions use no global information, i.e. lexical leg alone is not BM25 (no IDF)|
|RRF fusion of FTS leg + vector leg|strategy|https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual|n/a (pattern)|High|5|4|5|4|1|H|score = 1/(60+rank_lex) + 1/(60+rank_vec); rank-based fusion avoids calibrating incomparable scores. The constant and candidate windows require evaluation.|
|ParadeDB pg_search (true BM25 in Postgres)|tool|https://github.com/paradedb/paradedb/releases|AGPL-3.0 (+commercial)|High activity|3|3|4|4|3|M|pg_search 0.25.4 released 2026-08-25; native BM25 scoring + RRF hybrid incl. vector pushdown (0.25.1 changelog); AGPL conflicts with the stated permissive-license constraint; Rust/pgrx build adds packaging friction|
|VectorChord (vchordrq, RaBitQ quantization)|tool|https://github.com/tensorchord/VectorChord|AGPLv3 / Elastic License 2.0 dual|Young-mid (1.x, 2026)|2|2|3|2|3|M|Vendor benchmarks report large-collection indexing and footprint results. Their reproducibility, target relevance, and license fit require separate evaluation.|
|pgvectorscale StreamingDiskANN|tool|https://github.com/timescale/pgvectorscale|PostgreSQL License|Maintained, early-stage|2|2|3|2|3|L|0.9.0 adds PG18 support + concurrent index builds; disk-oriented design targets 10M-1B vectors, for which no target need is established; open issue #269 reports ~0.70 recall on Cohere 10M benchmark; requires pgrx/Rust toolchain to build|
|Resource isolation for a central service|strategy|https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html|n/a (ops practice)|High|3|3|3|3|2|M|Use a dedicated database and role; select cgroup and PostgreSQL memory limits only from current workload measurements. MemoryHigh throttles while MemoryMax is a last-resort hard boundary; exact values are deployment-specific.|
|Central PG17 hybrid service over file-local stores|strategy|https://www.postgresql.org/docs/17/ddl-schemas.html; https://github.com/lancedb/lancedb|n/a|-|3|3|4|3|3|M|A central database can provide one transactional SQL surface and shared metadata joins; file-local stores reduce daemon coupling and failure-domain sharing. Cross-repository benefit and operational cost require measurement.|

### Verdict
Candidate: pgvector plus built-in tsvector FTS, fused with RRF, is a
publicly documented central-service option. This lane does not establish that
it beats file-local stores for the target corpus. Before adoption, bind an
exact PostgreSQL deployment, extension package, workload, failure boundary,
resource budget, backup plan, and comparative benchmark. A possible schema is
`chunks(repo, path, body, tsv, emb)` with GIN and HNSW indexes and ranked CTEs;
all pins and index parameters require fresh verification.

## Evidence log
- pgvector CHANGELOG: 0.8.6 2026-07-29, 0.8.5 2026-07-08, 0.8.4 2026-06-30, 0.8.3 2026-06-17, 0.8.2 2026-02-25, 0.8.1 2025-09-04, 0.8.0 2024-10-30 (iterative scans), 0.7.0 2024-04-29 (halfvec/sparsevec/binary_quantize). Accessed 2026-08-25.
- packages.debian.org trixie: postgresql-17-pgvector 0.8.0-1 (amd64 among others), depends postgresql-17. apt.postgresql.org pool shows 0.8.6-1.pgdg+1. Accessed 2026-08-25.
- postgresql.org news banner 2026-08-13: PostgreSQL 18.6, 17.11, 16.15 ... released.
- PostgreSQL docs textsearch-controls.html (current): ts_rank/ts_rank_cd semantics, weights default {0.1,0.2,0.4,1.0}, normalization bitmask, no global statistics. Accessed 2026-08-25.
- pgvector README (master): HNSW options m/ef_construction/ef_search defaults, Index Build Time + maintenance_work_mem NOTICE, filtering-after-index-scan rationale for iterative scans, halfvec limits, binary rerank example. Accessed 2026-08-25.
- ParadeDB releases/changelog: pg_search 0.25.4 (2026-08-25); 0.25.1 vector pushdown for RRF queries; hybrid-search manual documents RRF 1/(60+rank). License AGPL-3.0 community + commercial. Accessed 2026-08-25.
- VectorChord repo/blog 2026: AGPLv3/ELv2 dual license; LAION-100M footprint table; 100x indexing claim (vendor-benchmark caveat noted).
- timescale/pgvectorscale: latest release 0.9.0 (PG18 support, concurrent builds); LICENSE = PostgreSQL License with no-maintenance-obligation disclaimer; issue #269 recall report. Accessed 2026-08-25.
- systemd.resource-control man page (latest): MemoryHigh throttling semantics, MemoryMax absolute limit + OOM-inside-unit, recommendation to prefer MemoryHigh with MemoryMax as last defense. Accessed 2026-08-25.
