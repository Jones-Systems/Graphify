# LANE L13 — T2 embeddings: best LOCAL embedding model for md-heavy documentation on CPU

> **Recovery status:** the exact Markdown below is committed at reviewed
> revision `d1dbac36208b0066fc8907bd9fe9408fc5c51a60`, but its immutable
> pre-commit origin is unavailable in this repository. Retain it as
> origin-unbound research; exclude it from validated synthesis until its
> evidence is independently re-established. Linked sources are citations,
> not current-version verification.

Date: 2026-08-25. Target env: Debian VPS, 16-core AMD EPYC Genoa, NO GPU, hard floor MemAvailable >= 3072 MiB during bursts, Python 3.13, offline/self-hostable, permissive licenses only.
Scope: BGE-M3 vs nomic-embed-text-v1.5 vs gte-small/gte-large vs mxbai-embed-large-v1 vs snowflake-arctic-embed family. Criteria: MTEB retrieval-subset quality, CPU tokens/sec at ~200k chunks (~60-80M tokens @ ~300-400 tok/chunk), encode-time RAM. Evidence: primary sources (HF model cards, PyPI, official docs), fetched 2026-08-25.

## Findings table

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|Snowflake/snowflake-arctic-embed-m-v1.5|tool|https://huggingface.co/Snowflake/snowflake-arctic-embed-m-v1.5|Apache-2.0|High (rel. Jul 2024, Snowflake-maintained, ONNX shipped in-repo)|5|4|5|5|1|H|MTEB Retrieval 55.14 NDCG@10 @768d (54.2 @256d MRL) with only 109M params - beats 335M mxbai (54.39) at 1/3 compute; BERT-base backbone, 512 ctx; ONNX in repo onnx/ dir|
|Snowflake/snowflake-arctic-embed-l-v2.0|tool|https://huggingface.co/Snowflake/snowflake-arctic-embed-l-v2.0|Apache-2.0|High (rel. Dec 2024)|3|2|3|4|2|H|BEIR-15 NDCG@10 55.6 (older-style MTEB-R table shows 55.98); 568M params (303M non-emb), 8192 RoPE ctx, 74 langs, MRL->256d (-0.18% rel); +0.46 NDCG over m-v1.5 for ~5x CPU cost|
|nomic-ai/nomic-embed-text-v1.5|tool|https://huggingface.co/nomic-ai/nomic-embed-text-v1.5|Apache-2.0|High (tech report Feb 2024; in fastembed supported list, 0.52GB ONNX)|4|3|3|3|2|H|MTEB avg 62.28@768d, MTEB-R ~53.01; 137M params, 8192 ctx, Matryoshka 64-768d; sentence-transformers needs trust_remote_code (custom module); community report of context cap in published ONNX variant|
|thenlper/gte-small|tool|https://huggingface.co/thenlper/gte-small|MIT|High (2023, legacy-MTEB era)|4|4|2|2|1|H|MTEB avg 61.36, MTEB-R 49.46 @33.4M params, 384d, 512 ctx - fastest tier but -5.7 NDCG vs arctic-m-v1.5|
|mixedbread-ai/mxbai-embed-large-v1|tool|https://huggingface.co/mixedbread-ai/mxbai-embed-large-v1|Apache-2.0|High (rel. Mar 2024)|3|2|3|4|1|H|MTEB avg 64.68 (56 ds), MTEB-R 54.39 @335M params, 1024d MRL-truncatable, 512 ctx - dominated by arctic-m-v1.5 (higher R, 1/3 params)|
|thenlper/gte-large|tool|https://huggingface.co/thenlper/gte-large|MIT|High (2023)|2|2|2|3|1|H|MTEB avg 63.13, MTEB-R 52.22 @~0.34B (BERT-large class per HF size tag), 1024d, 512 ctx - dominated on both quality and speed axes|
|BAAI/bge-m3|tool|https://huggingface.co/BAAI/bge-m3|MIT|High (rel. Jan 2024, FlagEmbedding)|2|1|2|2|3|H|MTEB English R 48.82 dense (LOWEST of set) despite 568M params; 8192 ctx, dense+sparse+ColBERT, 100+ langs; FlagEmbedding forces FP32 on CPU (calls model.float()); ~2.27GB fp32 weights approach the declared memory floor; value ONLY if cross-lingual or built-in hybrid lexical support is needed. GPU not required, but CPU fit requires measurement.|
|qdrant/fastembed|tool|https://github.com/qdrant/fastembed|Apache-2.0|High (active 1.x; official supported-models page fetched 2026-08-25)|5|4|4|1|1|H|Pure ONNX Runtime, zero torch dependency (ORT >=1.20 ships cp313 Linux wheels per PyPI; torch needs >=2.6 for py3.13); batch_size=256 default, data-parallel workers for offline bulk; supports nomic-v1.5/mxbai/gte-large/bge-small-en-v1.5/arctic v1 line per official Supported_Models page; TextEmbedding.add_custom_model loads arctic-m-v1.5 from its in-repo onnx/|
|ONNX INT8 dynamic quantization|technique|https://huggingface.co/docs/transformers/quantization/optimum|(tooling Apache-2.0/MIT)|High (standard ORT workflow, documented by HF optimum)|5|4|3|2|2|M|Weights ~4x smaller, 2-4x CPU speedup typical; accuracy delta must be validated against own recall set before cutover (per-channel QInt8 vs QUInt8: benchmark both on target CPU)|

## CPU throughput scenario (~200k chunks, ~60-80M tokens)

Anchors (measured): nomic-embed-text 137M via llama.cpp/Ollama = 850 tok/s short inputs, 620 tok/s @2k-token inputs on a 4-core Intel N100 mini PC (toolbrain.net build log); ONNX single-query warm latency bge-small-en-v1.5 6.1ms vs snowflake-arctic-embed-s 4.1ms (pdf-mcp benchmark docs). Any extrapolation to a 16-core Genoa-class CPU is illustrative and requires a deployment benchmark.

|Model class|Est. tok/s on 16c EPYC, ONNX int8, batch>=64|Full-corpus wall time|Basis|
|---|---|---|---|
|gte-small/bge-small (33M)|~4,000-8,000|~2.5-5.5h|[INFERENCE] scaled from N100 anchor + ORT thread scaling|
|arctic-m-v1.5 (109M) / nomic-v1.5 (137M)|~2,000-4,000|~5-11h|[INFERENCE] same anchor class as measured nomic N100 numbers|
|mxbai-large / gte-large (~335M)|~700-1,500|~13-32h|[INFERENCE] param-proportional|
|bge-m3 (568M) fp32 FlagEmbedding|~150-400|~55-148h|FlagEmbedding forces fp32 on CPU (verified in m3.py); perf regression reported between 1.2.x->1.3.x (GitHub issue #1308); dense-only + max_length=512 required tuning|
|bge-m3 via ONNX int8|~400-900|~24-55h|[INFERENCE] quantized; still slowest per token of the set|

## Encode-time RAM footprint (batch<=64 x 512 tok)

Weights fp32: gte-small ~134MB; arctic-m-v1.5 ~437MB; nomic-v1.5 ~550MB; mxbai-large ~1.34GB; gte-large ~1.36GB (HF tag 1.2GB ONNX); bge-m3 ~2.27GB. Peak = weights + activations + tokenizer overhead.
- gte-small/bge-small: peak <0.5GB - trivially safe.
- arctic-m-v1.5: peak ~0.7-1.0GB - safe vs 3072MiB floor. [INFERENCE from weight size]
- nomic-v1.5: peak ~0.9-1.2GB - safe. [INFERENCE]
- mxbai/gte-large: peak ~1.6-2.2GB - safe but chunky alongside other agents on shared host. [INFERENCE]
- bge-m3 fp32: peak ~3-4GB - GRAZES/BREACHES the MemAvailable >= 3072MiB hard floor when other lane processes are resident; int8 ONNX drops weights to ~0.6GB making it safe but still slowest. [INFERENCE from weights + activation scaling]
fastembed-reported ONNX model sizes (official Supported_Models page): nomic-v1.5 0.52GB, mxbai 0.64GB, arctic-m(v1) 0.43GB, gte-large 1.2GB, bge-small-en-v1.5 0.067GB.

## GPU flag
NONE of the compared models requires a GPU. All run CPU-only. BGE-M3 is the only candidate whose default library path is CPU-hostile (forced fp32, 2.27GB resident, slowest throughput); it remains legal-but-impractical here. The recorded candidates use Apache-2.0 or MIT licenses and are self-hostable offline after artifact acquisition.

## Verdict
Top pick: snowflake-arctic-embed-m-v1.5 - best MTEB-R of the set (55.14) at 109M params (beats 335M mxbai), Apache-2.0, ONNX shipped in-repo, no GPU, ~<1GB encode RAM, est. 5-11h full reindex on idle 16c EPYC. Integration sketch: pip install fastembed (+onnxruntime>=1.20 cp313); TextEmbedding.add_custom_model(model="Snowflake/snowflake-arctic-embed-m-v1.5", pooling=PoolingType.CLS, sources=ModelSource(hf="Snowflake/snowflake-arctic-embed-m-v1.5"), dim=768, model_file="onnx/model.onnx"); query prefix "query: ", docs unprefixed; batch 256, threads=physical cores; store vectors beside graphifyy node-link JSON and keep its BM25/link-graph signals for hybrid rerank. Quality upgrade path if ceiling hit: arctic-l-v2.0 (BEIR 55.6, 8192 ctx) overnight reindex; avoid BGE-M3 unless cross-lingual/hybrid becomes a requirement.
