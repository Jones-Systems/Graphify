---
name: graphify-corpus-navigation
description: Query local Graphify knowledge graphs for navigational context across project repos. Use when relational questions span many files (which spec governs this code, what links to this record, multi-hop paths); NOT for exact facts — always confirm against canonical sources.
---

# Graphify Corpus Navigation

## What this is

Local, prebuilt knowledge graphs over each project repo's tracked files.
Graph output is **routing evidence only** (EVAL-C22): it tells you where to
look, never what is true. Every exact claim must be confirmed by opening the
canonical source file.

## Registry

Each corpus lives at `$HOME/.agent-references/graphify/<corpus>/current/graph.json`
where `<corpus>` matches `tools/graphify/corpora.manifest` in the Codex-V3
worktree (codex-system, apm, grok-bot, caam, codex-system-v2, codex-v3,
universal-agents, ssh-bridge, alpha, alpha-triage, business-lessons,
alpha-recovery-log, goal-autonomy, github-actions, social-growth-engine,
app-intel, growth-intel, movement-engine).

If `current` is absent or its target lacks a PASS `validation.json`, say so and
fall back to ordinary read-only inspection. Never treat a missing/stale graph
as authoritative silence.

## Queries (offline, read-only)

```bash
ENV="$HOME/.agent-references/graphify/tool/env"
GRAPH="$HOME/.agent-references/graphify/<corpus>/current/graph.json"

"$ENV/bin/python" - <<PY
import json
g = json.load(open("$GRAPH"))
# nodes: id/label/kind/source_file ; links: source/target/kind
print(len(g["nodes"]), "nodes", len(g.get("links", [])), "links")
PY

"$ENV/bin/graphify"   query "<pattern>"  --graph "$GRAPH"
"$ENV/bin/graphify"   path   "<A>" "<B>" --graph "$GRAPH"
"$ENV/bin/graphify"   explain "<id>"      --graph "$GRAPH"
```

Always pass explicit absolute `--graph`; never rely on cwd-relative defaults;
never pass `--out`; never run extract/update from ordinary navigation.

## Routing rules

1. Pick exactly ONE corpus per question by repo subject; do not merge answers
   across corpora silently (PRD-C2 isolation).
2. Check freshness: compare question time against the run dir's
   `freshness.json`. `stale`/`unknown` ⇒ disclose and fall back to source.
3. Graph hits give node ids + `source_file` pointers — open those files before
   making any source-sensitive claim (ENG-C11/C15).
4. Navigation NEVER triggers refresh, network, credentials, extraction, or any
   mutation. If data seems outdated, report it; rebuilding is an explicit
   operator action via `tools/graphify/build-graph.sh`.
5. This skill is toggleable: if disabled, `current` will be absent — route to
   normal repository search without comment beyond noting unavailability.
