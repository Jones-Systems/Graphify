# L54 — Truncation strategies for large traversal results in tool payloads

## Evidence status

Recorded date: 2026-08-25. This file retains the public-source report and
omits its non-research wrapper. No later source currentness, deployment
environment, or adopted output limit is claimed.

## Findings

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|MCP opaque-cursor pagination protocol|strategy (spec)|https://modelcontextprotocol.io/specification/2025-03-26/server/utilities/pagination|MIT (spec repo)|Stable (2025-03-26 -> 2025-11-25; draft adds cacheable pages; 2026-07-28 RC stresses deterministic ordering)|5|4|4|3|1|H|Cursors are opaque server-defined strings; server controls page size; missing nextCursor = end; invalid cursor -> -32602. Verified 2026-08-25.|
|Keyset/cursor continuation for traversal results (stable ordering + snapshot semantics)|technique|https://modelcontextprotocol.io/specification/draft/server/utilities/caching|MIT|Spec-draft guidance; production pattern in GitHub MCP|5|4|5|4|2|H|Keep ordering stable during paging, encode validated state, reject expired cursors; mutable collections need explicit snapshot semantics.|
|GitHub MCP page/perPage + GraphQL after-cursor tools|tool (reference impl)|https://github.com/github/github-mcp-server|MIT|Mature (official)|4|3|3|3|1|H|perPage cap 100; GraphQL tools use after=pageInfo.nextCursor; instructions require identical filters/page size across pages (pkg/github/toolset_instructions.go).|
|Truncation envelope contract: {truncated, returnedChars/rows, totalEstimate, nextCursor, continuation hint}|technique|https://www.anthropic.com/engineering/writing-tools-for-agents|n/a (guidance)|Production guidance (published 2025-09-11)|5|4|5|4|1|H|Use pagination, range selection, filtering, or truncation; a truncated response should explain how the client can continue. Size limits require workload evaluation.|
|Claude Code output budgets (MAX_MCP_OUTPUT_TOKENS default 25000, warn 10k, _meta anthropic/maxResultSizeChars <=500k chars)|tool (client-side reference)|https://code.claude.com/docs/en/mcp|n/a|Shipped|3|2|3|2|0|H|Concrete ceilings real clients enforce; per-tool char annotation lets servers declare expected size; informs the proposed default node/char caps.|
|FastMCP ResponseLimitingMiddleware (+ custom token middleware)|tool|https://fastmcp.mintlify.app/servers/middleware|Apache-2.0|Shipped (v2 middleware API)|5|5|4|2|1|H|Byte limiter (default 1e6 bytes) truncates with suffix; on_call_tool is the sanctioned transform point; caveat: truncating serialized structured_content breaks output_schema — truncate before building ToolResult.|
|mcp-neo4j-cypher NEO4J_RESPONSE_TOKEN_LIMIT (tiktoken) + NEO4J_READ_TIMEOUT|tool (pattern donor)|https://github.com/neo4j-contrib/mcp-neo4j/blob/main/servers/mcp-neo4j-cypher/README.md|Apache-2.0|Mature (>=0.6.0; CVE-2026-35402 fixed in 0.6.0 — pin >=0.6.0)|4|3|4|2|2|H|Three-layer split: DB LIMIT (rows) != token limit (payload) != timeout (execution); response truncated via tiktoken. Canary fork adds NEO4J_CYPHER_MAX_ROWS/MAX_BYTES/TIMEOUT.|
|Reference envelope: inline small data, retain large payload behind a bounded reference, return {id,media_type,bytes,sha256} + stats|technique|https://www.anthropic.com/engineering/code-execution-with-mcp|n/a (guidance)|Production (Files-API file_id pattern)|4|3|5|4|3|H|The cited worked example reduced 150,000 tokens to 2,000 by keeping intermediates out of model context; retention, authorization, and deletion semantics still require a separate design.|
|Map-reduce summarization-before-return (community reports; dynamic community selection)|strategy|https://microsoft.github.io/graphrag/query/global_search/ ; https://www.microsoft.com/en-us/research/blog/graphrag-improving-global-search-via-dynamic-community-selection/|MIT (repo)|Mature (dynamic selection 2024-11-15)|3|2|4|4|4|M|Community-summary global search; the cited report claims large token-cost reductions at maintained win rates. Query-time model use, reproducibility, and deployment fit require separate evaluation.|
|Goal-conditioned pruning of observations before return (FocusAgent)|technique/paper|https://arxiv.org/abs/2510.03204|paper (arXiv)|WebArena/WorkArena evals; TMLR-listed|4|3|4|5|2|M|Small-LLM retriever keeps goal-relevant lines: >50% size reduction while matching strong baselines + injection robustness. The proposed analogue: score traversed nodes with a validated reranker, keep top-K.|
|Memory pointers instead of full-output injection (Context Window Overflow)|technique/paper|https://arxiv.org/abs/2511.22729|paper (arXiv)|Preprint, single-domain eval|3|2|4|4|3|M|Pointers to stored results replace truncation/summarization; ~7x fewer tokens in their materials-science experiment.|
|Prompt compression (LLMLingua family; LongLLMLingua reordering)|technique|https://github.com/microsoft/LLMLingua|MIT|Published, active|2|2|3|3|4|H|20x compression minimal loss (LLMLingua); 17.1% improvement at 4x via question-aware compression/reordering (LongLLMLingua). Needs small-LM perplexity scoring per payload on CPU — latency/RAM cost; defer.|
|Position-aware ordering + bookend summary of returned items|technique|https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00638/119630|paper (TACL 2023)|Published, widely replicated|5|2|4|4|1|H|U-shaped use of long inputs (Lost in the Middle): put reranked top evidence first/last, never bury hits mid-payload; repeat critical facts after bulk content. Free with existing reranker ordering.|
|Reducer evaluation discipline: log raw_tool_output vs truncated_observation; measure retained-evidence coverage|technique/paper|https://arxiv.org/abs/2510.15955 (EACL 2026); https://arxiv.org/abs/2605.29397 (Minimal Failure Set)|paper|Peer-reviewed (EACL 2026) + preprint framework|4|2|3|4|2|M|GPT-4o 77% on structured tool-output QA; accuracy degrades with length, shifts 3-50pp by processing strategy (Kate et al.). MFS coverage correlates with end-task success at >100x lower eval cost — cheap regression gate for cap changes.|

## Supporting quality evidence
- Context Rot (Chroma, 2025-07-14, https://www.trychroma.com/research/context-rot): 18 models degrade non-uniformly as input grows even on trivial tasks; focused ~300-token inputs beat ~113k-token inputs on a LongMemEval subset. Payload minimization is an accuracy lever, not just cost.
- Lost in the Middle (TACL 2023): truncation that discards the middle is safest; head-only cuts risk dropping end-relevant facts; tail-only risks early facts. Bookend summaries counteract.
- How Good Are LLMs at Processing Tool Outputs? (arXiv:2510.15955, EACL 2026): length is a confounder; strategy choice moves accuracy 3-50pp — prefer relevance-preserving reduction over mechanical cuts.
- FocusAgent (arXiv:2510.03204) + GraphRAG dynamic community selection (MSR, 2024-11-15): semantic/gist reduction preserves success at half-or-tenth tokens; mechanical truncation does not.

## Verdict
The recorded candidate is a layered output contract: stable cursor pagination,
explicit truncation metadata, independent row/token/byte/time limits, and
relevance-preserving ordering. The report's numeric caps are examples, not
accepted defaults. Any retained-reference mechanism needs separate
authorization, retention, and deletion rules, and every cap needs an
evidence-retention regression test.
