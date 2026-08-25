# LANE L64 — BEIR subset as local eval harness (T10 eval)

Target file: `research/raw/L64-beir-eval-harness.md` (NOT WRITTEN — this agent has no write tool; full content below).
All versions/URLs verified 2026-08-25 against PyPI/GitHub/HF primary sources.

## Findings

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|beir==2.2.0 (loader+evaluator+runfile IO)|tool|https://github.com/beir-cellar/beir|Apache-2.0|High (NeurIPS'21 D&B track; SIGIR'24 resource track)|5|4|1|4|1|H|PyPI latest 2.2.0, py>=3.9 → cp313-safe (checked 2026-08-25); GenericDataLoader + EvaluateRetrieval k=[1,3,5,10,100,1000]; util.save_runfile exports TREC run files|
|BeIR HF mirror org|tool(data)|https://huggingface.co/BeIR|per-dataset research terms|High|4|3|0|1|1|H|README links HF org beside live UKP zip mirror (both fetched 2026-08-25); per-zip md5s published|
|SciFact + NFCorpus sanity pair|dataset|https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip|research-use (redistributed as-is)|High|5|4|1|2|1|H|5,183+3,633 docs, 623 queries, ~1.43M tokens; NFCorpus 38.2 rel/Q → sensitive to fusion deltas; BM25S+J eval <1 s|
|SCIDOCS|dataset|…/scidocs.zip|research-use|High|4|3|2|3|1|H|25,657 docs / 1,000 q / 3.2M tokens; citation-prediction stresses lexical↔semantic disagreement — direct probe of RRF gating|
|FiQA-2018|dataset|…/fiqa.zip|research-use|High|4|3|2|3|1|H|57,638 docs / 648 q / 5.2M tokens; short noisy finance-forum posts ≈ ticket/chat corpora; 1,237 QPS single-core (BM25S+J)|
|ArguAna|dataset|…/arguana.zip|research-use|High|4|2|2|3|1|H|8,674 docs / 1,406 q; queries ARE full argument docs → exercises doc→doc path; caveat: query text inside corpus (self-match inflates lexical scores)|
|TREC-COVID|dataset|…/trec-covid.zip|research-use|High|4|2|4|4|2|H|171,332 docs / 50 q / 20.2M tokens; 493.5 rel/Q deepest judgments in BEIR → best probe for Recall@100 + rerank lift; 484 QPS BM25S+J|
|Webis-Touche-2020|dataset|…/webis-touche2020.zip|research-use|High|3|1|3|3|3|H|382,545 docs / 49 q / 74.2M tokens (longest docs in suite) → long-doc chunking + graph-signal stressor; embedding-dominated (~6–16 min) [INFERENCE]|
|CQADupStack|dataset|…/cqadupstack.zip|research-use|High|5|2|3|4|2|M|457,199 docs / 13,145 q / 44.9M tokens, 12 StackExchange forums incl. stackoverflow; duplicate-question retrieval = closest BEIR-native analog to code-Q&A dedup; convention metric MRR@10|
|Quora|dataset|…/quora.zip|research-use|High|3|2|2|2|1|H|522,931 docs / 10,000 q / 4.2M tokens; near-dup detection analog (issue/ticket dedupe); BM25 relatively weak → dense/RRF differentiation visible|
|Deferred big tier: DBPedia 4.64M, FEVER+Climate-FEVER 5.42M shared corpus, HotpotQA 5.23M, MSMARCO 8.84M docs|strategy|https://github.com/beir-cellar/beir#available-datasets|research-use|High|2|1|2|2|4|M|Multi-hour dense-encode bursts jeopardize MemAvailable≥3072 MiB floor scheduling; revisit post-phase-1; dbpedia-entity (400 q, 38.2 rel/Q) is strongest later graph probe|
|BRIGHT — stackoverflow + leetcode tasks|dataset|https://brightbenchmark.github.io/|CC-BY-4.0|Medium-High (ICLR 2025; 42k HF downloads)|4|2|4|5|2|M|BEIR has NO native source-code task; BRIGHT fills code-retrieval gap; custom retriever = function returning same {qid:{docid:score}} dict → drop-in for our run pipeline|
|bm25s==0.3.11|tool|https://github.com/xhluca/bm25s|MIT|High (306k weekly dl)|4|3|0|2|1|H|mmap-loadable NumPy/numba BM25; published single-core BEIR QPS (scifact 2,788 / fiqa 1,237 / trec-covid 484) → reference BM25 oracle to parity-check tantivy scoring|
|bm25-benchmarks CLI|tool|https://github.com/xhluca/bm25-benchmarks|unverified (check repo before vendoring)|Medium|3|2|0|2|1|M|Reproduces published QPS / index-time / NDCG@10 tables on demand; calibration anchors for harness timing claims|
|ranx==0.3.21|tool|https://github.com/AmenRa/ranx|MIT|High (ECIR'22/CIKM'22/SIGIR'23)|5|4|2|4|1|H|compare() with paired Fisher randomization + Tukey HSD; fuse()/optimize_fusion() tunes RRF k/weights on train splits; ir_datasets qrels import; dep numba 0.67.0 supports py≥3.10 → cp313 OK|
|pytrec-eval-terrier==0.5.10|tool|https://github.com/terrierteam/pytrec_eval|MIT (LICENSE read 2026-08-25)|High|4|2|0|2|1|M|trec_eval-parity bindings; independent metric engine to cross-check beir evaluator output|
|Chunk→doc max-pool qrels projection|technique|(internal design)|n/a|n/a|5|3|3|4|1|M|BEIR qrels are doc-level while prod retrieves chunks; max-pool chunk scores per parent doc BEFORE metrics or nDCG silently corrupts|
|Staged run-caching + bge-reranker-base ONNX int8 rerank stage|technique|https://huggingface.co/BAAI/bge-reranker-base|MIT|High|5|2|3|3|2|H|278,044,931 params; `onnx/model.onnx` shipped in-repo (HF API checked 2026-08-25); persist base runs as TREC runfiles → fusion/rerank ablations replay in seconds; top-100 rerank ≈ 8–20 min/full suite on 16c [INFERENCE]|

## Verdict
Top pick: `beir==2.2.0` (data+metrics+runfile IO) + `ranx==0.3.21` (paired-Fisher significance, RRF tuning) over phase-1 subset {scifact, nfcorpus, scidocs, fiqa, arguana} + trec-covid, plus CQADupStack (stackoverflow-weighted) as the code-adjacent set; add BRIGHT stackoverflow/leetcode when native-code coverage is required — BEIR has none.
Why: CPU-only costs are minutes-scale (grounded single-core QPS/index-rate tables), licenses Apache-2.0/MIT, Python-3.13-clean, and the {qid:{docid:score}} run contract is shared by beir, ranx and BRIGHT — one adapter serves both benchmarks.
Integration sketch: GenericDataLoader → production chunker → node-link JSON consumed by graphifyy==0.9.16 (real graph path exercised) → thin retrievers exposing `retrieve(corpus, queries, top_k=1000)` for tantivy-BM25 / sqlite-vec / gated 3-way RRF / PPR → cache TREC runfiles → metrics nDCG@10 (primary), Recall@100, MRR@10 (cqa) → adopt changes only on ranx.compare Fisher p<0.05.