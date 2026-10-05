# Work Note — Graphify CLI Access And Agent Trials

Artifact Type: `work-note`
Artifact ID: `worknote.graphify-agent-access`
Purpose: Preserve implementation, PR disposition, query qualification, and agent-trial evidence.
Governing artifact: `spec.graphify-agent-access`
Continuity owner: Graphify rollout thread coordinator
Consumers: Graphify Integration and Agent Usage thread; host-tooling owner; repository agents
Authority effect: none

## Binding And Write Ownership

The root coordinator is sole Git/index owner of the isolated Graphify worktree
`agent-cli-catalog-20261001`, branch `work/agent-cli-catalog-20261001`, based on
canonical main `95280dcb96069a7e074c1b80d92fb80af56a71f1`. The separate V3
guidance worktree is `graphify-agent-guidance-20261001`, branch
`work/graphify-agent-guidance-20261001`, based on main
`c561b8654f3cd02842e7aa297dc87bac6057b494`. Both were clean before writes.
The original rollout worktree and primary Graphify checkout remain preserved.

Root owns this note/spec, Graphify AGENTS.md/README/skill, and the V3 pointer.
The CLI builder owns only new reader/pull scripts and their two tests. It may
not mutate Git, existing producer tooling, dependencies, or host configuration.
Query workers receive read-only graph/source scopes and task-owned result paths.

## Research And Decisions

The completed private rollout has fifty-two selected archives and three empty
repositories. Its catalog, completion receipt, and final portfolio audit are
the current graph-generation evidence. Earlier eighteen/nineteen-corpus notes
are historical. Research was required to reconcile these contracts with old
navigation and host-tooling. Three independent source lanes covered CLI access,
host synchronization, and PR #395 disposition; root retains fan-in.

The framing lane selected a bounded stdlib reader. Upstream text handlers fail
the requested structured-result/parallel-edge contract; a new MCP is unnecessary
for this CLI scope. No competing implementation currently satisfies the same
bounded contract without equivalent reader work. The repository model default
loaded from current guidance is High Intelligence; ordinary framing used
GPT-6.1 Sol/xhigh. No source/release/runtime adoption is inferred from launches.

Host-tooling has immutable source releases but its current importer binds
Codex-V3/MIT and has no generic graph-store transfer. Its existing worktree
and owner are not edited. The implementation supplies a portable create-only
selected-store copy seam and documents host integration; exact remote transport
and activation remain unperformed pending established host scope.

PR #395 is open at `9de054eec85e0d361daf96eb71d088703051bf9b`. Its Linux
Python jobs failed; package passed. Local `753f808e` has unpushed test-fixture
compatibility fixes, with no current-head CI proof. It remains valuable source
work but is not the reader dependency: fixed nineteen membership and 256 MiB
per-member / 512 MiB set limits cannot consume the new T3/Jones graphs.
Preserve its source, checks, and review records. No closing, merge, or push has
been performed. The PR remains linked to this rollout thread.

## Verification And Next Effect

The reader and create-only pull command are implemented. Their affected group
is `graphify-agent-access`: `tests/test_graph_read.py` and
`tests/test_graph_pull.py`, selected together by unittest discovery. All 21
checks passed on the candidate, covering directed and parallel relationships,
late lexical matches, provenance, confinement, corrupt data, output bounds,
copy parity, concurrent distinct destinations, and handled cancellation during
creation and copying. Both skill frontmatter validators and diff whitespace
checks passed. Root inspected the implementation; no independent code review
is claimed.

The V3 `core-policy` group passed all 698 checks using the existing Python
3.14.7 environment with exact pinned Goal-Autonomy source commit
`2db0a0972406eae2b7e4b9546956361b18b46837`. The initial system-Python run
had one dependency import error; that was an environment limitation, not a
passing check. Its 506-test result is preserved separately from the final pass.

The catalog CLI listed 52 selected graphs and three empty repositories in
11,431 bytes. Original catalog SHA-256:
`4e8dd6418299ecb6f36560faf19ec380f5085b215badd12a67f7bde99bb21c3c`.
A real pull copied Codex V3, T3 Code, and Jones Code into a new task-owned
portable store. It completed in 13.983 seconds with 3.19 GiB peak RSS. Separate
byte readback confirmed the selected archive checksums and metadata match the
original catalog. Selected-store catalog SHA-256:
`0ad87e56813aeb2447dfeb9c6900a0fb58cca40e26324a6746f8264774e650e2`.
The absent external timing utility failed before any copy effect; a stdlib
measurement wrapper supplied the actual evidence. Successful selected-store
data persists as task-owned qualification evidence outside source Git.

Fresh-context trials are serialized because only one heavy query process is
admitted at a time. Codex V3 instruction discovery and source verification
passed using two queries, about 1.47 seconds and 0.45 GiB peak RSS each. T3 Code
graph qualification was partial: three queries took 5.788–7.5 seconds and
2.09 GiB peak RSS; graph pointers verified the API/error boundary while direct
source established the full session handoff. Broad searches were truncated and
dependency-corpus records crowded some results. Both agents handled snapshot
HEAD mismatches and confirmed claims in current source. Jones Code's committed
source verification passed while graph navigation was partial: three queries
took 8.14–10.4 seconds and about 3.15 GiB peak RSS. The graph's reactor-to-service
import was confirmed at committed HEAD
`d2c9281b8112dc3b2991642c4bdb985e4b08b9bb`; direct source established the full
message handoff. Its primary working tree was nonmaterialized/dirty by another
owner, so the verifier used Git objects without changing the checkout. Two
queries truncated and its snapshot HEAD also differed. No comparative
productivity, complete relationship, or running-application claim is supported.

All three agents discovered the bound canonical instructions, read the copied
graphs through the CLI, respected coverage/freshness limitations, and verified
source pointers. The useful outcome is qualified selective navigation, with
source fallback for chains that the graph did not establish. All eight heavy
queries exited zero under 8 GiB/2-core/120-second limits. The original graph
archives were reused; none was rebuilt.

Raw evidence, measured commands, candidate file hashes, copied store, and
per-agent reports are under the private local task root
`~/.local/share/agent-work/graphify-agent-cli-20261001/evidence/`.
No remote host, private enrollment, credential, held original, runtime pointer,
public graph store, repository visibility, or sudo effect has occurred.

## Integration Handoff

M Jones confirmed that `Jones-Systems/host-tooling` is the intended VPS/test-server
distribution repository. This confirms the integration destination; it does not
by itself authorize shared host activation or broaden the existing host scope.

Graphify owns `tooling/graph_read.py`, `tooling/graph_pull.py`, and its canonical
`.agents/skills/graphify-query/SKILL.md`. V3 adds only a trigger row and consumer
skill pointing to the bound Graphify release. These are isolated source changes,
not installed global guidance or shared runtime adoption. No graph rebuild was
needed for this access work.

For host-tooling, preserve Graphify custody when adding a revision-locked source
import and launcher; the current importer cannot represent that custody without
an explicit extension. Ship reader code and canonical skill together, keep
populated stores outside source-release roots, and bind `GRAPHIFY_READER` plus
`GRAPHIFY_CATALOG` per consumer. Source parity and graph-data parity need
separate readback. The new pull seam has local portability proof; it does not
implement remote transport, scheduled synchronization, snapshot regeneration,
or shared active-pointer changes.

PR #395 recommendation is `adapt`: preserve useful source/tests and qualify
their accepted successor custody before retiring it. It remains open and linked;
this catalog CLI does not require its merge. Its unpublished fixture fixes
remain on the original rollout branch, without current published-head CI proof.

The qualified source and consumer pointer are ready for the integration owner.
Local coherent checkpoints and clean-state readback are recorded in the task's
`evidence/delivery-checkpoints.json`; publication, PR closure, and shared host
activation have not been performed. The next integration effect is a bounded
host-tooling custody/import extension and exact consumer binding, followed by
separately scoped transport and host activation. The CLI is not an automatic
source-refresh or fleet-sync service.

## Global Discovery Correction — Owner Direction

M Jones directed Graphify to own every tool and invocation instruction, with
thin discovery in global AGENTS.md and existing provider equivalents, instead
of a Codex-V3-local consumer layer. The owner requested frontier judgment;
Astra/medium independently inspected the focused ownership and global-source
boundary and recommended the direct route plus Graphify-owned local binding.
The earlier V3-pointer checkpoint and integration wording above are superseded
for consumer discovery; historical trial evidence remains unchanged.

Root remains sole Git owner of both declared worktrees. The correction updates
Graphify's canonical skill, access spec, README, and global-route template, and
withdraws only the previously authored unshipped V3 route/skill. No executable
reader/copy code changes. A host-local binding identifies the tested candidate
and approved catalog; a Codex global skill symlink points to Graphify's actual
skill. The global paragraph is outside the existing codex-agent-core managed
block, which remains byte-identical. Owner direction covers these exact local
global discovery changes; no sudo or remote activation is included.

The local binding uses the original 52-graph catalog. Candidate status is
explicit and does not assert release, merge, server sync, or automatic refresh.
Other standard provider-global instruction files were absent in the focused
inspection; none is invented. The Graphify-owned route template supports later
rendering into existing provider instruction files through their authorized
host route. Host-tooling remains the distribution owner, without tool/guidance
custody. Live distribution remains unfinished.

Affected verification: canonical skill frontmatter, route/link resolution,
binding source/catalog identity, managed-block preservation, withdrawal of the
V3 pointer, and a read-only catalog invocation from outside Graphify. The prior
21 executable CLI checks remain applicable; no new code test is needed for this
instruction-only correction. Exact checkpoint and verification outcomes are
recorded in the task-owned global-routing evidence.
