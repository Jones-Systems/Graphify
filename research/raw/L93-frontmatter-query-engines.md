# LANE L93 — T14 obsidian: Dataview-class local query engines over YAML front-matter
Investigated 2026-08-25. Scope: offline engines and tools that query
structured Markdown front matter without an Obsidian runtime. Public package
and project facts are retained as recorded; no later currentness, host fit, or
persistence architecture is claimed.

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|python-frontmatter 1.3.0|tool (lib)|https://pypi.org/project/python-frontmatter/|MIT|Stable, widely deployed (3.9M dl/wk; py≥3.10)|5|4|3|4|1|H|YAML/TOML/JSON handlers, lossless round-trip dumps, `parse()` split of metadata/body; checked on PyPI 2026-08-25|
|sqlite-utils 4.2.1|tool/strategy (CLI+lib)|https://github.com/simonw/sqlite-utils|Apache-2.0|Very active on recorded date|5|4|4|4|1|H|Provides FTS5 configuration, bulk insert/upsert, and schema transforms for SQLite; storage co-location is a separate design decision.|
|Datasette 0.65.3|tool (read-only server)|https://pypi.org/project/datasette/|Apache-2.0|Mature, stable (py≥3.9)|4|3|3|3|1|H|Web UI + JSON API over any SQLite file; optional human-facing exploration layer over the front-matter table|
|Tantivy fast-field aggregation extension|strategy (extend pinned index)|https://quickwit.io/blog/tantivy-0.22|MIT (matches tantivy core)|Core mature; exposure depends on the chosen binding|5|3|3|3|2|M|Tantivy 0.22 (2024-04-12): terms aggs (bool/ip/date), top_hits, faster columnar fast fields; FastFieldRangeQuery landed 0.24 — VERIFY that the chosen Tantivy binding exposes aggregation APIs before adopting|
|mdbasequery|tool (CLI+TS lib)|https://github.com/intellectronica/mdbasequery|MIT|Alpha/early (16★, but CI + cross-runtime conformance tests; npm-published)|3|4|4|4|2|M|Executes Obsidian-Bases `.base` YAML queries over plain md dirs WITHOUT Obsidian: filter expressions (`score >= 7`), formulas w/ topo deps, groupBy, summaries, sort/limit/projection; outputs json/jsonl/yaml/csv/md; Node 20+/Bun/Deno 2.x|
|zk v0.15.6|tool (Go binary)|https://github.com/zk-org/zk|GPL-3.0 ⚠ copyleft|Mature, active (2.8k★; latest release 2026-07)|3|4|3|3|2|H|SQLite-indexed vault; filters --tag (AND/OR/NOT/glob), --created/--modified ranges, --linked-by/--link-to ±recursive, --match fts\|exact\|re; CAVEAT: only title/date/modified/tags/aliases are first-class indexed keys — other front-matter keys are template-printable ({{metadata.key}}) but NOT directly filterable; 0.15.6 added frontmatter link parsing|
|mdq|tool (Rust binary)|https://github.com/yshavit/mdq|Apache-2.0 OR MIT|Active (1.7k★; needs rustc ≥1.85.1)|3|3|2|3|1|H|jq-for-markdown element selectors incl. front matter (`+++[toml\|yaml] pattern`) with regex/anchors, JSON output, grep-like exit codes; per-file structure extraction, NOT a cross-corpus metadata index|
|obsidiantools 0.11.0|tool (lib)|https://pypi.org/project/obsidiantools/|BSD-3-Clause|Niche, slow-moving on recorded date|4|3|3|3|1|M|Provides a headless vault graph plus tabular metadata, tag, and backlink indexes; its pandas/numpy/networkx/lxml dependency cost requires measurement.|
|gray-matter 4.0.3|technique (JS lib)|https://www.npmjs.com/package/gray-matter|MIT|Stable but stale (js-yaml ^3 pin; 9M dl/wk legacy)|3|3|2|3|2|H|De-facto JS front-matter parser; only relevant if we accept a Node pipeline — otherwise redundant vs python-frontmatter|
|Dataview (obsidian-dataview)|repo (baseline/reference)|https://github.com/blacksmithgu/obsidian-dataview|MIT|Mature (9.3k★) but REQUIRES Obsidian runtime|1|0|0|0|5|H|DQL/DataviewJS index over front-matter + inline fields; excluded as headless engine — retained as the semantics template for a mini-DQL→SQL mapping|
|Datacore|repo (watch)|https://github.com/blacksmithgu/datacore|MIT|WIP alpha ("work-in-progress successor", 2.2k★)|1|0|0|0|5|H|Obsidian-plugin build target (manifest.json/esbuild plugin install script); no headless mode today — re-check when stable|
|Obsidian Bases `.base` spec|technique|https://github.com/obsidianmd/obsidian-help/blob/master/en/Bases/Bases%20syntax.md|(app proprietary; schema docs public)|GA in Obsidian 1.9+ (2025)|2|3|3|4|3|M|Official serialized schema is plain YAML: filters (and/or/not trees), formulas, properties, summaries, views — machine-readable spec enables headless executors (see mdbasequery row); native runtime stays closed/Obsidian-bound|
|Emanote|tool (site gen + query embeds)|https://emanote.srid.ca/|AGPL-3.0-or-later ⚠ copyleft|Maintained on recorded date|2|2|3|3|4|M|Headless `query:` embeds plus search over Markdown/front matter; the Haskell/Nix runtime and AGPL license add adoption constraints.|

**Verdict:** The public comparison identifies `python-frontmatter` as a
parser candidate, `sqlite-utils` as a possible indexing helper,
`mdbasequery` as a headless `.base` query implementation, and `zk` as a
single-binary reference with a GPL license constraint. It does not select a
database, sidecar, schema, synchronization policy, or serving path. Parser
fidelity, query semantics, custom-key coverage, dependency cost, license fit,
and source currentness require fresh evaluation.
