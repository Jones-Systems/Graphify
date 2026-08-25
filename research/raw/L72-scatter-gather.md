Let me understand my assignment. I'm L72, tasked with investigating "T11 federation: Scatter-gather federated search aggregation — rank-merge vs score-merge at the federation layer, per-corpus quotas, latency budget fanning to 18 corpora sequentially vs bounded parallel."

This is part of a research program: "100-lane investigation: improving graph-based and semantic search across M Jones's 18 VPS repos."

Per-lane output contract:
1. WRITE full findings to the exact raw path given below. Hmm — "given below" but no path is actually given in the message. The contract says "If your tool inventory lacks write, lead your final message with `PERSIST-NEEDED` and include the complete markdown." I don't have a write tool in my inventory (Read, Grep, Glob, Web Search, Yield, Hub, context7, next-devtools, shadcn). So I cannot write files. Therefore I must lead my final message with `PERSIST-NEEDED` and include the complete markdown.

Wait — but the yield protocol says my terminal yield MUST use exactly the shape with summary/files/architecture. And the context says "This task declares an output schema: the terminal `result.data` MUST be the full object matching it."

There's tension between the research-program contract (return message must be ONLY one line `LANE L72 DONE items=<count> headline=...`) and the harness yield protocol (structured result.data with summary/files/architecture).

Resolution: The yield protocol is the harness-level requirement — "Your terminal `yield` MUST use exactly this shape". The lane contract's "RETURN MESSAGE" can be embedded in the summary field or... Actually, let me think. The per-lane output contract says findings must be written to a raw path; since I lack write, I lead final message with PERSIST-NEEDED and include complete markdown. The final message is my terminal yield's data content presumably.

Best approach: put PERSIST-NEEDED + full markdown table in `summary` field (or architecture), include files array referencing where findings would go, and make the last line of summary the required one-liner? Actually the contract says RETURN MESSAGE must be ONLY one line. But the harness schema requires structured data. The pragmatic resolution: yield structured data whose fields contain the full markdown (PERSIST-NEEDED at start of summary), so the main agent gets everything. The "return message" in hub terms could also be sent via hub send to Main with the one-liner.

Actually, let me reconsider: I can send a hub message to Main — but hub messaging says "never long-form content". The one-liner `LANE L72 DONE items=...` fits hub messaging perfectly. Then my terminal yield contains the full structured data including PERSIST-NEEDED markdown.

Plan:
1. Investigate federated search aggregation: rank-merge (RRF - Reciprocal Rank Fusion) vs score-merge (normalized score fusion, e.g., CombSUM/CombMNZ, z-score normalization).
2. Per-corpus quotas (top-k per shard/corpus before merging).
3. Latency budgets: sequential vs bounded-parallel fan-out to N corpora.
4. Ground this in our actual stack: 18 VPS repos, Python 3.13, no GPU, offline/self-hostable, low RAM. Check what search stack exists in the repos — maybe look at the local project Codex-V3 directory for context on what search infrastructure exists.
5. Use web_search for primary sources: RRF paper (Cormack et al. 2009), Elastic/OpenSearch RRF support (note license! Elasticsearch RRF is under Elastic license / enterprise feature — important flag), OpenSearch hybrid search, SQLite FTS5, LanceDB, Qdrant, Vespa, Tantivy, DuckDB VSS, etc.
6. Produce the table with columns: |Item|Type|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
7. Verdict ≤3 lines: top pick, why, integration sketch.

The output path: "WRITE full findings to the exact raw path given below" — no path given below in my prompt. So I should note that; maybe use a sensible default like a lane file. Since I lack write anyway, I'll lead with PERSIST-NEEDED and provide full markdown, suggesting a path like `/home/malcolmjones/Projects/Codex-V3/.research/L72-federation.md` or similar. Let me check if there's an existing research directory structure in the workspace to match convention.

Let me start by looking at the workspace structure to understand the stack, then do web searches in parallel.

Key things to investigate:
- What do the repos currently use? Let me grep the workspace. Current dir is /home/malcolmjones/Projects/Codex-V3. But the research program spans 18 VPS repos — probably under ~/Projects or similar. Let me look quickly.
- Also there may be sibling lanes' outputs (S-A/S-B syntheses done) — maybe readable via agent:// or local:// artifacts. Could check `local://*.md`.

Investigation targets:
1. RRF (Reciprocal Rank Fusion): Cormack, Clarke, Buettcher 2009 SIGIR. k=60 typical. License: algorithm/patent-free, implementations everywhere.
   - OpenSearch hybrid queries with normalization processors (min-max, l2, z_score, arctan) — Apache 2.0.
   - Elasticsearch RRF — requires Enterprise/Platinum license? RRF was added in 8.8 as tech preview, GA'd later, but it's a licensed feature (Enterprise). Flag.
   - Vespa supports rank fusion natively.
   - Milvus hybrid search RRF/weighted scorer — Apache 2.0.
   - Qdrant Query API prefetch+fusion RRF — Apache 2.0.
   - Weaviate — BSD-3.
2. Score merge approaches:
   - Min-max normalization, z-score, CombMNZ, CombSUM (Fox & Shaw 1994), CORI normalization (Callan), SSL (switching small-to-large?), logistic regression based (CalibratedScore), 3-2-1... 
   - Score distributions: Z-score robust across corpora; recent work: "score-based fusion" needs calibration; rank fusion robust without calibration.
   - Learned fusion: lambdaMerge, LTR-based (XGBoost LTR) — but no GPU fine, CPU xgboost OK.
3. Per-corpus quotas:
   - Standard practice: fetch top-k per shard (Elasticsearch shards default from=10 sized by query), tail-cutting (LogMerge / "tail cut" in distributed IR), quota allocation proportional to corpus size/quality vs uniform quotas. DuckDB/SQLite per-corpus LIMIT.
   - Tail-cutting literature: "Result Merging and Search Trends" ... Known: Kirsch (Berkeley) early termination; ANCE... Actually key refs: "Optimizing Distributed Web Search" (Callan & Lu), "Efficient Query Evaluation using a Two-Level Retrieval Process" (Anh & Moffat WAND), "Tail-cutting in federated search" — the known technique is from Lu & Callan "Content-Based Retrieval in Federated Digital Libraries" and Craswell et al. TREC federated tracks; more recently "Fused Fusion"... I'll keep it practical: per-corpus top-k = max(perCorpusK, finalK) with oversampling factor α (e.g., 2×finalK), plus size-proportional allocation.
4. Latency budget fan-out:
   - Sequential over 18 corpora vs bounded parallel (asyncio.Semaphore(bound)). Python 3.13 asyncio; each corpus query likely local SQLite/FTS5 or HTTP to self-hosted engine.
   - p50/p95 math: sequential sum of latencies vs parallel max; hedged requests ("The Tail at Scale", Dean & Barroso 2013); timeout per corpus with partial results (graceful degradation); scatter-gather with deadline propagation.
   - Bounded parallel: semaphore ~ CPU cores (16) → all 18 corpora nearly concurrent; RAM footprint small for SQLite reads.
   - Hedge after p95×β; cancel losers.
5. Concrete tools for our stack:
   - Python: asyncio + asyncio.wait(timeout=...) / asyncio.timeout() (3.11+), TaskGroup (3.11+).
   - AnyIO capacity limiter. 
   - For merging: pure-python rrf implementation trivial; or use existing libs? `ranx` library (MIT?) for evaluation+fusion algorithms (RRF, CombSUM, etc.) — ranx is MIT licensed, good maturity. That's a nice concrete item.
   - DuckDB as federation layer? DuckDB can ATTACH multiple SQLite files and do UNION ALL + ORDER BY LIMIT pushdown — interesting technique item.
   - SQLite: ATTACH databases, UNION ALL queries with per-corpus LIMIT subqueries.
   - OpenSearch 2.x/3.x hybrid normalization — self-hostable Apache 2.0, but JVM RAM heavy (~1-2GB heap minimum) — flag against hard floor? MemAvailable floor 3072 MiB during compute bursts; a JVM resident is different from burst, still heavy.
   - Qdrant: Rust, low RAM, supports serverless/local mode via qdrant-client with :memory:, Query API with prefetch + RRF fusion built-in (v1.10+, 2024). Good fit if vector corpora live in Qdrant. But 18 repos may be text/graph; semantic search suggests embeddings exist somewhere.
   - LanceDB: embedded, Rust core, Apache 2.0, native FTS+vector hybrid with fusion (RRF default in hybrid search). v0.x→ now 2025 stable-ish. Low RAM embedded — great fit for Python 3.13.
   - Tantivy (Python bindings tantivy-py, MIT) — BM25 per corpus; fusion done in app layer.
   - Vespa: Apache 2.0 but heavyweight Java — poor fit.
   - Typesense/Meilisearch: Meilisearch has federated multi-index search (v1.6+, "searches" endpoint multi-search with federation) — Meilisearch is self-hostable, license changed? Meilisearch is free under MIT? Meilisource: meilisearch is licensed under MIT with some enterprise features (dedicated team?). Core is free AGPL? Let me verify: Meilisearch switched to... I believe meilisearch core remains MIT-ish? Actually Meilisearch v1.something moved some features behind EE; core is MIT. Need to check. Multi-index federated search added in v1.6 (Feb 2024) with `federation` option in multi-search. That's directly relevant!
   
6. Latency numbers/evidence:
   - Elasticsearch/OpenSearch docs on shard request latency, RRF cost (RRF requires retrieving windowsize per shard; ES docs recommend reducing window_size).
   - "The Tail at Scale": hedged requests reduce tail latency when first response slow.
   - asyncio concurrency overhead negligible vs I/O.

Also relevant: our deterministic-ID rebuild running (from context) — IDs matter for stable dedupe across corpora in federation (same doc appearing in multiple corpora → dedup by canonical ID before merge). Worth noting in integration sketch.

Now the deliverable format: table rows = candidate items (tools/techniques/strategies). Aim ~12-16 rows covering:

Techniques/strategies:
1. Reciprocal Rank Fusion (RRF) rank-merge (k=60) — Cormack 2009.
2. Weighted RRF (per-corpus weight tuning) — Milvus/Qdrant support weighted variants.
3. CombSUM/CombMNZ score-merge with min-max/z-score normalization (Fox & Shaw 1994; Savoy; Callan CORI).
4. Z-score/robust score calibration per corpus (score distribution matching; e.g., "calibrated score fusion", logistic calibration).
5. Per-corpus top-k quota + oversampling (tail-cutting; k_shard = α·k_final, α≈2–4) — Lu&Callan federated search; ES window_size guidance.
6. Size/provenance-weighted quotas (resource selection, CORI/Gloss, ReDDE) — decide how many results to pull from big vs small corpora.
7. Deduplication by deterministic doc ID pre-merge (ties to S-A/S-B deterministic-ID rebuild).
8. Deadline-bounded scatter-gather: asyncio.timeout + TaskGroup + Semaphore(cores) — partial results on timeout.
9. Hedged requests / speculative re-issue (Dean & Barroso, Tail at Scale) for straggler corpora.
10. Sequential baseline anti-pattern evidence: latency sums; when sequential OK (tiny local latencies <5ms each).

Tools/repos:
11. ranx (Python fusion/eval lib, MIT).
12. Qdrant Query API prefetch+fusion (RRF/DBSF), Apache-2.0, Rust.
13. LanceDB hybrid (vector+FTS native fusion RRF), Apache-2.0 embedded.
14. Meilisearch multi-search federation endpoint (v1.6+) — check license.
15. OpenSearch neural/hybrid normalization pipeline (min_score/min_max/l2/z_score/arctan), Apache-2.0, JVM-heavy flag.
16. Elasticsearch RRF — Elastic License v2/enterprise → requires-owner-approval flag; not adoptable freely for service use? ELv2 allows hosted restriction... ES source-available; self-host free tier lacks RRF (needs Enterprise license trial). Flag.
17. Milvus hybrid_search with ranker RRFRanker/WeightedRanker — Apache 2.0; heavier infra.
18. DuckDB ATTACH + SQL-side merge pushdown (MIT) — technique using tool.
19. SQLite ATTACH + compound SELECT merge (public domain) — zero-dep baseline.
20. Vespa native rank profiling/fusion — Apache 2.0 but Java-heavy; probably skip or low fit.

That's plenty; keep table focused ~14 rows.

StackFit scoring rationale: Python 3.13, no GPU, offline, low RAM, 18 local corpora (SQLite/FTS likely), CPU 16 cores.

Scores (my judgment):
- RRF: StackFit 5 (pure python trivial), EffGain 3 (removes per-engine score tuning), EffectGain 4 (quality robustness across heterogeneous scorers), QualGain 4 (proven TREC gains ~5-15% vs best single ranking), AdoptCost 1, Conf H (paper + universal adoption).
- z-score/CombMNZ: StackFit 5, QualGain 3-4, AdoptCost 2 (needs per-corpus score stats collection), Conf M-H (literature mixed vs RRF; RRF often wins w/o tuning).
- Quotas/tail-cut: EffGain 5 (latency + bandwidth), EffectGain 4, AdoptCost 1.
- Hedged/deadline: EffectGain 5 on p99.
- ranx: StackFit 5, AdoptCost 1, maturity high (v0.3.x? latest 2024-2025).
- Qdrant: depends whether we want a server; embedded mode exists but single-process; StackFit 3-4.
- LanceDB: embedded, StackFit 4-5 if embeddings present; hybrid fused search native.
- Meilisearch: adds service; license check needed; StackFit 2-3.
- OpenSearch: StackFit 1-2 (RAM/JVM).
- ES RRF: license flag, StackFit 1.
- Milvus: heavy, StackFit 1-2.
- DuckDB attach: StackFit 4, neat for batch/offline merges; less for online serving.
- SQLite ATTACH union-all: StackFit 5 baseline.

Latency budget section (architecture prose):
- Budget: e.g., total 300ms; per-corpus p50 ~10ms local SQLite FTS; sequential 18× ≈ 180ms + overhead; p95 tails blow past. Bounded parallel with bound=min(18, cpu)=16: wall ≈ ceil(18/16) waves ≈ ~max(p95_i) ≈ 30-40ms. Recommend TaskGroup + Semaphore(16) + per-corpus soft deadline (e.g., 150ms) + gather-with-timeout returning partials + hedge at p95×1.5 for stragglers.
- Memory: each coroutine holds ≤k results × small dicts → MB scale; fine above 3GiB floor.

Now, evidence gathering via web_search (primary sources):
- Cormack RRF paper (uwaterloo page / dl.acm).
- Fox & Shaw combination (probably cite via secondary; there's a classic tech report "Combination of multiple searches").
- OpenSearch docs: hybrid search normalization processors list (min_max, l2, z_score, arctan) — docs.opensearch.org.
- ES RRF license requirement — elastic.co docs "RRF is available under Enterprise license" / subscription matrix.
- Qdrant Query API fusion docs (qdrant.tech/documentation/concepts/explore/... "fusion" rrf/dbsf) version 1.10+.
- LanceDB hybrid search docs — lancedb.com docs, fusion() default RRF; version numbers (lancedb python 0.20+?).
- Meilisearch multi-search federation — meilisearch docs; released v1.6 (2024-02); license: meilisearch MIT? Verify. I recall Meilisearch core repo is MIT... Actually I think it's MIT. Some enterprise features (dedicated teams?) Hmm, meilisearch/meilisearch LICENSE file: MIT. Yes I'm fairly confident core is MIT.
- ranx PyPI — MIT, author Prasenjit Mitra? No—ranx by Elias Bassani (Amenadiel). Latest version 0.3.21? something like that (2024). Supports fusion algorithms: rrf, pl2? It has `ranx.fusion` with algorithms: rrf, comb_sum, comb_mnz, comb_min, comb_max, anzs, bayesfuse, borda, condorcet, isr, logn_isr, log_merge, mixed, pos_av_z, pos_dt, pos_sf, pos_st, probfuse, seg, exp_comb_sum, etc. Great — cite.
- "The Tail at Scale" CACM 2013 Dean & Barroso — hedged requests numbers (e.g., reduces 95th/99th percentile substantially; example: 95th percentile reduced ~40%? In paper: latency at 95th percentile decreased by 28%? I recall example where hedging cuts 99th percentile from 1800ms to <100ms in BigTable case study? Something like: "reducing median by X%..." Better: BigTable example: 1000-server job, hedging reduced tail: 99th percentile from 1810ms to 97ms? That rings right — "hedged requests reduced the 99th percentile latency from 1810 ms to 97 ms"? Hmm, I think the figure was: without hedging 95th percentile 1810ms... Let me just cite qualitatively unless verified via search.)
- Lu & Callan federated search / result merging; Callan CORI 1995/2000; Si & Callan ReDDE 2003. Maybe one row "resource selection" but scope is rank/score merge + quotas + latency. Keep resource-selection row short (quota allocation informed by corpus sizes).
- Tail-cutting: "Kurland? " Actually the modern term "tail cutting" from Anh & Moffat / or from Microsoft "Merging ranked lists..." There's "Nottelmann & Fuhr MARE"? Overkill. Practical citations: Elasticsearch `window_size` docs for RRF ("number of top results per shard"), OpenSearch `hybrid` query `normalization-processor window_size`. Also Vespa doc "the need for global phase / rerank depth". Cite ES/OpenSearch window_size guidance as evidence for quotas.
- asyncio.timeout (PEP? added 3.11), TaskGroup 3.11, Semaphore — cite python docs.
- DuckDB ATTACH sqlite extension docs.

Also possibly relevant prior lanes: check `agent://` artifacts? Not necessary. Focus.

Local repo recon: quick glob/grep in cwd for existing search code to ground StackFit. Look for sqlite fts, embeddings, qdrant, lancedb mentions in ~/Projects? The workspace root is Codex-V3. Peers mention "Codex-V3" coordinator stuff. The 18 repos are elsewhere (~/Projects/*?). Reading other sessions' files is prohibited for peer activity, but reading the user's repos is normal investigation. Keep it light: glob top-level dirs, grep for "fts5|qdrant|lancedb|meilisearch|opensearch" across Projects root maybe too broad; limit to cwd + siblings listing only. Medium thoroughness: cwd structure + any search-related module.

Let me plan tool calls:

Batch 1 (parallel):
- read /home/malcolmjones/Projects (directory listing)
- read cwd directory listing
- web_search: Cormack reciprocal rank fusion 2009
- web_search: OpenSearch hybrid normalization z_score min_max docs
- web_search: Elasticsearch RRF license enterprise requirement
- web_search: Qdrant Query API RRF DBSF fusion docs
- web_search: LanceDB hybrid search RRF fusion docs
- web_search: Meilisearch multi-search federation docs license
- web_search: ranx fusion library MIT
- web_search: The Tail at Scale hedged requests

That's a lot in one block but they're independent — allowed and encouraged. Then batch 2 follow-ups for versions (PyPI pages via read URL: pypi.org/project/ranx/, pypi lancedb, qdrant-client, meilisearch releases). read on URLs gives reader-mode; PyPI JSON API might be cleaner: https://pypi.org/pypi/ranx/json returns JSON — read can fetch URLs; JSON parse fine.

Also grep local for search stack usage.

Then compose findings markdown, yield with PERSIST-NEEDED lead in summary, and hub-send the one-liner to Main.

Wait — the return-message rule: "Your RETURN MESSAGE must be ONLY one line: LANE L72 DONE items=<count> headline=<one-line takeaway>." The return message here is the yield. But schema demands summary/files/architecture object. I'll satisfy both: summary starts with "LANE L72 DONE items=N headline=..." then PERSIST-NEEDED + markdown. Hmm, "ONLY one line" conflicts with schema; harness schema wins (system-level > context program). I'll put the one-liner as the very first line of summary followed by PERSIST-NEEDED and the full markdown, so Main can regex-grab the line while getting everything. Also send the exact one-liner via hub to Main (fire-and-forget) — cheap coordination consistent with fleet pattern.

Files array: [{path: ".research/L72-T11-federation.md", description: "Full lane findings (persist needed)"}] — but file doesn't exist since I can't write; describe accordingly ("pending persist"). Architecture: the latency-budget + merge design sketch.

Let me be careful about scores being defensible and evidence dated. Record versions: OpenSearch 3.x current (2025: OpenSearch 3.0 released May 2025), ES 8.x/9.x (9.0 April 2025), Qdrant 1.14/1.15 (2025), LanceDB python lancedb 0.24/0.25 (2025), Meilisearch 1.12-1.13 (2025), ranx 0.3.21ish, DuckDB 1.3 (2025), Python 3.13.

Today is 2026-08-25, so versions may have advanced; searches will reveal. Record what I find with dates.

Start executing. First batch: local recon + searches in parallel.

Actually also worth checking: does the user's stack already have a federation layer? grep cwd for "federat|scatter|rrf|reciprocal" etc.

Let me fire batch 1 now.

One more consideration on quotas evidence: Elasticsearch docs: RRF `rank_window_size` default 10 per shard... and general "top hits aggregation size per shard" — good enough. OpenSearch hybrid processor `window_size`. Also mention oversampling factor 2–4× empirical from ANN recall literature (e.g., ef_search oversampling) — cite generally.

Sequential vs bounded parallel math (include in architecture):
- t_seq = Σ p_i ≈ N·p̄ (+jitter tail linear)
- t_par(B) = ⌈N/B⌉·wave + max-tail; B=cpu cores 16 → two waves for 18 corpora.
- Python GIL irrelevant (I/O-bound); event-loop overhead µs-scale per op.
- Bound RAM: B·k·row_size; k≤200, row≈200B → ~640KB — trivially above floor.
- Degradation policy: per-corpus soft timeout τ_c = min(budget·0.5, p95_c·3); on expiry emit partial (empty ok) + metric; never fail whole scatter because one corpus hung (circuit breaker marks corpus degraded for cooldown).
- Hedging: reissue to stragglers at p95×1.5 if idempotent read.

Good. Execute.

For the local recon, keep it minimal: read directory of cwd and /home/malcolmjones/Projects.

Let me also consider checking S-A/S-B syntheses via local:// or agent:// to align terminology (deterministic-ID rebuild). Try `read agent://SYNTH-SA` maybe; risky unknown. Cheap: attempt in batch 1; failure harmless. Actually roster shows SYNTH-SA parked; its artifact may exist. I'll try `artifact://` discovery via bare history? Skip — medium thoroughness, don't burn calls. One attempt at agent://SYNTH-SA is fine.

Proceed.