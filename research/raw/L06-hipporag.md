# L06 — T1 GraphRAG: HippoRAG & HippoRAG 2 (PPR-over-KG retrieval)
Investigated 2026-08-25. Primary sources: arXiv 2405.14831v3 (NeurIPS'24), arXiv 2502.14802v2 (ICML'25), github.com/OSU-NLP-Group/HippoRAG @ main, pypi.org/project/hipporag (latest 2.0.0a4). All fetched 2026-08-25.

Score scales: StackFit/EffGain/EffectGain/QualGain 0–5 higher=better; AdoptCost 0–5 lower=better.

## Findings

|Item|Type|URL|License|Maturity|StackFit|EffGain|EffectGain|QualGain|AdoptCost|Conf|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|HippoRAG v1 (OpenIE KG + Personalized PageRank, single-step multi-hop retrieval)|technique|https://arxiv.org/abs/2405.14831|MIT|Published NeurIPS'24; code moved to `legacy` branch after v2; superseded|4|4|4|3|2|H|Single-step retrieval avg R@2/R@5 57.4/72.9 vs Contriever 46.2/59.9 and ColBERTv2 53.9/65.6 (Table 2); same-backbone deltas +3.0 R@2 MuSiQue, +11.5/+20.9 R@2/R@5 on 2Wiki; QA F1 avg 48.1 vs 42.5 ColBERTv2 (+17% 2Wiki F1); online retrieval 10–30× cheaper, 6–13× faster than IRCoT (v3, 2025-01-14)|
|HippoRAG 2 (passage nodes integrated into KG, query-to-triple seeding, deepened PPR + LLM recognition-memory filter)|technique|https://arxiv.org/abs/2502.14802|MIT|ICML'25 (v2 2025-06-19); active repo (3,963 stars, 420 forks)|5|4|5|4|3|H|Avg QA F1 59.8 vs 57.0 best dense (NV-Embed-v2) with NO regression on simple QA (NQ 63.3 vs 61.9) or NarrativeQA (25.9 vs 25.7) (Table 2); retrieval recall@5 avg 78.2 vs 73.4 NV-Embed-v2; multi-hop recall@5 avg +6.9 (MuSiQue +5.0, 2Wiki +13.9); only evaluated graph-RAG that beats dense everywhere|
|`hipporag` PyPI package (reference implementation)|tool|https://pypi.org/project/hipporag/|MIT|Pre-release alpha: PyPI latest 2.0.0a4; Python >=3.10; ~173 downloads/wk; alpha API churn|4|3|4|3|3|M|README (2026-08-25): OpenAI-compatible endpoints incl. loopback no-auth; vector backends parquet/Qdrant/Chroma/Milvus-lite; 2.0.0a5 binds persisted vectors+OpenIE state to endpoint/model identity; PPR executed via python-igraph|
|PPR-over-KG strategy reused on EXISTING graphifyy==0.9.16 node-link graphs (skip OpenIE entirely)|strategy|arXiv 2502.14802 + networkx link_analysis docs|n/a|Core algorithm trivially portable; v1 ablations isolate PPR contribution|5|5|4|3|1|M|v1 Table 5: removing PPR collapses avg R@5 72.9→56.2/59.2 — PPR is load-bearing; ms–seconds on ~100k-node graphs (scipy/igraph), no GPU; transfer to markdown-link/code-AST graphs is [INFERENCE]|
|Local OpenIE LLM: Qwen2.5-14B/32B-Instruct GGUF via llama.cpp/Ollama OpenAI-compatible endpoint|strategy|huggingface.co/bartowski GGUF READMEs|Apache-2.0 (Qwen2.5)|Mature tooling; hipporag documents any vLLM/OpenAI-compatible server|5|2|3|3|2|M|Q4_K_M: Qwen2.5-14B 8.99 GB, Llama-3.3-70B 42.52 GB; v1 Table 5: Llama-3.1-8B OpenIE within ~1pt of GPT-3.5 except 2Wiki; v2 ran all extraction with Llama-3.3-70B|
|CPU-friendly embedding backbone (Contriever/e5-large/gte-large) for query-node seeding + synonymy edges|strategy|huggingface.co/facebook/contriever|MIT / Apache-2.0|Mature; sentence-transformers CPU inference ~1–2 GB RAM; NV-Embed-v2 (7B) excluded on this host|5|4|3|2|1|M|v2 Table 7: HR2 beats its own dense retriever regardless of backbone → PPR delta survives weaker embedders|

## Verdict
**Top pick:** HippoRAG 2's retrieval mechanism (passage nodes + query-to-triple seeding + damping-0.5 PPR), MIT, ported directly onto our existing graphifyy node-link JSONs — no OpenIE step, no cloud keys, PPR costs seconds on CPU.
**Integration sketch:** load node-link JSON → embed node/passage texts once with e5-large/Contriever (CPU ~1–2 GB) → at query time take top-k phrase nodes (+ passage nodes × weight 0.05) as PPR reset distribution → PPR (damping 0.5, scipy/igraph) → rank passage nodes; add local Qwen2.5-14B OpenIE only if triple-level seeding proves needed.

## Local inference envelope (16-core EPYC, MemAvailable ≥ 3072 MiB)
- Retrieval-time compute negligible: PPR over ~100k nodes <1 GB RAM, sub-second.
- Full local OpenIE indexing: v2 consumed 12.2M tokens for 11.6k passages → overnight-to-days per large corpus on CPU; fine for incremental.
- Model menu: Qwen2.5-14B Q4 ≈ 12–16 GB RSS = recommended ceiling; 32B feasible/slow; 70B (~48 GB RSS) risks floor breach during KV growth — not recommended.
- Package risk: `pip install hipporag` pulls torch; pin exact version, treat save_dir formats as disposable.
