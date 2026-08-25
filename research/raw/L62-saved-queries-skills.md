# L62 — T9 interfaces: saved parameterized queries as skills

(recovered from lane transcript)

<system-notice>
Background job L62 has completed. Resume your work using the result below.
<task-result id="L62" agent="scout" status="completed" duration="6m14s">
<meta lines="10" size="3.5KB" />
<output>
{
  "architecture": "Recommended architecture for saved-parameterized-query skills on the existing S-A stack:\n\n(1) STORAGE — one YAML card per query, git-versioned AND indexed into a `skills` table in the existing SQLite DB (same DB as sqlite-vec): slug, semver, status(draft|published|deprecated), description (SKILL.md-style trigger phrasing: what it does + when to use + concrete phrases), params (JSON-Schema subset: type/enum/default/required/min-max), body (parameterized Cypher using ONLY named $params — never string interpolation), examples[] (args + expected result shape), safety(read_only=true, default LIMIT), quality(owner, validated_at, p50/p95 latency, invocation count, empty-result rate).\n\n(2) DISCOVERY — reuse the gated 3-way RRF already in production: tantivy BM25 over name+description+tags, a dedicated sqlite-vec collection over embedded description+example questions, exact tag match; below score threshold the agent falls back to normal PPR/BM25 fusion. This is RAG-over-tools (Gorilla-evidenced) applied to the query library.\n\n(3) INVOCATION — bind params at driver level -> EXPLAIN dry-run cost check (ES `_render/template` analog) -> execute read-only with enforced LIMIT+timeout -> return rows + provenance {skill_id, version, latency}.\n\n(4) MCP SURFACE — expose each published skill as an MCP Prompt (user-controlled) plus one generic `invoke_graph_skill(name, args)` tool (model-controlled); use MCP completions for argument autocomplete.\n\n(5) GOVERNANCE — CI gates: parse check, declared-vs-used param equality, deny WRITE clauses, mandatory LIMIT ceiling, EXPLAIN cost budget, golden-example pass against fixture graph; lifecycle draft->reviewed->published->deprecated (Apollo audit->safelist rollout pattern); telemetry quality score (success rate, empty-rate, p95) with auto-deprecation on schema drift; close the loop by mining agent traces — ad-hoc queries that succeed repeatedly are promoted to candidate skills (Scholia curation model). Pure Python + SQLite, offline, <50 MB RAM, no GPU, no cloud keys -> no owner approval needed.",
  "files": [
    {
      "path": "research/lanes/L62-saved-parameterized-queries-as-skills.md",
      "description": "Full findings table + verdict (NOT written to disk: lane has no write-capable tool and no target path was provided in the assignment — full markdown delivered inline in the return message under PERSIST-NEEDED)."
    }
  ],
  "summary": "Lane L62 (T9 interfaces): designed the saved-parameterized-queries-as-skills pattern for curated graph queries — skill cards (name + typed params + trigger-rich description + parameterized Cypher body) stored in git/SQLite, discovered semantically via the existing gated BM25+vec fusion (Gorilla/ToolLLM evidence that retrieval-over-tool-descriptions improves selection and cuts hallucination), invoked through an MCP Prompts + generic-invoke-tool dual surface with driver-level param binding, EXPLAIN dry-runs (ES search-template `_render` analog), read-only sessions and enforced LIMITs. Governance modeled on Apollo persisted-query safelisting (allow→audit→safelist→IDs-only rollout), Prometheus recording-rule naming/lint discipline (promtool analog in CI), Grafana variable typing lessons, and Scholia's curated-template corpus as the closest KG precedent; GrailQA grounds why templates remain the KGQA backbone; telemetry closes the loop by promoting successful ad-hoc agent queries into new governed skills. 11 items surveyed, all offline/no-GPU compatible; zero items require owner approval."
}
</output>
</task-result>

L62 is now idle — message it via `hub` to follow up; transcript at history://L62
</system-notice>