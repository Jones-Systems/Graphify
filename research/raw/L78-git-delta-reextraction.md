# LANE L78 — T12 freshness: Git-delta driven re-extraction into the code graph
Date recorded: 2026-08-25. Scope: Git-based change detection between
refreshes, cross-file edge correctness risks, and public tooling precedents.
No target inventory, cost, cadence, or runtime is established.

## Cost boundary

The generic break-even condition is
`changed_fraction × extract_cost + reconciliation_overhead + baseline_bookkeeping < full_rebuild_cost`.
The reviewed input did not provide public, immutable evidence for any operand,
so no target timing or break-even point is retained.

## Correctness risks (cross-file edges et al.), ranked

1. **Stale cross-file edges** — unchanged caller file A references symbols redefined in changed file B; naive file-level delta leaves A→B_old edges. Fix: two-phase reconciliation — compute *changed-symbol set* ⊆ changed-file set, recompute every edge whose endpoint qualified-name is in that set (requires name-keyed edge index or name-stable IDs). This is THE load-bearing piece.
2. **Wrong/missing baseline SHA** — assuming HEAD~1 or a stale stored SHA silently misses changes after rebase/amend/force-push/shallow clone. Fix: store per-repo `indexed_sha`; verify reachability (`git cat-file -e prev^{commit}`) else fall back to FULL rebuild. Never assume HEAD~1.
3. **Untracked files invisible to diff** — `git diff` does not show untracked paths (git-scm docs). Fix: union with `git status --porcelain=v1 -uall`.
4. **Deletions/renames orphan nodes+edges** — must handle D/R/T diff-filter letters and cascade-delete incident edges both directions, not just insert additions.
5. **Working tree ≠ HEAD during refresh** — indexing uncommitted files while commits move can mix source states. Bind every run to its declared source mode and revision.
6. **Torn state on crash** — mixed-version graph. Use staged output plus an atomic promotion boundary.
7. **Cross-repo edges** — repo B's edges into changed repo A are invisible to A-local git delta. A qualified-name registry plus a policy-defined full comparison is one candidate backstop; cadence requires measurement.
8. **Generated-noise churn** — generated or vendored paths can dominate raw diff volume; filters must be explicit, versioned, and tested.
9. **Global score staleness** — centrality or ranking computed before the delta becomes approximate; choose full recomputation or a validated incremental algorithm from measurements.

Recorded prior art shows different boundaries: CodeQL documents an overlay
flow for pull-request analysis, SCIP indexers emit repository snapshots, and
the archived stack-graphs project discussed blob-ID caching. None supplies a
complete target refresh protocol.

## Findings table

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|Git plumbing change detection: `diff --name-status -M --diff-filter=ACDMRT <base> HEAD` plus an explicit uncommitted-source policy|tool|https://git-scm.com/docs/git-status.html ; https://git-scm.com/docs/diff-options|GPLv2 (git binary)|mature Git interface|5|4|3|4|0|H|`git diff` does not enumerate untracked paths; porcelain status can do so. Rename and type-change handling must be explicit.|
|Stored-baseline revision plus reachability check and full fallback|technique|https://git-scm.com/docs/git-cat-file; https://github.com/sourcegraph/zoekt|public Git docs; Zoekt Apache-2.0|public precedent|5|2|4|5|0|H|Verify that the stored base is a reachable commit before using a delta. The recorded Zoekt source is a precedent for comparing stored branch/commit state and falling back.|
|Staged transactional refresh|technique|https://www.sqlite.org/lang_transaction.html|public domain|standard transaction pattern|5|2|5|4|1|H|Build and validate staged state before one explicit promotion boundary; exact delete/upsert and swap mechanics depend on the selected store.|
|Changed-symbol edge reconciliation|design lead|https://arxiv.org/abs/2211.01224|paper|unverified target design|5|3|5|5|2|M|The stack-graphs paper formalizes per-file subgraphs and later stitching. A changed-symbol reconciliation algorithm and completeness proof remain target work.|
|GitHub stack-graphs / tree-sitter-stack-graphs|repo|https://github.com/github/stack-graphs|MIT OR Apache-2.0|ARCHIVED 2025-09-09; core v0.14.1, tsg v0.10.0 2024-12-13|3|2|4|3|3|H|Archived read-only Sept 2025 → DO NOT adopt; its blob-ID caching idea (discussion #263) validates design|
|Zoekt `zoekt-git-index -incremental` (default true) + `-delta` mode|tool|https://github.com/sourcegraph/zoekt/blob/main/cmd/zoekt-git-index/main.go|Apache-2.0|active (Sourcegraph maintains; PR #1050 branch-aware delta)|3|3|3|4|1|H|Incremental-by-default trigram indexer; prior art + optional lexical layer; falls back to full rebuild when state diverges|
|Universal Ctags 6.2.1 JSONL per-file shards (`--append` is NOT update-safe)|tool|https://docs.ctags.io/en/latest/man/ctags.1.html|GPL-2.0|mature (rel 2025-10-25)|3|3|2|3|1|H|Docs: append adds without dedup/delete → regenerate changed file's shard; matches per-file staging|
|Watchman since-cursor file watching|tool|https://github.com/facebook/watchman|MIT|active weekly releases on recorded date|2|1|2|2|2|H|A cursor-based watcher is a possible lower-latency input, but necessity and correctness require a measured cadence and overflow policy.|
|GitPython 3.1.59 vs pygit2 1.20.0 vs plain subprocess git|tool|https://pypi.org/project/GitPython/ ; https://pypi.org/project/pygit2/|BSD-3 / GPLv2+linking-exception|current (both rel Aug 2026)|4|1|1|2|0|H|Subprocess git = zero deps, sufficient at scale; GitPython ≥3.1.59 required (≤3.1.58 vulns GHSA-284h-m62q-gf8w)|
|Periodic full-rebuild backstop + drift audit against `git ls-files`|strategy|https://git-scm.com/docs/git-ls-files|n/a|standard correctness backstop|5|1|5|5|0|H|A full comparison can detect missed-change classes. Cadence and cost require measurement.|
|Rename awareness `-M` + blob-tree-hash equality for moved identical content|technique|https://git-scm.com/docs/diff-options|n/a|maximal (git built-in)|3|2|1|2|0|H|Similarity-threshold misses degrade safely to delete+add under content-hash IDs|

## Verdict
Recorded candidate: Git plumbing with a stored reachable base revision, staged
refresh, changed-symbol reconciliation, and a periodic full comparison.
Whether uncommitted files participate is an explicit source-mode decision.
Generated-path filters, deletion and rename semantics, edge reconciliation,
promotion, base advancement, and fallback behavior require deterministic tests;
an unreachable base must force a full rebuild. No cost advantage is claimed.

### Key sources (all accessed 2026-08-25)
- git-scm.com/docs/git-status.html, /docs/diff-options (porcelain v1, -uall, ACDMRT, rename detection)
- github.com/github/stack-graphs/releases + commits (archived 2025-09-09); discussion #263; arxiv.org/abs/2211.01224
- github.com/sourcegraph/zoekt cmd/zoekt-git-index/main.go, cmd/zoekt-sourcegraph-indexserver/main.go, LICENSE (Apache-2.0), PR #1050
- docs.ctags.io ctags.1 (--append semantics), releases (6.2.1, 2025-10-25)
- github.com/facebook/watchman/releases (weekly through v2026.08.24.00, MIT)
- pypi.org/project/GitPython (3.1.59, 2026-08-10, BSD-3; GHSA-284h-m62q-gf8w); pypi.org/project/pygit2 (1.20.0, 2026-08-08, GPLv2+linking exception, libgit2 1.9.7)
- github.com/tree-sitter/tree-sitter-rust README benchmark (9.9 MB/s); tree-sitter issue #1277; docs.github.com CodeQL incremental-analysis page (overlay-only)
