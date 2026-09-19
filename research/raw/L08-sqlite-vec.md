# L08 — sqlite-vec: maturity, limits, performance, license, fit for ~200k-node corpus embeddings

Lane: L08 (T2 embeddings) · Research date: 2026-08-25 · All primary-source fetches made 2026-08-25 unless noted.

## Version & maturity snapshot
- Upstream `asg017/sqlite-vec`: pure-C single-file SQLite extension, successor to sqlite-vss. 8,046 stars / 349 forks / 202 open issues (GitHub API, 2026-08-25).
- Latest stable **v0.1.9 (2026-03-31)**: bugfix for DELETE on vec0 tables having metadata TEXT columns >12 chars (#274). PyPI package `sqlite-vec` latest = 0.1.9.
- Latest pre-release **v0.1.10-alpha.4 (2026-05-18)**: fixes around "the new ivf/diskann features". Main branch builds DiskANN by default (`SQLITE_VEC_ENABLE_DISKANN=1`) plus experimental IVF flag → ANN indexes exist only in the alpha line, NOT in stable.
- Official stance: "sqlite-vec is a pre-v1, so expect breaking changes!" (README banner).
- Release cadence: v0.1.0 2024-08 → 0.1.6 2024-11 → 0.1.7 / 0.1.8 / 0.1.9 by 2026-03-31; repo last push 2026-05-18 (~3 months quiet at research date). Author's stated plan (2024-08 announcement): reach v1 "next year or so", then maintenance mode.
- Sponsorship: Mozilla Builders (lead), Fly.io, Turso, SQLite Cloud, Shinkai (README).
- License: **MIT OR Apache-2.0** dual (announcement post + README); GitHub detects Apache-2.0. Permissive ✓

## Hard limits (C source `sqlite-vec.c` @ main commit 04d28bd, read 2026-08-25)
- Max dimensions per vector column: **8,192** (`#define SQLITE_VEC_VEC0_MAX_DIMENSIONS 8192`; enforced at CREATE VIRTUAL TABLE: "Dimension on vector column too large"). Per-vector bytes at cap: float32 32 KiB, int8 8 KiB, bit 1 KiB.
- Rows: **no hard cap** anywhere in source; rowid-keyed shadow tables, bounded only by SQLite limits (~9.2e18) and disk.
- Chunked storage: `chunk_size` default **1024** vectors/chunk, must be divisible by 8, max **4096** (`SQLITE_VEC_CHUNK_SIZE_MAX`).
- Column caps (site/features/vec0.md): metadata ≤16 (strict TEXT/INTEGER/FLOAT/BOOLEAN; WHERE ops only = != < <= > >=), partition keys ≤4 (docs: keep ~100s+ vectors per unique partition value), auxiliary ≤16.
- Element types float32 / int8 / bit; distances L2 + cosine (+L1 scalar) for f32/int8, Hamming for bit; binary quantization requires dims % 8 == 0. SQLite ≥3.41 recommended; Python: `pip install sqlite-vec` → `sqlite_vec.load(conn)` on stdlib sqlite3.

## Performance (official benchmarks, author's Mac M1 mini 8 GB, 2024-08 post)
100k disk-backed vectors, avg KNN latency:
- float32: 192d=17 ms · 384d=31 ms · 768d≈56 ms · 1024d=73 ms · 1536d=106 ms · 3072d=214 ms
- bit: 1536d=7 ms · 3072d=11 ms
1M vectors: float32 192d≈192 ms up to 3072d≈8.52 s; bit≈124 ms. Author's stated practical ceiling for latency-sensitive apps: "probably in the 100's of thousands" of vectors depending on dims/quantization.
Brute-force cross-tool, k=20: SIFT1M (1M×128d): faiss 10 ms < sqlite-vec static 17 ms < vec0 33–35 ms < DuckDB 46 ms < usearch 56 ms < numpy 136 ms. GIST1M (500k×960d): static 41 ms, usearch 46 ms, faiss 50 ms, vec0 87–89 ms, DuckDB 307 ms.
Third-party (simplevecdb README, sqlite-vec v0.1.6, 10k×384d): f32 3.55 ms · int8 3.93 ms · bit 0.27 ms (~13x faster than f32).
Quantization quality: binary quantization of text-embedding-3-large ≈"95% accuracy" (author anecdote); mxbai-embed-large-v1 / nomic-embed-text-v1.5 trained for binarization → claimed 5–10% quality loss for ~10x faster queries.

## Fit for ~200k-node Graphify corpus (embeddings beside graphifyy graphs in one SQLite DB)
- Storage @200k nodes: f32 768d ≈ 586 MB (+ few % shadow overhead); int8 147 MB; bit ≈ 19 MB; a 384d Matryoshka slice halves those again. Comfortable in one .db alongside node-link JSON tables.
- Latency @200k (linear extrapolation of official 100k numbers): f32 768d ≈ 110 ms/query (borderline); bit ≪ 20 ms. Recommended two-stage layout: bit coarse KNN k≈200 → rerank candidates against f32/int8 copy → exact-quality top-k near bit-scan cost. Partition keys (e.g., repo id) shrink scans further.
- RAM during bursts: KNN allocates per-chunk work buffers (chunk_size × dims × elem ≈ 3 MB/column at defaults), never the whole table → no threat to the MemAvailable ≥ 3072 MiB floor; OS page cache covers the rest.
- Integration: same database file as graphifyy graphs → JOIN vec0 rowids to graph node rowids in plain SQL; transactional consistency across graph rebuild + embedding insert; zero extra services; offline; CPU SIMD (AVX/NEON paths in source; x86 EPYC fine).
- Risks: pre-v1 breaking changes (pin ==0.1.9); stable line is brute-force only (DiskANN alphas immature — alpha.4 still fixing ivf/diskann bugs); metadata-in-vec0 had edge-case bugs (v0.1.9) → prefer ordinary SQL tables joined by rowid over vec0 metadata columns for rich filters.

## Findings

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|sqlite-vec v0.1.9 (pinned)|tool|https://github.com/asg017/sqlite-vec|MIT OR Apache-2.0|pre-v1; stable 0.1.9 2026-03-31; 8.0k stars; last push 2026-05-18; DiskANN only in 0.1.10 alphas|5|4|4|3|1|H|Pure-C ext, runs everywhere; 100k×768d f32 ≈56 ms/query brute force (official 2024-08); dims ≤8192 + no row cap verified in source; PyPI wheel + sqlite_vec.load() into Python 3.13 stdlib sqlite3|
|Bit/int8 quantization + float32 rerank|technique|https://alexgarcia.xyz/blog/2024/sqlite-vec-stable-release/index.html|(uses MIT extension)|shipped since v0.1.0; vec_quantize_binary() + int8 columns stable|5|4|3|3|2|H|bit@1536d 7 ms vs f32 106 ms @100k (official); ≈95% recall after binarization on t-e-3-large; binarization-trained models (mxbai/nomic) cut loss to 5–10%|
|Matryoshka dimension truncation (vec_slice+vec_normalize)|technique|https://github.com/asg017/sqlite-vec/blob/main/site/api-reference.md|(uses MIT extension)|shipped; first-class docs|4|3|2|2|1|M|Truncating 768d→384d halves storage and scan time linearly; requires Matryoshka-capable embedding model|
|sqliteai/sqlite-vector (SQLite Cloud)|tool|https://github.com/sqliteai/sqlite-vector|Elastic License 2.0 modified — free ONLY inside OSI-approved open-source projects; commercial production needs paid license (owner approval if adopted)|very active (pushed 2026-08-25); 1,096 stars; SIMD kernels + TurboQuant 2/3/4-bit|2|4|3|3|3|H|1M×768d INT8 preloaded: 37.6 ms/query @99.5% recall@20 (vendor benchmark, Apple M5 Pro); BLOB-based API, no vec0-style virtual tables|

## Verdict
Top pick: pin `sqlite-vec==0.1.9` — the only permissively-licensed, SQLite-native vector store that keeps 200k embeddings in the SAME .db as graphifyy graphs (rowid JOINs for semantic+graph hybrid queries, zero services, chunked scans far under the 3 GiB RAM floor). Store an int8 primary column + bit coarse column, query bit KNN k≈200 then rerank in SQL for exact-quality top-k at sub-20 ms-class cost. Skip the sqliteai fork (Elastic license would need owner approval); revisit when a stable release ships the in-progress DiskANN indexes.
