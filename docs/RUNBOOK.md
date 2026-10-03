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
