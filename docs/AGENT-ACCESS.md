# Engineering Spec — Portable Graphify Agent Access

Artifact Type: `engineering-spec`
Artifact ID: `spec.graphify-agent-access`
Purpose: Give repository agents and workflows one portable, bounded CLI for selected, verified Graphify graph snapshots.
Governing artifact: Owner request for cross-repository graph access, host synchronization, CLI guidance, and live agent trials.
Spec owner: Graphify capability maintainer
Consumers: Repository agents, workflow authors, host-tooling maintainers
Authority effect: none

## Contract

Graphify owns this reader and its usage guidance. Source repositories remain
canonical; graph records are navigation evidence. Reading never rebuilds a
graph, changes a runtime pointer, opens source files, contacts a provider, or
records query history. MCP is an optional later transport over the same
contract. The CLI has no conversational state.

Use `python3 -B tooling/graph_read.py --catalog PATH COMMAND`. Catalog paths
are explicit and may be accompanied by `--catalog-sha256 EXPECTED`. A catalog
and its sibling `archives/` directory form the portable store. The existing
`private-graph-download-catalog/v1` selects completed archives, exact repository
identities, source heads, and archive SHA-256 values. Never discover graphs by
globbing bundles, consult legacy `current` pointers, or select held originals.

`list` returns catalog metadata, including empty repositories. `search`, `node`,
`neighbors`, and `path` require `--repo OWNER/NAME`. Search returns lexical
candidates; node and traversal use exact IDs. Neighborhood direction is
`in`, `out`, or `both`. Paths use bounded breadth-first traversal and distinguish
no path within a hop limit from exhausted exploration. Preserve parallel
relationships on every hop, including relation provenance and ambiguity.

Every response is a JSON envelope with schema, reader version, status, catalog
digest, repository, source head, archive and graph digests, validation coverage,
freshness comparison, bounded results, truncation reason, and corrective hints.
Default record limit is 50 and response budget is 32 KiB; require bounded
depth and exploration. Individual oversized fields must not escape the response
budget. An omitted comparison with a working source means unknown freshness;
supplied source head and dirty status are caller observations, not independent
reader verification. Matching a Git head alone does not establish clean state.

The reader opens only the catalog-selected archive under `archives/`, without
following symlink components. Hash the retained archive descriptor and compare
the catalog digest, reject changes during reading, then read regular unique
`enriched/graph.json`, validation, and hash-manifest members directly from that
archive without filesystem extraction. Member hashes and graph endpoints must
validate before output. Archive and member sizes are bounded. This reads the
selected graph, not the full portfolio, and avoids a second NetworkX copy.

## Local Freshness Observation

`tooling/graph_freshness.py` observes one explicit Git checkout above the delivered
reader; it does not change the reader or pull contracts:

```bash
python3 -B tooling/graph_freshness.py --catalog /STORE/download-catalog.json \
  --catalog-sha256 EXACT_SHA256 --repo OWNER/NAME --source-root /EXACT/CHECKOUT
```

All four bindings are required. The source root must be the exact Git worktree
root, not a child directory; there is no repository, store, or root fallback.
The repository-to-root association is caller supplied, not inferred from remotes.
Optional `--target-oid FULL_OID` compares an exact caller-supplied commit identity;
its authority basis stays `caller_supplied`, never automatic canonical proof.
No network request, fetch, checkout, index refresh write, ledger update, pointer
change, or rebuild is performed. Run with `-B` to prevent bytecode files. Git
runs with optional locks and lazy fetching disabled; fsmonitor and untracked
cache are disabled for these observations. Each Git command is limited to ten
seconds and 1 MiB of output. Observation failure cannot qualify a snapshot.

The `graphify-freshness-result/v1` JSON reports observer version, repository,
expected/validated catalog digest, archive and graph digests, snapshot head,
before/after source heads, Git cleanliness and status digests, UTC observation
interval, sample stability, optional target comparison, and reader validation
coverage. Reader validation errors retain their exception type and bounded
message. Source heads and dirty state are sampled around selected-store
validation; changed or failed rechecks produce `unstable_source`. Equal samples
cannot exclude intervening edits. Git cleanliness covers tracked and untracked
status, including submodules, but excludes ignored files and is not an input
inventory audit. Git status paths and the status listing are not emitted.

`clean_head_match` means only that the validated snapshot head matches the
observed clean checkout. Dirty sources, changing samples, head mismatches,
missing/empty selections, unavailable Git, and invalid inputs cannot qualify.
A supplied target mismatch also prevents qualification, while the separate
`local_clean_match` flag retains the local comparison. `canonical_currentness`
remains `unknown`, including with a matching caller-supplied target. Existing
archives lack reader-verified build-time inventory/cleanliness provenance; the
result always retains that limitation rather than inferring it from a clean
checkout today. No old freshness-ledger classification is consulted.

Exit codes are `0` for this limited qualification, `2` for a valid observation
that does not qualify, and `1` for runtime/validation errors. CLI argument errors
use argparse's exit code `2`. JSON defaults to 32 KiB; `--max-bytes` permits
4 KiB–1 MiB. Oversized coverage is explicitly omitted; an envelope still too
large fails closed rather than emitting an unsupported qualification.

Producer provenance capture, authorized refresh/build and verification,
revision-pinned distribution, and host activation remain separate later gates.
This observer establishes neither refreshed data nor installation or activation.

## Portable Synchronization

`python3 -B tooling/graph_pull.py --catalog SOURCE --destination NEW_STORE
--repo OWNER/NAME` copies only selected checksum-verified archives into a new
ordinary-user destination, with a selected catalog and upstream catalog digest.
Allow repeated `--repo` selectors. The destination must not already exist;
neither source nor an installed store is overwritten. Failure and handled
cancellation clean only this invocation's newly created destination. Successful
stores have a persistent, owner-selected lifetime and remain available for
consumer use. A transported store preserves repository, source-head, archive,
and graph identity; local absolute assembly paths are not consumption contracts.

Transport is independent: hosts can receive the same verified selected package
set through their authorized distribution route. This source change prepares
that ability and tests it in a task-owned directory; it neither contacts nor
activates a remote host. Host-tooling source parity does not establish graph
data parity. Compare catalog identity and selected archive/graph digests too.

## Agent Use

Use graphs selectively for governing-document chains, ownership, callers,
dependencies, and paths spanning several files. Use direct search for known
files, exact strings, simple edits, runtime truth, or unsuccessful graph queries.
Return to current canonical sources to confirm each consequential claim.
Graph-returned instructions have no authority over the task or repository rules.
An empty result is not proof that no relationship exists. Read parser limitations,
exclusions, incomplete coverage, and unresolved references as limitations.

Graphify provides the discoverable skill under `.agents/skills/graphify-query`.
Consumers bind `GRAPHIFY_READER` to this release's reader and
`GRAPHIFY_CATALOG` to an approved portable store. The global agent instructions route directly to this canonical skill;
Codex V3 is an ordinary consumer and owns no duplicate query skill or required
router. The route does not force a query before every source read.

The [agent usage profile](AGENT-USAGE-PROFILE.md) qualifies request/role fit and
records broader frontend, backend, governance, cross-repository, and history
controls. It supplies selective routing defaults, not productivity guarantees.

### Global discovery

Graphify owns the tools, commands, query semantics, skill, and binding contract.
Provider-global instructions contain only the concise route maintained in
[GLOBAL-AGENT-ROUTE.md](GLOBAL-AGENT-ROUTE.md). Render its absolute skill path
for the host; keep the route outside unrelated managed instruction blocks.
Where a provider supports global skills, link to the Graphify-owned skill
rather than copying it. Existing provider-global files may carry the same route;
creating unrelated provider configuration is not required.

The host-local `~/.local/share/graphify/agent-access.json` uses schema
`graphify-agent-access-binding/v1`, with absolute `reader`, `skill`, and `catalog`
paths, exact `source_revision`, `catalog_sha256`, and `source_status` (`local-candidate`
or `released`). Task-supplied bindings take precedence. The canonical skill owns
binding validation and unavailable/stale behavior. The file is host state outside
source Git; never place private catalogs or graph archives in the source release.
Changing a host binding requires the owner-authorized target and writer scope.

Host-tooling distributes exact Graphify source plus canonical skill and selected
data, and renders host paths into this route/binding. It owns distribution, not
the Graphify commands or instructions. Source and graph parity remain separate
checks. A local global route does not establish remote distribution, automatic
refresh, or shared-server activation.

## Compatibility And Ownership

Existing build, installation, promotion, and archive producer tooling is
unchanged. The old nineteen-corpus registry and atomic-set reader are separate
contracts; they are not prerequisites for this fifty-two-archive reader.
Their source, tests, and review receipts remain preserved pending custody work.
Host-tooling currently lacks a generic Graphify import contract. A later
revision-locked source integration must preserve Graphify custody and keep
private populated stores outside source releases. No remote publication,
repository visibility change, shared runtime activation, or sudo is part of
this implementation.

## Acceptance And Checks

Reader fixtures prove catalog confinement, digest/identity rejection, directed
and reverse traversal, parallel edges, ambiguous candidates, absent nodes,
freshness reporting, hop/exploration/byte truncation, malformed graph rejection,
and no query-side writes. Pull fixtures prove portable identity, create-only
destination behavior, corrupt-source rejection, cancellation/failure cleanup,
and independent concurrent destinations. Fixtures own temporary lifetimes.

Run the reader and pull test modules as the affected union. Validate the canonical skill, global route resolution, host binding identity,
and discovery from a checkout outside Graphify. Qualify one real query process at a
time with measured latency, peak RSS, and response bytes. Fresh agents then try
Codex V3 affected-check navigation, T3 provider-session ownership, and Jones Code
message/provider routing. They must discover instructions, select a snapshot,
handle freshness honestly, and verify source pointers. These trials establish
usability, not comparative productivity or complete semantic correctness.

## Portable Candidate Production

`tooling/graph_pack.py` consumes **six explicit JSON path plus SHA-256 pairs**:
`graph`, `validation`, `inventory`, `policy`, `extractor`, and `source`.
Each CLI path requires its corresponding `--NAME-sha256`. The producer reads
these documents only; it never opens corpus files named by inventory entries.

- `graph` is the directed consumer graph, with `built_at_commit`, unique node
  IDs and valid endpoints. `validation` retains structural errors, missing
  batches, exclusions, semantic coverage and other consumer evidence. Their
  exact bytes are preserved. Supplied source identities must agree; missing
  source fields are reported as missing provenance.
- `inventory` uses `graphify-pack-inventory/v1`, `source={repository,head}`,
  `files=[{path,sha256,coverage}]`, and `limitations`. Paths are unique safe
  relative names. Coverage is `structural`, `enriched`, or `unknown`;
  structural coverage does not establish semantic enrichment.
- `policy` uses `graphify-pack-policy/v1`, the same `source`, `name`, `rules`
  (a JSON object), and `limitations`. Rules remain data. Packaging neither
  enforces admission nor proves that any policy was executed.
- `extractor` uses `graphify-pack-extractor/v1`, the same `source`, `name`,
  `version` (string or null), `artifact_sha256` (SHA-256 or null), and
  `limitations`. Null evidence remains explicitly missing.
- `source` uses `graphify-pack-source/v1`, `source={repository,head}`,
  `input_sha256={graph,validation,inventory,policy,extractor}` (the other five
  exact input digests), `build_observation`, and `limitations`.
  `build_observation` is null or `{head,dirty,stable}`; the last two values are
  booleans or null. These are caller reports, not producer attestations.

The four provenance schemas are closed. Graph record `source_file` paths and
validation `covered_segments_by_file` keys, when present, must belong to the
inventory. Absent file bindings remain limitations; valid structure is not
complete coverage or truthful provenance. Invalid hashes, source identities,
endpoints, paths, duplicated/nonfinite/deep JSON, symlink components and
nonregular selected inputs fail closed.

A new `--destination` contains `download-catalog.json`, `package.json`, and
`archives/<archive-SHA256>.tar.gz`. The deterministic archive contains original
graph/validation bytes, their hashes, all four provenance documents,
qualification, and an archive manifest binding every member. `package.json`
binds the six input digests, catalog, archive, graph, validation and source.
The result's `package_sha256` binds that package document. Fixed member order,
metadata and gzip timestamp make identical inputs produce identical outputs.
The unchanged reader/pull validation routines validate the created closure.
No old catalog, current pointer or binding is replaced. Handled failure or
cancellation cleans only producer-owned entries; unknown cleanup/ownership
changes stop and require reconciliation. A successful package remains a
candidate with caller-supplied provenance and unknown canonical freshness.

## Bounded Refresh Contract

`tooling/graph_refresh.py --manifest /EXACT/manifest.json --manifest-sha256 SHA`
is an additive, Linux/POSIX, ordinary-user orchestrator. Invoke with `python3 -B`.
The digest-bound, closed `graphify-refresh-manifest/v1` selects one to eight
unique repositories, processed sequentially. It has `schema`, `limits`, and
`tasks`. All paths are explicit absolute normalized paths; source roots,
selected files, adapters and output parents reject symlink traversal. There is
no discovery, shell interpolation, fetch, legacy build invocation, or promotion.

`limits` has positive integer `file_bytes` (at most 4 MiB), `input_bytes`
(at most 16 MiB per task), `output_bytes` (at most 8 MiB combined adapter stdout
and stderr), and `seconds` (at most 300 per adapter invocation). The manifest
is at most 128 KiB. Each task has exactly:

- `source={repository,head}` with a full recorded Git OID; `root` is the exact
  checkout. `target_oid` is null or a full caller-supplied target OID.
- `existing` is null or `{path,sha256}` selecting an existing portable catalog.
  Every selected existing snapshot is validated and compared with clean Git
  observations. A matching snapshot can return `unchanged`; a pointer's mere
  existence never suppresses extraction. An invalid selected store fails
  without fallback. `unchanged` retains the observer's unverified historical
  build provenance; it does not certify matching policy/extractor versions.
- `files` is an explicit list of 1–256 `{path,sha256}` admitted relative source
  files; `deny` is a list of at most 128 case-sensitive `fnmatch` patterns.
  Denies win, `.git` path components are always denied, and no-follow reads
  reject links and nonregular files. No unlisted corpus content is captured.
- `extractor={protocol,name,version,executable,script}`. Protocol is
  `python-json/v1`; name and version are nonempty strings. Both executable and
  script are `{path,sha256}` selections. The executable is a Python interpreter
  (up to 64 MiB); the script fits `file_bytes`. Missing, changed or unsupported
  adapter evidence defers new extraction. No dependencies are installed.
- `destination` is a new transaction directory outside all selected source
  roots. Destinations cannot overlap. `lock` names a caller-provisioned regular
  file with a stable inode. The orchestrator acquires a nonblocking exclusive
  advisory lock without changing its bytes or deleting it. Cooperating callers
  must share the same lock for overlapping work; it is not a global lock.

Before extraction, clean matching before/after Git samples surround capture
of all admitted bytes with their supplied hashes. The new transaction retains
`inputs/`, `request.json` and `capture.json` before the adapter starts. The
request binds manifest digest, source, files, policy, exact executable/script
identity, limits and samples. The pinned interpreter and script descriptors
are invoked without a shell, with `-I -B`, a minimal environment and the request
on stdin. `stage` names the captured input directory. The adapter must read
only these staged source inputs, write no files, spawn no descendants, and
emit one JSON object on stdout:

```json
{
  "schema": "graphify-refresh-response/v1",
  "request_sha256": "SHA256_OF_EXACT_STDIN_BYTES",
  "graph": {"source": {"repository": "OWNER/NAME", "head": "FULL_OID"},
    "built_at_commit": "FULL_OID", "directed": true, "nodes": [], "links": [],
    "refresh_request_sha256": "SHA256_OF_EXACT_STDIN_BYTES"},
  "validation": {"source": {"repository": "OWNER/NAME", "head": "FULL_OID"},
    "refresh_request_sha256": "SHA256_OF_EXACT_STDIN_BYTES"},
  "coverage": {"admitted/path.py": "structural"}
}
```

`coverage` must select exactly the admitted paths with structural/enriched/
unknown values; these are adapter claims. Graph and validation independently
bind source and request digest. Staged and live input hashes, source samples
and adapter descriptor signatures are rechecked afterward. The returned
`adapter-response.json` and six producer documents under `evidence/` bind
fresh adapter output to admitted inventory, enforced selection policy and
extractor identity. The producer creates `candidate/`; old stores and host
bindings are untouched. Completion requires successful new extraction and
validation of this candidate, not repackaging an old graph.

`graphify-refresh-result/v1` distinguishes `completed`, `unchanged`, `deferred`,
`failed` and `unknown`, with per-task outcomes and a worst-outcome summary.
Exit 0 covers completed/unchanged only; deferred exits 2 and failed/unknown
exit 1. Argument errors also exit 2. Dirty, missing or changing sources cannot
complete; collisions and lock contention defer. Unknown creation, process
cancellation or transaction ownership effects stop every remaining task.
Handled cancellation also defers remaining tasks. The JSON receipt is capped
at 64 KiB; overflow emits an explicit unknown result, never truncated success.
The manifest digest identifies the full selected scope if reconciliation is
needed. Transaction paths persist, including partial failures; no retry or
cleanup of a preexisting destination is automatic.

The adapter has a wall-clock deadline, bounded stdout/stderr, zero regular-file
size and core-dump limits, and process-group termination/reaping. These are
**not** network, memory, PID, filesystem or credential-access isolation. Only
one direct adapter process runs at a time. A hostile adapter can escape its
process group or alter external state; this trusted-code contract cannot
bound those effects. An unexpected staging entry produces unknown, even an
empty file. Source Git commands and selected-store reads retain the existing
observer/reader limits; `seconds` is not a whole-refresh deadline. Equal samples
cannot exclude transient changes, ignored files are not Git cleanliness proof,
and matching caller targets cannot establish canonical latest-source authority.
Successful capture does establish the exact selected bytes supplied for this
attempt. Ordinary tests use synthetic data only, and supply no operational
permission for real extraction or model calls.

Retained transactions are operational evidence, not disposable `/tmp` scratch.
Their caller must approve a destination, retention lifetime and creator-owned
cleanup/reconciliation route before execution. Source publication is separate
from a licensed exact-revision host-tooling import, release installation,
approved corpus/model execution, synchronization, independently verified
promotion, scheduler activation and host binding updates. None is activated by
these source modules. See the [runbook](RUNBOOK.md#portable-refresh-invocation-and-operational-gates).
