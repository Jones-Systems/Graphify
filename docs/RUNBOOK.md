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
