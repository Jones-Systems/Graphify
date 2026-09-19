# mj-graph-search — inherited MCP surface proposal

Status: **HISTORICAL PROPOSAL — unvalidated under the repaired provenance
contract and gated on DEC-9**. R6, R17, and R18 below are immutable historical
identities only; `research/RANKING.md` retains `GSR-P2-04` because downstream
implementation provenance remains unresolved. The existing middleware and
auth/isolation files are inherited implementation artifacts, not evidence that
this interface is accepted. No server registration is implied.

## Transport & posture
- **stdio first**: parent-process trust, no listener, no token on this
  transport (the OS process boundary is the trust anchor).
- Optional loopback HTTP/SSE later: launcher-minted bearer token REQUIRED;
  never bound beyond localhost.
- Proposed deterministic tool ordering: the inherited interface advertises the
  tools in the fixed order below. The names are not frozen by current research;
  they require separate interface approval.

## Tools (5, all read-only)

| # | Tool           | Purpose                                          | Required input |
|---|----------------|--------------------------------------------------|----------------|
| 1 | repo_search    | ranked hits over corpus chunks (BM25 now; hybrid RRF arrives with R3) | `query` |
| 2 | graph_neighbors| adjacency walk around a node                     | `node_id` |
| 3 | ppr_rank       | personalised PageRank from seed nodes            | `seeds` (1..8 ids) |
| 4 | fetch_nodes    | batch fetch of node records                      | `ids` (1..50 ids) |
| 5 | graph_schema   | vocabulary: node/edge kinds + counts             | — |

### Input-schema rules (flat, model-friendly)
- Enums wherever a closed set exists (`direction: out|in|both`,
  `kind: chunk|code|doc|entity`).
- Minimal `required`; every other knob has a server default.
- `additionalProperties: false` everywhere — typos surface as validation
  errors instead of silent ignores.

Example — `repo_search` inputSchema:

```json
{
  "type": "object",
  "properties": {
    "query":  {"type": "string", "minLength": 1},
    "corpus": {"type": "string", "description": "corpus_id; omit = all mounted"},
    "kind":   {"enum": ["chunk", "code", "doc", "entity"]},
    "limit":  {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
    "cursor": {"type": "string", "description": "opaque keyset from a prior page"}
  },
  "required": ["query"],
  "additionalProperties": false
}
```

## Output envelope (every tool)

```json
{
  "hits": [],
  "truncated": false,
  "next_cursor": null,
  "stats": {"nodes_considered": 0, "elapsed_ms": 0, "corpus": "*"},
  "schema_version": "1"
}
```

Truncation follows the layered caps (200 nodes / 8 KiB / ~25k-token estimate):
`truncated: true` ALWAYS carries `next_cursor` + `hint`. Oversized aggregates
spill to `~/.agent-references/graphify/spills/<sha256>.json` and return a
content-addressed ref. Search output is ordered gist-first: best evidence
first, 2-line aggregate gist last (Lost-in-the-Middle countermeasure).

## Annotations
All five tools declare `readOnlyHint: true`; repo_search, graph_neighbors,
ppr_rank and fetch_nodes additionally `idempotentHint: true`, signalling
clients they may cache and parallelise safely.

## Errors — SEP-1303 self-correction pattern
Execution failures (unknown node_id, empty corpus, over-budget query) are
reported IN-BAND as tool-result errors —
`{isError: true, content: [{type: "text", text}]}` — each text carries a
corrective hint (e.g. "node_id not found; call graph_schema for valid ids").
Never transport-level protocol errors: the model must be able to retry with
corrected arguments inside the same session.

## Auth (loopback transports only)
Tokens minted by the launcher via `TokenStore.mint()` (opaque,
token_urlsafe(32)); stored hashed with created/last_used/scopes; verified per
request by `require_token`. Store connections open SQLITE_OPEN_READONLY with
a SELECT-only sqlite authorizer — structural, not advisory.

## DEC-9 gate
Do NOT register this server with agent profiles until the owner lifts the
DEC-9 deferral. This document does not authorize an interim registration path.
