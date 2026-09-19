# LANE L17 - Reciprocal Rank Fusion (T3 hybrid): tuning evidence, alternatives, failure modes, three-way fusion recommendation

Date: 2026-08-25. Lane: L17. Program phase: 1 (graph/semantic search upgrade across 18 VPS repos).
Stack assumptions: Debian VPS, 16-core CPU-only, Python 3.13; BM25 via tantivy/FTS5-class engine; vectors via embedded LanceDB; PPR over pinned graphifyy==0.9.16 node-link graphs. Offline, permissive licenses only, no API keys.

## Findings

|Item|Type|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|RRF k=60 (Cormack/Clarke/Buettcher, SIGIR 2009)|technique|https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf|free paper|17y proven; industry default constant|5|3|4|4|0|H|"k = 60 was fixed during a pilot investigation and not altered during subsequent validation"; "near-optimal, but ... not critical" (pilot k sweep, TREC 351-400); beat Condorcet 7/7 (p~.008) and CombMNZ 6/7 (p~.04); +4-5% avg MAP over best individual system on TREC fusion runs; LETOR3 meta-learner MAP .6051 vs best individual ListNet .5846 (p<=.003)|
|Weighted RRF: sum_i w_i/(k+r_i(d))|technique|https://qdrant.tech/documentation/search/hybrid-queries/|n/a method; Qdrant impl Apache-2.0|production Qdrant v1.16 (2025); Milvus analog shipped earlier|5|3|4|4|1|M-H|Qdrant v1.16 Query API exposes {"rrf":{"k":60,"weights":[3.0,1.0]}} per prefetch list; lets a stronger retriever dominate without any score calibration; Qdrant FAQ recommends weighted RRF once validation data exists, plain RRF when scales incompatible/no labels|
|Convex combination of normalized scores (Bruch/Gai/Ingber, ACM TOIS 2024; arXiv 2210.11934)|technique|https://arxiv.org/abs/2210.11934|free paper (arXiv)|peer-reviewed 2024|4|3|4|4|2|H|s=alpha*n_sem+(1-alpha)*n_lex beats RRF in-domain AND out-of-domain; insensitive to normalization type (min-max / z-score / theoretical bounds mainly shift optimal alpha); raw unnormalized CC unstable (BM25 unbounded); alpha is sample-efficient to tune; per-dataset tuned RRF rank-offsets generalize POORLY out-of-domain|
|DBSF distribution-based score fusion (Qdrant v1.11+)|technique|https://qdrant.tech/documentation/search/hybrid-queries/|Apache-2.0 impl|production v1.11 (2024)|4|3|3|3|1|M|per-list z-mapping s_hat=(s-(mu-3sigma))/(6sigma), then sum of normalized scores for matching points; parameter-free and magnitude-aware; Qdrant FAQ guidance: DBSF when raw magnitudes meaningful + distributions well-behaved, RRF when scales incompatible or no eval set|
|Milvus WeightedRanker pattern (arctan-normalized weighted score sum)|strategy|https://milvus.io/docs/reranking.md|Apache-2.0 impl|production Milvus 2.4 -> 2.6 (explicit norm_score flag in Function API)|4|3|3|3|1|M|FinalScore=sum_i w_i*Normalize(s_i(d)); arctan-based transform unifies mixed metric types incl. BM25 before weighting; weights in [0,1], need NOT sum to 1 (C++ API doc); docs guidance table: WeightedRanker when one retrieval path known more important, RRFRanker (default k=60) otherwise|
|Weaviate relativeScoreFusion (min-max normalized convex combination, default since v1.24)|strategy|https://docs.weaviate.io/weaviate/concepts/search/hybrid-search|BSD-3 impl|production default since v1.24 (2023/2024)|4|2|3|3|1|M|hybrid_score = alpha*minmax(vector)+(1-alpha)*minmax(BM25); explicitly preferred over rankedFusion (1/(rank+60)) because it preserves score gaps; autocut cutoff logic REQUIRES relativeScoreFusion - a concrete production case where rank-only fusion discards needed information|
|Elasticsearch RRF retriever ops semantics (rank_constant=60, rank_window_size)|tool / ops evidence|https://www.elastic.co/docs/reference/elasticsearch/rest-apis/retrievers/rrf-retriever|Elastic-2.0/SSPL server (NOT adopting server)|GA production at scale|1|1|1|2|4|H|rank_constant defaults to 60 ("larger value gives lower-ranked documents more influence"); rank_window_size truncates each child retriever's candidates BEFORE fusion and must stay fixed while paginating; corroborates industry convergence on k=60; JVM server itself out of scope for our VPS - evidence only|
|CombSUM / CombMNZ classic data fusion (Fox & Shaw TREC-3 1994; Montague & Aslam CIKM 2002 lineage)|technique lineage|https://cir.nii.ac.jp/crid/1360011146303798784|free papers|classic, ~30y literature|3|1|2|2|2|M|CombSUM(d)=sum w_i*s_i(d); CombMNZ(d)=|lists containing d|*sum; Cormack 2009: CombMNZ results have "higher variance" because "by happenstance, some scores are more amenable than others"; on LETOR3 CombMNZ .6107 edged RRF .6051 but not significant (p~.2) - agreement bonus pays only when lists are reasonably independent|
|HippoRAG2 PPR integration: dense sim folded into PPR reset vector (lambda=0.05); PPR output IS the ranking|technique|https://arxiv.org/abs/2502.14802|MIT code (OSU-NLP-Group/HippoRAG); free paper|ICML 2025; NeurIPS'24 predecessor (2405.14831)|5|4|4|5|1|M|Neither HippoRAG paper does post-hoc dense-x-PPR interpolation: passage nodes are seeded with reset mass lambda*sim(q,v), lambda=0.05 default, then PPR ranks passages directly. Implication for fusion design: a bare PPR list degenerates without query seeds -> gate PPR contribution on KG seed count|
|RECOMMENDED: gated weighted three-way RRF for BM25+vector+PPR|strategy|self-synthesis (API shape per Qdrant v1.16 docs)|n/a|new for our stack; assembled from proven parts|5|4|4|4|1|M|score(d)=sum_i w_i/(60+r_i(d)) over top-100 windows of each source; absent doc => omit term (not zero); start w=(1.0,1.0,1.0); per-query gate w_ppr=0 if query links <2 KG seeds; pure stdlib O(N) merge, zero new dependencies|

## Verdict
Top pick: gated weighted three-way RRF - score(d)=sum_i w_i/(60+r_i(d)), ranks 1-based over each source's top-100 window, missing doc => term omitted; start w=(bm25:1.0, vec:1.0, ppr:1.0), tune w_ppr in {0.5,0.75,1.25} on dev queries, force w_ppr=0 when the query matches <2 KG seeds (HippoRAG2-style gating). Integration: fetch top-100 independently from FTS5-BM25, LanceDB, graphifyy PPR; fuse in ~20 lines of stdlib Python after queries; deterministic tie-break (-score, id). Keep K=60 (proven plateau, ES/Milvus default); defer convex combination until >=50 labeled queries AND bounded calibrated scores exist (Bruch TOIS24: CC ceiling higher, needs calibration); DBSF is label-free magnitude-aware fallback later.

## 1. Origin and k-tuning evidence (Cormack, Clarke, Buettcher - SIGIR 2009)
Formula: RRFscore(d) = sum_{r in R} 1/(k + r(d)), r(d) = 1-based rank of d in run r.
Exact wording from the paper:
- "k = 60 was fixed during a pilot investigation and not altered during subsequent validation."
- Pilot: four experiments fusing 30 Wumpus Search configurations on four TREC collections. Table 1 (TREC topics 351-400): 12-point k sweep shows MAP plateau ~.212-.215 through the middle of the range (peak .2147), falling off toward extremes (.2072 low end, .2098 high end); comparison points: best individual .2016, Condorcet .2074, CombMNZ .2039. Quote: "k = 60 was near-optimal, but that the choice was not critical."
- Rationale: "The constant k mitigates the impact of high rankings by outlier systems" while lower-ranked documents' importance "does not vanish as it would were ... an exponential function used."
Headline results: RRF exceeded Condorcet in all 7 sign-test comparisons (p~=.008), CombMNZ in 6/7 (p~=.04), and the best individual run in 6-7/7 (+4-5% average). On LETOR3 as meta-learner over 7 rankers: RRF MAP .6051 beats every member incl. ListNet .5846, RankSVM .5737 (p<=.003); CombMNZ .6107 edges RRF non-significantly (p~=.2).
Interpretation for us: k=60 is a robust plateau default, not a magic number - safe to pin, flat within roughly an order of magnitude. Industry converged on it: Elasticsearch rank_constant defaults 60, Milvus RRFRanker default k=60, Weaviate rankedFusion uses 1/(rank+60). Divergent counter-example worth knowing: Qdrant ships k=2 with ZERO-based ranks (= much sharper decay ~1/(r+1)); small-k variants behave differently, so pin ours explicitly rather than inheriting library defaults.

## 2. Alternatives compared
| Method | Formula | Uses magnitudes | Needs normalization | Needs labels | Robustness | Ceiling |
|---|---|---|---|---|---|---|
| RRF k=60 | sum 1/(60+r_i) | no | no | no | highest | medium |
| Weighted RRF | sum w_i/(60+r_i) | no | no | few (weights only) | high | medium-high |
| Convex combination | sum w_i*n_i(s_i) | yes | yes (bounded) | yes (alpha, w) | medium | high |
| DBSF | sum (s-mu+3sig)/6sig | yes | built-in per-list | no | medium | medium-high |
| CombSUM/MNZ | sum w_i*s_i (+|hits| factor) | yes | yes | helpful | low-medium (variance) | high when lists independent |
Notes:
- Convex combination: Bruch/Gai/Ingber (TOIS 2024) is the definitive hybrid-fusion study: CC > RRF both in-domain and out-of-domain; normalization choice barely matters as long as transforms are bounded and monotone (min-max, theoretical min-max, z-score all fine - they mostly shift optimal alpha); raw-score CC is unstable because BM25 is unbounded; alpha tunes from little data; and RRF's apparent parameter-freeness breaks down once per-source rank offsets differ - tuned offsets generalize poorly across domains.
- Weighted RRF: same rank-space robustness as RRF plus per-source reliability control. Production shape: Qdrant v1.16 {"rrf":{"k":60,"weights":[...]}}, weights indexed by prefetch order.
- DBSF: parameter-free magnitude-aware fusion (Qdrant v1.11+). Assumes roughly well-behaved per-list distributions computed per-query over returned candidates; heavy-tailed lists (our PPR masses) are its weak spot.
- CombMNZ: multiplies by list-membership count - strong consensus bias; Cormack showed higher result variance vs RRF; risky when sources correlate (our BM25 and PPR both partly entity/lexical-driven).

## 3. When RRF underperforms (evidence-backed regimes)
1. Scores are calibrated/bounded AND some labels exist: convex combination wins (Bruch TOIS24: in-domain and OOD; alpha sample-efficient). Weaviate made min-max CC its v1.24 default for exactly this reason.
2. One source is clearly stronger or reliability is heterogeneous: equal-vote RRF dilutes the strong source (Milvus docs: choose WeightedRanker when "you know one retrieval path is more important"; Qdrant FAQ: move to weighted RRF once you have validation data).
3. You tune rank offsets per dataset: tuned RRF generalizes poorly out-of-domain (Bruch) - either keep untuned k=60 or switch fusion family entirely.
4. Downstream logic consumes absolute thresholds or score gaps: fused RRF scores compress into a narrow band (~[0.006,0.033] per list at k=60), making cutoff/threshold heuristics brittle. Concrete case: Weaviate autocut requires relativeScoreFusion because rankedFusion erases gap information.
5. Sources are highly correlated: little diversity to exploit, consensus bias dominates (CombMNZ failure analysis in Cormack 2009). Relevant here: BM25 and PPR overlap lexically/entity-wise; expect diminishing returns from the third correlated list on exact-match-heavy queries.
6. PPR-specific degeneracy: with zero/few KG seeds the PPR ranking is noise. HippoRAG2 handles this structurally by folding dense similarity into the reset vector (lambda*sim, lambda=0.05) instead of trusting bare PPR - hence our seed-count gate on w_ppr.

## 4. Concrete recommendation: gated weighted three-way RRF
Spec:
- score(d) = sum over sources i in {bm25, vec, ppr} present in d's candidate sets of w_i * 1/(K + r_i(d)); K=60; r 1-based; term OMITTED if d not in that source's window (do not impute zeros).
- Window N = max(100, 5 * final_k) per source before fusion; final_k typically 20.
- Initial weights (1.0, 1.0, 1.0). Per-query gate: if PPR seeded with <2 matched KG phrase nodes, drop the ppr term (w_ppr:=0 for that query).
- Deterministic tie-break: (-score, doc_id).

```python
K = 60
def fuse(lists: dict[str, list[str]], weights: dict[str, float]) -> list[tuple[str, float]]:
    # lists e.g. {"bm25": [...top-N ids...], "vec": [...], "ppr": [...]}; ranks 1-based
    acc: dict[str, float] = {}
    for name, ids in lists.items():
        w = weights[name]
        if w == 0.0 or not ids:
            continue                      # gated-out (PPR without seeds) or empty source
        for rank, doc_id in enumerate(ids[:WINDOW], start=1):
            acc[doc_id] = acc.get(doc_id, 0.0) + w / (K + rank)
    return sorted(acc.items(), key=lambda kv: (-kv[1], kv[0]))
```

Tuning plan (once a labeled dev set exists, ~50+ queries): grid w_ppr in {0.5, 0.75, 1.0, 1.25}; optionally w_bm25/w_vec in {0.75, 1.0, 1.25}; verify K in {30, 60, 100} is flat (expect yes per pilot evidence). Metric: Recall@20 first, nDCG@10 second.
Why not convex combination now: BM25 unbounded, cosine bounded but model-dependent, PPR mass scale varies with query connectivity and graph size - none mutually calibrated, and we hold zero relevance labels today (Bruch's own caveat: CC needs those preconditions to realize its higher ceiling).
Why not DBSF now: per-query Gaussian-ish normalization assumes well-behaved distributions; sparse heavy-tailed PPR masses violate that. Revisit as phase-3 option.
Upgrade path: (a) log-scaled normalized convex combination a la Bruch once eval harness + labels land; (b) query-class-dependent weights (entity-heavy queries raise w_ppr); (c) keep fusion app-side even if LanceDB-native hybrid search is adopted later, so the spec above stays authoritative and deterministic.
Cost: O(N)-ish merge (~300 dict ops/query at N=100x3), sub-millisecond on EPYC core, trivially inside the 3072 MiB MemAvailable floor; stdlib only - satisfies offline/permissive/CPU-only constraints.

## Sources (all accessed 2026-08-25)
1. Cormack, Clarke, Buettcher - Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods, SIGIR 2009: https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf (DOI 10.1145/1571941.1572114)
2. Bruch, Gai, Ingber - An Analysis of Fusion Functions for Hybrid Retrieval, ACM TOIS 2024 / arXiv 2210.11934: https://arxiv.org/abs/2210.11934
3. Elasticsearch RRF retriever reference (rank_constant default 60, rank_window_size): https://www.elastic.co/docs/reference/elasticsearch/rest-apis/retrievers/rrf-retriever
4. Qdrant hybrid queries (RRF k=2 zero-based default; DBSF formula v1.11; parameterized weighted RRF v1.16): https://qdrant.tech/documentation/search/hybrid-queries/ ; guidance table: https://qdrant.tech/documentation/faq/
5. Milvus reranking (RRFRanker k=60 default; WeightedRanker arctan normalization; norm_score in 2.6 Function API): https://milvus.io/docs/reranking.md
6. Weaviate hybrid search concepts (relativeScoreFusion default since v1.24; rankedFusion 1/(rank+60); alpha; autocut dependency): https://docs.weaviate.io/weaviate/concepts/search/hybrid-search
7. HippoRAG (NeurIPS 2024, arXiv 2405.14831) and HippoRAG2 (ICML 2025, arXiv 2502.14802), MIT-licensed code OSU-NLP-Group/HippoRAG: https://github.com/OSU-NLP-Group/HippoRAG
