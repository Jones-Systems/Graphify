# Runbook

## Install (fresh host)

```bash
tooling/install.sh          # bootstraps venv without ensurepip, verifies hashes, smoke-tests CLI
```

## Deploy policies

```bash
for c in policies/*/; do c=${c#policies/}; c=${c%/}
  mkdir -p ~/.agent-references/graphify/$c/policy
  cp policies/$c/ignore.rules ~/.agent-references/graphify/$c/policy/; done
```

## Build wave (all corpora, sequential, RAM-guarded)

```bash
GF_TRACKED_ONLY=1 tooling/build-all.sh            # skips corpora with current pointer
FORCE=1 tooling/build-all.sh                      # rebuild everything
tooling/build-graph.sh <corpus> <root> [chunk]    # single corpus/chunk
```

Every build writes: `preflight.json`, `graph.json`, `validation.json`,
`freshness.json`, MemAvailable timeline in `build-log.txt`.

## Promotion (independent gate)

```bash
tooling/promote.sh <corpus> <run-dir> x --verified-by "<verifier session + evidence>"
```

Refuses without verifier attribution. Repoints `<corpus>/current` atomically.

## Toggle (assistant-facing integration)

```bash
tooling/toggle.sh status | disable | enable | verify
```

Cycle: disable → preservation bundle + fresh-session probe (expect
undiscoverable) → `verify` → enable → fresh-session probe → `verify`.
State vocabulary per INACT-C31.

## Refresh a single corpus after upstream changes

```bash
GF_TRACKED_ONLY=1 tooling/build-graph.sh codex-v3 /home/malcolmjones/Projects/Codex-V3 ""
tooling/promote.sh codex-v3 <new-run-dir> x --verified-by "..."
```
