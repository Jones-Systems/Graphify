# SCIP pilot protocol — public-fixture symbol edges

Prove a hash-pinned `scip` CLI, an independently pinned SCIP indexer, and the
pure-standard-library converter on one small public fixture before considering
any broader ingestion. This document does not identify or authorize access to
any protected repository. A prior uncommitted run report is historical context
only: its source commit, input index, converted graph, validation inputs, and
transcript are unavailable, so none of its reported results are acceptance
evidence.

## Fail-closed toolchain gate

The Go `scip` CLI is pinned in `tooling/requirements-scip.txt`. No executable
Python-indexer bootstrap is committed. In particular, do not use `npx`,
`npm install`, a remote Python bootstrap script, or a launcher that downloads a
JVM at run time.

Before any indexer execution, an operator must supply one immutable lock record
for the run. The lock record must contain all of the following:

- exact package name and version for the SCIP indexer;
- local package artifact path, byte count, and cryptographic digest;
- exact runner path, version output, byte count, and cryptographic digest;
- exact Python runtime path/version/digest and an immutable dependency lock;
- exact JVM distribution/version/path/digest when the runner can invoke Java;
- the pinned Go `scip` path/version/digest;
- the network-denial mechanism used while indexing; and
- the digest of the lock record itself in the run evidence.

Every digest must identify the exact local bytes that will execute. Missing,
mutable, registry-resolved, or mismatched evidence blocks the run. The runner
must be invoked by its verified absolute path in a network-denied sandbox; an
auto-downloading launcher is not an acceptable substitute. This repository
intentionally provides no fallback install or bootstrap command.

## Source binding and isolated copy

Use a public fixture that the operator is authorized to read. Bind the run to
an explicit full commit ID and create a new private temporary directory. Never
archive `HEAD`, reuse a pre-existing destination, or index the source checkout.

```bash
set -eu

: "${PILOT_SOURCE_REPO:?set an authorized public-fixture checkout}"
: "${PILOT_SOURCE_COMMIT:?set the exact 40-hex commit}"

case "$PILOT_SOURCE_COMMIT" in
  [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
  *) echo "PILOT_SOURCE_COMMIT must be a full lowercase commit ID" >&2; exit 2 ;;
esac

resolved_commit="$(git -C "$PILOT_SOURCE_REPO" rev-parse --verify \
  "$PILOT_SOURCE_COMMIT^{commit}")"
[ "$resolved_commit" = "$PILOT_SOURCE_COMMIT" ] || {
  echo "source commit did not resolve exactly" >&2
  exit 2
}

PILOT_RUN_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/graphify-scip-pilot.XXXXXXXX")"
cleanup() {
  chmod -R u+w -- "$PILOT_RUN_ROOT" 2>/dev/null || true
  rm -rf -- "$PILOT_RUN_ROOT"
}
trap cleanup EXIT HUP INT TERM

PILOT_COPY="$PILOT_RUN_ROOT/repo"
mkdir -m 700 -- "$PILOT_COPY"
[ -z "$(find "$PILOT_COPY" -mindepth 1 -print -quit)" ] || {
  echo "pilot destination is not empty" >&2
  exit 2
}

git -C "$PILOT_SOURCE_REPO" archive --format=tar "$resolved_commit" |
  tar -xf - -C "$PILOT_COPY"
[ -n "$(find "$PILOT_COPY" -mindepth 1 -print -quit)" ] || {
  echo "pilot archive produced an empty fixture" >&2
  exit 2
}
readonly PILOT_RUN_ROOT PILOT_COPY resolved_commit
```

The trap owns only the newly allocated `mktemp` directory. The protocol never
accepts an operator-selected cleanup target.

## Copy-only fixture preparation

If the selected indexer requires static package metadata, make the minimum
change inside `PILOT_COPY` only and record the patch in the run evidence. Do not
prescribe source-package names, modules, test paths, or symbol descriptors in
this public protocol. The fixture preparation must be deterministic and must
not read from the source checkout after the archive is created.

## Index, convert, and validate

Indexing remains blocked until the fail-closed toolchain gate above is
satisfied. The operator-owned runbook must record the exact argv and environment
for the verified runner; this document deliberately does not provide a package
manager or launcher command.

After the network-denied indexer produces `index.scip` inside `PILOT_COPY`:

1. verify the pinned Go `scip` binary digest again and record `scip version`;
2. dump `index.scip` to JSON inside `PILOT_RUN_ROOT`;
3. run `tooling/scip_convert.py` with `--root "$PILOT_COPY"`;
4. run `tooling/validate.py` against `PILOT_COPY`; and
5. preserve the source commit, lock-record digest, exact argv, input/output
   digests, validation output, and resource measurements as one run record.

No output filename, symbol count, graph fingerprint, module name, test name,
descriptor shape, or coupling statistic from a protected corpus belongs in
this protocol.

## Converter acceptance

Before a fixture run, exercise the converter with a generated public synthetic
index that covers definitions, references, relationships, self-reference
filtering, and local-symbol filtering. Require byte-identical output from file
and standard-input paths and require `tooling/validate.py` to pass. Synthetic
success proves converter mechanics only; it does not validate an indexer,
fixture, deployment profile, or broader corpus.

## Success criteria

Extension beyond the one public fixture is out of scope unless every criterion
below is recorded for a fresh, independently reviewable run:

1. the source commit and every executable byte are immutably bound as specified
   by the lock gate;
2. indexing runs with network access denied and no package/JVM bootstrap;
3. validation has no new fatal class, with warnings recorded rather than
   silently accepted;
4. repeated conversion of the same index is byte-identical;
5. edge growth stays below an operator-declared bound established from public
   fixture evidence;
6. peak memory, latency, and throughput are measured on the deployment target
   with the exact concurrency/thread/context parameters recorded; and
7. symbol-alias behavior is either normalized or explicitly bounded by a
   public-fixture baseline.

Authority effect: none. This protocol does not authorize installation,
network access, protected-repository access, pilot execution, promotion, or
deployment.
