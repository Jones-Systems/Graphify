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
seconds and 1 MiB of output. Before status, a bounded names-only config read
includes system, global/XDG, local, enabled worktree configuration and conditional
includes. Any `filter.*` key makes source observation unavailable, including
unused or empty definitions: status can execute clean/process filters while
revalidating tracked content, and disabling them could change cleanliness
semantics. This gate does not depend on where attributes select a driver (for
example worktree/index attributes, `.git/info/attributes`, or global attributes).
Indexed submodules also make observation unavailable; their independent config
is not traversed, and status recursion is disabled. These cases return
`ObservationError` / `observation_error` with qualification false, not a clean
checkout claim. Git configuration must remain unchanged during observation;
these separate read-only samples are not a sandbox against concurrent hostile
reconfiguration. Observation failure cannot qualify a snapshot.

The `graphify-freshness-result/v1` JSON reports observer version, repository,
expected/validated catalog digest, archive and graph digests, snapshot head,
before/after source heads, Git cleanliness and status digests, UTC observation
interval, sample stability, optional target comparison, and reader validation
coverage. Reader validation errors retain their exception type and bounded
message. Source heads and dirty state are sampled around selected-store
validation; changed or failed rechecks produce `unstable_source`. Equal samples
cannot exclude intervening edits. Git cleanliness covers tracked and untracked
status for accepted checkouts; indexed submodules cannot be qualified. It
excludes ignored files and is not an input inventory audit. Git status paths and
the status listing are not emitted.

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

### Native portable source release

The additive Graphify-owned `tooling/install_portable.py` prepares, installs and
verifies an exact committed five-helper release. See the
[native installation procedure](RUNBOOK.md#native-portable-source-installation)
for the manifest, bounded Git-blob selection, no-replace publication, cleanup,
qualification and explicit-path rollback contract. This ordinary-user Linux
source route preserves Graphify custody and does not perform a host-tooling
import or alter that import's licensing/owner policy. Shared host orchestration,
transport and activation remain under their existing owners.

The export contains no `.git`, query skill, host binding, catalog or archive.
Its release manifest is installed-source evidence, not a substitute for the
canonical skill's Git-checkout identity check. Invoke the helpers by explicit
release paths; installation does not adopt them into automatic agent discovery,
refresh schedules or assistant call paths. No dependencies or legacy venv are
installed. The refresh helper still needs a separately qualified production
extractor and explicit source/corpus execution authority.

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
After acquiring the lock, missing, unreadable or replaced lock identity is
`unknown`. Identity is checked before packaging and again on every task exit
while the descriptor remains locked, including unchanged, failure and
cancellation paths. A loss observed after packaging retains the candidate as
evidence but cannot report task completion or start a later task, even one
using a different lock. These are sampled checks; cooperating callers must
still preserve the lock inode throughout the run.

The retained-transaction check exempts `candidate/` only after the producer
successfully validates its owned closure. A foreign file, directory or
symlink rejected before producer acquisition remains unexpected, is preserved,
and makes the task `unknown`. A producer failure with confirmed cleanup and
unchanged transaction ownership remains `failed` and may allow later tasks.
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

### Separate structural adapter family

`tooling/refresh_adapter_structural.py` implements the existing stdin/stdout
protocol as `graphify-stdlib-structural`, version `1`. Select that exact
extractor name/version and pin both script and real interpreter path/hash in
the refresh manifest. It is standard-library-only and runs under the existing
descriptor-pinned `-I -B` invocation. It reads only admitted staged files,
rejecting symlink traversal, hard links, nonregular files, changed bytes and
hash mismatches. It validates the closed request, matching admission policy,
clean/equal caller samples and the exact stdin digest; it does not independently
observe the source or authenticate those samples.

Python extraction uses `ast.parse` without importing or executing admitted
code. File/class/function nodes and lexical `contains` edges use stable,
family-specific IDs. Imports resolve only exact admitted root-relative
`module.py` or `module/__init__.py` files; relative imports use the containing
package path. Ambiguous or absent modules are unresolved references. Imported
symbols, runtime module search paths, types and calls are not resolved.
Markdown extraction recognizes plain inline relative links to admitted paths,
with optional fragment/query suffixes. It skips images, external/absolute
links and fenced/indented/inline code; reference-style links, escaped or nested
destinations, percent decoding and full CommonMark parsing are outside this
subset. Unresolved recognized relative targets are recorded without reads.

Supported files parsed by this subset have `structural` coverage; unsupported
files and syntax, recursion or decoding failures have `unknown` coverage and
contribute to `structural_parser_errors`. Coverage is never `enriched`;
`semantic_coverage` is `none`, validation remains `partial`, and empty covered
segment lists make no semantic claim. Every graph record carries an admitted
`source_file`; graph/validation retain source/head and request SHA256. Records
are sorted and deterministic for identical request bytes and interpreter.

Bounds are 512 KiB request bytes, 24 JSON nesting levels, 10,000 request values,
100,000 AST nodes per Python file, 20,000 total graph/reference/error records,
and 4,096-character text fields. Existing manifest input/output byte limits
also apply. Records are budgeted during extraction and the complete response
is checked before stdout. Malformed/admission/hash/no-follow/resource failures
exit nonzero without success JSON. These bounds are not process RAM isolation.
The adapter writes no files, launches no children, reads no environment and
uses no network or model service.

This separate family does not claim graphifyy/networkx parity or replace
existing graph identities or semantics. It is available as reviewed source
preparation; it is **not included** in the fixed five-helper installer release.
Selection, real-corpus execution, operational resource qualification,
promotion and binding remain separate. The original G18-COR-002/003 P2
findings have separate refresh-source corrections and synthetic regression
coverage. Formal finding closure requires affected independent review of the
selected correction revision; this adapter alone does not qualify those
guarantees or an installed runtime.

## Incremental Git-Object Refresh

`tooling/graph_refresh_incremental.py --manifest /EXACT/manifest.json
--manifest-sha256 SHA` builds one create-only structural candidate for one
repository from Git objects in a producer-owned bare mirror. Invoke it with
`python3 -B` (it also adds its own directory under `python3 -I`). It is additive: `graph_refresh.py`, its v1 manifest, the v1
adapter request and the reader, pull and pack formats are unchanged.

The digest-bound, closed `graphify-incremental-manifest/v1` has exactly
`schema`, `repository`, `mirror_git_dir`, `commit`, `target`,
`admission_policy`, `extractor`, `runtime_probe`, `state_root`,
`previous_state`, `destination`, `lock`, `cache_quota_bytes` and `limits`:

- `mirror_git_dir` is an absolute bare repository; `commit` is a full OID in
  its object format. Nothing is fetched or checked out.
- `target={oid,observed_at,method}` is caller-supplied and may be all null.
  The result reports `target_relation.relation` as `current` (target equals
  commit), `behind` (commit is an ancestor of a target present in the mirror)
  or `unknown`. It is never canonical latest-source evidence.
- `admission_policy` is `graphify-admission-policy/v1` with `include` (1–128)
  and `deny` (0–128) printable-ASCII `fnmatchcase` globs, `max_files` (at most
  256), `max_file_bytes` (at most 4 MiB) and `max_total_bytes` (at most 16 MiB).
  Its digest is the SHA256 of sorted-key compact ASCII JSON without a newline.
- `extractor` must be protocol `python-json/v2`, name
  `graphify-stdlib-structural`, version `1`, with exact executable and script
  `{path,sha256}`. Other protocols or families are deferred, not modeled.
- `runtime_probe` must select this release's own `tooling/runtime_identity.py`.
- `state_root` is an existing directory reached without symlinks; the fragment
  cache is `<state_root>/fragment-cache` (created 0700 if absent; the cache
  requires an owner-only root). `previous_state` is
  null or `{path,sha256}` of an earlier `build-state.json`. `destination` is a
  new absolute path, which may sit below `state_root` but never overlaps the
  cache, mirror, lock, adapter, probe or previous build. `lock` is an existing
  stable file. `limits` has the `graph_refresh.py` fields and bounds.

Admission walks `ls-tree -r` of the commit. Denies win; then includes select.
Selected symlinks, gitlinks, other modes, unsafe or undecodable paths and blobs
over the file cap are recorded as unsupported rather than read. `check-attr
--source <commit>` then marks `filter`, `eol=crlf`, `working-tree-encoding` and
`ident` paths unsupported. Git runs with no system/global config or attributes,
`core.autocrlf=false` and `core.eol=lf`, so `text` and `text=auto` paths are
admitted with blob bytes. Mirror-local `info/attributes` still applies. File
count and total byte caps fail the run. Blobs are read with `cat-file --batch`
and verified against their object IDs.

Fragments are cached by `graphify-fragment-key/v1`: fragment schema, family,
adapter SHA256, runtime identity, a per-file policy digest (input basis and
`output_bytes`), path and content SHA256. Commit identity is not part of a key.
A previous build state supplies trusted blob-to-SHA256 digests; content read
for a cache miss must match that digest or the run fails. Every run sends all
current admitted files (reuse or extract) to one adapter run, which resolves
cross-file references over the whole admitted set, then packs once.

Cache fallbacks keep the run going and are reported in `cache_status`:
`cache_disabled:runtime_unidentified` when the runtime probe cannot identify
the runtime, `cache_unavailable: ...` for an unusable cache root, `full` at the
quota, `disabled` from the cache scan bound, `degraded` for corrupt, unreadable
or conflicting entries, and `reuse_rejected` when the adapter rejects a reused
fragment. That last case retries once with every file extracted and stores
nothing. Corrupt and foreign cache entries are preserved; there is no eviction.

The same commit, tree, admission policy, adapter, executable, per-file policy,
identified runtime and admitted/unsupported set as `previous_state`, with its
sibling `candidate/` package verified, returns `unchanged`. It creates no
output and does not run the adapter; the runtime probe still runs. A changed
commit with the same admitted set reuses every fragment and still repacks.

A completed destination holds `attempts/<n>/` (staged inputs, `request.json`,
`adapter-response.json`), `evidence/` (the six pack inputs), `candidate/`
(unchanged `graph_pack.pack` output) and `build-state.json`
(`graphify-build-state/v1`: identities, per-file `{path, blob_oid, sha256,
bytes, coverage, key_sha256}`, unsupported entries, package digests, `counts`,
`cache_status` and `target_relation`). Source evidence has
`build_observation=null`, so `build_observation` remains in
`missing_provenance`; validation adds `Git-object input; checkout cleanliness
not observed.`

Stdout is one bounded `graphify-incremental-result/v1` receipt. It carries
`status`, `reason`, `package` and `build_state` selections (`{path,sha256}`),
`counts` (`admitted`, `added`, `modified`, `deleted`, `reused`, `extracted`,
`unsupported`, `cache_hits`, `cache_misses`, `cache_corrupt`, `cache_full`),
`cache_status`, `runtime_identity`, `target_relation` and `attempts`. A rename
counts as one deletion and one addition. Exit 0 means `completed` or
`unchanged`, 2 `deferred` (lock contention, destination collision, unavailable
mirror or extractor, cancellation) and 1 `failed` or `unknown`. The lock,
retained-transaction and foreign-candidate checks are the sampled
cooperating-writer semantics of `graph_refresh.py`; a lost lock or unexpected
transaction entry is `unknown` and retained. The adapter remains trusted code,
not a sandbox, and this family makes no legacy semantic-replacement claim.

### Catalog assembly

`tooling/graph_catalog.py --package PATH SHA256 [...] --destination NEW_ABS`
(invoke with `python3 -B`; like the other existing helpers it cannot import
its siblings under `python3 -I`) assembles 1–128 selected
`graphify-pack-package/v1` packages, one per repository, into a new
`private-graph-download-catalog/v1` with copied, re-verified archives. An
incremental candidate's `candidate/package.json` and its receipt SHA256 are
direct inputs. `assembly.json` (`graphify-catalog-assembly/v1`) records each
selected package's identities and qualification; the reader and `graph_pull`
ignore it. Exit 0 is success, 1 an error (effect `not_completed` or `unknown`)
and 2 a usage error. Assembly validates consistency, not provenance or
freshness.

## Portable Release Closure V2

`tooling/install_portable.py --closure v2` prepares, installs and verifies a
closed `graphify-portable-release/v2` release. It contains the five existing
helpers plus `graph_catalog.py`, `graph_refresh_incremental.py`,
`fragment_cache.py`, `runtime_identity.py` and `refresh_adapter_structural.py`.
Without `--closure`, every command keeps the five-helper `v1` behavior, so
existing `v1` releases and their digests remain valid. See
[the v2 closure procedure](RUNBOOK.md#portable-release-closure-v2) for commands
and failure codes.

The manifest binds repository, commit, each helper's committed blob identity
and the installer's provenance. Verification rejects a release whose schema
does not match the selected closure. A `v2` release is a new digest-named
sibling release with no `current` pointer. It does not modify `v1` releases and
does not adopt the helpers into automatic agent discovery, refresh schedules
or assistant call paths. It lets the
[incremental refresh](#incremental-git-object-refresh) use the same release's
`tooling/runtime_identity.py` as its `runtime_probe`. This does not qualify a
production extractor or a host installation, and it makes no legacy
semantic-replacement claim.

## Portable Release Closure V3

`tooling/install_portable.py --closure v3` prepares, installs and verifies a
closed `graphify-portable-release/v3` release. It contains the ten `v2` helpers
plus `structural_languages.py`, which the structural adapter needs beside it
for family 2, and `semantic_batch.py`, which also uses the shipped
`graph_pack.py` and `graph_read.py`. The `v1` default and `v2` releases are
unchanged and still verify only under their own closure. See
[the v3 closure procedure](RUNBOOK.md#portable-release-closure-v3).

`v3` is installer source support only. It does not install a release, add a
`current` pointer or adopt the helpers into automatic agent discovery, refresh
schedules or assistant call paths. Agents can use a `v3` release only after an
operator installs and verifies one by explicit path from an exact merged
canonical commit and its prepared manifest SHA256.
