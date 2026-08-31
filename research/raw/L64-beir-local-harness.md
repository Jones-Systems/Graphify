# LANE L64 — BEIR subset as local eval harness (T10 eval)

Versions and URLs were recorded as checked against primary sources on
2026-08-25. No later currentness is claimed.

## Findings

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|beir==2.2.0 (loader+evaluator+runfile IO)|tool|https://github.com/beir-cellar/beir|Apache-2.0|High (NeurIPS'21 D&B track; SIGIR'24 resource track)|5|4|1|4|1|H|PyPI latest 2.2.0, py>=3.9 → cp313-safe (checked 2026-08-25); GenericDataLoader + EvaluateRetrieval k=[1,3,5,10,100,1000]; util.save_runfile exports TREC run files|
|BeIR HF mirror org|tool(data)|https://huggingface.co/BeIR|per-dataset research terms|High|4|3|0|1|1|H|README links HF org beside live UKP zip mirror (both fetched 2026-08-25); per-zip md5s published|
|SciFact + NFCorpus sanity pair|dataset|https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip|research-use (redistributed as-is)|High|5|4|1|2|1|H|5,183+3,633 docs, 623 queries, ~1.43M tokens; NFCorpus 38.2 rel/Q → sensitive to fusion deltas; BM25S+J eval <1 s|
|SCIDOCS|dataset|https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scidocs.zip|research-use|High|4|3|2|3|1|H|25,657 docs / 1,000 q / 3.2M tokens; citation-prediction stresses lexical↔semantic disagreement — direct probe of RRF gating|
|FiQA-2018|dataset|https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/fiqa.zip|research-use|High|4|3|2|3|1|H|57,638 docs / 648 q / 5.2M tokens; short noisy finance-forum posts ≈ ticket/chat corpora; 1,237 QPS single-core (BM25S+J)|
|ArguAna|dataset|https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/arguana.zip|research-use|High|4|2|2|3|1|H|8,674 docs / 1,406 q; queries ARE full argument docs → exercises doc→doc path; caveat: query text inside corpus (self-match inflates lexical scores)|
|TREC-COVID|dataset|https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/trec-covid.zip|research-use|High|4|2|4|4|2|H|171,332 docs / 50 q / 20.2M tokens; 493.5 rel/Q deepest judgments in BEIR → best probe for Recall@100 + rerank lift; 484 QPS BM25S+J|
|Webis-Touche-2020|dataset|https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/webis-touche2020.zip|research-use|High|3|1|3|3|3|H|382,545 docs / 49 q / 74.2M tokens (longest docs in suite) → long-doc chunking + graph-signal stressor; embedding time requires measurement.|
|CQADupStack|dataset|https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/cqadupstack.zip|research-use|High|5|2|3|4|2|M|457,199 docs / 13,145 q / 44.9M tokens, 12 StackExchange forums incl. stackoverflow; duplicate-question retrieval = closest BEIR-native analog to code-Q&A dedup; convention metric MRR@10|
|Quora|dataset|https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/quora.zip|research-use|High|3|2|2|2|1|H|522,931 docs / 10,000 q / 4.2M tokens; near-dup detection analog (issue/ticket dedupe); BM25 relatively weak → dense/RRF differentiation visible|
|Larger tier: DBPedia 4.64M, FEVER+Climate-FEVER 5.42M shared corpus, HotpotQA 5.23M, MSMARCO 8.84M docs|strategy|https://github.com/beir-cellar/beir#available-datasets|research-use|High|2|1|2|2|4|M|These collections require separate storage, encoding, and runtime estimates before inclusion; dbpedia-entity is a possible later graph-oriented probe.|
|BRIGHT — stackoverflow + leetcode tasks|dataset|https://brightbenchmark.github.io/|CC-BY-4.0|Medium-High (ICLR 2025; 42k HF downloads)|4|2|4|5|2|M|BEIR has NO native source-code task; BRIGHT fills code-retrieval gap; custom retriever = function returning same {qid:{docid:score}} dict → drop-in for the evaluation pipeline|
|bm25s==0.3.11|tool|https://github.com/xhluca/bm25s|MIT|High (306k weekly dl)|4|3|0|2|1|H|mmap-loadable NumPy/numba BM25; published single-core BEIR QPS (scifact 2,788 / fiqa 1,237 / trec-covid 484) → reference BM25 oracle to parity-check tantivy scoring|
|bm25-benchmarks CLI|tool|https://github.com/xhluca/bm25-benchmarks|unverified (check repo before vendoring)|Medium|3|2|0|2|1|M|Reproduces published QPS / index-time / NDCG@10 tables on demand; calibration anchors for harness timing claims|
|ranx==0.3.21|tool|https://github.com/AmenRa/ranx|MIT|High (ECIR'22/CIKM'22/SIGIR'23)|5|4|2|4|1|H|compare() with paired Fisher randomization + Tukey HSD; fuse()/optimize_fusion() tunes RRF k/weights on train splits; ir_datasets qrels import; dep numba 0.67.0 supports py≥3.10 → cp313 OK|
|pytrec-eval-terrier==0.5.10|tool|https://github.com/terrierteam/pytrec_eval|MIT (LICENSE read 2026-08-25)|High|4|2|0|2|1|M|trec_eval-parity bindings; independent metric engine to cross-check beir evaluator output|
|Staged run-caching + bge-reranker-base ONNX rerank stage|technique|https://huggingface.co/BAAI/bge-reranker-base|MIT|High on recorded date|5|2|3|3|2|H|The recorded model card exposed an ONNX file; persisted TREC runfiles can support repeatable fusion and rerank ablations. Runtime and quantized quality require measurement.|

## Verdict
The recorded candidate combines BEIR data, metrics, and run-file interfaces
with paired significance tests and explicit RRF evaluation. Dataset selection,
licenses, Python compatibility, storage, indexing, and elapsed time require
fresh verification and target measurement. BRIGHT is a separate candidate for
code-adjacent coverage because BEIR has no native source-code task.
Evaluation shape: load a licensed subset, preserve qrels and run files, expose
each retriever through the same `{query_id: {document_id: score}}` contract,
and compare predeclared metrics with paired significance testing. If a system
retrieves chunks while qrels identify documents, the chunk-to-document
aggregation rule must be declared and tested before scoring; the original
max-pool proposal remains an unverified design choice.
