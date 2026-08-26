# SCIP pilot protocol - R2 symbol edges (W1-c)

Prove the hash-pinned `scip` CLI + pure-stdlib converter path on ONE small
repo before extending SCIP ingestion to every corpus. Pilot repo:
**goal-autonomy** (`/home/malcolmjones/Projects/Goal-Autonomy`, 16 tracked
files, 11 `.py`). Every step below was executed and verified on this host
2026-08-25; results are recorded, not projected.

## Pins (authoritative values in tooling/requirements-scip.txt)

| tool | version | integrity |
|------|---------|-----------|
| Go `scip` CLI (github.com/scip-code/scip) | v0.9.0 | `scip-linux-amd64.tar.gz` sha256 `fc2e7273...fec75`, double-sourced: GitHub release-assets API `digest` field AND local sha256sum of the download agree; extracted binary reports `scip version v0.9.0` |
| @sourcegraph/scip-python | 0.6.6 (npm dist-tags.latest at pilot time) | fetched via `npx -y`; its native launcher bootstraps a JVM automatically |
| PyPI `scip` | NEVER INSTALL | unrelated GPL flow-cytometry package, not a SCIP client |

## Host prerequisites (verified here)

- `node`/`npm` available for `npx`.
- NO system java needed - the launcher fetches a JVM itself.
- `pip` MUST be resolvable on PATH or indexing aborts with "Could not find
  valid pip command" even though nothing is installed with it. This host has
  none; isolated workaround:
  ```bash
  python3 -m venv --without-pip /tmp/scip-venv
  curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
  /tmp/scip-venv/bin/python3 /tmp/get-pip.py -q
  export PATH=/tmp/scip-venv/bin:$PATH
  ```
- Python 3.13 triggers a benign "Python version ... is unsupported" notice
  from the bundled pyright; indexing still completed for all files.

## Protocol

1. Download + verify the pinned CLI exactly as written in
   tooling/requirements-scip.txt; `./scip version` must print v0.9.0.
2. Work on a tracked-only COPY so the indexer never writes into the real
   repo. scip-python indexes its CWD (a positional path is ignored) and
   drops `index.scip` into that CWD:
   ```bash
   mkdir -p /tmp/scip-run/repo
   git -C ~/Projects/Goal-Autonomy archive HEAD | tar -x -C /tmp/scip-run/repo
   cd /tmp/scip-run/repo
   ```
3. Make package metadata static IN THE COPY ONLY (upstream quirk:
   scip-python 0.6.6 crashes in `normalizeNameOrVersion` when
   `[project] version` is dynamic, and it wants a `[tool.pyright]` table):
   replace `dynamic = ["version"]` with `version = "0.0.0"`, then append:
   ```toml
   [tool.pyright]
   include = ["src", "tests"]
   ```
4. Index, dump, convert, validate:
   ```bash
   npx -y @sourcegraph/scip-python@0.6.6 index .          # -> index.scip
   scip print --json index.scip > goal-autonomy.index.json
   python3 tooling/scip_convert.py goal-autonomy.index.json \
     goal-autonomy.graph.json --root ~/Projects/Goal-Autonomy
   python3 tooling/validate.py goal-autonomy.graph.json \
     ~/Projects/Goal-Autonomy preflight.json run pin.json
   ```

## Recorded pilot results (2026-08-25)

| stage | result |
|---|---|
| indexing | 11 of 11 `.py` files ("Successfully wrote SCIP index"); index.scip 599,974 B |
| index JSON | 1,166,179 B (`scip print --json`) |
| converter output | **nodes=783 links=547** kinds={ref: 547} |
| node split | 608 defined in-corpus across 11 docs + 175 external dependency seeds (no source_file) |
| noise filtered | 2,282 `local N` function-local symbols dropped; self-links=0; anchorless docs=0 |
| validator | **PASS** nodes=783 edges=547 fatals=0 warn={external_bare_import:0, conservative_internal_looking:0} |
| graph fingerprint | sha256 `054a25becb3d9d57880d436beb4ba7454c2951ee1c79fbd96f091654cb4326b1` |
| top coupling | `src.goal_autonomy` module 188 deps, `cli` 121, `test_goal_snapshot_store` 58 |

Converter semantics used above (documented because SCIP fixes the data, not
the graph): one node per symbol string; source_file = first defining
document; cross-file references anchored on the document's module symbol
(descriptor ending `/__init__:`), falling back to its first definition;
intra-document references skipped; implements/type-def edges derive from
SymbolInformation.relationships when present.

Unresolved-class findings recorded during the pilot:

- `external_bare_symbol` count=175: never-defined symbols used as ref
  targets - mostly `python-stdlib 3.11` entities and `unittest.TestCase`,
  plus re-spelled in-corpus modules (next bullet). Kept as seed nodes;
  reported on stderr by the converter.
- scip-python 0.6.6 emits NO relationships and no `kind` field, so this
  pilot yields ref edges only. implements/type-def links activate without
  converter changes once a relationship-emitting indexer runs
  (rust-analyzer, scip-typescript).
- Descriptor aliasing: one module appears both as backticked definition form
  (`` `src.goal_autonomy.cli`/__init__: ``) and bare import form
  (`goal_autonomy.cli/__init__:`), producing near-duplicate nodes on
  import-heavy graphs. Acceptable at pilot scale; land a descriptor
  normalizer before corpus-wide promotion.
- `symbol_roles` arrives as an int bitmask (Definition=1, read-ref=8), not a
  name array; the converter accepts both encodings.

Synthetic acceptance (no real indexer needed): tooling/scip_convert.py is
smoke-tested against a handcrafted 2-document / 5-symbol index exercising
def/ref/implements/type-def/self-link/local filtering; the output passes
tooling/validate.py (nodes=5 edges=3 PASS) and is byte-identical across
file and stdin input runs.

## Success criteria for extending to all corpora

Extend corpus-by-corpus only when ALL hold:

1. validate.py returns PASS or PASS_WITH_WARNINGS with zero new fatal
   classes; record each graph's warning baseline per DEC-6 before moving on.
2. Edge budget sane: cross-file ref links within ~50x the file count of the
   corpus (pilot ratio: 547 edges / 11 files). A blowup means anchoring or
   local-filtering regressed - stop and re-check before promoting.
3. Determinism: converting an identical index twice produces byte-identical
   graph JSON (nodes and links are emitted sorted; asserted in smoke test).
4. RAM floor holds: pilot ran with MemAvailable >= 20 GiB against the
   3072 MiB floor; keep bulk SCIP runs behind the W1-b governor slices per
   the RANKING hard sequencer (no bursty jobs before B10 lands).
5. Descriptor normalizer decision recorded: either aliasing accepted with a
   recorded baseline or normalized before rollout.

