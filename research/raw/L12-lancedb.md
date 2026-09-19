# LANE L12 — LanceDB Embedded (T2 embeddings candidate)

Investigated 2026-08-25. Scope: performance benchmarks, license, disk-format stability,
zero-server operation on this Debian VPS (16 cores, no GPU, MemAvailable floor 3072 MiB),
Python 3.13 wheels, fit for 1–5M vectors derived from the 196k-node corpora.

## Verified facts (primary sources, all checked 2026-08-25)

- PyPI `lancedb` latest stable: **0.37.1**, `requires-python >=3.10`, ~7.1M weekly downloads.
  https://pypi.org/project/lancedb/
- Wheels are **cp38-abi3** (CPython stable ABI): manylinux_2_17_x86_64 + manylinux_2_28_x86_64,
  manylinux_2_24_aarch64, macOS x86_64/arm64, win_amd64 → install cleanly on Python 3.13.
  https://pypi.org/simple/lancedb/
- Default wheel targets x86-64-haswell (AVX2+FMA+F16C); `Illegal instruction` risk exists only
  on pre-Haswell CPUs (`lancedb-compat` package is the fallback). Our AMD EPYC Genoa has
  AVX2/AVX-512 ⇒ default wheel fine. (PyPI README)
- License: **Apache-2.0**, verified in-repo for both lancedb/lancedb (SDK) and
  lance-format/lance (core engine/format; ships MIT-embedded Polars/bitpacking snippets —
  still permissive). No cloud-only license on the embedded path.
- Zero-server: repo tagline "OSS **embedded** retrieval library"; `lancedb.connect('<PATH>')`
  opens a local directory directly — no daemon/service; local-FS or object-store backends.
- Cadence: stable releases every ~2 weeks (README); GitHub releases show an active
  v0.38.0-beta.N line as of today. Python SDK is still 0.x ⇒ occasional API churn until its 1.0.
- Disk format: Lance **file format 2.1 declared stable 2025-10-03** — newer readers keep reading
  2.1 data (forward backward-compat); older readers may REFUSE datasets using newer table
  feature flags. Package upgrades do NOT rewrite existing data (storage version pinned per
  dataset); 2.0→2.1 required a one-time dataset copy and is expected to be the last such.
  Lance **SDK 1.0.0 announced Dec 2025**: breaking API changes gated behind major-version
  bumps post-1.0 and decoupled from on-disk compatibility.
- Benchmarks (official blog; single-core search, top-k=10, nprobes=24, no raw-vector refine):
  | Index        | Recall@10 | avg ms | p99 ms | QPS/core |
  |--------------|-----------|--------|--------|----------|
  | IVF_PQ       | 74.8%     | 12.8   | 14.7   | 78       |
  | IVF_RQ 3-bit | 93.5%     | 3.8    | 4.7    | 261      |
  | IVF_RQ 5-bit | 96.2%     | 4.6    | 5.6    | 218      |
  | IVF_RQ 7-bit | 96.8%     | 5.0    | 5.9    | 201      |
  5-bit RaBitQ ≈2.8× QPS/core and ≈2.6× lower p99 vs unrefined IVF_PQ (+21.4 pp recall).
- Hot-memory ratios (docs.lancedb.com/indexing/vector-index): PQ ≈1/64–1/16 of raw;
  RaBitQ ≈1/32 raw (5-bit ≈5/32); scalar quantization ≈1/4; refinement against raw vectors
  can push effective footprint to ≈33/32 of raw. Query-time modes fast/normal/accurate trade
  recall vs latency on the same index.
- Caveats: HNSW recall highly sensitive to ef/nprobes defaults (lance-format/lance issue #8036,
  GIST1M deficits at default ef); benchmark figures above are vendor-published — no independent
  VectorDBBench-style confirmation surfaced in this pass.
- Hybrid retrieval: native BM25 FTS (`table.create_fts_index("col")`),
  `search(query_type="hybrid")`, default `RRFReranker()`, pluggable rerankers
  (docs.lancedb.com/search/hybrid-search, /search/full-text-search).

## Fit @ 1–5M vectors, 768-d float32

Raw = 3.07 GB (1M) … 15.36 GB (5M). IVF_RQ 5-bit hot set ≈ 0.48–2.40 GB ⇒ inside the
3072 MiB MemAvailable floor even at 5M vectors; index lives on disk with demand paging, so
RAM tracks the query working set rather than corpus size. 16 cores give parallel headroom
(200+ QPS/core single-threaded per vendor numbers).

## Findings table

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|lancedb Python SDK (embedded vector DB)|tool|https://github.com/lancedb/lancedb|Apache-2.0|High activity, pre-1.0 (stable 0.37.1, biweekly cadence)|5|5|4|4|2|H|PyPI 0.37.1 ≥3.10; cp38-abi3 manylinux wheels run on Py3.13; connect() opens local dir, zero server (checked 2026-08-25)|
|lance core engine + format (lance-format/lance)|repo|https://github.com/lance-format/lance|Apache-2.0|Format 2.1 stable 2025-10-03; SDK 1.0 Dec 2025|5|4|4|4|2|H|Format stability blog + SDK 1.0 policy decouple API breaks from stored data|
|Lance file-format 2.1 stability guarantees|technique|https://www.lancedb.com/blog/lance-file-2-1-stable|(spec of Apache-2.0 project)|Declared stable 2025-10-03|4|3|4|5|1|H|Newer readers read 2.1 data long-term; upgrades never auto-rewrite; old readers may refuse new feature flags → pin versions|
|IVF_RQ / RaBitQ quantized ANN index|strategy|https://www.lancedb.com/blog/rabitq-gets-faster-higher-recall-lower-latency-query-time-control|(in-repo Apache-2.0)|Recent (2025–26), shipping|5|5|5|4|2|M|96.2% recall@10 @ 4.6 ms avg, 218 QPS/core single-core; 5-bit hot ≈5/32 raw ⇒ 5M×768-d ≈2.4 GB fits floor|
|IVF_HNSW_SQ/PQ/FLAT index family|strategy|https://docs.lancedb.com/indexing/vector-index|(in-repo Apache-2.0)|Shipping, tuning-sensitive|4|3|4|3|2|M|Docs position HNSW-backed IVF as recall-first default; issue #8036 shows recall deficits at default ef — must tune nprobes/ef|
|Native BM25 FTS + hybrid RRF rerank|technique|https://docs.lancedb.com/search/hybrid-search|(in-repo Apache-2.0)|Shipping|4|4|5|4|1|H|create_fts_index + query_type="hybrid" + RRFReranker default; lexical+semantic fusion beside graphifyy link-graph expansion|

## Verdict

**Top pick:** `lancedb` embedded (pin ==0.37.x) as the T2 vector layer, indexed with 5-bit
IVF_RQ (RaBitQ): best recall-per-megabyte seen in this lane's review, 5M-vector hot set
(~2.4 GB @768-d) respects our 3072 MiB floor, fully offline, zero-server, Apache-2.0, and
Python 3.13-ready via cp38-abi3 wheels.

**Why:** disk-first design means RAM scales with working set, not corpus; Lance format 2.1
(Oct 2025) + SDK 1.0 policy de-risk long-term storage; built-in BM25 hybrid adds keyword
recall without extra infrastructure next to graphifyy's structural graphs.

**Integration sketch:** `pip install lancedb pyarrow`; DB dir per repo e.g.
`Graphify/vectors/<repo>.lance`; `db = lancedb.connect(path)`; table columns
(`node_id`, `chunk_id`, `text`, `vector`) fed by a local embedding model (documented
embedding-functions integrations incl. sentence-transformers work offline);
build IVF_RQ 5-bit cosine index + `create_fts_index("text")`; query via
`search(query_type="hybrid").rerank(RRFReranker())` fused with graphifyy neighbor expansion;
pin `lancedb==0.37.*`, snapshot datasets before any storage-version migration.
