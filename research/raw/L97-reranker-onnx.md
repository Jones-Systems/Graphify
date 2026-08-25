# LANE L97 — T15 Rerank: bge-reranker-base ONNX INT8 on CPU (EPYC-class)

Investigated 2026-08-25. Environment target: Debian VPS, 16-core AMD EPYC (Genoa/Zen4 → AVX-512 + VNNI ✓), no GPU, MemAvailable ≥ 3072 MiB floor, Python 3.13, offline/permissive-license only. Workload: rerank K∈{50,100} candidates × ~300-token passages after gated 3-way RRF.

## 1. Model facts (primary source, fetched 2026-08-25)
- `BAAI/bge-reranker-base`: **MIT** license (HF API metadata), 278M-param XLM-RoBERTa-base cross-encoder (12L/768h, ~86M non-embedding params), EN+ZH, 3.4M downloads. Official usage pattern: retrieve top-100 → rerank → keep top few (BAAI README).
- fp32 ONNX ≈ 1.1 GB; dynamic-int8 ONNX ≈ 280 MB; runtime RSS ≈ 0.45–0.9 GB incl. ORT arena ([DERIVED] from kftof/a-ivanovitch artifact sizes + ORT behavior). Fits memory floor as capped sidecar (limit ≤1.2 GB) or in-process addition.

## 2. Latency at 50–100 candidates × ~300-token passages
No public apples-to-apples EPYC benchmark of this exact model exists; anchors below, scaling stated with method:

| Anchor (measured) | Hardware | Model | Config | Result |
|---|---|---|---|---|
| Oaklight OpenVINO bench | Core Ultra 7 155H (~14 eff. cores, VNNI) | bge-reranker-v2-m3 (568M, 2.2× compute of base) | INT8, 512 tok, b=1 | **60.1 ms/pair** |
| Same | Same | same | INT8, b=16 | **19.2 pairs/s** (834 ms/16) |
| Same, FP16 ref | Same | same | FP16, b=1 / b=16 | 143.9 ms/pair; INT8 = 2.4–3.0× faster |
| a-ivanovitch card | unspecified x86, untuned | bge-reranker-v2-m3 | FP32 ONNX, 1024 tok, 10 docs | 890 ms/pair; ORT 1.33× vs PyTorch |
| ORT issue #19494 | unspecified | BGE reranker | INT8 batched, misconfigured | **8–15 s** for the batch (anti-anchor) |
| Qdrant reranker article | Apple M5 Pro, 15 thr | bge-reranker-base | ~256–512 tok | 16–45 docs/s |
| AMD official RAG doc | 2× EPYC 9745 (SMT off) | bge-reranker-v2-m3 **Q8_0** | end-to-end RAG, 4 users | chosen over BF16: 16 vs 10 tok/s/user |
| sbert.net CE efficiency bench | i7-13700K, 1000 samples | **bge-reranker-base**, bs 16–128 | onnx-qint8(avx512_vnni) / openvino-qint8 vs torch-fp32 | median speedup bars (images); conclusions below |

Scaling method [DERIVED]: MACs/pair ≈ 86M × L. At L=330: 28.4 GMAC/pair → 100 pairs = 2.84 TMAC. Oaklight achieves ≈3.0 TMAC/s on a mobile 14-core VNNI part; a 16-core Genoa with pinned cores reaches ≳ that → **100-candidate rerank ≈ 0.7–1.2 s p50; 50-candidate ≈ 0.35–0.6 s** (amortized 7–12 ms/pair), assuming: dynamic-int8, O2/O3-optimized graph, intra_op = dedicated physical cores, inter_op=1, length-bucketed batches, max_length=330. Budget 1.5–2× p95. If only 4 cores can be dedicated, multiply by ~4 → trim K to 25–50. Misconfiguration failure mode (oversubscription with other services, accidental intra_op=1, fp32, no graph opt): 2–15 s — the dominant operational risk (ORT #19494 class). Biggest single lever besides int8: **truncate max_length 512→~330 (−37% compute)**; latency scales ≈ linearly with sequence length.

## 3. Quality retention vs fp32
- Expected budget: |ΔNDCG@10| ≤ 0.005 typical for correct dynamic int8 on encoder rerankers; treat −0.01 as acceptance threshold, investigate anything worse (likely export/eval bug, not int8 noise).
- Evidence FOR neutrality: temsa QInt8 MiniLM-L12 (ORT 1.22.1): NDCG@10 +0.0023 / −0.0005 / −0.0037 across three reranking sets, MRR stable, with 1.27× latency win on AVX2-only CPU. stellars OpenVINO-int8 v2-m3: score Pearson 0.9976 vs fp32. AMD EPYC RAG: no reported answer-quality loss with Q8_0 reranker. sbert recommendation flowchart: openvino-qint8 is the default CPU pick "when minor performance degradations are acceptable".
- Evidence AGAINST (must heed): a-ivanovitch reports dynamic int8 **flipped the top-1 document on a significant fraction of queries** for bge-reranker-v2-m3 and shipped fp32-only. Rerankers are more quantization-sensitive than embedders because output is a 1-logit margin. Mitigation: per-channel weights (`per_channel=True`, ORT: improves accuracy when weight ranges are large), S8S8/QDQ format (ORT default first choice), and a quality gate on our own corpus before enabling.
- Required gate: on ≥100 sampled queries × identical top-100 candidate lists, measure ΔNDCG@10(int8−fp32), top-1 agreement, %queries with any top-10 reorder. Adopt if ΔNDCG@10 ≥ −0.01 AND top-1 agreement ≥ 95%. Zen4 has VNNI → `reduce_range=False` (reduce_range is only for non-VNNI AVX2/AVX512 saturation; per ORT docs it makes no difference on VNNI parts).

## 4. Serving pattern: in-process vs sidecar
| | In-process (onnxruntime in the search API proc) | Sidecar (TEI cpu-1.9 / infinity) |
|---|---|---|
| Added p50 latency | ~0 (function call) | +1–5 ms localhost HTTP — noise vs 100s of ms compute |
| Memory | +0.45–0.7 GB inside app RSS | isolated, cgroup-cappable (set MemoryMax=1.2 GB) |
| CPU governance | must manage intra_op + affinity yourself | built-in dynamic token batching, concurrency caps (`--max-batch-requests`, `--max-batch-tokens`) |
| Sharing across 18 repos | one copy per repo process (wasteful) | **one replica serves all** |
| Ops surface | none (pip dep) | one systemd unit/container; TEI officially lists BAAI/bge-reranker-base for `/rerank`; also loads pre-quantized int8 ONNX artifacts (kftof recipe) |
| Licenses | ORT MIT, optimum Apache-2.0 | TEI repo Apache-2.0 (GitHub API 2026-08-25); infinity MIT |
Recommendation: **start in-process** (fastest path, zero new services) via sentence-transformers `CrossEncoder(..., backend="onnx", model_kwargs={"file_name": "onnx/model_qint8_avx512_vnni.onnx"})`; promote to a **single shared TEI sidecar** once ≥2 repos need reranking, pinned to a dedicated core set with a memory cap. Both patterns are fully offline; no cloud keys → no owner-approval flags.

## 5. Batch sizing
- Sort all K pairs by tokenized length desc, slice into chunks of **32** (valid range 16–64; sbert swept 16–128 for this exact model, noting ONNX wins at *low* batch while OpenVINO pulls ahead at high batch). Cap tokens/run at ~12–16k (e.g., 32×384). Naive shuffled padding wastes ~30–45% compute; length-bucketing cuts that to <10%.
- One `session.run` at a time per process (queue via semaphore); ORT already parallelizes a single run across `intra_op_num_threads`. Set `intra_op_num_threads` = dedicated physical cores, `inter_op_num_threads`=1, graph opt ALL; warm up once at startup (first-run allocation dominates otherwise). Never leave default thread count when co-running with tantivy/sqlite-vec bursts — that oversubscription is the #19494 10–50× slowdown trap.

## 6. Findings table

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|BAAI/bge-reranker-base|tool|https://huggingface.co/BAAI/bge-reranker-base|MIT|mature (2023, 3.4M dl)|5|3|4|4|1|H|HF API metadata 2026-08-25; BAAI top-100 rerank guidance|
|ORT dynamic INT8 (quantize_dynamic, QInt8, per-channel, S8S8/QDQ)|technique|https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html|MIT|mature|5|4|0|2|1|H|ORT docs: dynamic rec'd for transformers; VNNI required for gains; reduce_range unnecessary on VNNI|
|optimum/sbert int8 export preset avx512_vnni (self-export)|tool|https://www.sbert.net/docs/cross_encoder/usage/efficiency.html|Apache-2.0|mature|5|4|2|2|1|H|sbert bench includes bge-reranker-base w/ this preset; kftof repro recipe|
|Graph-opt pre-process O2/O3 + startup warmup|technique|https://onnxruntime.ai/docs/performance/transformers-optimization.html|MIT|mature|5|3|1|1|1|H|ORT optimizer docs; fusion prerequisites for quant quality|
|Thread governance: intra_op=dedicated cores, inter_op=1, semaphore(1)|technique|https://github.com/microsoft/onnxruntime/issues/19494|MIT|mature|5|4|0|0|1|H|#19494: misconfigured batched int8 = 8–15 s|
|max_length truncation 512→330 + length-desc bucketed batches of 32 (token cap ~16k)|technique|[DERIVED from anchors above]|n/a|standard practice|5|4|0|0|1|M|linear seq-len scaling; sbert batch sweep 16–128; padding-waste math|
|OpenVINO static INT8 route (optimum-intel)|tool|https://github.com/Oaklight/openvino-meteor-lake-ai-inference/blob/main/docs/BENCHMARK_RESULTS.md|Apache-2.0|mature|4|4|2|3|2|M|60.1 ms/pair v2-m3 INT8, 2.4–3× vs FP16; sbert picks ov-qint8 on CPU w/ minor-loss tolerance (Intel-focused)|
|TEI sidecar cpu-1.9 (/rerank, token-dynamic batching, int8-ONNX loading)|strategy|https://github.com/huggingface/text-embeddings-inference|Apache-2.0|mature (1.9 line)|4|3|2|2|2|M|README lists bge-reranker-base; kftof serves int8 ONNX under TEI|
|Infinity sidecar (engine=optimum, Cohere-style /rerank)|repo|https://github.com/michaelfeil/infinity|MIT|active|3|3|2|2|2|M|docs: latest-cpu + --engine optimum requires ONNX in repo|
|In-process CrossEncoder backend="onnx" qint8|strategy|https://www.sbert.net/docs/cross_encoder/usage/efficiency.html|MIT/Apache-2.0 deps|mature|5|4|2|2|1|H|sbert native backend path; zero IPC; auto-uses repo ONNX|
|Quality gate: ΔNDCG@10≥−0.01 ∧ top-1 agreement≥95% on own corpus|strategy|https://huggingface.co/a-ivanovitch/bge-reranker-v2-m3-onnx|n/a|process|5|0|0|4|1|H|temsa neutral deltas vs a-ivanovitch top-1 flip counterexample|
|Prebuilt community int8 artifacts (Xenova/onnx-community, kftof, temsa)|tool|https://huggingface.co/kftof/bge-reranker-v2-m3-onnx-int8-avx2|inherit MIT/Apache|varies|3|3|2|1|1|M|convenient but unversioned provenance; prefer self-export for pinning|

## Verdict
Top pick: self-export bge-reranker-base → ONNX → dynamic INT8 (QInt8, per-channel, avx512_vnni preset) served **in-process** via sentence-transformers `backend="onnx"`, with max_length≈330, length-desc batching at 32, intra_op pinned to dedicated Genoa cores — expect **~0.35–0.6 s p50 for top-50 and ~0.7–1.2 s for top-100 × 300-token passages**, at ΔNDCG@10 within ±0.005 (gate at −0.01; the v2-m3 top-1-flip report mandates the gate). Promote to a single Apache-2.0 TEI cpu-1.9 sidecar (memory-capped, core-pinned) once a second repo needs reranking; OpenVINO-int8 is the fallback runtime if sbert-style micro-benchmarks favor it on this box.

Integration sketch (3 lines): `optimum-cli export onnx --model BAAI/bge-reranker-base --task text-classification` → `quantize_dynamic(m, weight_type=QuantType.QInt8, per_channel=True)` after `quant_pre_process` → `CrossEncoder(model_kwargs={"file_name": "onnx/model_qint8_avx512_vnni.onnx"})` behind a 1-slot semaphore between RRF and final slice, failing open to fused RRF order on timeout.

All sources fetched/verified 2026-08-25 unless dated inline. Items flagged requires-owner-approval: none (fully offline, permissive licenses: MIT/Apache-2.0 throughout).