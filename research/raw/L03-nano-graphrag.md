# L03 — nano-graphrag: implementation quality, vendoring feasibility, gaps (T1 GraphRAG lane)

Investigated: 2026-08-25. All URLs fetched live today unless noted. Environment: Debian VPS, 16 cores, no GPU, Python 3.13, MemAvailable floor 3072 MiB, offline-preferred, no cloud API keys without explicit owner flag.

## Identity & provenance

- Repo: https://github.com/gusye1234/nano-graphrag — MIT, 3,973★ / 424 forks / 84 open issues, created 2024-07-25, last push 2026-01-27, not archived (GitHub API, fetched 2026-08-25). Author: Jianbai Ye (GusYe/MemoDB).
- PyPI: latest **0.0.8.2 published 2024-10-19** (wheel 62.9 kB); `requires_python >=3.9`. Main branch still reports `__version__ = "0.0.8.2"` but carries post-release commits through 2026-01: new `entity_extraction/` DSPy module, Amazon Bedrock support, `aioboto3` in requirements.txt. **PyPI release is stale relative to main.**
- Lineage: LightRAG (HKUDS) and Medical Graph RAG both started as forks/extensions (README “Projects that used” section).
- Size (measured): `graphrag.py` = 383 lines; `_storage/gdb_networkx.py` ≈ 290; `_op.py` ≥ 1,075 (last def at line 1075) [INFERENCE on exact total]; author markets “~1100 LOC excluding tests and prompts” — claim predates the DSPy/Bedrock additions. Whole core package ≈ 2–3 kLOC. sdist = 58 kB.

## Implementation quality assessment

Architecture: one dataclass config (`GraphRAG`, ~40 knobs) wiring three swappable storage ports (`BaseKVStorage` → JSON files, `BaseVectorStorage` → nano-vectordb or hnswlib, `BaseGraphStorage` → NetworkX GraphML or Neo4j), plus a pure-function operator layer in `_op.py`: `chunking_by_token_size`/`chunking_by_seperators`, `get_chunks`, `extract_entities` (LLM JSON extraction per chunk + gleaning + merge-with-summary), `generate_community_report` (hierarchical Leiden → LLM community reports), and three query modes `local_query` (entity-vector seed → subgraph context), `global_query` (community-report ranking, NOT true map-reduce — top-K≤512 communities only), `naive_query` (chunk vectors). Every method has an async twin; LLM calls are concurrency-capped via semaphore decorator and md5-key cached to disk.

Quality positives: genuinely readable; clean port interfaces (drop-in storage classes); LLM response cache makes re-runs cheap; incremental insert dedups chunks by content hash; `only_need_context=True` returns retrieved context without generation (good for piping into our own tooling); tokenizer pluggable (tiktoken or HF).

Quality negatives found in source:
- Dead code: `node_embedding_algorithm="node2vec"` + `_node2vec_embed()` are vestigial — grep of `_op.py` shows zero references to `embed_nodes`/node2vec; entity vectors come from `embedding_func(name+description)`.
- Full community re-cluster + full community-report regeneration on EVERY insert (README states this explicitly) — expensive with an LLM in the loop.
- Unpinned deps incl. heavy unconditional ones: `graspologic`, `dspy-ai`, `neo4j`, `hnswlib`, `aioboto3` (requirements.txt on main).
- No document deletion API at all (grep of `graphrag.py` methods: only insert/query + private hooks).
- Global search deviates from MS GraphRAG map-reduce (documented in README Issues); covariates/claims not implemented (README Issues).
- Single-process JSON KV persistence, no cross-process locking; JSON-mode reliance strains small models (README itself warns qwen2-7B yields unparsable extraction output; offers `convert_response_to_json_func` hook + json_repair suggestion).

## Vendoring feasibility into our stack (graphifyy==0.9.16, NetworkX node-link JSON)

**Mandatory, not optional**: `pip install nano-graphrag` cannot resolve on our host. Its dep `graspologic` 3.4.4 pins `requires_python <3.13,>=3.9` (PyPI metadata, fetched 2026-08-25) and also pins `numpy<2.0`. On our Python 3.13 stack pip resolution fails outright.

Vendoring is nonetheless cheap because graspologic's live surface is exactly TWO lazy imports inside `_storage/gdb_networkx.py`:
1. `graspologic.utils.largest_connected_component` (in `stable_largest_connected_component`) → replaceable with `nx.connected_components` (~10 lines; the surrounding node/edge stabilization is already pure networkx).
2. `graspologic.partition.hierarchical_leiden` (in `_leiden_clustering`) → replace with `networkx.community.louvain_communities` (built-in since networkx 2.8, BSD-3) applied recursively to oversized communities to emulate hierarchy, or `leidenalg` 0.12.0 (`igraph` backend, cp313 wheels, but **GPL-3.0-or-later** — fine for internal runtime use, flag before any redistribution).
The third import (`embed.node2vec_embed`) is dead code — delete it during vendoring.

Also strip while vendoring: `dspy-ai`, `neo4j`, `hnswlib`, `aioboto3`, Bedrock/Azure branches (unused). Remaining hard deps: `openai` client (or drop `_llm.py` and inject our own funcs), `tiktoken` (or switch tokenizer_type=huggingface), `networkx`, `nano-vectordb` (vendor too — tiny MIT repo, 206★, pushed 2026-01-09), `tenacity`, `xxhash`. Result: a fully py3.13-clean, offline-capable package.

Interop: nano persists graphs as GraphML; graphifyy emits NetworkX node-link JSON. Adapter is trivial both directions (`nx.read_graphml` ↔ `nx.node_link_graph`, ~20 lines). Node attrs after ingest: `description`, `source_id` (chunk ids), `clusters` (JSON string of {level,cluster}); edge attrs: `weight`, `description`, `source_id`. Our structural code/markdown entities have names but thin descriptions — community-report quality will hinge on feeding text-rich docs (READMEs, issues, commit messages) alongside AST symbols.

RAM check: all-MiniLM-L6-v2 embeddings (~90 MB weights, few hundred MB runtime) fit comfortably under the 3 GiB floor; nano-vectordb brute-force numpy kNN ≈ 614 MB fp32 at 100k×1536-dim — fine at our corpus sizes; use 384–768-dim local models to cut it further.

## What it lacks (gap list)

No deletion/uninstall of documents; no incremental community updates (full regeneration per insert); global search capped at top-512 communities instead of true map-reduce; no covariates/claims; no BM25/hybrid lexical retrieval; no reranker stage; no streaming responses; no multi-hop/path queries over the graph; no eval harness beyond example notebooks (MultiHop-RAG ipynb); no cross-process file locks; no rate/token-budget limiter (on their ROADMAP, unchecked); small-model JSON fragility mitigated only by optional hooks; PyPI stale vs main so bug fixes land unreleased.

## Findings table

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|nano-graphrag (project overall)|tool|https://github.com/gusye1234/nano-graphrag|MIT|Active-ish (push 2026-01-27) but PyPI stale since 2024-10-19|4|2|4|2|2|H|MIT, 3973★; readable async pipeline w/ LLM cache + hash-dedup; unresolvable deps on py3.13 force vendoring|
|Core operator layer (_op.py + graphrag.py: chunk→extract→cluster→report→local/global/naive query)|technique|https://github.com/gusye1234/nano-graphrag/blob/main/nano_graphrag/_op.py|MIT|Mature core, actively patched on main|5|3|4|3|2|H|Measured: graphrag.py 383 ln, _op.py ≥1075 ln; clean Base*Storage ports; only_need_context mode fits pipe-into-graphifyy design|
|NetworkXStorage + KV/vector storage abstraction (GraphML persistence)|component|https://github.com/gusye1234/nano-graphrag/blob/main/nano_graphrag/_storage/gdb_networkx.py|MIT|Mature; batch APIs added on main|4|2|2|2|1|H|GraphML ↔ node-link JSON adapter ~20 lines via nx.node_link_graph/read_graphml; node attrs description/source_id/clusters map cleanly onto graphifyy exports|
|nano-vectordb (built-in default vector store)|tool|https://github.com/gusye1234/nano-vectordb|MIT|Small but stable (push 2026-01-09, 206★)|5|2|2|1|1|M|Brute-force numpy cosine + JSON/pickle persistence; ~614 MB fp32 @100k×1536-dim — OK under our RAM floor at our corpus scale; hnswlib class available if needed|
|graspologic dependency|technique|risk-blocker|https://pypi.org/project/graspologic/|MIT|Tested py3.9–3.12 only; 3.4.4 requires_python <3.13; numpy<2 pin|0|0|0|0|4|H|PyPI metadata fetched 2026-08-25: requires_python "<3.13,>=3.9" ⇒ pip install nano-graphrag fails on Python 3.13; only 2 live imports exist (LCC + hierarchical_leiden), both replaceable|
|Swap hierarchical_leiden → networkx louvain_communities (recursive oversize split)|technique|https://networkx.org/documentation/stable/reference/algorithms/community.html|BSD-3|Built into networkx ≥2.8 (we already ship networkx)|5|2|2|1|1|H|Zero new deps, py3.13-safe; loses Leiden refinement guarantees + native hierarchy (emulate by recursing on communities > max_graph_cluster_size=10); leidenalg 0.12.0 is the faithful alt but GPL-3+|
|Local/offline LLM backend via injected best/cheap_model_func (ollama example)|strategy|https://github.com/gusye1234/nano-graphrag/blob/main/examples/no_openai_key_at_all.py|MIT (example)|Documented first-class path|3|1|3|2|3|M|Working ollama+cache example shipped; README warns qwen2-7B produces unparsable JSON → extraction failures; needs ≥8B-class model on CPU (fits 64 GB, watch 3 GiB floor); default OpenAI gpt-4o/4o-mini path = requires-owner-approval|
|Local CPU embeddings (sentence-transformers all-MiniLM-L6-v2 replacing openai text-embedding-3-small)|strategy|https://github.com/gusye1234/nano-graphrag/blob/main/examples/using_local_embedding_model.py|MIT (example)|Documented; wrap_embedding_func_with_attrs sets dim/max_token_size|4|3|2|1|1|H|~90 MB model, CPU-only, fully offline; 384-dim cuts vector-store RAM ~4× vs 1536-dim; quality below OpenAI embeddings (QualGain low but positive vs no vector layer at all)|
|DSPy entity-extraction module (main-only, tuned small-model extraction)|technique|https://github.com/gusye1234/nano-graphrag/tree/main/nano_graphrag/entity_extraction|MIT|Experimental (roadmap item, benchmark doc 17.9 kB)|2|1|2|2|3|M|Targets Qwen2-7B/Llama-3.1-8B extraction quality; drags dspy-ai dep; absent from PyPI 0.0.8.2; skip unless we commit to small-local-LLM extraction|
|Vendor-and-strip strategy (vs pip install): take _op/_storage/base/_utils/prompt + nano-vectordb, drop graspologic/dspy/neo4j/hnswlib/aioboto3, add louvain clustering + injected local funcs|strategy|https://github.com/gusye1234/nano-graphrag|MIT (vendor keeps NOTICE)|Proven pattern (LightRAG forked it)|5|2|3|2|1|H|~2–3 kLOC total; post-strip hard deps = networkx+tiktoken(+numpy) already in our stack; isolates us from stale-PyPI drift; cost = we own the patch set|

**Verdict**: Top pick = vendor nano-graphrag's operator core (MIT, ~2–3 kLOC) as the semantic-query layer over graphifyy's NetworkX graphs — it is the only candidate whose storage model (file-based NetworkX + JSON KV + tiny numpy vector store) matches ours with zero infra. Why: py3.13 resolution failure rules out pip-install anyway, and the graspologic surface to excise is two functions. Integration sketch: vendor + strip → louvain-based hierarchical clustering → sentence-transformers CPU embeddings → GraphML↔node-link adapter for graphifyy artifacts → LLM decision gated (local Ollama ≤8B vs owner-approved API) since every high-value path (extraction, community reports) is LLM-bound.

### Evidence log
- GitHub API repo objects (stars/license/dates): fetched 2026-08-25.
- PyPI JSON for nano-graphrag (0.0.8.2, 2024-10-19) and graspologic (3.4.4, <3.13): fetched 2026-08-25.
- Source reads @ main sha acb35c0: graphrag.py (383 ln), _storage/gdb_networkx.py (full), _op.py (def inventory via regex), requirements.txt, __init__.py (0.0.8.2), examples/no_openai_key_at_all.py, docs/ROADMAP.md.
