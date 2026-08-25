# Research Manifest — 100 lanes: graph & semantic-search improvement program

Stack context for every lane: Debian VPS, 16 CPU cores (no GPU), 64 GB RAM with
hard floor MemAvailable ≥ 3072 MiB during compute; Python 3.13; pinned
`graphifyy==0.9.16` structural graphs (NetworkX node-link JSON) over 18 corpora;
no cloud/API-key services unless flagged `requires-owner-approval`.

Scoring axes per item: StackFit / EfficiencyGain / EffectivenessGain /
QualityGain / AdoptionCost(0-5, lower better) / Confidence(H/M/L).

| Lane | Theme | Question |
| --- | --- | --- |
| L1 | T1 graphrag | Microsoft GraphRAG: architecture, local feasibility without Azure, cost profile |
| L2 | T1 graphrag | LightRAG (HKUDS): incremental GraphRAG claims, local run evidence |
| L3 | T1 graphrag | nano-graphrag: minimal implementation worth vendoring? |
| L4 | T1 graphrag | Graphiti (Zep) temporal KG: can it run fully local, what does it add over structural graphs |
| L5 | T1 graphrag | Community-detection + summarization strategies (Leiden/Louvain offline, no-LLM variants) |
| L6 | T1 graphrag | HippoRAG/HippoRAG2: PPR-over-KG retrieval effectiveness evidence and local cost |
| L7 | T1 graphrag | Evidence comparing KG-based vs vector-only retrieval quality on doc-heavy corpora |
| L8 | T2 embeddings | sqlite-vec: maturity, performance, fit as our vector store inside SQLite |
| L9 | T2 embeddings | LanceDB embedded: perf, licensing, disk format stability |
| L10 | T2 embeddings | Qdrant local-mode vs server: when is each right |
| L11 | T2 embeddings | usearch/hnswlib: raw index speed and persistence options |
| L12 | T2 embeddings | Model2Vec/static embeddings: speed-quality envelope for our scale (~12k files) |
| L13 | T2 embeddings | Best local embedding model for md-heavy docs: BGE-M3 vs nomic vs gte (CPU latency!) |
| L14 | T2 embeddings | Matryoshka + binary/int8 quantization: storage and recall tradeoffs |
| L15 | T3 hybrid | rank-bm25 vs tantivy-py BM25: index build time/query speed at our scale |
| L16 | T3 hybrid | Tantivy full-text in Python: maturity, features vs FTS5 |
| L17 | T3 hybrid | Reciprocal Rank Fusion: tuning evidence, alternatives (convex combination) |
| L18 | T3 hybrid | ColBERT/PLAID late interaction on CPU: realistic latency for 300k-link corpus |
| L19 | T3 hybrid | SPLADE sparse neural retrieval: local inference feasibility without GPU |
| L20 | T3 hybrid | Postgres tsvector+pgvector hybrid on existing pg17: integration win? |
| L21 | T3 hybrid | Local rerankers survey: bge-reranker-base/v2-m3 CPU latency vs quality |
| L22 | T4 entity-res | Splink probabilistic ER: fit for person/org entities across repos |
| L23 | T4 entity-res | dedupe library: current state, scaling |
| L24 | T4 entity-res | RapidFuzz blocking strategies (already a dep): best practice patterns |
| L25 | T4 entity-res | Wikidata reconciliation: offline dumps vs API patterns for entity anchoring |
| L26 | T4 entity-res | GLiNER zero-shot NER locally: model size, quality on our content |
| L27 | T4 entity-res | Cross-repo ID join-table patterns (bioguide/FEC-style) governance |
| L28 | T4 entity-res | ER evaluation: precision/recall measurement at threshold for entity merges |
| L29 | T5 code-graphs | tree-sitter grammar coverage gaps for py/ts/go/swift/md frontmatter |
| L30 | T5 code-graphs | Glean (Meta) code indexing: self-hosting reality check |
| L31 | T5 code-graphs | Sourcegraph SCIP indexers offline: usable without Sourcegraph? |
| L32 | T5 code-graphs | stack-graphs name resolution: applicability to cross-file refs |
| L33 | T5 code-graphs | Joern CPG: security/flow insights value for agent context |
| L34 | T5 code-graphs | Reusing LSP/scip data we already generate into graphs |
| L35 | T5 code-graphs | Import/dependency graph extractors comparison (grimp, pydeps, madge…) |
| L36 | T6 local-llm | Ollama on this host: best extraction models under RAM floor, throughput |
| L37 | T6 local-llm | llama.cpp server: concurrency + quant profiles for batch extraction |
| L38 | T6 local-llm | vLLM CPU-only: realistic or skip |
| L39 | T6 local-llm | Structured output reliability: outlines/xgrammar/guidance |
| L40 | T6 local-llm | Small-model entity/relation extraction quality: Qwen3-4B, Phi-4-mini, Llama-3.2-3B |
| L41 | T6 local-llm | Nightly enrichment budget design under 3 GiB floor (throttling, batching) |
| L42 | T6 local-llm | Quantization tradeoffs (Q4_K_M/Q5/Q8) for extraction fidelity |
| L43 | T7 storage | SQLite unified store pattern: FTS5 + json1 + vec together — schema designs |
| L44 | T7 storage | DuckDB + VSS over parquet graph snapshots: analytics ergonomics |
| L45 | T7 storage | KV/fingerprint stores: LMDB vs sqlite vs files for freshness ledgers |
| L46 | T7 storage | Parquet-backed graph snapshots: conversion + query patterns |
| L47 | T7 storage | Neo4j Community local: value vs networkx+JSON for our query patterns |
| L48 | T7 storage | FalkorDB: resource claims verification on CPU-only host |
| L49 | T7 storage | Kùzu embedded graph DB: Cypher locally — integration effort + perf |
| L50 | T8 mcp | MCP spec current capabilities for exposing graph queries (resources/tools/prompts) |
| L51 | T8 mcp | Existing graph DB MCP servers inventory (kuzu/neo4j/memgraph/graphQL) |
| L52 | T8 mcp | Local filesystem/code-search MCP servers: quality survey |
| L53 | T8 mcp | Agent ergonomics: function/tool schemas for graph traversal that models use well |
| L54 | T8 mcp | Truncation strategies for large traversal results in tool payloads |
| L55 | T8 mcp | Multi-agent isolation/auth for one shared local MCP server |
| L56 | T8 mcp | Measured overhead: MCP roundtrip vs direct CLI invocation for agents |
| L57 | T9 interfaces | openCypher via Kùzu: ergonomics win for agents vs custom CLI |
| L58 | T9 interfaces | Local GraphQL layer over graphs: worth operating? |
| L59 | T9 interfaces | DuckDB SQL over graph tables as agent query surface |
| L60 | T9 interfaces | NL→query without LLM: template mining from real agent questions |
| L61 | T9 interfaces | Best-in-class CLI UX patterns (rg/fzf/jq style) applied to graph nav |
| L62 | T9 interfaces | Parameterized saved-queries-as-skills pattern design |
| L63 | T9 interfaces | Cross-graph linking: evaluate graphify merge-driver/merge-graphs at our scale |
| L64 | T10 eval | BEIR subset as local eval harness: which datasets fit our domain |
| L65 | T10 eval | RAGAS/TruLens metrics runnable without cloud APIs |
| L66 | T10 eval | Self-supervised golden sets from our own repos (question generation) |
| L67 | T10 eval | Recall@k tooling for comparing hybrid stacks offline |
| L68 | T10 eval | p95 latency budgets for agent-perceived search; measurement harness |
| L69 | T10 eval | A/B protocol aligned to EVAL-C22 12-task suite: operational design |
| L70 | T10 eval | LLM-judge biases and mitigations for ranking experiments |
| L71 | T11 federation | graphify merge-graphs across our corpora: test at 196k-node scale |
| L72 | T11 federation | Scatter-gather federated search aggregation patterns |
| L73 | T11 federation | Namespace/prefix strategy for multi-corpus node IDs |
| L74 | T11 federation | Shared entity-hub corpus (people/orgs) design pattern |
| L75 | T11 federation | Lightweight provenance standards (PROV-O subset) for graph edges |
| L76 | T11 federation | When NOT to merge corpora: isolation benefit evidence |
| L77 | T11 federation | Cross-corpus path-finding UX: routing heuristics for corpus selection |
| L78 | T12 freshness | Git-delta driven re-extraction: affected-file cost model |
| L79 | T12 freshness | watchdog file-watch vs cron refresh: reliability tradeoffs |
| L80 | T12 freshness | Merkle-tree change detection for staging views |
| L81 | T12 freshness | Partial graph update safety: graphify update --force semantics audit |
| L82 | T12 freshness | Content-addressed chunk caching designs |
| L83 | T12 freshness | Refresh scheduling under RAM floor: cgroup/nice throttling patterns |
| L84 | T12 freshness | Staleness signaling formats for agents (freshness headers/badges) |
| L85 | T13 context-eff | Graph-guided context packing: traversal-bounded snippet assembly |
| L86 | T13 context-eff | Token-budget-aware traversal depth selection algorithms |
| L87 | T13 context-eff | Precomputed community-summary briefs (offline) as agent primers |
| L88 | T13 context-eff | Map-reduce summarization caching layers for repo QA |
| L89 | T13 context-eff | Speculative prefetch during agent turns: patterns and risk |
| L90 | T13 context-eff | Prompt-cache-friendly stable serializations of graph results |
| L91 | T13 context-eff | Citation format minimizing tokens while preserving spans |
| L92 | T14 obsidian | Obsidian vault projection from graphs: owner-review value |
| L93 | T14 obsidian | Dataview-class engines over YAML front-matter locally |
| L94 | T14 obsidian | Backlink indexes beyond wikilinks: extending md extractor edges |
| L95 | T14 obsidian | Foam/Dendron hierarchical-note↔graph-node mappings |
| L96 | T14 obsidian | Front-matter schema governance across heterogeneous repos |
| L97 | T15 rerank | bge-reranker-base CPU latency/quality on 100-candidate pools |
| L98 | T15 rerank | LLM-as-reranker with small local models: reliability data |
| L99 | T15 rerank | Learning-to-rank from usage signals we can capture locally |
| L100 | T15 rerank | PageRank/centrality priors fused into hybrid ranking |

Phases: P1=L1-10 … P10=L91-100. Group syntheses: S-A(T1-T3) S-B(T4-T6)
S-C(T7-T10) S-D(T11-T14) S-E(T15+cross-cutting), dispatched alongside later waves.
