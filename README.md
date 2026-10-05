# Graphify

Graphify contains source tooling, corpus policies, and research guidance for
maintainers working on knowledge-graph builds and agent navigation. It is the
thin repository layer: corpus contents, environments, staged source copies,
graphs, databases, model artifacts, and runtime evidence belong outside Git.

The source includes policy preflight, staged structural extraction, graph
validation, sequential build orchestration, promotion, and integration-toggle
scripts. Their presence does not establish a working installation, fresh
graphs, or active assistant integration.

## Start with the source

Coding agents start with [AGENTS.md](AGENTS.md). Maintainers can use
[the runbook](docs/RUNBOOK.md) to understand command interfaces, effects,
evidence requirements, and known limitations.

For a local reading route, use an existing checkout with Git, a shell, and
`sed`. Run these commands from the repository root:

```sh
git rev-parse --show-toplevel
git ls-files -- README.md docs/RUNBOOK.md tooling/install.sh tooling/build-graph.sh
sed -n '1,32p' AGENTS.md
sed -n '1,40p' docs/RUNBOOK.md
```

The output identifies the checkout, lists the selected tracked source paths,
and prints the opening agent guidance and runbook text. These commands inspect
source; they do not install dependencies, read corpora, or start a build.

## Find the relevant interface

| Task | Source or guide |
| --- | --- |
| Install, build, refresh, promote, or toggle integration | [Operational runbook](docs/RUNBOOK.md), with command syntax and acceptance requirements |
| Inspect orchestration and extraction source | [Tooling](tooling/) |
| Query or copy selected portable snapshots | [Canonical query skill](.agents/skills/graphify-query/SKILL.md), backed by `tooling/graph_read.py` and `tooling/graph_pull.py` |
| Review versioned corpus exclusions | [Corpus policies](policies/) |
| Understand research eligibility | [Research ranking and provenance](research/RANKING.md) and [positive-claim registry](research/positive-claims.json) |
| Inspect batch scheduling examples | [Deployment documentation](deploy/README.md), inherited and unvalidated |
| Understand the proposed agent query interface | [MCP surface proposal](docs/MCP-SURFACE.md), with registration gated by DEC-9 |
| Understand the symbol-edge experiment | [SCIP pilot protocol](docs/SCIP-PILOT.md), unexecutable until its complete operator-supplied run lock is independently verified |

## Portable agent access

The catalog CLI reads selected checksum-verified graph archives without a
provider session or MCP server. Global agent instructions route directly to
Graphify; Codex V3 is an ordinary consumer. Graphify owns the host binding,
[canonical query skill](.agents/skills/graphify-query/SKILL.md), and the
[access contract](docs/AGENT-ACCESS.md), including commands, freshness, and
create-only snapshot copies. Host-tooling distributes pinned source and
selected data. Populated stores remain outside source Git; the legacy promoted
corpus interface does not locate portable catalogs.

## Operational limits

The installer pins and hash-checks the `graphifyy==0.9.16` wheel, but its
bootstrap and dependency closure are not completely locked in advance.
The installer and build runner check available memory at entry or stage
boundaries; these samples do not continuously preserve a memory floor.

Preflight applies global denies and corpus policy, with remaining files
defaulting to inclusion. Tracked-only selection can fall back when Git
enumeration fails, and bounded canary scans do not prove absence of secrets.
Review the authorized source scope and emitted inventory before accepting
a run.

Run directories are intended to be retained snapshots; the scripts do not
enforce immutability. Promotion requires independent verification of the
exact run, including freshness, even though the script only records supplied
attribution and checks limited conditions. Toggle verification likewise
requires an actual external fresh-session check.

The runbook owns these procedures and their detailed limits. Installation,
corpus access, promotion, and deployment require an authorized operation;
enabling assistant integration or changing its call-path wiring requires
explicit owner approval.

## Research status

Only the exact claims admitted by the positive-claim registry have the
eligibility described in the research contract. “Validated” does not establish
source currentness, independent reproduction, implementation acceptance, or
runtime readiness.

`GSR-P2-04` remains open and blocking for provenance-clearance claims about
downstream implementations that relied on the historical R1–R20 synthesis.
The [accepted provenance contract](docs/PROVENANCE-CUSTODY.md#accepted-provenance-contract)
preserves that limitation. Historical custody instructions and compatibility
identities do not authorize resuming prior work or activating integrations.
