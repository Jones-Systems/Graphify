# Graphify Master Ranking — T1–T15 consolidation

Date 2026-08-25 · Inputs: five group syntheses S-A…S-E (98 raw lanes; provenance gaps footnoted) · Host: Debian 13, 16-core EPYC Genoa, no GPU, SwapTotal=0, MemAvailable ≥3072 MiB during bursts · graphifyy==0.9.16, Python 3.13, offline-preferred.

Scoring: `Score = Impact / EffortFactor × ConfMult` — EffortFactor S=1.00, S-M=1.125, M=1.25, L=2.00; ConfMult H=1.00, M-H=0.90, M=0.75. Ties broken by higher Impact, then dependency leverage. G = owning synthesis. Everything below is zero-cloud/zero-NC-license unless flagged owner-gated.

## 1. Master top-20 (deduped across groups)

|Rank|Recommendation — integration sketch|G|Impact|Effort|Conf|Score|Dependencies|Prereq-chain|
|---|---|---|---|---|---|---|---|---|
|1|Stable federated node identity — `(corpus_id, rel/path#slug@h8)` CURIEs minted at ingest + surrogate PK + `id_aliases`; FIX offline_extract.py abs-path bug first |C+D (C3≡D1)|5|M|H|4.44|Loader/index layer only; pinned graphifyy untouched|None upstream. KEYSTONE: eval comparability (C8), golden sets (C9), scatter dedup (D3), governance joins (B5), serializer order (D10)|
|2|SCIP→KG symbol edges — scip-python/rust-analyzer/scip-typescript → hash-pinned Go `scip` CLI `print --json` → ~200-line stdlib converter → def/ref/implements edges via validate.py gates |B (B2)|5|M|H|4.44|Hash-pinned binaries; NEVER PyPI `scip`|Feeds A1 KG seeds; SCIP strings = code-entity twin of B5 xref|
|3|Hybrid retrieval backbone — BM25 top-100 ∥ bit-KNN-rescored dense ∥ PPR(damping 0.5, λ≈0.05); gated weighted RRF Σwᵢ/(60+rᵢ(d)), w_ppr=0 under <2 KG seeds |A (A1; folds A5 PPR leg)|5|M|H|4.00|R12 embeddings + R5 store + heading-aware chunking (A8a)|After W1 legs exist; gates E1 rerank stage|
|4|Retrieval eval harness + promotion gate — beir+ranx paired-Fisher nDCG@10/Recall@100 over BEIR subset+BRIGHT+CQADupStack; cached TREC runfiles; adopt on p<0.05 |C (C8)|5|M|H|4.00|R1 stable IDs|ONE gate serves rerank ΔNDCG, Splink thresholds, RRF retune, quant downgrades|
|5|Unified per-corpus SQLite store — chunks + FTS5 external-content (+ai/ad/au) + vec0 FLOAT[768] rowid-aligned + JSONB cols; RRF in SQL CTEs; WAL, BEGIN IMMEDIATE single-writer |C (C1; absorbs A2)|5|M|H|4.00|sqlite-vec 0.1.9; R1 for real FKs|Kills 3-store drift class; LanceDB migration trigger >1M vectors (no re-embedding via A4 twins)|
|6|Consolidated read-only MCP server — FastMCP, 5 tools (`repo_search/graph_neighbors/ppr_rank/fetch_nodes/graph_schema`), readOnlyHint, names frozen at v1 |C (C5)|5|M|H|4.00|Rides R5/R13 backends; ships as ONE unit with R17+R18|Interim: lift DEC-9 and register already-shipped graphify-mcp now|
|7|Splink Fellegi-Sunter ER backbone — person/org linkers over mention tables, DuckDB ≤2.5 GiB EM, unsupervised; clusters → canonical_entity_id before indexing |B (B1)|5|M|H|4.00|Wrapped by R14 blocking + R15 gates|Feeds B5 claims and D6 hub; org name-only residue → GLiNER/vector lane|
|8|Content-addressed incremental refresh — git-plumbing change detection vs stored base SHA → BLAKE3 CAS (WITHOUT ROWID) → tantivy term-delete upsert; 97–99.5% hit expected; nightly drift backstop |D (D2)|5|M|H|4.00|blake3 1.0.9, tantivy 0.26.x, B10 slice governance|Rev tokens gate D9 envelope + D8 brief regen|
|9|Cross-corpus RRF scatter-gather — asyncio TaskGroup Sem(16); soft timeout min(0.5·budget, 3·p95)→PARTIAL; oversample max(100,3k); CURIE dedup BEFORE fusion; weighted RRF k=60 |D (D3)|5|M|H|4.00|R1 IDs; stdlib fuse|SQLite ATTACH interim → PG17 UNION ALL if OQ2 ratifies central DB|
|10|Token-budget-ledger context packing — tiktoken reserves-first hard ledger; score-per-token best-first frontier; PPR distance decay replaces hop caps; PCST prize-minus-cost; strongest-evidence-last |D (D7)|5|M|H|4.00|R9 seeds; tiktoken 0.14.0|Consumes fused+expanded candidates; Adaptive-RAG tiers D∈{1..3}/B∈{4k,8k,16k}|
|11|Entity identity governance package — append-only entity_identifier log (verified>matched>reviewed>retracted ladder), PG17 partial unique indexes, nomenklatura match_proposal queue; merges supersede, never delete |B (B5)|5|M|H|4.00|PG17 instance (owner ruling OQ2); R7 cluster output|SCIP symbol strings give the identical machinery for code entities|
|12|Offline embedding model — snowflake-arctic-embed-m-v1.5 (Apache-2.0, MTEB-R 55.14 @109M) via fastembed + onnxruntime≥1.20 cp313; "query: " prefix asymmetry |A (A3)|4|S|H|4.00|None|Unlocks dense leg (R3) + int8/bit twins (A4)|
|13|Parquet snapshots + SQL surface — node_link_data → pyarrow 25.0.1 zstd nodes/edges.parquet under immutable snapshots/{date+sha256} + MANIFEST + latest symlink; duckdb==1.5.5 read-only views |C (C2)|4|S|H|4.00|None|sha256 = rebuild-cache key for ALL derived indexes; max exit-optionality|
|14|Recall-first blocking engine — token-sort keys ∥ capped trigram ∥ SNM w=10 ∥ metaphone; rapidfuzz cpdist JaroWinkler sweep cutoff≈0.85; block caps >500; count-comparisons-before-run |B (B3)|4|S|H|4.00|rapidfuzz (already transitive dep)|Shrinks C(200k,2)=2×10¹⁰ → ~10⁶–10⁷ candidates, seconds-minutes on 16 cores|
|15|ER evaluation + promotion gates without ground truth — Wilson95-LB precision ≥0.99 auto-merge tier; paired cluster-bootstrap ΔF1 CI >−0.005; band-stratified clerical sampling 150/band |B (B6)|4|S|H|4.00|R7; shares R4 label machinery|Protects every threshold change (Splink config, GLiNER θ, quant downgrades)|
|16|SQLite freshness/validation ledger — canonical source_fingerprints + validation_evidence CHECK(valid/stale/unknown); synchronous=FULL; navigators mode=ro; promotion = one ACID txn |C (C4)|4|S|H|4.00|Shares R5 SQLite lifecycle|Preserves ENG-C11 tri-state contract; same authorizer hook as R18|
|17|Layered output/truncation contract — ~200-node/~8 KiB/25k-token caps via middleware; every cut returns {truncated,total_estimate,next_cursor,hint}; artifact-ref spill; CLI NDJSON streams |C (C6)|4|S|H|4.00|FastMCP middleware; reranker gist-first ordering|Evidence: output shaping = 4× context cut with strictly better Hit@1/MRR|
|18|Shared-server auth/isolation — launcher-minted opaque bearer tokens; SQLITE_OPEN_READONLY + query_only + sqlite3_set_authorizer SELECT-only; DynamicUser/MemoryMax~4G blast-radius wall |C (C7)|4|S|H|4.00|Loopback posture; OAuth deferred until egress|Structural enforcement, never advisory; protects the 3072 MiB floor|
|19|Federate-don't-merge posture — per-corpus graphs canonical; `graphify global add --as <corpus>` union view; pair-merges gated on B1–B4 clearance AND ≥100-query probe nDCG win ≥5% |D (D4)|4|S|H|4.00|R1 IDs|STARTS-style meta-layer supplies routing summaries|
|20|HTTP-cache freshness envelope — {state valid\|stale\|unknown, as_of, max_age_s, revalidate_after_s, rev{git_sha,tantivy_gen}} ~40 LOC; stale=serve+async revalidate; if_fresh_rev returns 304-analog |D (D9)|4|S|H|4.00|R8 manifests rev tokens|Score axis ≠ truth axis; recency decay stays orthogonal|

**Near-misses:** #21 D10 prompt-cache-friendly serializer (4.00, tied — first cut) · #22 B4 GLiNER2.5-base span proposer (3.60) · #23 C9 self-supervised golden-set mining (3.60) · 3.20 band: B7 Wikidata exact anchors, B10 enrichment governor, D5 classifier-lite router, D6 entity-hub claim store, E1 CE rerank stage · 3.00 band: A4 quantize-thrice twins, A6+D8 Leiden communities+primer briefs, A8 chunking/bi-temporal lifts, B8 code-graph completeness bundle, C10 faithfulness metric tier.

**Dedup notes:** C3≡D1 identity merged; A5 PPR folded into R3 (it IS that rec's graph leg); A2 vector-store pin absorbed into R5 (same sqlite-vec substrate); A7≡E1 post-fusion rerank merged (near-miss band); A8c parquet shape covered by R13; S-D's batch-refresh.slice ≡ B10 governor (one systemd recipe).

## 2. Tiering

**Tier 1 — implement now (high-confidence × low-effort × high-impact; all H, Imp≥4, S/S-M):** ranks **1, 2, 12, 13, 14, 15, 16, 17, 18, 19, 20** — stable CURIE identity (+offline_extract.py fix); SCIP→KG edges; arctic-embed embeddings; parquet snapshots+DuckDB; blocking engine; ER promotion gates; freshness/validation ledger; truncation contract; auth/isolation; federate-don't-merge; freshness envelope. Zero generative LLM, zero new daemons, zero license exposure.

**Tier 2 — implement after Tier 1 validates (dependencies named):**
- R3 hybrid backbone ← needs R12 embeddings + R5 store + A8a heading-aware chunking.
- R4 eval harness ← needs R1 IDs; must precede ANY enablement gate (rerank, thresholds, RRF retune).
- R5 unified store ← OQ2 amalgamation-vs-serialize ruling shapes vendor pin.
- R6 MCP server ships as ONE delivery unit with R17+R18 ← rides R5/R13.
- R7 Splink ← sandwiched by R14 (recall) and R15 (promotion); feeds R11.
- R8 incremental refresh ← after stores exist; requires B10 slice governance in place.
- R9 scatter-federation ← needs R1 + healthy per-corpus legs; interim ATTACH form first.
- R10 packing ← needs R9 seeds + tiktoken calibration.
- R11 governance package ← needs OQ2 (PG17) ruling + R7 clusters.
- Then near-miss band in dep order: D10 (post-R1), B4 GLiNER, C9 mining (post-R4), E1 rerank (post-R4 gate + R3 window; model pick E3 decided BY the gate), A4 twins, A6+D8 (OQ3), B8 (OQ8), C10 (OQ1/3), B7 (OQ4), D5 router (post-R9 evidence), D6 hub (post-R7).

**Tier 3 — deferred pending owner decisions (gating choice named):**
- A9 LightRAG local semantic layer, B9 constrained extraction tier, E5 nightly Qwen3-Reranker ← compute-window ruling (OQ1).
- B5-PG17 live-row indexes, D3 UNION-ALL endgame, Litestream targets ← substrate ruling (OQ2).
- A6+D8 leidenalg route ← GPL internal-use ruling; else BSD networkx louvain/LPA fallback.
- B7 Wikidata dumps/EventStreams; hosted prompt-cache wiring ← egress/API-key ruling (OQ4).
- E4 TEI sidecar, Ollama-vs-bare-llama-server, mdbasequery Node sidecar, ephemeral Neo4j sandbox ← one daemon-ownership ruling (OQ5).
- B8 Go import edges ← Go toolchain approval; Swift grammar work dropped if no Swift repos (OQ8).
- C11 ladybug Cypher ← demonstrated multi-hop demand; C12 NL template router ← measured question mix from R4; C13 saved-query skill cards ← golden sets exist; A10 neural sparse ← post-R3 eval gap evidence.
- graphifyy re-pin 0.9.49 ← cache-namespace cutover acceptance (OQ9); decide before refresh automation lands.

## 3. Rejected/excluded (consolidated master list)

- **Graph platforms:** microsoft/graphrag ($60–150/corpus, maintenance mode, Azure deps); LazyGraphRAG (never shipped); Graphiti/Zep (~160 LLM calls/5 KB; Zep Cloud proprietary; steal edge schema only); Neo4j CE always-on (GPLv3, 1.7–2.9 GiB heap vs floor); FalkorDB (SSPL, Docker-only); Kuzu (archived 2025-10-10); Memgraph (BSL 1.1, RSS economics); Apache AGE (PG17 release-tag inconsistency); Kythe/Glean platform class (JVM/Haskell ops weight — borrow edge vocabularies); Meta Glean self-host (broken Docker, Thrift-only); stack-graphs (archived 2025-09-09); Joern hot-path (pysrc2cpg gaps, RAM spikes; off-peak nightly optional); CodeQL CLI (custom license); LSIF anything (superseded by SCIP); DuckPGQ (DuckDB version conflict); Delta/Iceberg/DuckLake time travel (overkill at tens-of-MB snapshots); Apache GraphAr (incubating churn); RDF/pyoxigraph named-graph substrate (second query paradigm).
- **ER/entity tooling:** Zingg (AGPL + Spark JVM); dedupe as backbone (stale, ~1e5-row ceiling, label burden — tactical comparator bootstrap only); recordlinkage (stale, py3.13 untested); ZeroER (research code); KGTK (dormant); full QLever/WDTK Wikidata builds (450–500 GB, floor breach — subset carve adopted instead); mGENRE (CC-BY-NC); OpenTapioca (dead) and wikidata.reconci.link (throttle/403, no SLA); REL entity linking (2020-era models, KB mapping step); Wikibase/yente/NATS hubs (8 GB-class RAM); OpenSanctions DATA (CC BY-NC — client code MIT is fine); content-hash PRIMARY node IDs (rename ⇒ ~40.5k-edge repair passes).
- **Vector/search engines:** Qdrant local mode (>20k-point warning, exclusive lock; standalone server deferred to true 1–5M); rank-bm25 (unmaintained since 2022, O(q×N), GB-scale dict); BGE-M3 (weakest EN retrieval of set, fp32 CPU floor-grazer); hosted embedding APIs (cloud keys); sqliteai/sqlite-vector fork (Elastic License 2.0); SQLite official Vec1 (pre-1.0, track only); full-corpus ColBERTv2/PLAID (P95 235–455 ms; parked behind NextPlaid/FastPlaid/MUVERA triggers); Elasticsearch/OpenSearch-service/Meilisearch/Milvus/Weaviate (license gates/JVM heap/daemon RAM); pyserini (Java haul, no significance tests); convex-combination & DBSF fusion today (need ≥50 labeled queries); raw-score cross-corpus merges CombSUM/CombMNZ/z-score (uncalibrated units — rank-merge RRF only).
- **Weights/models/policy-blocked:** jina-embeddings-v3, splade-v3, jina-reranker-v2, GLiREL, FlashRank bundled artifacts, prebuilt community int8 ONNX uploads, Qwen2.5-3B judge (NC/unversioned provenance unless waived); generative listwise reranking RankGPT-style (shuffle collapse 65.80→25.17 DL19); pointwise 3–8B causal scoring (~min/query CPU); permutation/Kemeny aggregation (×5–20 multiplier); JSON-grammar-constrained reranking (validity≠correctness); ms-marco TinyBERT/MiniLM fallbacks (weak code transfer); f16/bf16 weights and ≤Q3_K quants for schema-bearing extraction; XGrammar/outlines as primary constraint engines; ik_llama.cpp fork (watchlist); vLLM CPU persistent service; llama-cpp-python in-process; Ollama Cloud endpoints; RAPTOR/ToG-2 (no-local-LLM policy); doc2query--, LLMLingua, GraphRAG LLM community reports (policy/latency); YAKE (GPLv3).
- **Misc tooling:** PyPI squatters `scip` (GPL cytometry lib) and dead `tantivy-py`; scip-callgraph PoC (unverified license); madge/pydeps/modulefinder as edge feeders; pip nano-graphrag/graspologic (requires_python <3.13); Watchman since-cursor watching; inotify/watchdog as PRIMARY refresh (IN_Q_OVERFLOW swallowed silently — daytime dirty-marker at most); anacron-gated cron.daily (binary absent on host); pymerkle (GPL, unmaintained — ~150-LOC fixed-fanout tree instead); `graphify update --force` (audited silent no-op, cli.py skips flag); per-step speculative prefetch (Amdahl-bound, E[save]≤0); cspy RCSP solver (stale, wrong shape); TOON serialization (−14.5% real vs compact JSON + prompt tax); ranx as RUNTIME dep (offline experiments only); sequential fan-out default; merge-graphs as DEFAULT federation (330–360 MB vs 512 MiB cap) and merge-driver automation (hard-cap aborts); merged-global cross-corpus indexes (blockers B1–B4 all presently TRUE); Dataview/Datacore/Emanote/zk as headless metadata engines (runtime-bound/AGPL/GPL); Litestream S3 object-storage targets (local-dir shipping fine); cloud-bound eval defaults (RAGAS/DeepEval/Phoenix gpt-4o judges); speed-first search MCPs fff/grix as products (measured negative hit-rate); wholesale graph-vendor MCP adoption; local GraphQL layer (graphify-mcp already ships).

## 4. Implementation wave proposal

**Parallel capsules (independent surfaces, no file collisions):**
- **W1-a**: R1 identity + offline_extract.py fix ∥ R13 snapshots ∥ R12 embeddings ∥ R16 freshness ledger — one cutover commit (<1 h at measured rates).
- **W1-b**: R14 blocking engine (standalone rapidfuzz) — plus HARD SEQUENCER: B10 governor slices land here, before ANY bursty job (Splink DuckDB, SCIP bulk, decode).
- **W1-c**: R2 SCIP toolchain hash-pins + converter piloted on 2 repos.
- **W1-d**: R17+R18 middleware authored against a FastMCP stub ahead of the server.

**Sequential spine:** W1-a → R5 unified store → R3 fusion backbone (acceptance smoke: fused nDCG > BM25-only on harness subset) → R4 harness gating everything downstream.

**Parallel tracks with the spine:** R7 Splink wrapped by R14+R15 (→ R11 after OQ2) ∥ R8 refresh → R19 posture → R20 envelope (rev-token chain) ∥ W1-d → R6 MCP server shipping R17+R18 inside.

**W3:** R9 scatter → R10 packing; near-miss band slots in behind named deps (E1 rerank strictly behind the R4 gate; model pick by gate outcome per E3).

**Owner-gated, unscheduled:** B5-if-PG17, A9, B9, E4/E5, B7, B8-Go portion, A6+D8-if-GPL-declined (fallback networkx community detection).

## 5. Open questions for owner (consolidated, deduped across groups)

1. **Compute windows** (S-A Q1, S-B R9–10, S-C Q3, S-E Q1/Q5): approve scheduled local-LLM batches that dip below MemAvailable 3072 MiB (7B Q4 ≈ 4.7 GB weights) under the B10 slice/governor? Sub-ruling: accept +0.35–1.2 s interactive rerank p50, and a periodic local judge (default Phi-3.5-mini MIT)?
2. **Storage substrate** (S-A Q2, S-C Q2, S-D Q2): vendor SQLite amalgamation ≥3.51.3 (WAL-reset corruption fix) vs serialize-checkpoints on stock 3.46.1 vs central PG17 (compass :5499)? One ruling covers R5/R16/R11/R9-endgame/backups.
3. **Licenses** (S-A Q3, S-B Q4, S-C Q3, S-D Q3, S-E Q3): GPL-3 leidenalg/igraph internal use OK? Any NC-weight waivers (GLiREL, jina-reranker-v2, Qwen2.5-3B)? Any redistribution plans for Graphify artifacts at all?
4. **Egress/API keys** (S-B Q3, S-C Q4, S-D Q5): quarterly 100–160 GB Wikidata dumps + EventStreams SSE + compliant-UA API via proxy? Hosted keys for embeddings/judge/prompt-cache wiring (up to ~90% input-cost cut)?
5. **Daemon ownership** (S-B Q5, S-C Q7, S-D Q4, S-E Q4): ONE ruling assigning who owns long-running units + memory caps: Ollama vs bare llama-server, TEI rerank sidecar, Node/Bun sidecar (mdbasequery), ephemeral Neo4j sandbox y/n.
6. **Review/eval budget** (S-A Q5, S-B Q1, S-E Q6): fund ≈500 blind pair reviews + ~100-doc golden sets + ~50-query labeled set as ONE recurring line (covers Splink calibration, rerank gate, RRF tuning, regression guards)?
7. **Growth forecast** (S-A Q4): expected merged-corpus vector count within 12 months — >1M flips R5 to LanceDB-first day-one (fp32/int8 twins make migration re-embedding-free).
8. **Scope** (S-B Q2/Q6/Q7, S-D Q7): any Swift among the 18 repos? Install Go toolchain? Include worktree farms (Codex-V3-worktrees ~113) in corpus scope — changes churn model? Adopt Joern nightly security-evidence layer now or defer?
9. **Program hygiene** (S-D Q1, S-C Q5/Q1): graphifyy re-pin 0.9.16→0.9.49 (fixes audited `extract --force` silent no-op; changes cache namespace — decide before refresh automation); lift DEC-9 to register shipped graphify-mcp ahead of the consolidated server; assign ownership of T11-boundary lanes (L63/L68–L70 payloads).
10. **Latency/freshness SLOs** (S-C Q6, S-D Q6): MCP surface budgets (federation sketch p50≤180 ms/p95≤450 ms); confirm sub-hour freshness NOT required (nightly+manual stands); confirm nothing ever leaves loopback (else OAuth 2.1/RFC 8707 un-defers).

---
*Provenance footnotes:* L70's raw file mis-persisted (holds research manifest; true payload lives in L74's file); L13/L19/L20 raw provenance repaired from recovered loose records; L14/L18/L31/L35/L68 recovered from agent artifacts only; L92/L94–L96 and L99/L100 never landed (raised as S-D Q8 / S-E Q5). A9 impact 4\* held owner-conditional per S-A.
