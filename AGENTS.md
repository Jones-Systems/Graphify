# Graphify agent guidance

Graphify is the thin source layer for graph tooling, corpus policies,
operational documentation, and bounded research claims. Keep corpora,
environments, staged source copies, graphs, databases, model artifacts, and
runtime evidence outside Git. The default runtime root is
`~/.agent-references/graphify`; its presence does not prove installation,
validation, or activation.

Use the declared task checkout, branch, and write scope with one Git owner.
Preserve unrelated changes and keep runtime artifacts out of Git staging.

## Load the relevant guidance

Graphify owns portable query/copy tools and their canonical consumer skill.
Global agent instructions provide discovery from any repository; Codex V3 is
an ordinary consumer. For cross-file graph navigation, read
[the query skill](.agents/skills/graphify-query/SKILL.md), then confirm pointers
in current source. The host-local binding and thin global route are defined by
[the access contract](docs/AGENT-ACCESS.md#global-discovery).

- For installation, policy deployment, builds, promotion, or toggles, read
  [the runbook](docs/RUNBOOK.md).
- For research claims, read [the ranking contract](research/RANKING.md) and
  [the positive-claim registry](research/positive-claims.json). For provenance
  custody, use the [accepted contract](docs/PROVENANCE-CUSTODY.md#accepted-provenance-contract);
  its historical work instructions are not the current task.
- For batch deployment, read [the deployment examples](deploy/README.md).
  They remain inherited and unvalidated; consult the runbook for the actual
  installer and build memory guards.
- For MCP work, read [the surface proposal](docs/MCP-SURFACE.md), including
  its DEC-9 gate. For SCIP work, read [the pilot protocol](docs/SCIP-PILOT.md),
  which remains unexecutable without its complete independent operator lock.

## Preserve the boundaries

Repository instructions and script availability do not authorize corpus
access, runtime mutation, installation, promotion, deployment, or assistant
integration. Bind each operation to the owner's authorized target and scope.
Assistant call-path wiring and enabling integration require explicit owner
approval; existing approval applies only within its scope.

Preserve the `graphifyy==0.9.16` artifact pin and hash checks. Never invoke
upstream platform installers (`graphify install --platform ...`). The current
installer does not pre-lock every bootstrap and dependency artifact.

The installer checks memory at entry; builds sample it at stage boundaries:
stop below 3072 MiB available and warn below 4096 MiB. These checks do not
continuously preserve the memory floor.

Review corpus scope and deny-first policy before building, then review the
emitted inventory as acceptance evidence. Global denies do not make the
remaining inventory default-deny. Tracked-only selection can fall back when
Git enumeration fails, and bounded canary scanning cannot establish absence
of secrets.

Retain run snapshots and evidence. Their preservation is an operating
requirement; the scripts do not enforce immutability. Promotion requires
actual independent verification bound to the exact run, with attributable
evidence. Toggle verification requires an external fresh-session check.
Neither requirement is satisfied merely by recording a string or state.

Only registered claims have the eligibility described by the research
contract. Validated research does not establish currentness, reproduction,
implementation acceptance, or runtime readiness. `GSR-P2-04` remains open
and blocking for provenance-clearance claims about downstream implementations
that relied on the historical R1–R20 synthesis. Preserve historical
compatibility identities; existing helpers do not resolve that limitation.

## Verify the changed scope

For documentation-only work, check the exact diff, changed paths, whitespace,
relative links, and statements against the relevant source. Report that
bounded result without claiming runtime validation.

The default provenance checker reads excluded material and tracked content.
Do not run it under a source-only scope that excludes those reads. Changes to
the provenance contract require its affected checks and an authorized read
scope. Historical verification ledgers do not authorize broader access.
