PERSIST-NEEDED

# LANE L42 — T6 local-llm: GGUF quantization tradeoffs for extraction fidelity
Investigated: 2026-08-25. Question: Q4_K_M vs Q5_K_M vs Q8_0 vs f16 (Q6_K as reference) for entity/relation extraction — published perplexity/degradation, JSON-schema adherence, RAM math. Constraints honored: Debian VPS, 16-core CPU-only, MemAvailable floor 3072 MiB, offline/permissive.

## 1. Published perplexity / degradation data

Primary source A — official llama.cpp scoreboard, LLaMA-3-8B base, Wikitext-2 (tools/perplexity/README.md, rev f364eb6f):

| Quant | bpw* | Size GiB | PPL | PPL ratio vs f16 | KLD | Same top-p |
|---|---|---|---|---|---|---|
| f16 | 16.0005 | 14.97 | 6.2332 | 1.0000 | 0.000551 | 100% (ref) |
| Q8_0 | 8.5008 | 7.96 | 6.2343 | 1.000425 (+0.04%) | 0.001355 | 97.67% |
| Q6_K | 6.5633 | 6.14 | 6.2534 | 1.003490 (+0.35%) | 0.005452 | 96.03% |
| Q5_K_M | 5.7036 | 5.33 | 6.2886 | ~1.0089 (+0.89%) | 0.010762 | n/r |
| Q4_K_M | 4.8944 | 4.58 | 6.4071 | 1.028160 (+2.82%) | 0.031273 | 91.90% |
| Q4_K_M +imatrix | 4.8944 | 4.58 | 6.3829 | +2.41% (ΔPPL 0.1513) | 0.028152 | n/r |

*bpw measured on Llama-3.1-8B (tools/quantize/README.md). Model-dependent: same quants on Llama-2-70B cost far less (Q4_K_M +1.20%, Q5_K_M +0.40%, Q6_K +0.16%, old scoreboard in same README); Llama-3-class is more quant-sensitive than Llama-2.

Primary source B — Kurt, "Which Quantization Should I Use?" (arXiv:2601.14277, pub 2026-01-11; Llama-3.1-8B-Instruct, llama.cpp b7600, lm-eval v0.4.9.2, Xeon 8488C CPU): downstream Avg of GSM8K/HSwag/IFEval/MMLU/TQA — f16 69.47; Q4_K_M 69.15; Q5_K_M 69.36; Q6_K 69.23; Q8_0 69.41 (all within noise except 3-bit: Q3_K_S 65.49, −5.7%). WikiText-2 PPL: f16 7.32, Q8_0 7.33, Q6_K 7.35, Q5_K_M 7.40, Q4_K_M 7.56, Q3_K_S 8.96. Critical detail: **format matters more than nominal bits** — same-PPL 5-bit variants diverged sharply on GSM8K/IFEval; Q3_K_M collapsed strict-format numeric extraction (GSM8K strict-match 9.86 vs f16 24.64) while loose-extract stayed 73.16 — direct evidence that rigid output formats degrade before general fluency does. Paper's Pareto frontier: Q5_0 (accuracy-favoring), Q4_K_S (balanced); Q6_K/Q8_0 dominated on compression-per-quality but are the drift-minimizing choices.

Corroboration — Unsloth Dynamic v2.0 (2025-04-24), Gemma-3-27B 5-shot MMLU: Q4_K_M 71.23% (15.41 GB), Q5_K_M 71.77% (17.95 GB), Q8_0 71.60% (26.74 GB), Q6_K 71.87%, BF16 71.50% — non-monotonic spread ≈±0.3 pp = measurement-noise scale; higher bits buy nothing measurable on general knowledge at 27B.

CPU throughput (Kurt Table 3, tg128/pp512 tok/s): f16 2.83/79.57; Q4_K_M 5.12/87.70; Q5_K_M 6.85/58.24; Q6_K 6.33/59.81; Q8_0 5.03/71.42. On CPU, decode is bandwidth-bound: all quants beat f16 by 1.8–2.4×; Q8_0 decodes *slower* than Q5_K_M/Q6_K despite more bits (kernel effects); prefill ordering is irregular. Absolute values will differ on our 16-core Genoa but ordering holds.

## 2. JSON-schema adherence

Two layers must be separated:
- **Syntax (parseable JSON): fully orthogonal to quant level.** Grammar/schema-constrained decoding (llama.cpp GBNF ← JSON-schema converter; Ollama `format`=schema since 2024-12; llama-server response_format) forces valid JSON at any bit-width. Caveats: converter edge-case bugs exist (issue #25923: empty-object schemas, huge maxLength produce rejected grammars), and constrained sampling costs +6–86% wall-clock in the QuantCall experiment.
- **Semantics (correct entities/spans/values/tool-choice/abstention): degrades with bits, model-family-dependent:**
  - QuantCall bench (github.com/Happynood/quant-toolcall-bench, BFCL-derived, SVR/TSA/AC metrics): Qwen3-0.6B SVR 87.7%(FP16)→87.3%(Q4_K_M), AC 60.5→57.5 — stable to Q4_K_M. Counter-example: Llama-3.2-1B degrades significantly even at Q8_0; hardest case (parallel calls) SVR 57.2%→33.8% at Q4_K_M. Finding: model family predicts quant sensitivity better than parameter count. GBNF did NOT rescue semantic errors.
  - 30k-generation study (r/LocalLLM, 2026, 5 small models): Q8_0 statistically indistinguishable from f16; Q4_K_M near-indistinguishable overall; Q3_K_M broke schema compliance in 3/5 models including loss of correct abstention (declining irrelevant extractions).
  - Domain IE evidence: Bornet et al. 2026 (clinical IE, 7 Qwen3/DeepSeek-R1 models, 2–8 bit, DOI 10.3233/SHTI260295): performance plateaus around 4–5 bits, precision×size interaction significant. Communications Medicine 2025 (pathology extraction, s43856-025-00808-8): 4-bit zero-shot substantially below 16-bit (confounded with model size). Mekala et al. EMNLP 2025 (long-context): 8-bit ≈ −0.8% avg; 4-bit up to −59% on some long-context settings → risk grows with prompt/document length, which is exactly our repo-extraction regime.
  - No published span-NER/relation-F1 GGUF-quant sweep exists yet (gap); nearest proxies above.

Policy derived: syntax via constraints always; semantics require ≥Q5_K_M default, Q4_K_M only after golden-set validation, never ≤Q3_K for schema-bearing extraction.

## 3. RAM math per model size

Formula: file_GB ≈ params_B × bpw/8 (bpw: f16 16.0005, Q8_0 8.5008, Q6_K 6.5633, Q5_K_M 5.7036, Q4_K_M 4.8944). Peak RSS ≈ file (mmap-resident during inference) + KV cache + compute buffers (~0.5–1 GiB) + runtime (~0.3 GiB).
KV bytes/token (f16) = 2 · n_layers · n_kv_heads · head_dim · 2. Examples: Llama-3.1-8B = 2·32·8·128·2 = 128 KiB/token → 1.0 GiB @8k, 4.0 GiB @32k. Qwen3-8B = 144 KiB/token; Qwen3-14B = 160 KiB/token → 1.25 GiB @8k. `--cache-type-k/v q8_0` halves these.

Measured weights (llama.cpp READMEs, Llama-3.1-8B): f16 14.96 GiB, Q8_0 7.95, Q6_K 6.14, Q5_K_M 5.33, Q4_K_M 4.58.

Peak footprint @8k ctx, f16-KV (weights+KV+~0.75 buffers), GiB:

| Model | f16 | Q8_0 | Q6_K | Q5_K_M | Q4_K_M |
|---|---|---|---|---|---|
| 8B (measured) | ~16.7 | ~9.7 | ~7.9 | ~7.1 | ~6.3 |
| 14B (est. from bpw) | ~31 | ~17 | ~13.5 | ~12 | ~10.5 |

Floor rule: peak_footprint ≤ typical MemAvailable − 3072 MiB. On the shared 64 GB host recommend default cap ≈12 GiB per extraction run (fits any 8B quant incl. Q8_0, and 14B @Q5_K_M/Q4_K_M); schedule 14B-Q8_0 or 32B runs exclusively. Disk mirrors RAM for GGUF (memory==disk requirement per llama.cpp).

## Findings

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|Q4_K_M k-quant|technique|https://github.com/ggml-org/llama.cpp/pull/1684|MIT|mature (default since 2023-06)|5|5|3|3|1|H|L3-8B +2.82% PPL, KLD .0313, same-top-p 91.9%; L3.1-8B-Instr downstream Avg 69.15 vs f16 69.47 (Kurt 2026-01); QuantCall Qwen3 SVR −0.4pp; fails on fragile families (parallel-call SVR −23pp)|
|Q5_K_M k-quant|technique|https://github.com/ggml-org/llama.cpp/pull/1684|MIT|mature|5|4|4|4|1|H|L3-8B +0.89% PPL, KLD .0108; downstream Avg 69.36 (−0.11 vs f16), IFEval parity; best MMLU among quants in Unsloth Gemma3-27B set (71.77% vs BF16 71.50%); bartowski default rec when it fits|
|Q6_K|technique|https://github.com/ggml-org/llama.cpp/pull/1684|MIT|mature|4|4|4|4|1|H|+0.35% PPL, KLD .00545, same-top-p 96.0%; Avg 69.23; near-lossless middle at 41% of f16 RAM; decodes faster than Q8_0 on CPU|
|Q8_0|technique|https://github.com/ggml-org/llama.cpp/pull/1684|MIT|mature|4|3|4|5|1|H|PPL ratio 1.000425, KLD .00136; 30k-gen study: zero measurable tool-call delta vs f16; 47% smaller than f16, tg128 5.03 vs 2.83 t/s (CPU); the drift-minimizing practical choice|
|f16/bf16 weights|technique (reference)|https://github.com/ggml-org/llama.cpp/blob/master/tools/perplexity/README.md|MIT (tooling)|baseline|2|1|1|5|2|H|2× Q8_0 RAM, slowest decode; BF16↔F16 cast itself shifts logits (KLD 2.5e-5) — no meaningful fidelity gain over Q8_0; skip|
|imatrix quants (WT-calibrated; IQ4_XS)|technique|https://github.com/ggml-org/llama.cpp/pull/4861|MIT|mature (since 2024-06)|4|4|3|3|2|M-H|L3-8B Q4_K_M+imatrix ΔPPL 0.151 vs 0.175, KLD .0282 vs .0313; IQ4_XS 4.14 GiB KLD .0363 ≈ plain Q4_K_S; needs calibration corpus (our repos can supply it)|
|Grammar-constrained decoding (JSON-schema→GBNF)|strategy|https://github.com/ggml-org/llama.cpp/blob/master/docs/development/parsing.md|MIT|mature|5|2|4|3|1|H|Guarantees syntactic JSON at ANY quant; does not fix wrong entities/tool-choice; +6–86% wall clock (QuantCall); converter edge-case bugs (#25923)|
|Ollama structured outputs|tool|https://ollama.com/blog/structured-outputs|MIT|mature (GA 2024-12)|5|3|4|3|1|H|`format`: JSON-schema over llama.cpp grammars; drop-in from Python client; pairs with any quant choice|
|KV-cache q8_0 quantization|strategy|https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md|MIT|mature|4|3|2|2|1|M|Halves KV RAM (8B@8k: 1.0→0.5 GiB); minor quality risk mostly on K-cache; frees budget for higher weight bits|
|Unsloth Dynamic v2.0 GGUFs|tool (artifact family)|https://unsloth.ai/blog/dynamic-v2|Apache-2.0 (tooling); artifacts inherit base-model license|active (2025-04)|3|3|3|3|2|M|Vendor-reported: KL-divergence-guided selective tensor upquant matches stock Q4_K_M size with equal/better MMLU; vendor-benchmarked only|
|QuantCall harness|benchmark/repo|https://github.com/Happynood/quant-toolcall-bench|unlisted|early (2025/26)|4|2|4|4|2|M|Per-quant SVR/TSA/AC/FCR; reusable methodology for our extraction golden-set; finding: family > size predicts quant fragility|
|Kurt 2026 unified eval + released quants|evidence/artifact|https://arxiv.org/abs/2601.14277|arXiv paper; quants on HF uygarkurt/Llama-3.1-8B-Instruct-GGUF|new (2026-01)|4|2|4|4|2|M-H|Only controlled single-checkpoint sweep of 13 GGUF formats incl. CPU throughput; proves format choice ≠ bit-width label; template for our own eval|

**Verdict:** Top pick **Q5_K_M** for 7–14B instruct GGUF extraction models — ~99.1% PPL retention, downstream Avg within 0.11 pp of f16, equal-or-best MMLU across two independent quant sets, ~36% of f16 RAM (8B ≈ 7.1 GiB total @8k ctx; 14B ≈ 12 GiB), faster CPU decode than both f16 and Q8_0. Integration: llama-server/Ollama with response_format=json_schema (syntax guaranteed regardless of bits), --cache-type-k/v q8_0, mmap, 16 threads; adopt Q4_K_M only after passing llama-perplexity KLD<~0.02 vs f16 plus a 100-doc golden-set entity/relation span-F1 gate; never deploy ≤Q3_K for schema-bearing tasks (strict-format collapse: GSM8K-SM 24.6→9.9); skip f16 — Q8_0 is statistically indistinguishable at half the RAM.

Environment fit: all picks offline-capable, MIT/Apache tooling, CPU-only, no API keys; nothing flagged requires-owner-approval.