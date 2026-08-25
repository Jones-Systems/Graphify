# L09 - LanceDB embedded (T2 embeddings lane)

Researched: 2026-08-25 (all sources retrieved same day). Lane scope: evaluate LanceDB
embedded (OSS) as the semantic/vector tier for M Jones's 18 VPS repos, alongside the pinned
graphifyy==0.9.16 structural-graph stack (markdown link-graphs + code AST, NetworkX node-link JSON).
Environment targets: Debian 13 VPS, 16-core AMD EPYC Genoa (AVX-512 capable), NO GPU,
64 GB RAM with hard floor MemAvailable >= 3072 MiB during bursts, Python 3.13,
offline/self-hostable + permissive license required; cloud/API-key components flagged requires-owner-approval.

## Findings table

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|LanceDB OSS embedded (lancedb PyPI 0.37.1, 2026-08-10)|tool|https://github.com/lancedb/lancedb|Apache-2.0|Mature (11.3k stars, ~7.1M weekly downloads, biweekly stable cadence)|5|4|4|4|1|H|Embedded connect(path), no server; cp310-abi3 manylinux_2_28 wheel valid on CPython 3.13; PyPI retrieved 2026-08-25|
|Lance columnar format v2 (lance-format/lance, pylance)|tool|https://github.com/lance-format/lance|Apache-2.0|Stable format contract; SDK fast-moving (6,970 stars)|4|3|3|3|1|H|README: stable data_storage_version is a long-term reader-compat contract; 'next' alias unstable; retrieved 2026-08-25|
|IVF_PQ disk ANN index (memory-mapped)|technique|https://docs.lancedb.com/indexing/vector-index|(part of OSS)|Stable default workhorse|4|3|4|3|1|H|Index mmap-ed from disk; PQ codes ~192 B/vector at D=1536 (num_sub_vectors=192, ~32x compression); query working set tens of MB|
|IVF_RQ multi-bit RaBitQ quantization (2026-07)|technique|https://www.lancedb.com/blog/rabitq-gets-faster-higher-recall-lower-latency-query-time-control|(part of OSS)|New (vendor blog 2026-07-10; no independent replication yet)|3|3|4|4|1|M|Vendor single-core bench: 96.8% Recall@10, p99 5.9 ms, 200 QPS/core vs IVF_PQ 74.8%/14.7 ms/78 QPS|
|IVF_HNSW_SQ / IVF_HNSW_FLAT variants|technique|https://docs.lancedb.com/indexing/vector-index|(part of OSS)|Stable|4|3|3|4|1|M|Independent 2026 test reached R@10 0.97-0.99 with IVF_HNSW_SQ + refine_factor (implicit-none.com)|
|Native BM25 full-text search (Tantivy-free)|technique|https://docs.lancedb.com/search/full-text-search|(part of OSS)|Stable; legacy tantivy-py path removed upstream|5|3|4|3|1|H|create_fts_index('text', replace=True); no external service or extra dependency; optimize() consolidates unindexed fragments|
|Hybrid vector+FTS with RRFReranker (+ optional local CrossEncoderReranker)|strategy|https://docs.lancedb.com/search/hybrid-search|(part of OSS; rerank models local)|Stable; RRF is default fusion|5|3|4|4|1|H|search(query_type='hybrid').rerank(RRFReranker()); cross-encoder needs pre-downloaded HF model but stays fully offline|
|Zero-server deployment pattern: one writer per table, concurrent readers (MVCC+OCC)|strategy|https://docs.lancedb.com/faq/faq-oss|(n/a)|Documented production pattern|5|2|3|2|1|H|Conflicting writers retry then can fail ('Too many concurrent writers'); batch writes; periodic optimize/cleanup in maintenance window|
|Version + format pinning: lancedb==0.37.x, data_storage_version='2.0', never --pre track|strategy|https://lance.org/format/file/versioning/|(n/a)|Recommended practice|5|1|3|1|0|H|Biweekly releases skipped stable minors (no 0.28/0.31/0.35) and shipped breaking changes (add_columns builder API in 0.37.x); V2 manifest paths unreadable before lance 0.17.0|
|LanceDB Cloud / Enterprise|tool|https://cloud.lancedb.com|Commercial (not OSS)|GA/beta offering|1|0|0|0|5|H|REJECTED for this program: managed/cloud violates offline constraint and would be requires-owner-approval; embedded OSS already covers need|

## Verdict
Top pick: lancedb==0.37.1 embedded as the T2 vector store - Apache-2.0 throughout, true zero-server
(pip install; connect('./index/<repo>')), Python 3.13 covered via abi3 manylinux_2_28 wheels (Debian 13 glibc OK;
EPYC Genoa exceeds the Haswell/AVX2 SIMD baseline), and disk-mmap ANN keeps query RSS to tens of MB so the
3072 MiB MemAvailable floor holds. Independent 2026 numbers beat pgvector ~2x on p50 latency at matched recall
(1.30 vs 2.50 ms at R@10=0.95) plus 20x ingest / 11.6x index-build speed - exactly our single-node low-concurrency profile.
Integration sketch: one table per repo under ./index/, rows keyed by graphifyy node-id ingested from NetworkX node-link
JSON via pyarrow; plain exact scan below ~100k vectors, then IVF_PQ(num_partitions~=rows/4096, num_sub_vectors=D/8)
with refine_factor or IVF_HNSW_SQ; native-BM25 hybrid + RRFReranker over chunk text; single writer process;
pin data_storage_version='2.0' plus lancedb/pylance/pyarrow versions.

## Evidence detail

### Performance (retrieved 2026-08-25)
- implicit-none.com pgvector-vs-LanceDB reproducible benchmark (2026; LanceDB 0.36.0 vs pgvector 0.8.6; 100k x 1536-dim):
  p50 at ~R@10 0.95: LanceDB 1.30 ms vs pgvector 2.50 ms; at ~0.99: 1.86 vs 3.42 ms (LanceDB on IVF_HNSW_SQ;
  scalar-quantized plateau ~0.95 without refine_factor). Ingest 20x faster, index build 11.6x faster, ~1/3 disk usage.
  At 8 concurrent clients LanceDB 611->1338 QPS vs pgvector 350->2376 QPS (GIL / in-process serving limits).
  Our usage (local CLI tooling, low concurrency) sits squarely in LanceDB's winning regime.
- IISWC 2025 empirical study (atlarge-research.com PDF): storage-oriented high-concurrency setup; older LanceDB
  IVF_PQ config <100 QPS even at 256 concurrent queries; quantization reduced accuracy. Confirms concurrency is the
  weak axis, not raw single-thread speed.
- AIMultiple 2026 (7 engines, MedRAG-50k, recall equalized at R@10=0.95): relevance spread tiny across engines
  (nDCG@10 0.803-0.817; LanceDB top at 0.817). Engine choice moves speed/memory, not baseline quality.
- Vendor RaBitQ/IVF_RQ blog (2026-07-10): large gains over IVF_PQ (table above) - promising but vendor-only;
  keep IVF_PQ/HNSW as defaults until independently replicated.
- Scale note: repo corpora (1e3..1e5 chunks) do not strictly need an ANN index; exact scans are fast and lossless.
  Introduce indexes only when a merged corpus passes ~100k vectors.

### License
- Both lancedb/lancedb and lance-format/lance show 'License: Apache License 2.0' on GitHub (retrieved 2026-08-25);
  Rust third-party licenses published per repo (RUST_THIRD_PARTY_LICENSES.html).
- DB/search layer fully offline, zero API keys. Hosted embedding-function providers are opt-in extras and would be
  requires-owner-approval; plan uses locally computed embeddings instead.
- LanceDB Cloud/Enterprise are separate commercial products; not needed for embedded operation.

### Disk-format stability
- Stability attaches to the FILE FORMAT, not the SDK: each dataset records data_storage_version; once written with a
  stable version ('2.0'), future Lance releases keep reading it. Older readers may not open newer formats; the 'next'
  alias carries no guarantee (lance README + lance.org versioning guide, retrieved 2026-08-25).
- Separate knob: V2 manifest paths require lance >= 0.17.0 readers; migrate_manifest_paths_v2() exists but must not run
  concurrently with other operations.
- SDK cadence is fast (~every 2 weeks; stable minors 0.28/0.31/0.35 skipped entirely; 0.37.x changed add_columns to a
  builder API). Therefore: pin package versions AND explicit data_storage_version='2.0'; never build persisted indexes
  on the fury.io --pre track; keep one lancedb build per dataset directory.

### Zero-server operation on this VPS
- Install = pip install lancedb (pulls pylance + pyarrow + numpy); db = lancedb.connect('/abs/path') opens a plain
  directory. No daemon, no port, no systemd unit. CPU-only operation; wheel SIMD baseline x86-64-haswell
  (AVX2/FMA/F16C) satisfied by EPYC Genoa; pre-Haswell hosts would need lancedb-compat (not our case).
- Wheels: lancedb-0.37.1-cp310-abi3-manylinux_2_28_x86_64 (abi3 -> works on CPython 3.13); pylance abi3 likewise;
  pyarrow ships dedicated cp313 wheels; all require glibc >= 2.28 (Debian 13 far exceeds).
- RAM profile: IVF_PQ/HNSW indexes are memory-mapped from disk; resident working set per query ~= nprobes share of
  partition pages (tens of MB at our scale) + refinement buffer k*refine_factor*D*4 bytes (~6 MB example) + fixed
  codebook/centroid metadata (MBs). OS page cache may grow toward index size but stays reclaimable, so the
  MemAvailable >= 3072 MiB floor is safe. Index BUILD peaks higher than steady state (training samples,
  intermediates) - schedule builds outside other compute bursts or cap build parallelism.
- Concurrency: embedded library with MVCC + optimistic concurrency control; conflicting writers retry and can fail
  with 'Too many concurrent writers'. Pattern: single logical writer (one indexing job), many readers; batch adds;
  table.optimize() and cleanup_old_versions() periodically in a maintenance window.
- Full-text/hybrid: native Lance FTS with BM25 (tantivy-py dependency removed); RRFReranker fusion built in;
  CrossEncoderReranker runs offline if the model was pre-downloaded. No cloud anywhere in the retrieval path.

## Risks and mitigations
1. Fast SDK churn / occasional breaking changes -> lock lancedb==0.37.1 (+pylance/pyarrow pins); upgrade deliberately.
2. Quantized recall loss -> set refine_factor against raw vectors; benchmark recall@10 on our own chunks before
   trusting defaults (AIMultiple shows engines tie only when recall is equalized).
3. High-concurrency serving is the weak axis (IISWC 2025; implicit-none 2026) -> irrelevant for single-user CLI use;
   if ever needed, fan out per-process readers rather than threads inside one Python GIL.
4. Write contention on shared dataset dirs -> exactly one writer per table; never two processes writing one repo table.
5. Unindexed recent fragments slow queries between optimizes -> run table.optimize() after each indexing pass.

## Sources (all fetched 2026-08-25)
- https://pypi.org/project/lancedb/ (v0.37.1, 2026-08-10; abi3 manylinux_2_28 wheel; haswell SIMD note)
- https://github.com/lancedb/lancedb (Apache-2.0, 11,267 stars)
- https://github.com/lance-format/lance (Apache-2.0, 6,970 stars; file-format stability statement)
- https://lance.org/format/file/versioning/ ; https://lancedb.github.io/lance/api/py_modules.html (data_storage_version; manifest-v2 caveat)
- https://implicit-none.com/en/pgvector-vs-lancedb-benchmark/ (independent equal-recall benchmark, 2026)
- https://atlarge-research.com/pdfs/2025-iiswc-vectordb.pdf (IISWC 2025 empirical study)
- https://aimultiple.com/open-source-vector-databases (equal-recall quality comparison, 2026)
- https://www.lancedb.com/blog/rabitq-gets-faster-higher-recall-lower-latency-query-time-control (vendor, 2026-07-10)
- https://docs.lancedb.com/indexing/vector-index ; /search/full-text-search ; /search/hybrid-search ; /faq/faq-oss
- https://arxiv.org/abs/2608.12812 (2026 preprint: ~11x faster indexing claim, provisional)
