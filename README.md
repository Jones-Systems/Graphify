# Graphify

Capability repo for Graphify knowledge-graph operations on this VPS — the
**thin layer** in the Universal-Agents pattern: everything that drives,
validates, and governs graph builds; none of the heavy artifacts themselves.

## Layout

| Path | Contents |
| --- | --- |
| `tooling/` | install / toggle / preflight / validate / build / promote scripts + corpus manifest (migrated from Codex-V3 @ `fc1172d`) |
| `policies/<corpus>/ignore.rules` | versioned per-corpus deny-first policies (the authoritative copies; runtime reads from `~/.agent-references/graphify/<corpus>/policy/`) |
| `docs/RUNBOOK.md` | operational procedures: install, build waves, promotion gate, toggle cycle |
| `tooling/graph_read.py`, `tooling/graph_pull.py` | stateless snapshot queries and create-only selected-store copies |
| `.agents/skills/graphify-query/SKILL.md` | canonical consumer instructions for portable snapshot access |
| `research/` | research program: raw lane findings, group syntheses, master ranking, implementation plans |

## Portable agent access

The catalog CLI reads selected checksum-verified graph archives without a
provider session or MCP server. Global agent instructions route directly to
Graphify; Codex V3 is an ordinary consumer. The Graphify-owned host binding makes
the reader and approved catalog discoverable from any repository; use [the graph query skill](.agents/skills/graphify-query/SKILL.md)
for commands and interpretation. [The access contract](docs/AGENT-ACCESS.md)
defines global discovery, bounded responses, freshness, portable copy behavior,
and host custody.
Populated stores remain outside source Git. Existing promoted-corpus runtime
paths below are a separate interface and do not locate portable catalogs.

## Runtime layout (outside Git)

```
~/.agent-references/graphify/
  tool/env/                 pinned venv (graphifyy==0.9.16)
  <corpus>/policy/          deployed policy copies
  <corpus>/runs/<id>/       immutable runs: preflight, graph.json, validation, freshness
  <corpus>/current -> ...   promoted pointer (post independent verification)
  toggled.state             active-verified | temporarily-inactive-verified | ...
  skills[/skills-disabled]/graphify-corpus-navigation   nav skill (toggleable)
```

## Hard rules

- Pin `graphifyy==0.9.16`; verify SHA-256 before install; fail closed.
- Never invoke upstream platform installers (`graphify install --platform …`).
- MemAvailable floor **3072 MiB** (warn 4096) measured around every build step.
- Deny-first exclusions; secret canaries stop builds.
- Promotion only after builder evidence **plus** independent verification.
- No assistant call-path wiring without explicit owner approval (toggle exists for exactly this).
