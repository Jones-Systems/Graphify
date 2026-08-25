# S-A Synthesis — Themes T1–T3 (GraphRAG · Vector/Embeddings · Hybrid Retrieval)

Date: 2026-08-25 · Host: Debian VPS, 16-core EPYC Genoa, no GPU, Python 3.13, MemAvailable ≥3072 MiB during bursts · graphifyy==0.9.16 structural graphs (NetworkX node-link JSON, ~196k nodes / 18 repos, md-heavy) · offline-preferred; no cloud keys without owner flag.
Inputs: raw files L01–L12, L15–L17, L19, L21; L13/L14/L18/L20 recovered from lane yield artifacts (no raw files exist); L19/L21 facts cross-checked against lane yields (raw files hold partial transcripts).

## 1. Consolidated top-10 recommendations

|Rank|Recommendation|Source lanes|Impact(0-5)|AdoptionEffort(S/M/L)|Confidence|Dependencies|
|---|---|---|---|---|---|---|
|1|Hybrid retrieval backbone: tantivy BM25 ∥ dense KNN ∥ graph PPR, fused by gated weighted three-way RRF score(d)=Σᵢ wᵢ/(60+rᵢ(d)) over top-100 windows (omit absent terms; w=(1,1,1); force w_ppr=0 when query matches <2 KG seeds)|L15,L16,L17,L07|5|M|H|#3,#4|
|2|Vector store (dedupes 5 lanes): pin sqlite-vec==0.1.9 vec0 tables in the SAME SQLite DB as graphifyy graphs (rowid JOINs, transactional, exact brute-force ≈100–150 ms @200k×768d); migrate to lancedb==0.37.x embedded IVF_RQ 5-bit + refine_factor past ~500k–1M vectors; Qdrant server reserved for true 1–5M/multi-process needs|L08,L09,L10,L11,L12|4|S|H|#3|
|3|Embedding model: Snowflake/snowflake-arctic-embed-m-v1.5 (Apache-2.0, ONNX in-repo, MTEB-R 55.14 @109M params) served offline via fastembed + onnxruntime>=1.20 (cp313 wheels verified); prefix queries "query: ", docs unprefixed|L13|4|S|H|—|
|4|Encode-once/quantize-thrice: write fp32 + int8 twin + bit-packed columns in one pass; query bit-KNN overfetch ~10×k → rescore vs fp32/int8 (96–99% retention at 4–32× storage cut); MRL-slice to 256d + renormalize where latency-bound|L14,L08|4|S|M|#3|
|5|Graph signal without LLMs: HippoRAG-2-style Personalized PageRank (damping 0.5, passage-node reset λ≈0.05) directly over existing node-link JSONs; scipy/igraph PPR = seconds at ~100k nodes, no extraction pass|L06,L07|4|S|M|existing graphifyy exports|
|6|LLM-free community layer: leidenalg==0.12.0 + igraph==0.11.8 (sorted vertices/edges + fixed seed ⇒ deterministic); recursive hierarchy; summaries = top-k PageRank representatives + LP-seeded labels + conductance/min-size pruning — replaces GraphRAG LLM community reports|L05,L01,L03|3|S|H|—|
|7|Reranker stage (gated): answerai-colbert-small-v1 (33M, <100 ms/query CPU) or bge-reranker-base ONNX-int8 (MIT, 2.2–6.3 s/100cand; cap pool at 50); enable only where held-out ΔnDCG@10 confirms (fit-dependent wins)|L18,L21|3|M|M-H|#1 fused window|
|8|Cheap lifts bundle: (a) heading-aware md chunking BEFORE any indexing (±9pt token-recall swing); (b) bi-temporal edge fields valid_at/invalid_at/expired_at copied into NetworkX JSON; (c) GraphRAG 7-table parquet artifact shape for interop|L07,L04,L01|3|S|H|none|
|9|Local-LLM semantic layer (owner-gated): lightrag-hku==1.5.6 fully local (Ollama 4B-class extractor, bge-m3 embedder) using insert_custom_kg to mount OUR graph.json beside its corpus-derived KG; mix-mode queries; incremental inserts dodge GraphRAG ≈14M-token community-rebuild tax|L02,L07,L03|4*|L|M|owner OK for RAM-floor-breaching batch windows|
|10|Phase-2 neural sparse: OpenSearch neural-sparse-doc-v2-distill (Apache-2.0, 67M, BEIR-13 50.4 vs BM25 45.6; tokenizer-only query path ≈BM25 speed) via ST>=5.0 SparseEncoder → ONNX Runtime int8; postings stored OUTSIDE LanceDB (no native sparse index)|L19|2|M|M|#1|

\* conditional on approved compute windows. Recs 1–8 are zero-LLM, day-one adoptable.

## 2. Architecture recommendation

Adopt a zero-LLM hybrid stack now: heading-aware chunk store per repo → tantivy==0.26.0 inverted index ({chunk_id u64, repo, path, symbol_path, body}; writer heap≈512 MB, ≤8 threads) plus sqlite-vec==0.1.9 vec0 tables (fp32[768] + int8 twin + bit twin of snowflake-arctic-embed-m-v1.5, encoded offline once via fastembed/onnxruntime>=1.20) inside ONE SQLite database that also holds the graphifyy node-link JSON → each query runs three legs — BM25 top-100, bit-KNN k≈200 rescored against fp32 (exact, sub-150 ms class at 200k×768d), PPR (networkx/scipy, damping 0.5, λ=0.05 passage seeding) over the structural graph — fused by gated weighted RRF score(d)=Σᵢ∈{bm25,vec,ppr} wᵢ/(60+rᵢ(d)), w=(1.0,1.0,1.0), w_ppr=0 unless ≥2 KG seeds, deterministic tie-break (−score, id) → optional answerai-colbert-small-v1 rerank of the fused top-50. leidenalg 0.12.0 communities give hierarchical navigation summaries at zero token cost. Escalation triggers: corpus >~500k–1M vectors → lancedb 0.37.x IVF_RQ 5-bit + refine_factor; owner approves local-LLM windows → LightRAG 1.5.6 dual-KG (its extraction + our graph via insert_custom_kg); precision ceiling hit → neural-sparse doc-v2-distill postings fused as a fourth RRF leg.

## 3. Rejected/excluded

- microsoft/graphrag standard pipeline — $60–150+/corpus hosted or multi-day CPU generation; project in maintenance mode; Azure SDK hard deps.
- LazyGraphRAG — announced 2024, never shipped in OSS package.
- pip-installing nano-graphrag/graspologic — graspologic pins requires_python <3.13 ⇒ unresolvable; vendor-and-strip only if ever needed (superseded by leidenalg route).
- Graphiti/Zep adoption — ~160 LLM calls per 5 KB doc on CPU; ~60 pre-1.0 releases/16 mo; Zep Cloud proprietary; temporal machinery idle on static snapshots (steal edge schema instead).
- Qdrant local mode — RAM-resident NumPy brute force, vendor warns >20k points, exclusive lock; standalone server deferred (extra daemon unjustified below 1–5M vectors).
- rank-bm25 — unmaintained since 2022; O(q×N) rescans; tens-of-GB dict index at 1M chunks breaches RAM floor.
- PyPI package named tantivy-py — dead squatter; install `tantivy`.
- BGE-M3 — lowest English retrieval of surveyed set (48.82 MTEB-R), fp32-forced CPU path grazes floor; 568M sparse head too heavy.
- CC-BY-NC weights (jina-embeddings-v3, naver/splade-v3, jina-reranker-v2-multilingual) plus jina-v2 <2 docs/s CPU kernel — license + unusable latency.
- Hosted embedding APIs (OpenAI/Cohere/Voyage) — cloud keys ⇒ requires-owner-approval under offline rule.
- sqliteai/sqlite-vector fork — Elastic License 2.0 (paid license required outside OSI projects).
- Neo4j CE (GPLv3 JVM service), FalkorDB (SSPL binaries), Kuzu (deprecated upstream).
- Full-corpus ColBERTv2/PLAID retrieval — CPU-feasible but heavy (P95 ~235–455 ms end-to-end at 523k docs); parked behind NextPlaid/FastPlaid/MUVERA triggers.
- Convex-combination and DBSF fusion today — need calibration labels (≥50 queries); revisit after eval harness exists.
- SQLite official Vec1 — pre-1.0, self-admitted insufficient testing, absent from Debian repos; track only. NetworKit deferred (>~10M edges).

## 4. Cross-theme synergies

- Quantization × stores: one encode job writing fp32/int8/bit serves sqlite-vec bit-coarse+rescore AND a later LanceDB IVF_RQ migration — no re-embedding on migration (recs 2×4).
- arctic-m-v1.5 is natively MRL → 256d slices halve scan time with no second model (3×4).
- The PPR gate (w_ppr=0 below 2 seeds) derives from HippoRAG2 own reset-vector design — bare PPR degenerates without seeds; the gate is what makes three-way fusion safe (5×1).
- Statistical Leiden summaries replace GraphRAG LLM community reports while keeping the navigation payoff — global-sensemaking structure at zero tokens (6 vs 9-alternative).
- Heading-aware chunking multiplies every downstream consumer (tantivy, vec0, PPR passages, reranker all share one chunk store) — run it before any indexing (8a gates all).
- Reranker consumes the FUSED top-50 window, preserving RRF calibration-free property; gating on held-out ΔnDCG@10 avoids documented regression cases (7×1).
- LightRAG insert_custom_kg means the owner-gated LLM layer INHERITS the PPR-ready structural graph rather than re-extracting entities (9×5).
- PG17 route (L20) shares the identical RRF formula — swapping substrate changes storage, never ranking logic; option stays open at near-zero lock-in.

## 5. Open questions for owner

1. Local-LLM compute windows: approve scheduled batch indexing that temporarily dips below MemAvailable 3072 MiB (7B Q4 ≈4.7 GB weights)? Or approve hosted API keys? Gates rec 9 (LightRAG), HippoRAG OpenIE, any GraphRAG-standard revisit.
2. Storage substrate: default file-local SQLite + Lance dirs, vs L20 isolated research DB on the running compass-pg :5499 PG17.11 instance (cgroup MemoryHigh=1536M)? Both support the same RRF; decision affects backup/ops story.
3. GPL acceptance: leidenalg (GPL-3+) + igraph (GPL-2+) fine for internal VPS use — any redistribution plans for Graphify artifacts?
4. Growth forecast: expected merged-corpus vector count within 12 months? >1M ⇒ skip sqlite-vec-first and start on LanceDB day-one.
5. Eval budget: fund a ~50-query labeled set (single-hop + MultiHop-RAG-style) to tune RRF weights, validate the reranker, and guard regressions?
