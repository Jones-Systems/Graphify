# L01 — Microsoft GraphRAG (lane T1)

Investigated: 2026-08-25 (all primary-source fetches this date). Package state: graphrag 3.1.2 on PyPI.
Scope: pipeline architecture; fully-local/no-Azure feasibility; indexing cost & LLM dependency depth; storage format; realistic value on md-heavy corpora of ~12k files.

## 1. Pipeline architecture (verified against microsoft.github.io/graphrag + repo @ main, v3.1.x)

**Index** (CLI `graphrag index`, config emitted by `graphrag init`):
load documents → chunk into TextUnits (default ~1200 tokens; fast method recommends 50–100) → per-chunk LLM extraction of entities + relationships (+ optional claim/covariate extraction) with "gleanings" follow-up loop → merge duplicates, LLM-summarize entity/relationship descriptions → hierarchical Leiden clustering (graspologic-native, Rust) → bottom-up multi-level community report generation (map-reduce) → embeddings written to vector store → parquet tables + stats.json.

**Query modes:** Local Search (entity-centric neighbor fan-out) · Global Search (map-reduce over community reports; holistic corpus questions) · DRIFT Search (community-informed iterative fan-out) · Basic Search (plain top-k vector RAG).

**CLI indexing methods:** `standard` | `fast` | `standard-update` | `fast-update`. No LazyGraphRAG mode exists in the OSS package.

## 2. Fully-local feasibility (no Azure, no cloud API keys)

- **Model layer:** v3.0.0 (released 2026-01-27, semversioner record) removed fnllm and standardized on **LiteLLM**: model types `chat`/`embedding` + `model_provider` (openai|azure|ollama|gemini|…). Any OpenAI-compatible endpoint (Ollama, vLLM, LiteLLM proxy) can serve it; official docs say proxies "seem to work reasonably well" but they "frequently see issues with malformed responses", and the model **must support structured outputs (JSON schema)**. Custom model injection is library-only (no CLI).
- **Vector layer:** a vector store has been mandatory since v1; default is a **local LanceDB directory** → fully offline. Only three embedding fields remain in v3: text_unit_text, entity_description, community_full_content.
- **NLP-only path:** `--method fast` (FastGraphRAG) replaces LLM entity/relationship extraction with NLTK/spaCy noun-phrase detection (en_core_web_md auto-installs) + co-occurrence edges; the **only remaining LLM use is community report generation** (summarization, not strict JSON extraction) → the smallest feasible burden for a small local model.
- **Dependency depth:** hard deps include azure-identity ~=1.25, azure-search-documents ~=12.0, azure-storage-blob ~=12.30 (pulled even for pure-local runs), spacy/textblob/nltk/blis, pandas ~=3.0, pyarrow ~=25, networkx ~=3.6, numpy ~=2.4, graspologic-native >=1.2,<1.3. Python `>=3.11,<3.14` → VPS Python 3.13 ✓. Indexing mechanics are CPU-only; GPU needed only if self-hosting the LLM.
- **Policy flag:** the standard method is effectively tuned/tested on hosted gpt-4-series models; using any hosted API ⇒ `requires-owner-approval` under the current no-cloud-keys rule.

## 3. Indexing cost & LLM dependency depth

- Microsoft docs (fetched 2026-08-25): **graph extraction ≈75% of total indexing cost**.
- Datapoints: ~$10 to index one large book on GPT-4-class models (community measurement, Aug 2024); "$20–500 to index a typical enterprise corpus" (Towards AI, 2026-05-01); production analysis: 10k docs × ~500-token chunks × 3–5 LLM calls/chunk plus summarization across 3–4 community levels (Medium/GraphPraxis, 2026-03-18).
- Envelope for our target corpus (12k md files, ~800 tokens avg ⇒ ~9.6M corpus tokens ⇒ ~8k chunks at 1200): ≥16k extraction calls (+gleanings) + description merges + multi-level reports ≈ **25–40M LLM tokens**. gpt-4o-mini: single-digit-to-low-double-digit dollars; gpt-4o: roughly $60–150+. Fully local, CPU-only 7B-class model at ~20–40 tok/s generation ⇒ ~5–6M output tokens ⇒ **55–70 h of pure generation**, realistically multi-day wall-clock — and sub-8B models routinely violate GraphRAG's strict JSON response contract even with json-repair in the loop. Quality, not time, is the binding constraint.
- Query-time cost: Global search maps over dozens of community reports per question; DRIFT is heavier (iterative agentic loops).
- **LazyGraphRAG** (MS claim: 0.1% of full indexing cost) announced 2024-11-25 was **never shipped in the OSS package** — no CLI mode or package as of 3.1.2 (GitHub discussions #1490, #1934 confirm).

## 4. Storage format

Seven parquet tables (schema documented, semver'd, with migration notebooks v1→v2→v3 that avoid re-indexing): `documents`, `text_units`, `entities` (title/type/description/frequency/degree), `relationships` (source/target/description/weight/combined_degree — literally the edge list), `communities` (Leiden hierarchy), `community_reports` (rank/findings[]), `covariates` (optional claims). Plus LanceDB vector sidecar. Directly readable with pyarrow/polars; converts trivially to networkx node-link JSON for graphifyy interop.

## 5. Realistic value on ~12k-file md-heavy corpora

- Independent systematic evaluation ("RAG vs. GraphRAG", arXiv 2502.11371, 2025-02-17): strengths are complementary — GraphRAG wins query-focused summarization/global sensemaking; plain RAG is often equal or better on precise factoid QA at far lower cost. Expect value mainly for "what are the themes across all 18 repos" style queries, not lookup.
- Our md corpora already carry human-curated structure (links/headings) that pinned graphifyy==0.9.16 exploits for free; GraphRAG's marginal gain concentrates on *implicit* cross-file entity relations, which require the expensive standard pipeline to surface.
- Project status: README (fetched 2026-08-25) declares **maintenance mode — no new features or PRs**, bug fixes/CVE patches only (patches still landing through 3.1.2, next-release entries dated 2026-08-24). Long-term feature upside is capped.

## Findings

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|Microsoft GraphRAG (microsoft/graphrag)|tool|https://github.com/microsoft/graphrag|MIT|Mature, maintenance mode (v3.1.2, 35.7k★)|2|1|3|3|4|H|PyPI latest 3.1.2 fetched 2026-08-25; README maintenance-mode warning; Azure SDKs are hard deps|
|Standard LLM extraction indexing (--method standard)|strategy|https://microsoft.github.io/graphrag/index/methods/|(project MIT)|Mature, default method|1|0|4|4|5|H|Docs: extraction ≈75% of index cost; ~$10/book GPT-4-class (2024-08); $20–500/enterprise corpus (2026-05)|
|FastGraphRAG NLP indexing (--method fast)|technique|https://microsoft.github.io/graphrag/index/methods/|(project MIT)|Documented in v3 docs, actively patched (3.0.6 streaming fix)|4|3|2|2|2|H|NLTK/spaCy noun phrases + co-occurrence edges; LLM only for community reports; 50–100-token chunks advised|
|Leiden hierarchy + community reports via graspologic-native|technique|https://github.com/graspologic-org/graspologic-native|MIT|Mature (>=1.2,<1.3 pinned by graphrag)|4|2|3|3|2|H|Rust Leiden implementation; liftable onto existing graphifyy NetworkX graphs with zero LLM involvement|
|Global-search map-reduce querying|strategy|https://microsoft.github.io/graphrag/query/global_search/|(project MIT)|Mature|2|1|4|3|3|M|Maps over community reports per query; arXiv 2502.11371 shows wins concentrated in summarization/sensemaking tasks|
|Local/DRIFT search engines|technique|https://microsoft.github.io/graphrag/query/drift_search/|(project MIT)|Mature|2|1|3|2|3|M|Entity fan-out; DRIFT adds iterative LLM loops → higher query-time token spend|
|Parquet tables + LanceDB sidecar artifact format|technique|https://microsoft.github.io/graphrag/index/outputs/|n/a (format of MIT project)|Stable; semver'd with migration notebooks|4|2|1|1|1|H|7 documented tables incl. ready-made edge list; pyarrow/polars/networkx-friendly|
|LiteLLM provider layer (Ollama/OpenAI-compatible path)|strategy|https://microsoft.github.io/graphrag/config/models/|(project MIT)|Default since v3.0.0 (2026-01-27)|3|1|2|2|3|H|Docs: proxy setups work but malformed-JSON failures frequent; structured-output-capable model required|
|Incremental updates (standard-update/fast-update)|technique|https://microsoft.github.io/graphrag/cli/|(project MIT)|Documented CLI methods|3|3|2|1|2|M|period/size columns exist specifically for incremental merges; avoids full re-index on changed repos|
|LazyGraphRAG (deferred-cost indexing)|strategy|https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/|n/a|Unreleased in OSS (announced 2024-11-25)|1|0|2|2|5|H|No package/CLI mode in graphrag 3.1.2; confirmed absent via discussions #1490/#1934|

## Verdict
Top pick: do NOT adopt graphrag as a dependency; lift two ideas into graphifyy — graspologic-native Rust Leiden community detection and the 7-table parquet artifact shape (both MIT, zero LLM needed). FastGraphRAG is the only near-offline run mode today but still needs an LLM for reports and produces noisy co-occurrence graphs strictly worse than our curated md link-graphs for navigation. Revisit standard GraphRAG only if the owner approves hosted API keys (requires-owner-approval); LazyGraphRAG remains unreleased vaporware in OSS.
