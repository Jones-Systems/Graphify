# L11 — sqlite-vec for T2 embeddings (research findings)

Date: 2026-08-25 · Lane: L11 (T2 embeddings) · Scope: sqlite-vec maturity, limits (dimensions/rows), performance, license; fit for ~200k-node corpus embeddings inside SQLite next to graphifyy structural graphs; comparison with SQLite FTS5 for hybrid search.

Environment verified live on this VPS (2026-08-25, python3 probe): **Python 3.13.5, system SQLite 3.46.1, FTS5 compiled in (`ENABLE_FTS5`)**, `sqlite-vec` pip package not yet installed.

## Findings table

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|sqlite-vec (stable line v0.1.9)|tool|https://github.com/asg017/sqlite-vec|MIT OR Apache-2.0 (dual)|Pre-v1, very active; stable v0.1.9 (2026-03-31), alpha v0.1.10-alpha.4 (2026-05-18); ~1.4M weekly PyPI downloads; single lead author (Alex Garcia), backed by Mozilla Builders + Fly.io/Turso/SQLite Cloud sponsorships|5|4|4|3|1|H|Zero-dependency single-C-file extension; `pip install sqlite-vec`; declared pre-v1/breaking-changes in official API docs (checked 2026-08-25)|
|sqlite-vec int8/bit quantization modes|technique|https://alexgarcia.xyz/sqlite-vec/api-reference.html|MIT OR Apache-2.0|Shipped in v0.1.x stable (`vec_int8`, `vec_bit`, `vec_quantize_binary`); i8 scalar quantizer (`vec_quantize_i8`) still TODO stub|5|3|3|2|2|H|Author bench (2024-08-01): 100k x 3072d queries 214 ms float32 vs 11 ms bit (19x); bit storage 1 b/elem = 32x smaller than f32; ~95% recall anecdote for binary-quantized workload -> needs rerank validation|
|SQLite FTS5 (already in system SQLite)|tool|https://sqlite.org/fts5.html|Public domain (SQLite)|Rock-solid, in-core since SQLite 3.9.0 (2015); local VPS runs 3.46.1 with FTS5 enabled (verified 2026-08-25)|5|3|3|3|0|H|bm25() ranking, highlight()/snippet(), external-content/contentless tables, porter+trigram tokenizers; handles millions of rows; zero new dependencies|
|Hybrid: vec0 KNN + FTS5 BM25 fused via RRF in one SQLite DB|strategy|https://sqlite.org/fts5.html (ch.5 aux functions)|Public domain + MIT OR Apache-2.0|Both sides production-proven individually; fusion is plain SQL over two ranked subqueries joined on rowid (reciprocal-rank fusion or weighted score)|5|4|4|4|2|M|Same database file as graphifyy node-link JSON tables => transactional consistency + SQL joins across graph/text/vector; hybrid lexical+dense is standard corpus-QA practice; gain magnitude workload-dependent (needs small eval)|
|SQLite official Vec1 extension (v0.7, context/watch)|tool|https://sqlite.org/vec1/doc/trunk/doc/vec1.md|Public domain (SQLite.org)|Official SQLite.org extension, pre-1.0 (roadmap itself says "testing is insufficient"); IVFADC+OPQ ANN, L2+cosine, AVX2/NEON, f32-only, requires training step; NOT yet in Debian packages|4|4|3|4|3|H|Published tests: 760k x 768d cosine, nprobe 48 => recall@10 0.934 at ~1048 QPS single-thread (AMD 5950X); training 44 s on 16 threads; no partition keys, no dot-product yet (roadmap 2026)|

## Verdict
Top pick: pin `sqlite-vec==0.1.9` (stable, NOT the 0.1.10-alpha line) and store the ~200k-node embeddings as a `vec0` virtual table in the same SQLite DB as the graphifyy node-link JSON, paired with an FTS5 external-content table over node text for hybrid BM25+dense retrieval via SQL-side rank fusion. At 200k x 768d float32 (~586 MiB raw vector bytes; 154 MB as int8, 19 MB as bit) brute-force KNN lands around 100-150 ms/query (extrapolated from author's disk-backed benches: 100k x 768d <75 ms, 1M x 192d 192 ms) with exact recall@k=1.0 — comfortably within our no-GPU/low-RAM constraints and fine for research workloads. Re-evaluate official SQLite Vec1 (or sqlite-vec's experimental IVF/DiskANN alphas) only if interactive-latency ANN becomes a requirement; adopt-cost stays low because everything lives in the existing single-file SQLite artifact.

## Evidence appendix

### sqlite-vec facts (versions/dates)
- Stable release **v0.1.9, published 2026-03-31** (fixes DELETE failures with long metadata text values). Alpha **v0.1.10-alpha.4, published 2026-05-18** introduces/exercises Rescore, IVF, DiskANN indexes — explicitly pre-v1, may break. (GitHub releases, checked 2026-08-25.)
- First stable v0.1.0 announced **2024-08-01** (Alex Garcia blog: "Introducing sqlite-vec v0.1.0", dated August 1st, 2024): "written entirely in C with no dependencies, MIT/Apache-2.0 dual licensed".
- License confirmed twice: repo/blog statement + PyPI package metadata ("MIT License, Apache License, Version 2.0"). PyPI weekly downloads ~1.4M (checked 2026-08-25).
- Install: `pip install sqlite-vec`; also npm/gem/cargo/go bindings; precompiled loadable extensions via GitHub Releases; single `sqlite-vec.c`. Works offline after install; no cloud keys.

### Hard limits (from sqlite-vec.c main branch, lines verified 2026-08-25)
- `#define SQLITE_VEC_VEC0_MAX_DIMENSIONS 8192` — dimension per vector column capped at 8192 (error "Dimension on vector column too large"). Our candidate 384/768/1024/1536 all fine.
- `VEC0_MAX_VECTOR_COLUMNS 16`, `VEC0_MAX_PARTITION_COLUMNS 4`, `VEC0_MAX_METADATA_COLUMNS 16`, `VEC0_MAX_AUXILIARY_COLUMNS 16` per vec0 table.
- Element types: float32 (4 B/elem), int8 (1 B/elem), bit (1 b/elem). Distance: L2/cosine for f32+int8, Hamming for bit.
- Rows: no explicit row cap beyond SQLite's own limits (max rowid 2^63) — 200k rows is far inside; the real constraint is brute-force query latency + transient scan memory (chunked via incremental blob I/O, bounded per chunk).
- No ANN index in stable line: v0.1.x KNN is exhaustive/brute-force => recall@k = 1.0 exactly, latency linear in rows x dims. ANN (IVF/DiskANN/rescore) only in 0.1.10 alphas.

### Performance numbers (author-published, alexgarcia.xyz blog 2024-08-01; disk-backed unless noted)
- SIFT1M (1M x 128d, k=20): ~35 ms/query avg, ~4 s index build (brute force).
- 100k x 3072d f32: 214 ms; 1536d: 105 ms; <=1024/768/384/192d: <75 ms.
- 100k x 3072d **bit**: 11 ms (~19x faster than f32 same shape).
- 1M x 192d f32: 192 ms; 1M x 3072d f32: 8.52 s (brute force stops being interactive here).
- Extrapolation for us: **200k x 768d f32 ~= 100-150 ms/query**, exact results; int8 roughly half the bytes again faster-ish, bit ~30x faster but needs float rerank of top-N to protect recall.

### Storage math for ~200k-node corpus (per embedding column)
- 768d float32: 200000 x 768 x 4 B = 586 MiB (+small shadow-table/chunk overhead).
- 768d int8: 146 MiB. 768d bit: 18.3 MiB (32x smaller than f32).
- Matryoshka-friendly slicing available (`vec_slice` + `vec_normalize`).
- Fits easily in the graphifyy DB file; bursts stay far above the 3 GiB MemAvailable floor since scans are chunked.

### FTS5 facts (sqlite.org/fts5.html, checked 2026-08-25)
- In-core since SQLite 3.9.0; Debian's 3.46.1 ships it enabled (locally verified via `pragma compile_options` => `ENABLE_FTS5`).
- Built-in auxiliary functions: `bm25()`, `highlight()`, `snippet()`; external-content tables avoid duplicating text; contentless/contentless-delete variants shrink storage; trigram tokenizer enables substring matching.
- Public-domain license; zero deployment cost on this host.

### Hybrid sketch (fits our stack)
```sql
-- dense side
CREATE VIRTUAL TABLE vec_nodes USING vec0(
  node_id INTEGER PRIMARY KEY,
  emb float[768],
  +repo TEXT          -- metadata col (v0.1.6+), filterable in WHERE
);
-- lexical side (external content: no text duplication)
CREATE VIRTUAL TABLE fts_nodes USING fts5(body, content='nodes', content_rowid='id');
-- fusion: reciprocal rank fusion over the two ranked subqueries, joined on node_id
WITH d AS (SELECT node_id, ROW_NUMBER() OVER (ORDER BY distance) r
           FROM vec_nodes WHERE emb MATCH :q AND k = 100),
     t AS (SELECT id node_id, ROW_NUMBER() OVER (ORDER BY bm25(fts_nodes)) r
           FROM fts_nodes WHERE fts_nodes MATCH :qs LIMIT 100)
SELECT d.node_id, 1.0/(60+d.r) + 1.0/(60+t.r) AS score
FROM d JOIN t USING(node_id) ORDER BY score DESC LIMIT 20;
```
Single DB file => embeddings, FTS index, and graphifyy link-graph JSON stay transactionally consistent and joinable in plain SQL; backup story unchanged (one file).

### Watch item
Official SQLite **Vec1** (sqlite.org, version 0.7) now provides real ANN (IVFADC+OPQ, AVX2) with published recall/QPS curves (e.g., 760k x 768d cosine: recall@10 0.934 @ ~1048 QPS single-thread). Pre-1.0 (self-admitted insufficient testing), f32-only, needs a training step, absent from Debian repos — track, don't adopt yet.
