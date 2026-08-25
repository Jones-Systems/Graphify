# Lane L38 (T6 local-llm): vLLM on CPU-only — feasibility verdict

**Investigated:** 2026-08-25. Sources: official vLLM docs (latest dev + stable), PyPI release index, AMD published benchmarks (2025 blog + 2026 ZenDNN 5.2 article), vLLM GitHub quantization docs/issues. Box under evaluation: Debian VPS, 16-core AMD EPYC (Zen 4 "Genoa", AVX-512 capable), no GPU, 64 GB shared RAM, **hard floor MemAvailable ≥ 3072 MiB during compute bursts**, Python 3.13.

## Verdict up front

**EXCLUDED for this box** — vLLM-on-CPU is *technically real* (first-class x86 backend, official wheels, Zen 4 is precisely the minimum supported AMD ISA, Python 3.13 supported), but it fails three of our hard constraints: (1) throughput at 16 shared cores is far below interactive-bar for any model useful enough to matter, (2) resident footprint of even a 1B-class deployment (~3–5 GB incl. runtime + KV cache + weight prepack) collides with the 3 GiB MemAvailable floor for a persistent service, and (3) our stack has **zero generative-LLM consumer today** (embeddings arctic-embed-m-v1.5 and reranking bge-reranker-base already run on plain CPU without vLLM). Revisit triggers listed at the end.

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|vLLM x86 CPU backend (AVX-512/oneDNN, FP32/BF16/FP16)|technique|https://docs.vllm.ai/en/latest/getting_started/installation/cpu/|Apache-2.0|Mature (in-tree, CI bench suite, perf dashboard hud.pytorch.org CPU)|1|0.5|0.5|0.5|3|H|Docs (read 2026-08-25): Linux, `avx512f` rec.; "AMD requires at least 4th gen (Zen 4/Genoa) or higher" — our Genoa exactly meets minimum. Python 3.10–3.13 supported|
|Official CPU wheels + Docker (`vllm-<v>+cpu-cp38-abi3-manylinux_2_34_x86_64` since 0.17.0; `vllm/vllm-openai-cpu` image; index `wheels.vllm.ai/<v>/cpu`)|tool|https://docs.vllm.ai/en/latest/getting_started/installation/cpu/ ; https://pypi.org/simple/vllm/|Apache-2.0|Mature|1|0.5|0.5|1.0|2|H|PyPI latest stable = **vLLM 0.27.1**; cp38-abi3 wheels install on Py 3.13. Friction: GitHub-release URL or extra-index + `--torch-backend cpu`; wheel installs need `LD_PRELOAD` Intel OpenMP (libiomp5), TCMalloc recommended|
|ZenCpuPlatform / zentorch (ZenDNN kernels, `vllm[zen]` extra; auto-engages on AuthenticAMD+avx512; bf16/fp32 only, fp16 unsupported)|technique|https://github.com/amd/ZenDNN-pytorch-plugin ; RFC https://github.com/vllm-project/vllm/issues/35089|Apache-2.0|Newer (RFC merged into tree; Docker target `vllm-openai-zen`)|1|1.5|1.0|1.0|2|H|Docs: linear layers dispatched through ZenDNN; weight prepack `VLLM_ZENTORCH_WEIGHT_PREPACK=1` (duplicates weights in blocked layout at load → transient extra RAM)|
|CPU quantization: INT8 W8A8 (oneDNN GEMM); GPTQ/AWQ INT4 via CPU WNA16 kernels|technique|https://github.com/vllm-project/vllm/blob/main/docs/features/quantization/README.md|Apache-2.0|Supported on x86 CPU (AWQ converted to GPTQ-like layout for CPU kernel)|2|1.0|1.0|0.5|2|H|Compatibility matrix lists AWQ/GPTQ/INT8-W8A8 supported on x86 CPU; makes ≤1–3 B models fit small RAM — but still insufficient for our floor as a *resident* service|
|KV-cache/threading sizing (`VLLM_CPU_KVCACHE_SPACE`, `VLLM_CPU_OMP_THREADS_BIND`, reserve 1–2 cores for frontend)|strategy|https://docs.vllm.ai/en/latest/getting_started/installation/cpu/#faq|n/a (config)|Documented tuning surface|0|0|0.5|0|2|H|Current docs: KVCACHE_SPACE default `0` (older builds defaulted 4 GiB); doc examples set 40 GiB on 32-core boxes. Tuning down to ~1–2 GiB to respect our floor caps concurrent sequences to near-single-stream|

## Revisit triggers
1. A generative consumer lands (semantic-enrichment DEC-10 upgrade choosing local generation over embeddings-only).
2. Host RAM grows or the floor relaxes for scheduled batch windows.
3. vLLM CPU throughput improves an order of magnitude on Zen 4 (track their CPU perf dashboard).
