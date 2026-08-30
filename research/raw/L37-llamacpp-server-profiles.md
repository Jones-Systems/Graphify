# Lane L37 — T6 local-llm: llama.cpp `llama-server` on CPU-only local hardware

Researched 2026-08-25. Target assumptions: CPU-only Linux with no GPU, Python 3.13, offline-capable operation, and a deployment-declared available-memory floor. Public benchmark and model data are retained as recorded and were not independently revalidated during remediation.

## 1. Server concurrency model (`-np` / `-c`) — verified against master README (b10621-era, fetched 2026-08-25)
- `-np, --parallel N` = server slots (**default -1 = auto** since mid-2026; was 1). `-cb/--cont-batching` continuous batching **enabled by default**.
- `-c, --ctx-size N` is the **total** context budget; per-slot context = c/np (server-bench derives "total context based on number of slots and expected per-slot context"). New `--kv-unified` (default on when slots=auto) shares one unified KV buffer across sequences; `--cache-reuse N` enables KV-shift chunk reuse; `--cache-prompt` (default on) gives prefix caching across calls — big win for repeated system prompts in a search pipeline.
- All slots submit into one shared batch → concurrent requests decode together (`llama_decode()` per step). Aggregate throughput ≠ np × single-stream; per-slot speed drops while aggregate rises until CPU saturated. Measure with repo's `scripts/server-bench.py` (reports "Average total generation speed" AND "per slot") or k6 harness in `tools/server/bench/`.
- Illustrative 16-core profile: `-t 16 -tb 16 -np 4 -c 16384` (4096/slot) or `-np 2`; `-b 2048 -ub 512` defaults fine; `--metrics` for Prometheus; `--api-key` + loopback bind.

## 2. Memory formula under a declared memory floor
Peak RSS ≈ **W + K + C + O**:
- W = GGUF file bytes (weights, mmap'd resident when hot)
- K = n_layer × d_gqa × ctx_total × (bytes_k + bytes_v); per-element: f16 = 2.0 B, q8_0 = 1.0625 B, q4_0 = 0.5625 B. (d_gqa = n_kv_heads × head_dim; verify exact number in server startup log "KV buffer size" line.)
- C ≈ 100–800 MiB compute/logits buffers at `-b 2048 -ub 512`; O ≈ 0.2–0.5 GiB runtime.

Worked budgets (ctx 32,768 total, `-ctk q8_0 -ctv q8_0`, KV sizes computed from published configs):

| Deployment | W (GiB) | KV q8_0 (GiB) | Total estimate (GiB) |
| --- | ---: | ---: | ---: |
| Qwen3-4B Q4_K_M | 2.33 | 2.39 (144 KiB/tok f16 ×0.53) | ~5.7 |
| Qwen3-8B Q4_K_M | 4.68 | 2.39 | ~8.1 |
| Qwen3-14B Q4_K_M | 8.38 | 2.66 (160 KiB/tok) | ~12.0 |
| Qwen3-14B Q8_0 | 14.62 | 2.66 | ~18.3 |
| Llama-3.1-8B Q4_K_M | 4.58 | 2.13 (128 KiB/tok) | ~7.7 |
| Phi-4 Q4_K_M | 8.43 | ~3.32 (200 KiB/tok, 40L×1280) | ~12.8 |

The worked profiles suggest that memory bandwidth may bind before model storage for some CPU deployments. Recalculate weight, cache, and buffer demand against current available memory before use. `--load-mode mmap+mlock` pins weights and therefore requires explicit headroom validation; bare mmap can incur page-eviction latency under concurrent load.

## 3. Measured tok/s, CPU-only EPYC (community + vendor)
- **EPYC 9554 (Genoa 64C, 12-ch DDR5-5600, 460.8 GB/s), Phi-4 14B, llama-bench b6040, tg128, `-numa distribute -t 64`, 2025-08:** Q4_K_M 29.54 t/s @ 8.43 GiB · Q5_K_M 26.08 @ 9.87 · Q6_K 23.81 @ 11.2 · Q8_0 19.53 @ 14.51 · F16 11.40 @ 27.31. → **Q4→Q8 costs ~34% decode speed** (bandwidth-bound).
- **EPYC 9374F (Genoa), Gemma-2-27B Q4_K_M, r/LocalLLaMA 2024-12:** 15.45 t/s Linux `--numa distribute` 32t vs **5.25 t/s without NUMA tuning** (3× swing — placement dominates).
- **AMD ZenDNN backend, EPYC 9755 (Turin, but Genoa 9004 officially supported), build b9326 vs ZenDNN 5.2.2, Jun 2026:** prompt processing native baselines: Llama-3.1-8B BF16 694 t/s, Qwen3.5-9B Q8_0 633 t/s @128c; ZenDNN ≈2× dense pp (up to 4.5× MoE); **decode currently falls back to native CPU path**; perplexity delta ≤0.0004 (numerically equivalent).
- Caution: shared cloud slices starve bandwidth (EPYC 9654 1/6 rental → ~3 t/s large model, r/LocalLLaMA 2025-01).
- **Illustrative 16-core Genoa-class estimate [INFERENCE, bandwidth share unknown]:** single-stream tg128: 3–4B Q4_K_M ≈ 30–70 t/s; 7–8B Q4_K_M ≈ 15–35 t/s; 14B Q4_K_M ≈ 8–22 t/s. Prompt processing (compute-bound, scales with cores, ZenDNN-multipliable): ~150–300 t/s pp for 8B-class. Short-output tasks (query rewrite ≤200 tok) land at 1–10 s worst-case on 8B–14B. **Gate adoption on an deployment-target `llama-bench -m … -t 16,32 -p 512 -n 128` + `scripts/server-bench.py -np 4` run.**

## 4. Quant profile ladder (file sizes from official/vendor HF repos, fetched 2026-08-25)

| Model (GGUF) | Q4_K_M | Q5_K_M | Q8_0 | License |
|---|---|---|---|---|
| Qwen/Qwen3-4B-GGUF | 2.33 GiB | 2.69 GiB | 3.99 GiB | Apache-2.0 |
| Qwen/Qwen3-8B-GGUF | 4.68 GiB | 5.45 GiB | 8.11 GiB | Apache-2.0 |
| Qwen/Qwen3-14B-GGUF | 8.38 GiB | 9.79 GiB | 14.62 GiB | Apache-2.0 |
| bartowski/Meta-Llama-3.1-8B-Instruct-GGUF | 4.58 GiB | 5.34 GiB | 7.95 GiB | Llama community lic. |
| bartowski phi-4 (14B) | 8.43 GiB | 9.87 GiB | 14.51 GiB | MIT |

Newer-gen Qwen3.5-4B/9B appear in AMD's Jun 2026 benches but official public GGUF repos were inaccessible (HTTP 401) on 2026-08-25 — recheck before adopting.

## 5. Candidate table

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|llama.cpp `llama-server`|tool|https://github.com/ggml-org/llama.cpp|MIT|production (rel v0.3.0/b10621, 2026-08)|5|3|4|3|1|H|Master README 2026-08-25: OAI-compatible chat/completions/embeddings + reranking endpoint (PR #9510), Prometheus `--metrics`, grammar/JSON-schema output; 113k stars (AMD blog 2026-08-18)|
|Slot concurrency `-np`/`-c` + cont-batching|technique|https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md|MIT|stable|5|4|3|0|1|H|README: `-np` default auto, `-cb` default on, unified KV buffer; `scripts/server-bench.py` measures aggregate vs per-slot tok/s; k6 bench harness in tools/server/bench|
|NUMA/thread placement (`--numa distribute`, `-t phys`)|strategy|https://www.reddit.com/r/LocalLLaMA/comments/1h3l2ch|MIT(stack)|stable|4|4|2|0|0|H|EPYC 9374F 27B Q4: 15.45 t/s with distribute vs 5.25 without (2024-12); AMD tuning guide: test -t 16 vs 32, numactl membind|
|Flash-attn + KV q8_0 (`-fa on -ctk q8_0 -ctv q8_0`)|technique|https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md|MIT|stable|5|4|2|1|1|H|-ctk/-ctv list q8_0/q4_0/q5_*; q8_0 ≈ 50–55% of f16 KV with negligible ppl loss; q4_0 has documented quality cliff (discussion #24518); K more sensitive than V (PR #7412 lineage)|
|`--load-mode mmap+mlock` residency|strategy|https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md|MIT|stable|4|2|1|0|0|H|--mlock/--mmap deprecated in favor of --load-mode (auto/mmap/mlock/mmap+mlock); mlock counts against the declared memory floor; validate the profile on deployment hardware|
|Qwen3-4B quant ladder|model profile|https://huggingface.co/Qwen/Qwen3-4B-GGUF|Apache-2.0|stable|5|5|3|3|1|H|HF API sizes 2026-08-25 (Q4_K_M 2.33 GiB…); KV 144 KiB/tok f16 → 32k q8_0 KV only 2.39 GiB; whole deployment ~5.7 GiB|
|Qwen3-8B quant ladder ⭐|model profile|https://huggingface.co/Qwen/Qwen3-8B-GGUF|Apache-2.0|stable|5|4|4|4|1|H|Sizes verified; ~8.1 GiB total @32k ctx q8-KV; illustrative estimate 15–35 t/s [I]; best latency/quality point for short pipeline outputs|
|Qwen3-14B quant ladder|model profile|https://huggingface.co/Qwen/Qwen3-14B-GGUF|Apache-2.0|stable|4|3|4|5|1|M|Sizes verified; ~12 GiB @32k q8-KV; 14.66B-class measured 29.5 t/s Q4 on full 9554 → illustrative estimate 8–22 t/s [I]; quality ceiling pick|
|Meta-Llama-3.1-8B-Instruct ladder|model profile|https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF|Llama community license|stable|3|4|4|4|1|H|HF API sizes 2026-08-25 (Q4_K_M 4.58 GiB, Q8_0 7.95 GiB); non-OSI license adds review friction vs Apache Qwen|
|Phi-4 14B ladder|model profile|https://ahelpme.com/ai/llamacpp-ai/llama-bench-the-phi-4-14b-and-amd-epyc-9554-cpu/|MIT|stable|3|3|4|4|1|H|Measured on EPYC 9554 (2025-08, build b6040): Q4_K_M 29.54 t/s/8.43 GiB → Q8_0 19.53/14.51; strongest math/reasoning at 14B; heavier KV per token than Qwen3|
|ZenDNN GGML backend (`-DGGML_ZENDNN=ON`)|technique|https://www.amd.com/en/developer/resources/technical-articles/2026/llama-cpp-on-amd-epyc.html|MIT + Apache-2.0 libs|new (upstream 2026-08, tested vs b9326)|5|4|3|0|2|M|AMD 2026-08-18: supports EPYC 9004 Genoa; ~2× dense prompt-processing, ≤0.0004 ppl delta; decode still native-CPU fallback; zero runtime flags|
|ik_llama.cpp fork|repo|https://github.com/ikawrakow/ik_llama.cpp|MIT|active fork|3|3|2|0|3|M|Discussion #164 (2024-12, 7950X Zen4): PP 2–4×, TG 1.1–1.6× vs upstream; 2026 issue #1699/#2155 show regressions on some MoE/MXFP4 paths; needs AVX-512 build flags on Zen4|

## Verdict
Recorded candidate: **llama-server (pin v0.3.0/b10621) + Qwen3-8B-Instruct Q4_K_M**, `-t 16 -np 4 -c 16384 -fa on -ctk q8_0 -ctv q8_0 --load-mode mmap+mlock --numa distribute --metrics`. The source comparison estimated an ~8 GiB total footprint and identified Qwen3-14B Q4_K_M as a larger asynchronous option. Neither footprint nor throughput is accepted for a deployment until measured on its hardware.
Integration sketch: build native (`cmake -DGGML_NATIVE=ON`), run as a local service bound to a configurable loopback endpoint behind the target query-rewrite/entity-extraction stage, and gate use on deployment-target `llama-bench` and `scripts/server-bench.py` results that confirm the declared memory floor and required throughput.
