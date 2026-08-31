# LANE L13 — T2 embeddings: best LOCAL embedding model for md-heavy documentation on CPU

> **Evidence status:** the underlying report was committed at reviewed
> revision `d1dbac36208b0066fc8907bd9fe9408fc5c51a60`; this file is a
> sanitized derivative. Its immutable pre-commit origin is unavailable in
> this repository. Retain it as origin-unbound research; exclude it from
> validated synthesis until its evidence is independently re-established.
> Linked sources are citations, not current-version verification.

Recorded date: 2026-08-25. Scope: BGE-M3 vs
nomic-embed-text-v1.5, gte-small/gte-large, mxbai-embed-large-v1, and
the snowflake-arctic-embed family. Criteria: recorded retrieval quality,
model size, CPU support, and licensing. The report cites model cards, package
indexes, and official documentation as read on the recorded date; no later
currentness or deployment fit is claimed.

## Findings table

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|Snowflake/snowflake-arctic-embed-m-v1.5|tool|https://huggingface.co/Snowflake/snowflake-arctic-embed-m-v1.5|Apache-2.0|High (rel. Jul 2024, Snowflake-maintained, ONNX shipped in-repo)|5|4|5|5|1|H|MTEB Retrieval 55.14 NDCG@10 @768d (54.2 @256d MRL) with only 109M params - beats 335M mxbai (54.39) at 1/3 compute; BERT-base backbone, 512 ctx; ONNX in repo onnx/ dir|
|Snowflake/snowflake-arctic-embed-l-v2.0|tool|https://huggingface.co/Snowflake/snowflake-arctic-embed-l-v2.0|Apache-2.0|High (rel. Dec 2024)|3|2|3|4|2|H|BEIR-15 NDCG@10 55.6 (older-style MTEB-R table shows 55.98); 568M params (303M non-emb), 8192 RoPE ctx, 74 langs, MRL->256d (-0.18% rel); +0.46 NDCG over m-v1.5 for ~5x CPU cost|
|nomic-ai/nomic-embed-text-v1.5|tool|https://huggingface.co/nomic-ai/nomic-embed-text-v1.5|Apache-2.0|High (tech report Feb 2024; in fastembed supported list, 0.52GB ONNX)|4|3|3|3|2|H|MTEB avg 62.28@768d, MTEB-R ~53.01; 137M params, 8192 ctx, Matryoshka 64-768d; sentence-transformers needs trust_remote_code (custom module); community report of context cap in published ONNX variant|
|thenlper/gte-small|tool|https://huggingface.co/thenlper/gte-small|MIT|High (2023, legacy-MTEB era)|4|4|2|2|1|H|MTEB avg 61.36, MTEB-R 49.46 @33.4M params, 384d, 512 ctx - fastest tier but -5.7 NDCG vs arctic-m-v1.5|
|mixedbread-ai/mxbai-embed-large-v1|tool|https://huggingface.co/mixedbread-ai/mxbai-embed-large-v1|Apache-2.0|High (rel. Mar 2024)|3|2|3|4|1|H|MTEB avg 64.68 (56 ds), MTEB-R 54.39 @335M params, 1024d MRL-truncatable, 512 ctx - dominated by arctic-m-v1.5 (higher R, 1/3 params)|
|thenlper/gte-large|tool|https://huggingface.co/thenlper/gte-large|MIT|High (2023)|2|2|2|3|1|H|MTEB avg 63.13, MTEB-R 52.22 @~0.34B (BERT-large class per HF size tag), 1024d, 512 ctx - dominated on both quality and speed axes|
|BAAI/bge-m3|tool|https://huggingface.co/BAAI/bge-m3|MIT|High (rel. Jan 2024, FlagEmbedding)|2|1|2|2|3|H|MTEB English R 48.82 dense (lowest of the compared set) despite 568M params; 8192 ctx, dense+sparse+ColBERT, 100+ languages; the recorded FlagEmbedding path uses FP32 on CPU and the weights were reported at ~2.27 GB. GPU is not required, but CPU fit requires measurement.|
|qdrant/fastembed|tool|https://github.com/qdrant/fastembed|Apache-2.0|High (active 1.x; official supported-models page fetched 2026-08-25)|5|4|4|1|1|H|Pure ONNX Runtime, zero torch dependency (ORT >=1.20 ships cp313 Linux wheels per PyPI; torch needs >=2.6 for py3.13); batch_size=256 default, data-parallel workers for offline bulk; supports nomic-v1.5/mxbai/gte-large/bge-small-en-v1.5/arctic v1 line per official Supported_Models page; TextEmbedding.add_custom_model loads arctic-m-v1.5 from its in-repo onnx/|
|ONNX INT8 dynamic quantization|technique|https://huggingface.co/docs/transformers/quantization/optimum|(tooling Apache-2.0/MIT)|High (standard ORT workflow, documented by HF optimum)|5|4|3|2|2|M|Weights ~4x smaller, 2-4x CPU speedup typical; accuracy delta must be validated against own recall set before cutover (per-channel QInt8 vs QUInt8: benchmark both on target CPU)|

## Recorded public performance anchors

The report cites a public N100 build log for nomic-embed-text and public
ONNX single-query measurements for small BGE and Arctic models. Those
measurements use different hardware and workloads. The removed report-level
extrapolation did not establish throughput or full-corpus wall time for any
deployment; each candidate requires a deployment-bound benchmark.

## Recorded model-size observations

Recorded FP32 weight sizes were approximately 134 MB for gte-small,
437 MB for arctic-m-v1.5, 550 MB for nomic-v1.5, 1.34 GB for
mxbai-large, 1.36 GB for gte-large, and 2.27 GB for bge-m3. The cited
FastEmbed model list reported ONNX package sizes of 0.52 GB for nomic-v1.5,
0.64 GB for mxbai, 0.43 GB for Arctic v1, 1.2 GB for gte-large, and
0.067 GB for bge-small-en-v1.5. Package or weight size is not peak RSS;
activations, tokenization, batching, and runtime overhead must be measured.

## GPU flag
None of the compared models requires a GPU. The recorded candidates use
Apache-2.0 or MIT licenses and can run offline after artifact acquisition.
The report identified the default BGE-M3 library path as the heaviest CPU
option in the set, but did not establish deployment suitability.

## Verdict
The origin-unbound report favored snowflake-arctic-embed-m-v1.5 on its
recorded retrieval score, parameter count, license, and shipped ONNX file.
That preference is not a validated synthesis conclusion. A fresh evaluation
must re-establish source currentness, deployment memory and throughput, query
prefix behavior, and target-corpus retrieval quality before selecting a model.
