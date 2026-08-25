# LANE L41 — T6 local-llm: Nightly enrichment budget design

Constraint decomposition: (1) anonymous growth — KV cache = ctx × layers × kv_dim × B/elem, MULTIPLIED by OLLAMA_NUM_PARALLEL (Ollama FAQ: context mem ∝ parallel × ctx); (2) mmap'd weight pages (7B Q4_K_M ≈ 3.8 GiB, llama.cpp #3359) count toward cgroup usage AND MemAvailable — ceilings below working set cause weight-page refault thrash, not protection; (3) bandwidth-bound decode: bare-metal Genoa 25–45 t/s tg / 800–2000 t/s pp for 7B Q4_K_M (#11733, r/LocalLLaMA), VM lands lower; (4) kernel docs: memory.high CAN be breached and must be paired with an "external monitor" reducing workload (admin-guide/cgroup-v2) — the worker governor IS that monitor; cgroup bounds blast radius, governor guarantees the floor.

## Findings table

|Item|Type|URL|License|Maturity|StackFit|EffGain|EffectGain|QualGain|AdoptCost|Conf|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|Ollama v0.32.x single-stream enrich profile|strategy|ollama docs+FAQ|MIT|stable|5|3|4|4|2|H|NUM_PARALLEL=1, MAX_LOADED_MODELS=1, FLASH_ATTENTION=1, KV_CACHE_TYPE=q8_0, num_ctx=8192, NUM_THREADS=12 ⇒ ≈5.1 GiB charged total|
|enrich-model.slice cgroup isolation|technique|systemd docs|n/a|mature|5|4|4|3|2|H|MemoryHigh=8G throttle / MemoryMax=11G leak ceiling; CPUQuota=1150%; Nice=10 + idle IO class|
|systemd-oomd ManagedOOMMemoryPressure|technique|systemd docs|n/a|mature|4|3|3|3|2|H|kills leaf services on pressure; model svc isolated from worker svc (worker slice MemoryMax=3G)|
|Worker governor (floor authority)|strategy|/proc/meminfo + PSI|n/a|new for our stack|5|5|5|4|2|H|pre-flight defer unless MemAvailable ≥ weights+2·KV_max+3 GiB+1 GiB (≈10 GiB); pause <4096 MiB / resume >6144 MiB hysteresis; PSI trigger "some 150000 1000000"; shed model via keep_alive:0 on sustained stalls|
|SQLite lease ledger resume|strategy|sqlite WAL|n/a|mature|5|4|4|4|2|H|enrich_job PK(repo,item,model_id,prompt_rev); CAS claim + 15-min lease TTL + startup stale-lease reset; per-item atomic commit; deterministic decode (temp 0, seed, num_predict cap) makes retries idempotent|
|Nightly systemd timer|strategy|systemd|n/a|mature|5|3|3|3|1|H|Persistent=true + RandomizedDelaySec; phase sequencing unloads model (keep_alive=0) before embedding/rerank phases|
|Budget formula|technique|derived|n/a|n/a|4|4|3|3|1|M|items = T_window/(in_tok/pp_tps + out_tok/tg_tps); conservative 7B plan ≈385 items/6h (8 t/s gen, 60 t/s pp, 1500in/250out); self-calibrate from eval_count/eval_duration in final stream chunk after night 1|

## Verdict
Top pick: Ollama 0.32.x in `enrich-model.slice`, single-stream profile (NUM_PARALLEL=1, q8_0 KV, 8k ctx ≈ 5.1 GiB charged) inside MemoryHigh=8G/MemoryMax=11G slices, floor enforced by a MemAvailable+PSI worker governor with hysteresis, crash-safe resume from a SQLite lease ledger — ~385 items/6h conservative.
Rejected: partial-token streaming checkpoints (outputs ≤500 tok; commit loss already bounded), vLLM CPU (allocator appetite vs floor — see L38), llama-cpp-python in-process (no kill-domain separation).
