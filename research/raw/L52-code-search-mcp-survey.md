# LANE L52 — Local filesystem/code-search MCP servers survey
Date: 2026-08-25 · Environment: Debian VPS, 16 cores, no GPU, Python 3.13, offline-first, MemAvailable ≥ 3 GiB floor.
Scope: filesystem/git/ripgrep-wrapper MCP servers; which tool-design patterns produce the best agent hit-rates; what our graph MCP (graphifyy==0.9.16 + tantivy + LanceDB + PPR-over-KG) should copy.

## Findings table

|Item|Type|URL|License|Maturity|StackFit|EffGain|EffectGain|QualGain|AdoptCost|Conf|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|@modelcontextprotocol/server-filesystem v2026.7.10|tool|https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem|MIT|Official reference, stable|2|1|0|1|1|H|11 CRUD tools incl. name-substring search_files, allowed-dirs sandboxing; no content search, no ranking/shaping — baseline-class surface|
|mcp-server-git (official ref)|tool|https://github.com/modelcontextprotocol/servers/tree/main/src/git|MIT|Official reference|3|1|1|1|1|H|status/log/diff/branch/commit tools over local checkout; useful pattern: provenance edges (commit↔file) we already mine for the KG, not a search layer|
|mcollina/mcp-ripgrep|tool|https://github.com/mcollina/mcp-ripgrep|MIT (unverified this pass)|Small OSS, Node ≥18|3|1|0|1|1|M|Thin rg wrapper (search/count/list-files/list-types); raw rg ordering, no ranking → serves as the control condition in our design space|
|entireio/pgr (Rust, stateless)|tool|https://github.com/entireio/pgr|MIT|Experimental research artifact, 62★, public evals 2026-04|5|4|3|4|1|H|First-search replay N=50 real agent queries: Hit@1 26%→34% (+8 pts), MRR .318→.405 (+0.088), output chars 6,566→1,587 (4.1×); implementation prompts MRR .306→.500, Hit@1 14.3%→42.9%; E2E full60 cost −8.2%, search calls −9.5%; pre-read replay Hit@3 +10.4 pts [CI +0.8,+20.0]; definition-first ranking, tests/vendor demotion, grouped+trimmed planner-oriented output; shells out to rg, no index/daemon|
|dmtrKovalenko/fff|tool|https://github.com/dmtrKovalenko/fff|(unverified)|OSS, active|2|1|1|0|2|H (via pgr public evals)|Bigram-index+mmap+SIMD+frecency MCP: median search_code latency 14.7ms→1.7ms yet Hit@1 −8 pts vs baseline and wall-clock only −4% — tool exec was 0.4% of wall clock. Definitive negative result: raw scan speed does not buy agent hit-rate|
|kyo5uke/grix (`grix mcp`)|tool|https://github.com/kyo5uke/grix|MIT|New, CI-tested, ≥v0.3.x (Linux CI numbers at v0.3.2, README accessed 2026-08-25)|3|2|1|1|2|H|Trigram index with ripgrep-identical results (property-tested); Linux kernel tree 92,823 files: rare literal 2.31s→14ms (168×), common literal 13.2×, regex 8.7×; index 129 MiB; incremental refresh ~0.3s via size+mtime sidecar overlay, fs-events watch mode; MCP tools code_search + list_matching_files; zero writes inside repo (~/.cache/grix)|
|probelabs/probe (@probelabs/probe MCP)|tool|https://github.com/probelabs/probe|MIT (per repo; not re-verified in this pass)|Active OSS, enterprise-oriented|4|3|2|4|2|H|Tree-sitter AST parsing returns complete functions/classes (not 512-char chunks); Elasticsearch-style boolean queries (AND/OR/+req/-excl/ext:/lang:) exploiting LLM-as-query-translator; BM25/TF-IDF/hybrid SIMD ranking, optional BERT rerank; --max-tokens budget + session dedup; zero indexing, fully offline/deterministic; MCP tools search/query/extract/symbols|
|oraios/serena v1.5.3 (serena-agent)|tool+technique|https://github.com/oraios/serena|MIT|Mature, ~28.3k★|4|3|2|3|2|H|LSP-backed symbolic tools: find_symbol (global/local, name or substring), find_referencing_symbols, symbol overview, declarations/implementations; uvx launch, --project-from-cwd. Symbol-level navigation is the highest-precision retrieval primitive agents use|
|github/github-mcp-server|tool — requires-owner-approval (GitHub PAT / cloud endpoint)|https://github.com/github/github-mcp-server|MIT|Production (GitHub official)|2|1|1|2|2|H|Remote search_code etc.; pattern worth copying despite token dependency: GITHUB_TOOLSETS env progressively discloses only needed toolsets, shrinking tool-selection confusion|
|Anthropic agent-tool design canon|strategy|https://www.anthropic.com/engineering/writing-tools-for-agents (+ effective-context-engineering-for-ai-agents, code-execution-with-mcp; accessed 2026-08-25)|guidance|Authoritative vendor engineering posts|5|2|3|5|1|H|Targeted tools > generic API dumps; response_format=concise\|detailed ≈3× token cut; explicit pagination {returned,total_estimate,next_cursor,has_more} and NEVER silent truncation; Claude Code default ~25k-token response cap; truncation/error messages must steer the next action; grep/glob framed as just-in-time retrieval primitives; evaluate whole workflows (tool-selection accuracy, redundant-call rate, pagination continuation)|
|Agent Retrieval Bench (ARB)|benchmark/technique|https://arxiv.org/abs/2607.24882 (Jul 2026)|paper|Preprint w/ open repo (eyuansu62/agent-retrieval-bench)|4|1|2|4|2|M|No dominant retrieval family on gold-file localization: one embedder tops MRR, another Recall@20, RepoMap tops budgeted context yield @8K tokens; logged agent trajectories missed ALL gold files on 27–35% of samples → fuse lexical+vector+graph and evaluate ReadRecall@budget, not Hit@k alone|
|SWE-Explore + Deep-Agentic-Search studies|evidence/technique|https://arxiv.org/abs/2606.07297 ; https://arxiv.org/abs/2608.01507 (Jun/Aug 2026)|papers|Preprints|4|1|2|3|1|M|Agentic explorers beat classical retrieval esp. on line-level coverage (SWE-Explore); but read-only repo-QA flips: semantic retrieval 65.2% vs deep agentic/grep 46.2% correct at <½ cost per correct answer → task-conditioned hybrid: RAG/graph seeds first, agentic expansion second|

## Verdict (≤3 lines)
Top pick: **port pgr's ranking/output-shaping layer** — definitions-first, tests/vendor demotion, grouped trimmed path:line:symbol snippets, ≤~1.6k-char default payloads, explicit truncation + next_cursor — onto our tantivy+PPR stack, and expose **serena-style find_symbol/find_references tools mapped to the graphifyy KG** instead of an LSP. Add probe's --max-tokens/session-dedup and Anthropic's concise/detailed response profiles; validate with ARB-style ReadRecall@budget on our 18 repos. Do NOT add a generic filesystem/git MCP: both harnesses on this box already ship shell rg/grep allowlists + native grep/glob/read tools (verified ~/.codex/config.toml and opencode.jsonc contain zero FS/code-search MCPs), so fff/grix-style speed wins are also mostly moot at 18-repo scale — grix becomes relevant only if any single repo exceeds ~100k files.

## Integration sketch for our stack
```
graph-mcp tools (stateless stdio like pgr; warm tantivy/LanceDB handles kept by existing services):
  search(query, max_tokens≈4000, response_format=concise|detailed, cursor)
    -> ranked path:line:symbol snippets; rank = bge-reranker over BM25 candidates,
       boosted: definitions (KG node kind=symbol-def) > impl refs > docs; demote tests/vendor
    -> truncation message states total_estimate + next_cursor + narrowing hint (Anthropic pattern)
  find_symbol(name_pattern, kind?, lang?)      # serena semantics backed by graphifyy nodes
  references(symbol_id)                        # KG call/import edges = find_referencing_symbols
  expand(node_id, hops<=2, direction=out|in)   # PPR-over-KG neighborhood as next-action menu
  read(path, start_line, end_line)             # line-selector reads, never whole files
Eval: ARB protocol — gold = files touched in real session diffs from our 18 repos;
report DiscoveryHit@k, ReadRecall@budget(8K), tokens/task, redundant-search rate.
```

## Key quantitative evidence recap
- Search = 48.8% of all agent tool calls (98,555/202,142 across 1,983 public checkpoints; entireio dataset 2026-04-15): reads 49%, bash-search-fallback 23.5%, dedicated grep 23.5%. Any graph-MCP improvement compounds across half the loop.
- Ranking beats speed: pgr vs baseline MRR +0.088 [−0.007,+0.182] while faster-but-unranked fff scored MRR −0.012 [−0.089,+0.066]. Gains concentrate in the FIRST query (implementation prompts Hit@1 14.3%→42.9%) and decay over reformulations — front-load fusion quality.
- Output shaping ≈ free 4× context reduction (6,566→1,587 chars) with strictly better Hit@1/Hit@3 — adopt before touching models/indexes.
- Hybrid conditioning: semantic/RAG best for QA-style asks (65.2% vs 46.2%), agentic/graph expansion best for localization coverage; RepoMap-style graph summaries best per-token under an 8K cap (ARB) — exactly our PPR-over-KG niche.