# Design Brief — Graphify Agent Usage Profile

Artifact Type: `design-brief`
Artifact ID: `brief.graphify-agent-usage`
Purpose: Route agent requests using observed navigation results and costs.
Governing artifact: `spec.graphify-agent-access`
Brief owner: Graphify capability maintainer
Consumers: Repository agents, coordinators, workflow authors
Authority effect: none

## Recommended requests

Graphify is a selective navigation aid for unfamiliar ownership, dependencies,
callers, and governing documents. It finds candidate source locations; current
source establishes facts. This profile supplements the [canonical query
skill](../.agents/skills/graphify-query/SKILL.md), which owns invocation semantics.

| Request or role | Use |
| --- | --- |
| Repository investigator or researcher | Find unfamiliar owners and related governing documents across files. |
| Backend builder or debugger | Locate execution owners, error mappings, and candidate tests; verify the complete flow in source. |
| Frontend builder | Locate component, state, and contract boundaries. Use source and UI evidence for behavior and visual work. |
| Cross-repository investigator or reviewer | Find candidate interfaces and consumers, with repository and dependency revisions explicitly bound. |
| Coordinator retrieving previous decisions | Use native thread/history tools first; query Graphify after identifying a repository question. |
| Operator checking live services or providers | Use authorized runtime observations; graphs cannot establish what is running now. |
| Known path, exact local edit, or identified symbol | Prefer direct source reading or source search. A graph query is optional. |

Start with one narrow query using a distinctive symbol, module, or document
name. Permit one focused follow-up when it can resolve a useful lead, such as
node neighbors. For a two-repository comparison, apply that budget separately
to each repository. Switch to source search for noisy, empty, materially stale,
truncated, or expensive results. These are practical defaults, not measured
optimal limits. Apply the host's current admission policy before heavy work.

Confirm paths, symbols, relationships, and line references against the intended
source revision. An import is not proof of a runtime call; containment is not
an execution trace. Empty or limited results do not prove absence. A snapshot
predating a feature cannot establish that feature's ownership. Cross-repository
compatibility requires the actual pinned producer revision.

## Qualification cases

The October 2026 assessment covered 16 repository requests with independent
source-first and graph-first retrieval lanes. Labels describe graph contribution,
not whether source fallback eventually answered the request.

| Case | Request | Graph contribution |
| --- | --- | --- |
| UI-A1 | Composer submission and error restoration | Unhelpful initial query: vendored matches crowded the result. |
| UI-A2 | Provider selection, request, defaults | Partial: resolver/caller pointers; source established defaults and validation. |
| UI-A3 | Display-only message status impact | Partial: message type pointer; source established rendering/state boundaries. |
| UI-A4 | Known skill rule for empty results | Correct skip: exact canonical-file read. |
| API-B1 | Submitted turn to provider execution | Partial: runtime/reactor owners; source established the full chain. |
| API-B2 | Assistant event to stored message | Partial: ingestion/persistence owners; neighborhood did not establish the chain. |
| API-B3 | Provider failures and existing tests | Useful navigation: precise error-mapping symbol, confirmed in source. |
| API-B4 | Provider used by a running server now | Correct skip: live metadata is required. |
| GOV-C1 | Affected-check policy to runner | Partial: governing links; source established manifest and runner wiring. |
| GOV-C2 | Whether a bug fix triggers implementation planning | Useful navigation: governing trigger documents, confirmed in source. |
| GOV-C3 | New reader/global/distribution ownership | Unhelpful snapshot: graph predated the access implementation. |
| GOV-C4 | Known continuity note and earlier decisions | Correct skip: exact work-note read; current GitHub state has separate authority. |
| XREP-D1 | Compare two provider handoff contracts | Partial: follow-up found contracts; source established behavioral differences. |
| XREP-D2 | Goal dependency consumers and interface impact | Partial, materially stale: supplied producer checkout differed from the consumer's pinned dependency. |
| XREP-D3 | Graphify to host-tooling distribution | Unhelpful snapshot: current source supplied the contract. |
| XREP-D4 | Dashboard owners in an empty repository | Correct skip: catalog reported empty; no modules invented. |

Totals: two useful, seven partial, three unhelpful, four appropriate skips.
An additional native-history control retrieved an earlier decision through the
thread reader; Graphify does not index that conversation history.

All 22 executed graph invocations exited zero without timeout or stderr. A
separate attempt was refused by CPU admission before execution. An identical
raw result independently requested by two cases was reused without a duplicate
execution. The CLI suite passed 21 tests on reader revision
`7f0a46b4b6c2663ad515c5f187dd5fbb45c3a6d4` with Python 3.13.5.

| Queried repository | Invocations | Elapsed range | Maximum RSS |
| --- | ---: | ---: | ---: |
| t3code | 9 | 6.560–8.025 s | 2.094 GiB |
| Jones-Code | 6 | 9.586–14.728 s | 3.147 GiB |
| Codex-V3 | 4 | 1.479–2.515 s | 0.446 GiB |
| Graphify | 2 | 0.118 s | 0.026 GiB |
| Goal-Autonomy | 1 | 0.120 s | 0.030 GiB |

These process measurements reinforce selective use and serial admission. They
are not production capacity or latency guarantees.

## Evidence and limits

Comparison source revisions were t3code `e4325b79fb72221a2ca5050bce4dfe9363f45377`,
Jones-Code `d2c9281b8112dc3b2991642c4bdb985e4b08b9bb`, Codex-V3
`a8ef76feb11451f8f102b94e5efa352ddb9d49d2`, Goal-Autonomy
`61b0bf784243618aab314c09674cd5e7fc3b846c`, Graphify
`7f0a46b4b6c2663ad515c5f187dd5fbb45c3a6d4`, and host-tooling
`27a04d8fc50a818e80ac1054becbf541168aee76`. These are trial pins,
not claims about current branches or installed runtimes. Dirty/nonmaterialized
Jones source and the advancing V3 checkout were inspected through committed
Git objects. V3's actual Goal dependency is 2.1.0 at
`2db0a0972406eae2b7e4b9546956361b18b46837`; the assigned Goal checkout
was 0.1.0 and could not establish that compatibility.

Catalog SHA-256 was
`4e8dd6418299ecb6f36560faf19ec380f5085b215badd12a67f7bde99bb21c3c`.
Every queried snapshot reported a source-head mismatch. Large application
snapshots also reported one parser error each, structural warnings, unreported
exclusions, and unassessed runtime qualification. No completeness claim follows
from valid digests or successful queries.

This is a qualitative assessment, not a productivity benchmark. Source-first
measurements were incomplete and heterogeneous. Source fallback is not graph
success. One UI lane encountered sibling-result exposure; affected cases were
assigned fresh isolated source verification. Second-query terms were chosen
before substantive source inspection, but interpreted after verification.
The evidence supports bounded routing recommendations, not a universal
preference for graph-first work or measured time savings.

Private raw results, admission records, subprocess metrics, test receipts, and
coordinator summaries remain outside Git in the task-owned
`~/.local/share/agent-work/graphify-agent-cli-20261001/evidence/usage-profile-20261005/`.
No private graph archives or conversation excerpts are published here.

## Delivery boundary

Graphify owns this profile, its canonical query skill, and CLI. Global agent
guidance supplies thin discovery. Host-tooling distribution, immutable release
installation, snapshot refresh, and shared host activation remain separate work.
These trials did not prove fleet synchronization or fresh graphs for every repo.
The inspected host-tooling revision did not implement a Graphify distributor.
