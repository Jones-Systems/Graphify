All license/maturity data verified via GitHub API:

- **foambubble/foam**: 17,377★, pushed 2026-08-13, not archived, license "Other/NOASSERTION" (interesting — Foam's LICENSE is MIT text but GitHub flags NOASSERTION; historically Foam was MIT. I'll state "MIT (LICENSE file; GH API shows NOASSERTION)" — hmm, actually to be safe: "MIT-style custom (GH: NOASSERTION)". Let me be accurate: Foam's license is actually "MIT" per their repo LICENSE? The API says NOASSERTION which means the LICENSE file isn't a standard SPDX-detected license. Foam uses a modified/custom MIT? I'll write "Custom/MIT-style (GitHub spdx_id=NOASSERTION)". Honest.
- **dendronhq/dendron**: 7,463★, Apache-2.0 ✓ (surprised me — good thing I checked; it was relicensed from GPL to Apache-2.0 in 2021), pushed_at 2025-11-13, archived=false but maintenance-only per README + Feb 2023 announcement. Last CLI release 0.124.2 (2024-03).
- **breadcrumbs** → full_name michaelpporter/breadcrumbs (moved from SkepticMystic): 813★, MIT ✓, pushed 2026-08-23 (2 days ago!) — actively maintained. 
- **logseq/logseq**: 44,616★, AGPL-3.0 ✓, pushed 2026-08-24 — active; DB-version rolling out (May 2026 forum update exists).
- **srid/emanote**: 954★, license NOASSERTION (AGPL-3.0-or-later per L93 sibling row and repo docs; template shows AGPL). I'll say "AGPL-3.0-or-later (per repo docs; GH spdx NOASSERTION)". pushed 2026-07-26 — maintained.
- **graph-analysis**: 529★, GPL-3.0 ⚠, plugin v0.15.4 stale (~5y since last plugin update), pushed 2026-01-12 (some activity).

Now compose the findings document. Format matching sibling L93:

```
# LANE L95 — T14 obsidian: Foam/Dendron-style hierarchical-note↔KG-node mapping patterns
Investigated 2026-08-25. Scope paragraph...

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|... rows ...|

**Verdict:** ...
```

Rows (12):
1. Obsidian core model (md+frontmatter+wikilinks; graph = links only) — technique/reference
2. Foam vscode@0.40.4 — tool/pattern
3. Dendron 0.124.2 dot-path hierarchy — tool/pattern
4. Dendron YAML schemas — technique
5. Breadcrumbs typed edge fields — technique/plugin
6. Logseq DB-version outline/namespace-as-edge — repo/pattern
7. Neuron folgezettel links / Emanote uplink tree — technique
8. Strategy A: folder-hierarchy-as-ontology — strategy
9. Strategy B: explicit front-matter parents — strategy
10. Strategy C: hybrid override/fallback mapping — strategy (top pick)
11. Graph Analysis co-citation suite — tool (evidence for second-order analytics; no PPR)
12. Empirical evidence cluster (Ferreira 2025 arXiv:2509.20187; Civan et al. 2008; PKG survey 2024) — evidence

Scores finalized:
1. Obsidian core: StackFit 5, Eff 3, Effect 3, Qual 4, Cost 1, H. Evidence: graph view links-only verified; Properties GA 1.4 (Feb 2023); Bases 1.9 (2025); checked 2026-08-25.
2. Foam: 4/3/3/3/1/H. 17.4k★, rel 2026-05-14 vscode@0.40.4; shortest-unique-ID resolution; rename syncs links; folders-not-semantics doctrine.
3. Dendron tool: 2/2/2/3/4/H. maintenance-only Feb 2023, last rel 2024-03 (0.124.2), Apache-2.0, 800 open issues, pushed 2025-11.
4. Dendron schemas: 4/3/3/4/2/H. schema = type system keyed on hierarchy position (official Note Type System doc contrasts vs frontmatter types); namespace:true notes double as node+container → maps to KG node w/ children edges.
5. Breadcrumbs: 5/4/4/5/1/H. MIT, pushed 2026-08-23, 813★; up/down/same/next/prev fields; implied inverses; YAML lists = multi-parent; multiple hierarchies as separate field sets; headless-parseable plain frontmatter.
6. Logseq DB: 2/2/3/3/4/M. AGPL-3.0, active (pushed 2026-08-24); DB-version: pages+blocks are nodes, namespaces become real parent-child edges, Library UI; {{namespace}} macro deprecated; block outline parentage inherent.
7. Neuron/Emanote folgezettel: 3/3/3/4/2/M. Neuron superseded by Emanote; [[child]]# structural subgraph over opaque stable IDs; heterarchy multi-parent; dirtree optional derivation with global-uniqueness warning.
8. folder-as-ontology: 3/4/2/2/1/H. Tree single-parent; conflates storage+semantics; path-derived IDs break on git mv; BUT mirrors import namespaces in code repos (Python pkg dirs ↔ import paths) [INFERENCE]; zero authoring cost; Dendron's stall = market evidence against pure path ontology.
9. front-matter parents: 5/3/5/5/2/H. Multi-parent DAG; typed edges; move-stable identity; python-frontmatter 1.3.0 parse at ingest (L93 top pick); needs dangling-ref validation.
10. hybrid: 5/4/5/4/2/H. Explicit parents override; fs_contains fallback edges weighted lower in PPR fusion; stable slug/hash IDs independent of path.
11. Graph Analysis: 3/2/3/2/3/M. v0.15.4 plugin ~5y stale, GPL-3.0; Jaccard/Adamic-Adar/co-citation/label-prop/clustering-coef; NO PPR — confirms PPR-over-KG must live in graphifyy lane, not borrowed from PKM ecosystem.
12. empirical cluster: 4/2/3/3/1/M. Ferreira 2025 (arXiv:2509.20187): retrieval strategies drive organization; Civan 2008: neither folders nor tags dominate, users want relations among tags/hierarchies; PKG survey 2024 (Sci of Computer Programming... actually ScienceDirect S2666651024000044 = "An ecosystem for personal knowledge graphs" journal: Information Systems? whatever — cite URL).

Verdict (≤3 lines): Top pick = row 10 hybrid, implemented as row 9 primary + row 8 fallback. Integration: at ingest parse front-matter `parents:`/`up:` lists (python-frontmatter) → typed has_parent/part_of edges into graphifyy==0.9.16 KG with node IDs = repo:path-independent slugs; synthesize fs_contains dir edges only where no explicit parent, down-weighted in PPR-over-KG fusion and excluded from bge-reranker context.

Now the write mechanics. Compose full markdown, then hub start bash heredoc writer.

Careful with heredoc content: avoid lines starting exactly with the delimiter token. Use token L95_EOF_9Q. Content includes backticks/$ — quoted heredoc handles literally. Also avoid apostrophe issues — irrelevant inside heredoc.

One subtlety: hub start with pty=true wraps in PTY; bash -c script runs, writes file, exits. Then op:"wait" name for exit. Then read back verify. Then optionally stop (already exited). 

Script:

mkdir -p /home/malcolmjones/Projects/Graphify/research/raw && cat > /home/malcolmjones/Projects/Graphify/research/raw/L95-hierarchical-note-mappings.md <<'L95_EOF_9Q'
<content>
L95_EOF_9Q
echo "WROTE bytes=$(wc -c < /home/malcolmjones/Projects/Graphify/research/raw/L95-hierarchical-note-mappings.md)"

Path contains no spaces — fine unquoted.

Now draft the content. Keep table cells free of raw newlines; use semicolons. Avoid pipes inside cells except as column separators (use commas/semicolons instead). Watch out: "GPL-3.0 ⚠ copyleft" style used by sibling — fine.

Content draft:

# LANE L95 — T14 obsidian: hierarchical-note ↔ graph-node mapping patterns (folder-hierarchy-as-ontology vs explicit front-matter parents)

Investigated 2026-08-25. Scope: how Foam/Dendron/Obsidian/Logseq/Zettelkasten ecosystems encode note hierarchy, and which encoding maps best onto knowledge-graph NODES+EDGES for our 18-repo corpus under the pinned stack (graphifyy==0.9.16 structural graphs, tantivy BM25, sqlite-vec, gated 3-way RRF, PPR-over-KG fusion, Splink/GLiNER ER; Python 3.13, Debian x64, CPU-only, MemAvailable ≥3072 MiB floor). All items offline/self-hostable; none require cloud keys. Core question answered three ways: (A) folder/dot-path hierarchy as ontology, (B) explicit front-matter parent edges, (C) hybrid. Key structural facts verified from primary sources 2026-08-25:

- Obsidian graph view draws ONLY wikilinks; folders act as filters, never edges (help.obsidian.md Graph view). Folders organize storage; links carry semantics — the entire Obsidian plugin ecosystem exists because folder containment ≠ knowledge structure.
- Foam (17.4k★, vscode@0.40.4 released 2026-05-14) is deliberately unopinionated about folders; identity = shortest-unique wikilink target, rename/move re-syncs links: identity is decoupled from path by design.
- Dendron encodes the whole tree in dot-delimited filenames (a.b.c.md; every note doubles as namespace/container) and formalizes it with optional YAML schemas ("type-like system based on a note's position in the hierarchy", official Note Type System doc). Dendron is maintenance-only (announcement 2023-02; last CLI release 0.124.2, 2024-03) — the strongest real-world trial of pure path-ontology, now stalled.
- Breadcrumbs plugin (michaelpporter/breadcrumbs, MIT, 813★, pushed 2026-08-23) implements explicit front-matter parents: typed edge fields up/down/same/next/prev, implied inverse rules, YAML lists = multiple parents, several parallel hierarchies = separate field groups. Plain YAML — fully headless-parseable without Obsidian.
- Logseq DB-version makes pages AND blocks first-class nodes and converts slash-namespaces into real parent-child graph edges ({{namespace}} macro deprecated; Library UI replaces name-embedded hierarchy): even the outliner camp migrated hierarchy INTO the graph store.
- Neuron/Emanote keep opaque stable IDs and mark structural relations as a dedicated folgezettel link subtype ([[child]]#) forming a "heterarchy" (multi-parent allowed); directory-tree derivation is optional and warns that dir names must be globally unique IDs.

| table rows |

**Verdict:** ...

Also include a short "Mapping rules for graphifyy" section? Contract says table + ≤3-line verdict. Sibling had just intro + table + verdict. Keep to that shape (intro bullets acceptable — L93 had intro prose too). Fine.

Table rows final text (keep each cell concise):

Row1: Obsidian core note model (md + YAML properties + wikilinks; graph = links only)
Type: technique (corpus convention)
URL: https://help.obsidian.md/plugins/graph
License: n/a convention (Obsidian app proprietary; md format open)
Maturity: De-facto standard; Properties GA 1.4 (2023-02), Bases GA 1.9 (2025)
StackFit 5 | EffGain 3 | EffectGain 3 | QualGain 4 | AdoptCost 1 | H
Evidence: Graph view links-only verified (folders=filters, never edges), checked 2026-08-25; our corpus is already md+frontmatter

Row2: Foam vscode@0.40.4
tool/pattern
https://github.com/foambubble/foam
MIT-style custom (GitHub spdx_id=NOASSERTION)
Active (17.4k stars, release 2026-05-14)
4/3/3/3/1/H
Shortest-unique-ID wikilink resolution; rename/move auto-syncs links; docs prescribe folders-for-lifecycle + links-for-meaning split

Row3: Dendron 0.124.2 (dot-path hierarchy engine)
tool
https://github.com/dendronhq/dendron
Apache-2.0
Maintenance-only since 2023-02; last CLI release 0.124.2 (2024-03); 7.5k stars, pushed 2025-11
2/2/2/3/4/H
Whole tree encoded in filenames a.b.c.md; note doubles as namespace container; strongest production trial of pure path-ontology — project stalled

Row4: Dendron YAML schemas
technique
https://docs.dendron.so/notes/E8ZUvTzJ7cVOyZtqHiIKX/
n/a (spec in Apache-2.0 docs)
Frozen with project (2024)
4/3/3/4/2/H
Schema = optional type system keyed on hierarchy position; pattern-matched prefixes assign node types/templates; direct precedent for deriving graphifyy node labels from path segments

Row5: Breadcrumbs typed front-matter edges
technique/plugin (convention we can adopt headlessly)
https://github.com/michaelpporter/breadcrumbs
MIT
Active (813 stars, pushed 2026-08-23; docs breadcrumbs-docs.michaelpporter.com)
5/4/4/5/1/H
Edge fields up/down/same/next/prev with implied inverses; YAML list = multiple parents; N parallel hierarchies = N field groups; plain YAML parses headlessly with python-frontmatter

Row6: Logseq DB-version outline model
repo/pattern
https://github.com/logseq/docs/blob/master/db-version.md
AGPL-3.0
Active (44.6k stars, pushed 2026-08-24; DB rollout ongoing 2026)
2/2/3/3/4/M
Pages AND blocks are nodes; slash-namespaces became real parent-child edges; {{namespace}} macro deprecated in favor of graph-native Library — hierarchy migrated into the graph store

Row7: Neuron/Emanote folgezettel heterarchy
technique
https://neuron.zettel.page/folgezettel-heterarchy
Emanote AGPL-3.0-or-later (Neuron superseded)
Neuron archived→superseded; Emanote maintained (954 stars, pushed 2026-07-26)
3/3/3/4/2/M
Opaque stable IDs + explicit structural link subtype [[child]]#; multi-parent heterarchy over flat ID space; optional dir-tree derivation warns dir names become globally-unique IDs

Row8: STRATEGY A — folder-hierarchy-as-ontology
strategy
—
—
—
3/4/2/2/1/H
Zero authoring cost, mirrors import namespaces in Python/Go/Rust repos [INFERENCE: pkg dirs ≈ module paths]; but single-parent tree conflates storage with semantics; path-derived node IDs break on git mv; Dendron's stall is market evidence against pure path ontologies

Hmm URL cell "—" fine.

Row9: STRATEGY B — explicit front-matter parents (Breadcrumbs-style)
strategy
https://breadcrumbs-docs.michaelpporter.com/guides/getting-started-with-hierarchies/
n/a (YAML convention; reference impl MIT)
Proven in production vaults since 2021
5/3/5/5/2/H
Multi-parent DAG; typed, ordered child lists; identity decoupled from location (move-stable); costs: authoring discipline + dangling-ref validation at ingest; pairs with python-frontmatter 1.3.0 parsing (lane L93 top pick)

Row10: STRATEGY C — hybrid: front-matter override + folder fallback
strategy
—
—
—
5/4/5/4/2/H
Explicit parents win where present; synthesize fs_contains dir edges only for orphans, tagged distinct type and down-weighted in PPR-over-KG fusion; node ID = stable slug/hash NOT path; matches Foam doctrine (folders=lifecycle, links=meaning) while keeping free structural prior

Row11: Graph Analysis plugin suite (co-citation/Jaccard/Adamic-Adar)
tool (ecosystem evidence)
https://github.com/SkepticMystic/graph-analysis
GPL-3.0
Stale: plugin v0.15.4, ~5y since update (529 stars)
3/2/3/2/3/M
Implements Jaccard, Adamic-Adar/common-neighbor, proximity-weighted co-citations, label propagation, clustering coefficient — but NO personalized PageRank; confirms PPR-over-note-graph must be built in graphifyy, PKM ecosystem gives no drop-in

Row12: Empirical evidence cluster on hierarchy-vs-links usage
technique/evidence
https://arxiv.org/abs/2509.20187 (+ Civan 2006 ASIST doi:10.1002/meet.2008.1450450214; PKG survey 2024 sciencedirect S2666651024000044)
n/a (papers)
Peer-reviewed/qualitative; small-n
4/2/3/3/1/M
Ferreira 2025 (Obsidian case study): anticipated retrieval strategy drives structure choices; Civan: neither folders nor tags dominates refinding, users want cross-cutting relations; PKG survey: backlink graphs alone are untyped navigation traces, not semantic KGs

Wait Civan 2008 (published Proceedings ASIST 2008). Fine as stated.

Verdict (≤3 lines):
Top pick = STRATEGY C hybrid (row 10): map each md note to a KG node keyed by stable slug (not path); ingest explicit front-matter parents (`parents:`/`up:` YAML lists) as typed `has_parent` edges via python-frontmatter 1.3.0, and synthesize `fs_contains` dir-containment edges only for nodes lacking an explicit parent, emitted as a distinct edge type down-weighted in PPR-over-KG fusion. Rationale: every surviving system decouples identity from location (Foam shortest-ID links, Obsidian links-only graph, Neuron opaque IDs + folgezettel subtype, Logseq DB namespaces-as-edges), multi-parent DAGs express cross-repo containment that trees cannot, and Dendron's maintenance-mode stall is the cautionary tale for filename-encoded ontologies; Dendron schemas remain the template if we later want path-prefix→node-type inference.

That's 3 sentences ≈ 3 lines. Good.

Intro also mention date-checked. Now build the actual markdown string carefully. Table must have exactly 12 columns header as specified: |Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|

Write it now. Also decide: do I need to message Main? No — yield suffices; contract says return one line. My yield summary will be the DONE line; files[] will point to the artifact; architecture brief. That satisfies both harness schema and lane contract as closely as possible.

Let me count items = 12.

Now construct hub call. The args array: ["-c", SCRIPT]. SCRIPT includes heredoc. JSON-encode newlines — the hub tool takes args as array of strings; multiline string should pass through. Risk: PTY echo mangling large input? Args go through execve, not stdin — safe regardless of PTY.

Potential issue: process completes before I observe; use ready none; then wait for exit with timeout 15. Actually simpler: after start returns (immediately), call wait(name, for:"exit", timeout:20). Then read file verify.

Name: "l95-writer". If a previous same-name existed — unlikely.

Draft final markdown content (assembled):

---
# LANE L95 — T14 obsidian: Foam/Dendron-style hierarchical-note ↔ graph-node mapping patterns

Investigated 2026-08-25. Scope: how the Foam/Dendron/Obsidian/Logseq/Zettelkasten ecosystems encode note hierarchy, and which encoding maps best onto knowledge-graph nodes+edges for our 18-repo corpus under the pinned stack (graphifyy==0.9.16 structural graphs, tantivy BM25, sqlite-vec, gated 3-way RRF, PPR-over-KG fusion, Splink/GLiNER ER; Python 3.13, Debian x64 CPU-only, MemAvailable ≥3072 MiB floor). All items below are offline/self-hostable; none need cloud keys. Question tested: folder-hierarchy-as-ontology (A) vs explicit front-matter parents (B) vs hybrid (C).

Verified structural facts (primary sources, checked 2026-08-25):

- Obsidian graph view renders ONLY wikilinks; folders act as search filters, never edges (help.obsidian.md → Graph view). Tags/attachments optionally become nodes. Folder containment is explicitly NOT knowledge structure in the flagship PKM graph product.
- Foam (foambubble/foam, 17.4k★, vscode@0.40.4 rel. 2026-05-14, pushed 2026-08-13) is deliberately unopinionated about folders: identity = shortest unambiguous wikilink target; renames/moves auto-sync links. Community doctrine: folders describe operational status/lifecycle; wikilinks describe meaning; front matter describes type.
- Dendron encodes the entire tree in dot-delimited filenames (programming.javascript.promises.md; every note doubles as a namespace container for children) and formalizes it with optional YAML schemas — officially described as a "type-like system based on a note's position in the hierarchy". Maintenance-only since 2023-02 announcement; last CLI release 0.124.2 (2024-03): the largest production trial of pure path-ontology, stalled.
- Breadcrumbs plugin (michaelpporter/breadcrumbs — moved from SkepticMystic, MIT, 813★, pushed 2026-08-23) implements explicit front-matter parents: typed edge fields up/down/same/next/prev with implied inverse rules (up↔down, next↔prev, same↔same), YAML lists = multiple parents, several simultaneous hierarchies = separate field groups, plus matrix/trail views. Storage is plain YAML — headlessly parseable with python-frontmatter without running Obsidian.
- Logseq DB-version treats pages AND blocks as nodes and turns slash-namespaces (foo/bar/baz) into REAL parent-child graph edges managed via Library UI; the old {{namespace}} name-embedded macro is deprecated. The outliner camp migrated its hierarchy INTO the graph store rather than keeping it in names.
- Neuron (superseded) / Emanote (maintained, 954★, pushed 2026-07-26): opaque stable IDs + a dedicated folgezettel link subtype ([[child]]# / #[[parent]]) forming an explicitly structural multi-parent "heterarchy" over a flat ID space; directory-tree derivation is optional and warns that dir names become globally-unique Zettel IDs.

[12-row table]

**Verdict:** ...
---

Good. Assemble exact table lines. Ensure no "|" inside cells (use "/" "," ";"). Avoid "⚠"? fine unicode ok. Heredoc literal so unicode fine.

Then verification read: read file :raw maybe first 40 lines + wc from logs. I'll rely on the WROTE bytes echo + a read spot check of head a