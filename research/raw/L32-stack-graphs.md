# LANE L32 — GitHub stack-graphs: name-resolution quality (py/ts), maintenance state, integration cost

*Investigated 2026-08-25. Sources: GitHub repo/releases, crates.io, docs.rs, PyPI, BaseMind architecture docs.*

## Maintenance state (verified)
- github/stack-graphs ARCHIVED (read-only) since 2025-09-09; README banner: "no longer supported or updated by GitHub" (verified live).
- Final upstream release 2024-12-13: stack-graphs 0.14.1, tree-sitter-stack-graphs 0.10.0, -python 0.3.0, -typescript 0.4.0.
- No official successor. Maintained continuation: Goldziher/basemind fork (basemind-stack-graphs 0.14.1 et al., released 2026-07-20, tree-sitter 0.26 port, 2 stitching panics fixed; removed C FFI/serde/SQLite storage; ~40 downloads — bus-factor 1).
- BaseMind's own product uses stack-graphs only for Python(+Java); TS/JS switched to oxc_semantic+oxc_resolver — implicit verdict on TS rule maturity.

## Name-resolution quality
- PYTHON (-python 0.3.0, grammar 0.23.5): solid — 27-file corpus covers aliased/wildcard/relative/root-path imports, class members, superclasses, self, decorators, lambdas, nested functions, pattern matching, redundant re-exports. Known gap: chained_methods.py.skip. Crash fixes through v0.2.0 (2024-07).
- TYPESCRIPT (-typescript 0.4.0): weak — TSX added 2024-07; "basic tsconfig.json/package.json analysis"; heuristic path-based module resolution, no type-system awareness; parser crash tree-sitter-typescript#283 (generic type arg in decorator).

## Integration cost
- No official Python bindings. stack-graphs-python-bindings 0.0.14 (PyPI 2025-05-05, MIT, PyO3/maturin, >=3.12): Indexer(db,[Language]).index_all / Querier(db).definitions(Position) — cross-file def lookup works. Caveats: WIP 0.0.x API, 22 dl/wk, point-query only (no bulk ref->def dump), py3.13 wheels unverified.
- CLI route (cargo install --features cli ...; index / query definition PATH:L:C) also positional-only against SQLite cache DB; no bulk export.
- Bulk cross-file edges require a small Rust sidecar: per-file graphs from TSG rules, stitch per reference, emit ref->def JSONL -> merge into graphifyy graph edges feeding PPR fusion. Est. 2–4 days. Incremental indexing + lazy stitching = low RAM; offline; MIT OR Apache-2.0; fits CPU-only/no-GPU/MemAvailable-floor constraints.

## Findings table
|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|github/stack-graphs core lib 0.14.1 (frozen)|repo/tool|https://github.com/github/stack-graphs|MIT OR Apache-2.0|Frozen (archived 2025-09-09)|3|2|3|4|3|H|Archive banner verified 2026-08-25; last release 2024-12-13; 398K crate downloads|
|tree-sitter-stack-graphs 0.10.0 (CLI+lib)|tool|https://crates.io/crates/tree-sitter-stack-graphs|MIT OR Apache-2.0|Frozen, stable|3|2|2|3|2|H|index/query-definition by line:col into SQLite cache; no bulk JSON export; tree-sitter ^0.24 (docs.rs)|
|tree-sitter-stack-graphs-python 0.3.0 (py rules)|technique|https://crates.io/crates/tree-sitter-stack-graphs-python|MIT OR Apache-2.0|Mature-ish, frozen|4|3|4|4|2|H|27-file corpus: relative/aliased/wildcard imports, superclasses, pattern matching; gap: chained_methods.py.skip|
|tree-sitter-stack-graphs-typescript 0.4.0 (ts rules)|technique|https://crates.io/crates/tree-sitter-stack-graphs-typescript|MIT OR Apache-2.0|Immature, frozen|2|1|1|2|2|H|Basic tsconfig/package.json analysis; TSX only since 2024-07; crash tree-sitter-typescript#283; BaseMind dropped it for oxc|
|Goldziher/basemind fork (basemind-stack-graphs 0.14.1, ts 0.26 port)|tool/fork|https://github.com/Goldziher/basemind|MIT OR Apache-2.0|Active (2026-07-20), young|4|3|3|3|3|M|docs.rs ARCHITECTURE.md: 0.26 port, 2 panics fixed, storage/C-FFI removed; 40 downloads — bus-factor 1|
|stack-graphs-python-bindings 0.0.14 (PyPI)|tool/bindings|https://pypi.org/project/stack-graphs-python-bindings/|MIT|WIP 0.0.x (2025-05-05)|5|4|3|3|1|M|Indexer/Querier cross-file def lookup working (README); requires-python>=3.12; point queries only; 22 dl/wk; wraps frozen upstream|
|Strategy: py-only SG ref→def edges via sidecar → graphifyy+PPR; TS via oxc_resolver instead|strategy|(rows above)|n/a|n/a|5|4|4|4|3|M|SG fits offline/CPU/low-RAM; TS rules inadequate (ecosystem precedent); JSONL edge export merges into existing KG fusion|

Verdict: top pick — adopt stack-graphs for PYTHON ONLY (prototype via stack-graphs-python-bindings 0.0.14; productionize via basemind forked crates behind a small Rust sidecar emitting ref->def JSONL into graphifyy node edges feeding PPR fusion; est. 2–4 d). Skip TS rules — quality poor and ecosystem successor uses oxc; vendor/pin everything given upstream archival.