# LANE L53 — Tool-schema design for search and traversal
Date: 2026-08-25. Scope: recorded naming conventions, parameter shapes, and
result-size contracts from function-calling literature and public MCP servers.
No local service, implementation stack, or deployment state is established.

## Candidate table

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|Anthropic "Writing effective tools for agents"|strategy|https://www.anthropic.com/engineering/writing-tools-for-agents|n/a (blog)|pub 2025-09-11|5|4|4|4|1|H|Fewer higher-level tools beat many CRUD wrappers; `response_format` enum concise/detailed; pagination+cursor+truncation+actionable errors; Claude Code default 25k-token tool-response cap; interpretable names over UUIDs|
|OpenAI function-calling guide|strategy|https://developers.openai.com/api/docs/guides/function-calling|n/a (docs)|accessed 2026-08-25 (gpt-5.x era)|5|3|4|4|1|H|"Aim for fewer than 20 functions at start of a turn" (soft); `strict:true` always (additionalProperties:false, all-required fields, null-typed optionals); "use enums… make invalid states unrepresentable"; schemas bill as input tokens; tool_search defers rare tools (gpt-5.4+)|
|MCP spec rev 2025-06-18 Tools|standard|https://modelcontextprotocol.io/specification/2025-06-18/server/tools|open spec|stable revision|5|2|3|5|1|H|`outputSchema`⇔`structuredContent` MUST-conform + serialized-text fallback SHOULD; ToolAnnotations (readOnlyHint, destructiveHint dflt=true, idempotentHint, openWorldHint dflt=true); content audience/priority annotations|
|BFCL v4|benchmark|https://gorilla.cs.berkeley.edu/leaderboard.html|open|live leaderboard read 2026-08-25 (EECS tech report 2025)|3|3|3|4|2|H|Simple→multiple −1–2pts, →parallel_multiple −3.5–7pts (Opus 4.5 FC 95.5→88.5); AST eval treats nested args as brittle; removing multi-type training collapses irrelevance detection to 6.99% → few overlapping tools, few simultaneous calls|
|RoTBench|paper/benchmark|https://arxiv.org/abs/2401.08326|open|EMNLP 2024 (arXiv Jan 2024)|4|2|3|3|1|M|Identifier corruption: GPT-4 tool-selection ≈80% clean → 58.10% union-noise; tool-name noise hurts more than param-name noise; errors propagate downstream → freeze stable names|
|On the Robustness of Agentic Function Calling|paper|https://arxiv.org/abs/2504.00914|open|TrustNLP@NAACL 2025 (Apr 2025)|4|1|2|3|0|M|Paraphrased requests AND added distractor tools both break call consistency → avoid semantically overlapping tool surfaces|
|ToolDocs (Hsieh et al.)|paper|https://arxiv.org/abs/2308.00675|open|EMNLP 2023|5|4|4|4|1|H|Documentation quality alone lifts zero-shot CLI tool-use F1 0.13→0.45 (~3.5×), TabMWP +8.6pts — largest single lever; beats few-shot without docs|
|HammerBench|paper|https://arxiv.org/abs/2412.16516|open|Dec 2024 rev Feb 2025|3|1|2|2|0|M|Parameter-name/value errors are a dominant multi-turn failure mode → constrain with enums, minimal required sets, documented defaults|
|GitHub MCP Server consolidation|repo precedent|github.blog changelogs 2025-10-14 / 2025-10-29 / 2025-12-10 (github/github-mcp-server)|MIT|production, active 2025|5|4|4|3|2|H|Six get_pull_request_* tools merged into `pull_request_read(method enum)`; 5 default toolsets; X-MCP-Tools selective loading; vendor-reported 60–90% context-window reduction|
|mcp-neo4j-cypher 0.6.0|repo precedent|https://github.com/neo4j-contrib/mcp-neo4j (PyPI 0.6.0, rel 2026-04-10)|Apache-2.0|production|4|2|3|3|1|H|Minimal 3-tool surface: get_neo4j_schema → read_neo4j_cypher / write_neo4j_cypher; schema-disclosure-first; [INFERENCE] raw-Cypher passthrough shifts query-authoring burden onto the model vs purpose-built verbs|
|Brave/Tavily search MCPs|repo precedent|github.com/tavily-ai/tavily-mcp (src/index.ts); npm @modelcontextprotocol/server-brave-search|MIT|production 2025|5|3|4|3|1|H|Tight caps declared in-schema: Tavily max_results dflt 5 range 5–20; Brave count≤20 offset≤9 → defaults small, ranges enforced by validation|
|Filesystem reference server|repo precedent|github.com/modelcontextprotocol/servers src/filesystem|MIT|maintained; read_file deprecated→read_text_file|4|2|3|3|1|H|verb_noun snake_case throughout; batch variant read_multiple_files(paths[]) tolerates per-item failure; search_files glob-only; readOnlyHint annotations; clean deprecation path|

## What models handle best (synthesis)

**Naming.** All audited production servers use snake_case verb_noun (`read_text_file`, `create_issue`, `get_neo4j_schema`). ≤32 chars, one obvious verb per intent, unique first tokens across the surface (five `list_*` tools are indistinguishable to a router). Freeze names once published — identifier noise is the worst-degrading perturbation measured (RoTBench: GPT-4 tool selection 80%→58%). Prefer human-interpretable values (paths, symbols, titles) over bare UUIDs; expose technical IDs only when a follow-up call needs them.

**Parameter shapes.** Flat top-level params dominate every good real schema; deep nesting has no supporting evidence (BFCL ablation finds nested cases too sparse to matter, yet AST-matched nested structures are measurably more brittle). Conventions: enums over free strings on closed domains; no paired booleans ("make invalid states unrepresentable"); plural-named arrays with maxItems caps (`ids≤20`, `seeds≤2`); minimal `required` (query/node_id/ids/seeds) with conservative server-side defaults stated in descriptions; `additionalProperties:false`; optionals typed `T|null`. Consolidate workflows behind one discriminating enum param (GitHub's `method`; Anthropic's schedule_event) instead of per-engine wrappers.

**Result-size contracts.** Defaults are small everywhere: 5–20 items (Brave/Tavily), 25k-token hard ceiling (Claude Code), target ≤8KiB (~2k tokens) for concise pages. Cursor-based pagination, not raw offsets (Brave caps offsets at 9 because they scale badly). Truncation must be explicit (`truncated:true` + opaque `next_cursor`) and truncation/error text must teach recovery by naming the narrowing parameters. Verbosity controlled via `response_format: concise|detailed` enum. Two-stage progressive disclosure (cheap id+snippet page → targeted full-payload fetch) is the shared pattern of Context7 (resolve→query), filesystem (search→read), GitHub (list→get).

## Generic candidate schema

The public evidence supports evaluating a small read-only surface. The
following five-tool sketch is a generic design candidate, not a binding
interface or description of an existing service:

1. `repo_search(query*, mode=hybrid[hybrid|lexical|vector], scope?[all|code|docs|null], path_glob?, lang?, limit 1..30=10, response_format=concise[concise|detailed], cursor?)` — single fused entry point; engine composition stays server-side (Anthropic consolidation rule).
2. `graph_neighbors(node_id*, direction=in|out|both default both, edge_types[]?, depth 1..3=1, limit 1..50=25)`.
3. `ppr_rank(seeds*[]maxItems:2, top_k 1..50=20, alpha 0.05..0.5=0.15)` — the schema encodes a bounded seed set via maxItems; the limit requires evaluation.
4. `fetch_nodes(ids*[]maxItems:20, fields=node[node|content|edges]=node)` — stage-2 progressive disclosure; per-id failures reported individually (filesystem batch precedent).
5. `graph_schema()` — returns node/edge type inventory once (neo4j get_neo4j_schema precedent; cheap planner context).

All tools: `annotations:{readOnlyHint:true, idempotentHint:true, openWorldHint:false}` (closed corpus); MCP `outputSchema` declared; both structuredContent and serialized-text fallback returned.

Unified result envelope (outputSchema):
```jsonc
{"schema_version":"v1",
 "hits":[{"id":"node:a1b2","score":0.83,"path":"src/x.py","symbol":"foo","loc":{"start":10,"end":42},"snippet":"≤280 chars in concise mode"}],
 "truncated":false,"next_cursor":null,
 "stats":{"engines":["lexical","vector","fusion"],"elapsed_ms":120}}
```
Rules: deterministic order (score desc, id asc tiebreak); stable id format cross-tool; server-enforced caps (default 10/max 30 hits; ~8KiB concise page; absolute ceiling 25k tokens); never silent elision — truncated:true + next_cursor always accompany cuts; errors set isError:true with recovery instructions naming valid parameters.

## Recorded conclusion

The public comparison supports evaluating a consolidated, read-only tool
surface with flat enum-constrained parameters, minimal required sets, an
explicit paginated result envelope, read-only and idempotent annotations, and
a two-stage identifier-to-detail flow. The five-tool sketch above remains a
candidate: names, caps, pagination semantics, compatibility with the selected
protocol revision, and evaluation criteria must be independently specified
and tested before adoption.
