# Runbook

These procedures describe the source tooling. Execute only within the owner's
authorized host, corpus, runtime, and operation scope. Script availability,
recorded state, and documentation do not establish runtime readiness or grant
permission to install, build, promote, deploy, or wire assistant integration.

The default runtime root is `~/.agent-references/graphify`, overridden by
`GF_ROOT` where supported. Keep environments, policy copies, staged sources,
graphs, databases, and runtime evidence outside Git.

## Install

```bash
tooling/install.sh
```

The installer pins `graphifyy==0.9.16` and checks the expected wheel SHA-256
before installing it. It checks an existing source archive when present.
Preserve those checks and fail on a mismatch. Never use upstream platform
installers (`graphify install --platform ...`).

This is not a completely pre-locked installation: bootstrap paths download
`get-pip.py`, dependency resolution is not hash-locked in advance, and
`resolver-lock.txt` records the resulting environment after installation.
The final CLI help invocation is a smoke check, not runtime acceptance.

The installer checks `MemAvailable` at entry: below 3072 MiB stops the
operation and below 4096 MiB emits a warning. Its final memory reading is a
sample, not a continuous guard.

## Native portable source installation

`tooling/install_portable.py` installs Graphify's own five portable Python
helpers, independently of the legacy venv above and of host-tooling vendoring.
It requires Linux, Python 3.10+ with its standard library, local Git supporting
`--no-lazy-fetch` (older Git fails closed), and libc/
filesystem support for Linux `renameat2(RENAME_NOREPLACE)`. It installs no pip
packages, model dependencies, timers, services, global commands, skill links,
agent bindings or graph data. This route makes no licensing determination and
does not change host-tooling's source-owner/license import policy.

The coordinator first binds the authorized host, an existing owner-controlled
release parent outside the checkout, a trusted canonical Graphify checkout at
an exact full commit, and the interpreter. A proposed dedicated parent is
`~/.local/share/graphify/portable/releases`; the installer requires an explicit
absolute path and never creates its ancestors. Host access, parent provisioning
and source transfer use their separately authorized routes. Do not weaken SSH
trust or use sudo to compensate for a missing route. Install VPS and test only
when each has its own proved operation binding; one host's success is not fleet
completion.

From the reviewed, committed source installer, prepare the exact manifest:

```bash
python3 -B /SOURCE/tooling/install_portable.py prepare \
  --source /SOURCE --revision FULL_COMMIT --destination /RELEASE_PARENT
```

The checkout must be its exact Git top-level, with HEAD equal to the selected
commit and a recognized canonical `Jones-Systems/Graphify` origin spelling.
That origin is a local assertion, not remote authentication. Git reads use local
objects, disable replacement refs, lazy fetching and optional locks, and do not
run checkout filters. The source checkout and its Git metadata must be trusted
and stable for the operation; no repository or filesystem sandbox is claimed.
No fetch occurs. Each Git subprocess has a ten-second deadline and bounded
stdout. Only the explicit closure's blobs and the installer's blob are selected;
uncommitted module bytes and untracked files are never copied. The running
installer must itself be byte-identical to its committed blob, so an uncommitted
installer cannot qualify a release. Read source and installer from the same
accepted revision, rather than running an unrelated installed copy.

Prepare emits `manifest`, `manifest_sha256` and the proposed `release` path.
Review and retain that output, then pass its exact digest:

```bash
python3 -B /SOURCE/tooling/install_portable.py install \
  --source /SOURCE --revision FULL_COMMIT --destination /RELEASE_PARENT \
  --manifest-sha256 PREPARED_MANIFEST_SHA256
python3 -B /SOURCE/tooling/install_portable.py verify \
  --release /RELEASE_PARENT/PREPARED_MANIFEST_SHA256 \
  --manifest-sha256 PREPARED_MANIFEST_SHA256
```

The closed `graphify-portable-release/v1` manifest binds repository, commit,
the ordered five-file closure, and installer provenance. Every file record
contains `path`, Git `blob_oid`, raw-byte `sha256`, byte count, committed
`source_mode` and installed `mode` (`0444`). The installer record identifies
the producer but its bytes are not added to the installed five-file closure.
The release identity is SHA-256 of sorted-key compact ASCII manifest JSON with
no trailing newline. `release.json` stores those bytes plus one newline.
Digests bind the selected content, not publisher authenticity or licensing.

The release contains exactly `release.json` and `tooling/{graph_read,
graph_pull,graph_freshness,graph_pack,graph_refresh}.py`. Directories have mode
`0555`; files have mode `0444`. Verification checks the exact entry set, modes,
regular single-link files, bytes, Git blob hashes and manifest identity without
opening any graph/store/binding. No-follow directory traversal rejects symlink
components. Each source blob is capped at 1 MiB and the manifest at 16 KiB.
Source and destination trees cannot overlap. Install creates a unique sibling
stage, verifies it, and publishes without replacing an existing destination.
An existing exact release is verified without rewriting it; drift or a collision
fails. Filesystem durability uses file/directory fsync. Read-only modes and
verification detect drift; the owning user can still deliberately change them.

On failure or handled SIGINT/SIGTERM before publication, only the invocation's
recorded staging entries are cleaned. Unknown ownership or unexpected entries
refuse cleanup and report the retained stage path. A failure/cancellation after
publication reports that the release requires readback and retains it. Reconcile
that exact release with `verify` before retry. Forced process/host termination
may leave a stage or published release; no automatic sweep or prior-output
cleanup is provided. Keep required receipts outside disposable scratch.

Qualification runs all five installed `--help` entrypoints with `python3 -B`,
then bounded synthetic functional checks, and verifies the release again.
Record exact interpreter, source revision and manifest identity independently
for each host. A helper help check proves loadability, not a working graph
store, production extractor, provider access or refresh success. The source
tests exercise the real installed reader against a synthetic empty catalog;
the five existing portable-tool suites cover their other synthetic behavior.

Use explicit release paths, for example
`python3 -B /RELEASE_PARENT/SHA/tooling/graph_read.py --help`. There is no
`current` pointer. Rollback selects a previously verified retained release path;
it neither removes files nor rolls back graphs or mutable state. The canonical
query skill's automatic binding route still requires a Graphify Git checkout;
this exported tree does not establish agent-binding adoption. A production
`python-json/v1` refresh adapter and corpus authorization remain separate.
G18-COR-002/003 remain deferred and unchanged for their affected operational
guarantees. Installing these helpers neither repairs nor qualifies those paths.

## Deploy policies and review corpus scope

The versioned policy owner is `policies/<corpus>/ignore.rules`. The default
runtime copy is `<runtime-root>/<corpus>/policy/ignore.rules`. Deploy only the
policy copies covered by the authorized operation; do not treat all corpus
names as an access grant.

Review the exact corpus root, policy, and intended inventory before building.
Preflight applies global denies first, then corpus rules, but remaining files
default to inclusion. The build runner can create a comment-only policy when
the runtime policy is missing, so policy presence alone is insufficient.

`GF_TRACKED_ONLY=1` requests Git-tracked selection. If Git enumeration fails,
preflight falls back to ordinary filesystem selection. Check the emitted
`tracked_only` value and admitted paths before accepting the run.

Canary scanning examines selected markers in a bounded prefix of files no
larger than 1 MiB. A passing scan does not establish absence of secrets.
Inspect only the inventory and evidence allowed by the operation's read scope.

## Build a corpus or sequential wave

```bash
tooling/build-graph.sh <corpus> <root> [chunk]
tooling/build-all.sh [manifest]
FORCE=1 tooling/build-all.sh [manifest]
```

The wave runner uses each manifest row's tracked-only setting; an outer
`GF_TRACKED_ONLY` value does not override it. Review the manifest targets
before authorizing a wave. It skips corpora with an existing `current`
pointer unless `FORCE=1`; that skip does not prove freshness.

Builds use a host lock. A `deferred_lock` result exits successfully without
building, so neither exit zero nor the wave's passed count alone establishes
that a new run completed.

The build runner samples `MemAvailable` at stage boundaries. It stops below
3072 MiB and warns below 4096 MiB. These checks do not continuously preserve
a host-wide floor during a stage; `preflight.py` itself has no memory guard.

Preflight supplies the inventory used to create the fixed staging view.
The runner checks staging ownership and containment before replacing that
view. Staging remains after the run and can contain admitted source copies;
its retention and later replacement belong to the authorized runtime scope.

A completed build records the following under `<corpus>/runs/<id>/`:

- `preflight.json`
- `graphify-out/graph.json`
- `validation.json`
- `freshness.json`
- `build-meta.json`

Memory readings and progress go to command output. The wave runner captures
build output in `<runtime-root>/build-log.txt`; a standalone build does not
automatically save that log.

Treat run directories as retained snapshots. Immutability is not mechanically
enforced, and promotion later writes `promotion.json` into the run. Preserve
the exact evidence needed to identify and verify each run.

Validation checks graph structure, admitted sources, and other recorded
conditions. The current validator emits a freshness classification without
performing a comparison against later source state. Its `valid` value alone
does not prove currentness.

## Promote after independent verification

Before promotion, obtain an independent verifier's evidence for the exact
corpus and run. That evidence must address the admitted source scope and
policy, validation result and warnings, and freshness against the intended
source state. Bind the verifier identity and evidence reference to that run.

```bash
tooling/promote.sh <corpus> <run-dir> --verified-by "<verifier session + evidence>"
```

The attribution string is the fourth argument. Do not insert an extra
argument before `--verified-by`.

The script requires a nonempty fourth argument and rejects validation status
`BLOCKED`. It does not verify the flag spelling, verifier independence,
evidence contents, or freshness. Those remain requirements of the authorized
promotion operation.

Promotion updates `<corpus>/current` with `ln -sfn` and writes
`promotion.json`. The source does not demonstrate an atomic pointer swap.
Read back the exact pointer and promotion record before reporting success;
reconcile an uncertain prior effect before retrying.

## Toggle assistant integration

Use one subcommand per invocation:

```bash
tooling/toggle.sh status
tooling/toggle.sh disable
tooling/toggle.sh enable
tooling/toggle.sh verify
```

Explicit owner approval is required before enabling integration or changing
assistant call-path wiring. Bind approval to the actual skill and wiring
hooks; the toggle script can execute those hooks. Disabling also mutates
runtime state and must remain within the authorized operation.

`disable` preserves and checks a bundle, moves the skill to its disabled
sibling, and records `implementation-applied-verification-pending`.
After an external fresh-session check confirms the intended skill and
call-path behavior is unavailable, `verify` records
`temporarily-inactive-verified`.

An approved `enable` preserves the disabled state, restores the skill, and
records `restored-verification-pending`. After an external fresh-session
check confirms the intended discovery and behavior, `verify` records
`active-verified`.

The `verify` command performs neither fresh-session check itself. Preserve
the actual external evidence before recording either verified state.
The fallback text from `status` does not prove a skill is installed or active.

## Refresh after source changes

For a read-only comparison before deciding whether to refresh, bind one
selected portable snapshot to its exact local checkout:

```bash
python3 -B tooling/graph_freshness.py --catalog /STORE/download-catalog.json \
  --catalog-sha256 EXACT_SHA256 --repo OWNER/NAME --source-root /EXACT/CHECKOUT
```

Optionally add `--target-oid FULL_OID` for a caller-supplied target comparison.
The observer rejects any effective `filter.*` configuration and indexed
submodules before status, returning unavailable source observation without
executing filters or entering submodules. It checks names across Git config
scopes and includes; unused or empty filter definitions are rejected too.
Keep Git configuration unchanged during the observation: sampling does not
isolate concurrent reconfiguration. Do not disable filters to force a clean
qualification; that would change the checkout comparison's semantics.

The observer validates through the delivered reader and samples Git before and
after validation with optional locks disabled. Exit `0` means only a stable
sampled clean-checkout head match (and matching target if supplied); exit `2`
means an observation that does not qualify; runtime/validation errors exit `1`.
Argument errors also exit `2`. Canonical latest source remains unknown, and
build-time inventory/cleanliness provenance remains unverified. See the
[observer contract](AGENT-ACCESS.md#local-freshness-observation) for bounds and
limitations. Observation never starts a build, updates a freshness ledger or
current pointer, or distributes/activates data. Producer provenance capture,
authorized refresh verification, and revision-pinned distribution/activation
remain separate gates; old ledger labels are not authority for them.

For an authorized Git corpus, use its exact root:

```bash
GF_TRACKED_ONLY=1 tooling/build-graph.sh <corpus> <root> ""
```

Review the resulting inventory and run evidence, obtain independent
verification against the changed source, and then use the promotion command
above. A current pointer, successful exit, or emitted freshness label is not
a substitute for that verification.

## Related contracts

[Deployment examples](../deploy/README.md) remain inherited and unvalidated.
They do not authorize installing units or changing host controls. The
installer and build-runner memory checks described above are sampled guards;
preflight itself has no memory guard.

Use [the research ranking](../research/RANKING.md),
[the positive-claim registry](../research/positive-claims.json), and
[the accepted provenance contract](PROVENANCE-CUSTODY.md#accepted-provenance-contract)
for research eligibility and retained limitations. Historical custody
actions and verification ledgers are not instructions to resume that work.

[MCP registration](MCP-SURFACE.md) remains gated by DEC-9.
[The SCIP pilot](SCIP-PILOT.md) remains unexecutable without its complete
independently verified operator lock. Existing helper implementations do not
establish acceptance, provenance clearance, or activation authority.

For changes confined to this guidance, verify the diff, paths, links,
whitespace, and source correspondence. The default provenance checker reads
excluded material and is unsuitable when the authorized read scope excludes
it. Documentation checks establish documentation consistency only.

## Portable Refresh Invocation And Operational Gates

The additive producer and refresh contracts are documented in
[agent access](AGENT-ACCESS.md#portable-candidate-production). The producer
packages six explicitly selected JSON inputs; it does not extract a graph:

```bash
python3 -B tooling/graph_pack.py \
  --graph /INPUT/graph.json --graph-sha256 GRAPH_SHA \
  --validation /INPUT/validation.json --validation-sha256 VALIDATION_SHA \
  --inventory /INPUT/inventory.json --inventory-sha256 INVENTORY_SHA \
  --policy /INPUT/policy.json --policy-sha256 POLICY_SHA \
  --extractor /INPUT/extractor.json --extractor-sha256 EXTRACTOR_SHA \
  --source /INPUT/source.json --source-sha256 SOURCE_SHA \
  --destination /NEW/CANDIDATE
```

For separately authorized automatic refresh, prepare and digest an exact
`graphify-refresh-manifest/v1` as defined in the
[refresh contract](AGENT-ACCESS.md#bounded-refresh-contract). For example,
this shape selects one repository and a trusted synthetic-style adapter;
placeholder hashes/OIDs must be replaced with verified values:

```json
{
  "schema": "graphify-refresh-manifest/v1",
  "limits": {"file_bytes": 1048576, "input_bytes": 4194304,
    "output_bytes": 4194304, "seconds": 60},
  "tasks": [{
    "source": {"repository": "OWNER/NAME", "head": "FULL_SOURCE_OID"},
    "root": "/EXACT/CHECKOUT", "target_oid": null,
    "existing": {"path": "/OLD_STORE/download-catalog.json", "sha256": "CATALOG_SHA"},
    "files": [{"path": "src/example.py", "sha256": "CONTENT_SHA"}],
    "deny": ["private/*", "*.key"],
    "extractor": {"protocol": "python-json/v1", "name": "approved-adapter", "version": "1",
      "executable": {"path": "/EXACT/REAL/PYTHON", "sha256": "EXECUTABLE_SHA"},
      "script": {"path": "/EXACT/adapter.py", "sha256": "SCRIPT_SHA"}},
    "destination": "/APPROVED_RUNS/NEW_TRANSACTION",
    "lock": "/APPROVED_RUNS/EXISTING_LOCK_FILE"
  }]
}
```

Set `existing` to null only for an explicitly selected initial build. The lock
must already be a regular file, with a stable inode shared by cooperating
invocations. Output parent directories must exist. Select a fresh transaction
destination each attempt; never reuse a failed/unknown path before explicit
reconciliation. Then invoke only within the owner's execution envelope:

```bash
python3 -B tooling/graph_refresh.py --manifest /EXACT/manifest.json \
  --manifest-sha256 MANIFEST_SHA
```

Inspect every task outcome. Exit 0 can mean `unchanged`, which is a sampled
clean-checkout match with historical build evidence still unverified;
`completed` specifically means new extraction and a validated candidate.
Deferred work never counts as completed. Save the bounded receipt with the
manifest and retained transaction evidence. No candidate is promoted, and no
existing catalog/current/binding pointer changes. The old legacy scripts,
`FORCE` behavior and inherited systemd examples above are unchanged and remain
unvalidated for this portable path. No scheduler is installed or enabled.

An acquired lock that disappears, cannot be read back, or changes identity
produces `unknown`, including when the loss is observed after candidate
packaging or during an unchanged/error/cancellation exit. All remaining tasks
stay unstarted, even with independent locks. A foreign `candidate/` rejected
before producer acquisition likewise remains preserved and produces `unknown`.
Reconcile the exact retained transaction and lock before any separately
authorized retry; do not treat an existing candidate as successful completion.

Before any real run, bind owner-approved repositories, source roots and target
basis, admitted paths/hashes and deny policy, exact interpreter/adapter,
per-task limits, destinations, stable locks and retained-data lifetime. Review
adapter behavior and authorize any model/provider/network effects separately:
the adapter is trusted code, not a sandbox. Select synthetic test roots outside
`/tmp`; the test fixture's creating layer cleans its exact tree on success,
failure and handled cancellation. Operational transaction evidence persists
until a separately authorized creator-owned cleanup/recovery action.

Delivery gates remain separate: accepted Graphify licensing and notices plus
an exact reviewed upstream revision are prerequisites for host-tooling import;
source publication alone does not satisfy them. Host release/install requires
its approved route and installed-revision readback. Data transfer and server
synchronization require selected catalog/archive/graph identities and fresh
per-host receipts; receipt equality alone is not live host authentication.
Promotion requires independent verification of the exact candidate, admitted
scope and source evidence. Scheduler activation, host bindings and assistant
integration require their own explicit operational authorization and readback.
Canonical latest-source qualification needs independently established target
authority; a caller-supplied target or matching local checkout cannot supply it.

### Preparing the structural adapter

For a separately selected structural candidate, the source adapter is
`tooling/refresh_adapter_structural.py`; set extractor protocol
`python-json/v1`, name `graphify-stdlib-structural`, version `1`, and retain the
exact script path/SHA256. Bind a real, non-symlink Python executable and hash
that works with the existing `/proc/self/fd/N -I -B` invocation. No pip,
graphifyy, networkx, provider or model dependency is required. The
[structural family contract](AGENT-ACCESS.md#separate-structural-adapter-family)
defines its syntax subset, request validation, limits and coverage semantics.

This file is a separate upstream source contribution, outside the fixed
five-helper installer closure. Its synthetic checks exercise the unchanged
refresh/pack/reader/pull chain; they neither install this adapter nor authorize
a real pilot. Preserve existing legacy graph identities and explicitly select
this family for a new candidate. Legacy-parity extraction still needs an exact
interpreter and hash-locked dependency closure proved under fd-pinned isolated
execution; the existing legacy bootstrap does not establish that evidence.

Before a real pilot, retain all source-selection, host, stable-lock,
destination/lifetime and independent-verification requirements above, plus
measure time, peak RAM and output for one bounded selection before choosing
a schedule. G18-COR-002/003 now have synthetic source corrections; formal
closure still requires affected independent review of the correction revision.
Qualify the selected installed revision and its lock/transaction assumptions
before any real invocation. Source checks do not establish operational acceptance.
Do not use successful synthetic adapter tests as acceptance of those paths,
real graph freshness, server synchronization or a legacy replacement.

## Incremental Structural Builds From A Bare Mirror

These source helpers are not yet in an installed portable release closure;
the fixed five-helper release does not contain them. Use an exact checkout or
a later separately installed release that includes `graph_refresh_incremental.py`,
`fragment_cache.py`, `runtime_identity.py`, `refresh_adapter_structural.py` and
`graph_catalog.py` in one `tooling/` directory.

1. Prepare a producer-owned bare mirror holding the selected commit, an
   existing stable lock file, an owner-only `state_root`, and a new destination
   parent. This helper neither fetches nor creates the mirror.
2. Write a `graphify-incremental-manifest/v1` per the
   [incremental contract](AGENT-ACCESS.md#incremental-git-object-refresh), with
   `extractor.protocol` `python-json/v2`, the exact adapter and interpreter
   hashes, and `runtime_probe` set to the same release's
   `tooling/runtime_identity.py`. Use `previous_state: null` for a cold build.
3. Run `python3 -B /RELEASE/tooling/graph_refresh_incremental.py --manifest
   /EXACT/manifest.json --manifest-sha256 SHA`. Record the receipt.
4. For the next run, pass the receipt's `build_state` selection as
   `previous_state` and a new destination. `unchanged` creates nothing and
   selects the previous package.
5. Assemble a catalog with `python3 -B /RELEASE/tooling/graph_catalog.py
   --package CANDIDATE/package.json SHA256 --destination /NEW/catalog`.

Treat `deferred` as retryable only after its cause is resolved; treat
`unknown` as a hold that needs reconciliation of the retained destination and
lock. Retained destinations, cache entries and candidates are never deleted by
these helpers. Their removal needs separate creator-owned cleanup authority.

Checks so far are synthetic: owned work repositories pushed into owned bare
mirrors, with the real structural adapter and runtime probe. They cover cold
and incremental equality, counters, cache fallbacks, Git attributes, lock and
transaction handling, and reader, pull and catalog interoperability. They are
not a real-repository pilot, installed-release qualification, measurement of
time or memory, scheduler activation, server synchronization or promotion.
Each of those needs its own authorization, binding and readback.

## Portable Release Closure V2

`tooling/install_portable.py` selects one closure per command with
`--closure v1|v2`; omitting it selects `v1`. Closure `v1` is the
`graphify-portable-release/v1` five-helper release described in
[native portable source installation](#native-portable-source-installation),
and its manifest shape is unchanged. Closure `v2` is the closed
`graphify-portable-release/v2` release with exactly ten helpers, in manifest
order: `graph_freshness.py`, `graph_pack.py`, `graph_pull.py`, `graph_read.py`,
`graph_refresh.py`, `graph_catalog.py`, `graph_refresh_incremental.py`,
`fragment_cache.py`, `runtime_identity.py` and `refresh_adapter_structural.py`,
all under `tooling/`. The installer itself is recorded as provenance but is
not installed.

Pass the same closure to every command for one release:

```bash
python3 -B /SOURCE/tooling/install_portable.py prepare --closure v2 \
  --source /SOURCE --revision FULL_COMMIT --destination /RELEASE_PARENT
python3 -B /SOURCE/tooling/install_portable.py install --closure v2 \
  --source /SOURCE --revision FULL_COMMIT --destination /RELEASE_PARENT \
  --manifest-sha256 PREPARED_MANIFEST_SHA256
python3 -B /SOURCE/tooling/install_portable.py verify --closure v2 \
  --release /RELEASE_PARENT/PREPARED_MANIFEST_SHA256 \
  --manifest-sha256 PREPARED_MANIFEST_SHA256
```

Source selection, origin and installer-provenance checks, limits, modes,
create-only publication and cleanup are the same as for `v1`. Each of the ten
records binds a path to the committed blob OID, SHA256, byte count and source
mode at the selected commit. Prepare fails with
`missing_or_nonregular_source_blob` if any of the ten is absent or not a
regular blob, and with `source_blob_limit` if any exceeds 1 MiB. The manifest
records the commit, not a tree OID. Because `revision` is part of the
manifest, the release identity differs for every commit. Compute the
installable digest with `prepare --closure v2` at the exact commit to be
installed, not at a pull-request head that will not be installed.

The release contains exactly `release.json` and the ten `tooling/` files.
Verification requires the manifest schema to match the selected closure.
Verifying a `v2` release without `--closure v2`, or a `v1` release with
`--closure v2`, fails with `release_closure_mismatch`. Install with one
closure's digest under the other closure fails with `manifest_digest_mismatch`
before writing anything.

Existing `v1` releases remain valid and are verified as before with `verify`
alone or with `--closure v1`. Installing a `v2` release creates a new sibling
named by its own digest. It neither changes nor removes any `v1` release, and
there is still no `current` pointer. Select a release by explicit path; rollback
selects a different retained, verified release path. A `v2` release provides
the [incremental build](#incremental-structural-builds-from-a-bare-mirror)
helpers in one `tooling/` directory, so its own `runtime_identity.py` can be the
manifest's `runtime_probe`. The installer source tests use synthetic helper
bytes. Qualifying a real `v2` release on a host still needs its own exact
commit, prepare/install/verify readback, and authorized operation binding.
Installing the closure does not schedule refreshes, bind agents or promote
graphs, and makes no semantic-replacement claim for the legacy extractor.
