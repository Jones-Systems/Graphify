# Work Note — Search Research Provenance Successor

Artifact Type: `work-note`

Artifact ID: `worknote.graphify-search-research-provenance-successor`

Purpose: Preserve custody, acceptance boundaries, and delivery evidence for the provenance repair of Graphify pull request #1.

Governing artifact: `research/RANKING.md`

Continuity owner: T3C-GRAPH successor coordinator

Consumers: Graphify maintainers, reviewers, verifiers, and future research consumers

Authority effect: none

## Outcome

Repair the public-source provenance and acceptance claims carried by Graphify
pull request #1 without expanding into live graph promotion, external indexing,
protected-corpus access, host installation, or a broader graph product. The
delivery is complete only when every accepted research claim is traceable to an
eligible raw input, contaminated or unknown-origin evidence remains excluded,
the exact candidate passes its declared checks and independent review, and the
pull request is merged into its verified `main` base with direct readback.

## Successor Binding And Git Ownership

- Repository: `Jones-Systems/Graphify`.
- Successor branch: `work/search-research-provenance-successor`.
- Successor worktree:
  `/home/malcolmjones/Projects/Graphify-worktrees/search-research-provenance-successor`.
- Starting revision: `4a3ffa0de6fef80cbde0a06eda28460ec3b9ed36`.
- Starting revision ancestry: contains pull-request head
  `e1c8b4395d135b4dad3bbbbcaef6571f5425db5f` and all first-repair commits.
- Sole Git/index owner: the T3C-GRAPH successor coordinator. Other lanes are
  read-only unless assigned an explicit, non-overlapping file cone; no other
  lane may stage, commit, switch, merge, rebase, or advance refs here.

## Recovered Source Custody

| Source | Custody disposition |
| --- | --- |
| Primary PR checkout, `work/search-research-wave1@e1c8b439` | Clean at intake and equal to the remote pull-request head. Evidence-only; do not edit. Its broad research-complete and Tier-1-ready claims are superseded where the repaired provenance contract is narrower. |
| First repair, `work/search-research-provenance-repair@d1dbac36` | Contains six repaired research paths and is fully included in the successor base. Preserve in place. An unexplained untracked 975-byte regular file named ` […]` remains uninspected and unowned; it is excluded from every successor input and effect. |
| Second repair, `work/search-research-provenance-repair-v2@4a3ffa0d` | Clean at intake. Selected as the successor base because it contains the first repair plus nine additional provenance-hardening commits. Preserve its worktree in place; continue only from the isolated successor. |
| Continuity audit, `docs/graphify-continuity-audit@29ab9736` | Unique `docs/WORK-NOTE.md` and handoff retained as historical evidence. Their research-complete, pilot-success, and promotion-readiness assertions are not current acceptance evidence where they conflict with the repaired contract. No commit is copied wholesale. |
| Codex-V3 source delivery | Pull request #194 is merged. Its accepted source/tooling delivery is not recreated here, and it grants no runtime or corpus authority. |

The named predecessor threads are
`1329a323-63a7-4213-b07a-49d271b8930f` (Graphify Reconciliation
Workstream) and `2b4fea55-7257-4d3d-8a98-8ebace9d5261` (Reconcile
Graphify Candidate). Their two intake worktrees are clean at the same
`6687e7522c436f2560b7c9594861fc46cb537fe9`; neither contains unique tracked or
untracked delivery residue. Thread settlement remains a separate lifecycle
effect and cannot substitute for repository delivery.

## Accepted Provenance Contract

- The reviewed repair input is `d1dbac36208b0066fc8907bd9fe9408fc5c51a60`;
  candidate raw inputs are bound by the immutable tree recorded in
  `research/RANKING.md` and the allowlist in `research/positive-claims.json`.
- A file count is not completeness or acceptance evidence. Intake classified
  100 lanes represented by 95 files as 21 validated/consumed, three
  qualified/unconsumed, 46 inherited
  blobs excluded as not public-safe, 14 incomplete, two origin-unbound, nine
  misrouted, and five missing.
- L13 and L19 retain unknown origins. L14, L18, L68, L88, and L92 remain
  missing. Missing, unknown-origin, incomplete, misrouted, excluded, or
  contaminated material cannot silently become an accepted claim source.
- Finding severities and effects remain intact. In particular, `GSR-P2-04`
  remains open and blocking for downstream implementation claims that rely on
  historical R1-R20 evidence. The bounded research allowlist/checker repair
  does not clear consumer-by-consumer implementation provenance.
- `docs/SCIP-PILOT.md` correctly treats the historical uncommitted pilot inputs,
  result, and transcript as unavailable and non-acceptance evidence. The
  protocol remains unexecutable until a complete independently verified
  operator-run lock exists.
- The 46 excluded inherited blobs remain present in branch history and the
  candidate tree. Their exclusion from synthesis does not by itself establish
  whole-branch public safety; final review must verify that accepted outputs do
  not consume them.

## Delivery And Verification Ledger

- Pull request #1 was verified open, non-draft, same-repository, and based on
  `main@4d78b2226af9efe3a3296e69eb1de5a880d9e06f` at intake. Its remote head was
  `work/search-research-wave1@e1c8b4395d135b4dad3bbbbcaef6571f5425db5f`.
- Intake found no reviews, review threads, comments, or status-check rollup.
- The pull-request body overstates completion, reports 87 raw findings while
  the head contains 93, and names absent `research/spec-requirement-inventory.md`.
- Required candidate checks are
  `python3 tooling/check_research_provenance.py --self-test`,
  `python3 tooling/check_research_provenance.py`, and repository diff/whitespace
  integrity. Record exact revision and result here after execution.
- Independent non-bot review must bind the exact candidate revision. Preserve
  every finding and its blocking effect through remediation and renewed review.

### Repair checkpoint `9a37fb7c525c900fc1affdfe76b6fbae5d735b41`

The admitted first-pass review lanes reported the following dispositions:

- `GSR-SEC-01` (P2): fixed. Every semantic claim-table cell and exact row shape
  is now bound by a claim-map digest, and narrative raw references are limited
  to the declared provenance-map section.
- `GSR-CHK-01` (P2): fixed. Supported Python sources use their declared source
  encoding; undecodable or NUL-bearing supported executables fail closed.
- `GSR-CHK-02` (P2): fixed. Bounded JavaScript template interpolation is
  evaluated, while unresolved interpolation fails closed.
- `GSR-CHK-03` (P2): fixed. Tracked reads traverse every component relative to
  pinned no-follow directory descriptors, and Git blob identity is calculated
  from the bytes already read rather than reopening the path.
- `NAR-P2-01` and `NAR-P2-02`: fixed. Deployment values and the MCP surface are
  explicitly inherited, unvalidated proposals rather than research-authorized
  readiness claims.
- Raw-identifier/vocabulary P3 findings: fixed without rewriting immutable raw
  evidence. The ranking now distinguishes the two stack-graphs repository
  identifiers and treats L42's early policy sentence as historical wording;
  current registered claims remain parameterized experiments.

At this checkpoint, one admitted serial process passed the focused self-test,
all declared provenance groups, Python bytecode compilation, and
`git diff --check`. The self-test includes regressions for the unchecked table
cell, Latin-1 Python consumer, interpolated JavaScript path, and replaced parent
directory. These results qualify this checkpoint only; final review and merge
use the later exact candidate revision and renewed checks.

### Final-review remediation checkpoint `7f4bb416dd87ef8e3e4101ecba9428e99abdae9b`

Independent correctness and security review of the prior candidate found four
additional P2 guard defects. `GSR-FCR-01` is fixed by accepting only one exact
header per tabular positive section. `GSR-FCR-02` and
`GSR-SEC-FINAL-01` are fixed by decoding cooked JavaScript template escapes,
retaining known template components across unsupported nested interpolation,
and marking unresolved paths fail-closed. `GSR-FCR-03` is fixed by opening the
leaf nonblocking before rejecting non-regular objects. Expanded regressions
cover extra and altered headers, escaped interpolated and non-interpolated
templates, nested dynamic interpolation, and FIFO leaves. One admitted serial
process passed the expanded self-test, all declared provenance groups, Python
bytecode compilation, and whitespace validation at this checkpoint.

Renewed review then found `GSR-FCR-02` / `GSR-SEC-FINAL-02` still admitted the
valid JavaScript code-point escape `\\u{61}`. Checkpoint
`613ed36254f71be15f857b5bcc267d919c8e78ca` decodes bounded braced Unicode
escapes, rejects invalid or out-of-range values, and adds the missing exact-path
regression. The expanded 55-case raw-path adversarial set and all declared
provenance groups passed before this checkpoint was recorded. Exact-revision
renewed review remains the final finding-closure gate.

Renewed review of that checkpoint preserved the same finding identities after
showing that leading-zero braced code points and JavaScript line continuations
could still spell the excluded raw-source directory. Checkpoint
`a7bbdbf4d985124249960dca4d6537de64ba0651` decodes those forms, applies the
same bounded decoder to quoted literals, and covers legacy octal escapes used
by non-strict JavaScript. Its focused self-test passed with 59 raw-path
adversarial cases. The complete declared check set and independent review must
bind the later exact candidate that contains this custody update.

Independent review of the resulting candidate kept `GSR-FCR-02` and
`GSR-SEC-FINAL-02` open after finding compound template concatenation and the
remaining JavaScript line-separator continuations. It also opened
`GSR-SEC-FINAL-03` (P2): the inherited fixed staging path could retain a file
that a later preflight excluded. Checkpoint
`65d5f7ee2d22b754c4e9bf1389be73ddb96bb12e` evaluates concatenation before
literal decoding, covers all four JavaScript line terminators, replaces the
fixed staging view from the current admitted inventory on every run, and makes
validation reject any graph source absent from that inventory. Focused tests
passed with 62 raw-path adversarial cases and a cleanup-owned stale-stage
fixture. Exact-candidate full checks and renewed independent review remain
required.

## Stop And Recovery Boundaries

Stop the affected mutation on source drift, an active or unknown writer,
unowned dirty state, loss of rollback, protected-corpus access, or evidence that
an excluded source can influence an accepted output. Do not inspect or remove
the first repair's unknown file, alter either repair worktree, access live graph
runs, promote pointers, install dependencies or services, register call paths,
or invoke an automated pull-request review bot.

## Next Action

Audit the exact successor tree against the accepted source vocabulary, raw
identifier mapping, contaminated-row exclusions, footnotes, and generated
positive-claim allowlist. Make the smallest coherent repair, run the admitted
checks, obtain independent exact-revision review, update the existing pull
request without rewriting history, synchronize with verified `main`, and merge
only after all gates are satisfied.
