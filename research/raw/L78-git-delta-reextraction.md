PERSIST-NEEDED

# LANE L78 — T12 freshness: Git-delta driven re-extraction into the code graph
Date: 2026-08-25 · Scope: change detection via git between refreshes, cost model vs full rebuild at our scale, cross-file-edge correctness risks, tooling.

## Cost model at our scale (grounded)

**Corpus measured (directory listing of ~/Projects, 2026-08-25):** ~20 primary repos, each small-to-medium (largest files seen are lockfiles: uv.lock 476 KB, package-lock.json 212 KB, one 537 KB PNG; docs-heavy Python/TS/Go/Swift). Critically there are huge worktree farms (Codex-V3-worktrees alone lists "…113 more"; Universal-Agents ~27, CAAM ~17, growth-intel ~16, BusinessLessons ~14). If worktree checkouts enter the corpus, per-worktree `git status` runs multiply and identical-content files recur across worktrees — content-hash IDs dedupe them naturally.

**Extraction throughput:** official tree-sitter-rust benchmark: 2,157 lines parsed in 6.48 ms ≈ **9.9 MB/s ≈ 333k lines/s single core**; plausible native range **5–15 MB/s**, worst-case grammars ~1.3 MB/s (tree-sitter issue #1277). Even at a conservative effective 1 MB/s (parse + queries + SQLite writes, Python-bound):

| Scenario | Estimate [INFERENCE unless noted] |
|---|---|
| Total tracked text, 18–25 small repos | ~100–500 MB (order-of-magnitude) |
| Full rebuild, 1 core @ 1–5 MB/s effective | 1.5–8 min CPU |
| Full rebuild, 16-way parallel | **seconds to ~1 min wall clock** |
| RAM floor | tree-sitter+SQLite worker ≈ tens of MB × 16 ≪ 3072 MiB floor — never binding |
| Typical daily churn across 20 repos | tens–hundreds of files ≈ 1–5% of corpus → delta extract < 1–3 s |

**Break-even:** delta wins when `changed_fraction × extract_cost + reconciliation_overhead + baseline_bookkeeping < full_rebuild_cost`. At ~30 s full rebuilds, delta saves ~29 s/day at daily cadence — irrelevant. Delta matters only if refresh cadence is per-agent-session (many×/hour), where it cuts p99 refresh latency from ~30 s to ~2 s and avoids re-running downstream stages (edge resolution, ranking) globally. **Conclusion: adopt delta for latency/freshness, not throughput; keep full rebuild as cheap routine path.**

## Correctness risks (cross-file edges et al.), ranked

1. **Stale cross-file edges** — unchanged caller file A references symbols redefined in changed file B; naive file-level delta leaves A→B_old edges. Fix: two-phase reconciliation — compute *changed-symbol set* ⊆ changed-file set, recompute every edge whose endpoint qualified-name is in that set (requires name-keyed edge index or name-stable IDs). This is THE load-bearing piece.
2. **Wrong/missing baseline SHA** — assuming HEAD~1 or a stale stored SHA silently misses changes after rebase/amend/force-push/shallow clone. Fix: store per-repo `indexed_sha`; verify reachability (`git cat-file -e prev^{commit}`) else fall back to FULL rebuild. Never assume HEAD~1.
3. **Untracked files invisible to diff** — `git diff` does not show untracked paths (git-scm docs). Fix: union with `git status --porcelain=v1 -uall`.
4. **Deletions/renames orphan nodes+edges** — must handle D/R/T diff-filter letters and cascade-delete incident edges both directions, not just insert additions.
5. **Worktree ≠ HEAD during refresh** — indexing dirty worktree while commits move. Content-hash-keyed rows stay self-consistent regardless; record HEAD at refresh start.
6. **Torn state on crash** — mixed-version graph. Fixed staging + atomic swap already in stack covers this.
7. **Cross-repo edges** — repo B's edges into changed repo A are invisible to A-local git delta. Global qualified-name registry + nightly full pass backstops.
8. **Generated-noise churn** — uv.lock/package-lock rewrites dominate raw diff volume; filter `*.lock`, dist/, node_modules/ before counting changes.
9. **Global score staleness** — centrality/ranking computed pre-delta becomes approximate; recompute globally (cheap at <1M nodes) rather than approximating.

Prior art confirms the hard part is unsolved off-the-shelf: CodeQL `database create` is a full rebuild per commit (incrementality exists only as PR-flow `--overlay-base/--overlay-changes`); SCIP/LSIF indexers emit whole-repo snapshots; GitHub archived stack-graphs (2025-09-09) — the one purpose-built file-incremental name-resolution engine — leaving orchestration to integrators anyway (their own discussion #263 sketches blob-ID caching, validating our design).

## Findings table

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|Git plumbing change detection: `diff --name-status -M --diff-filter=ACDMRT <base> HEAD` ∪ `status --porcelain=v1 -uall`|tool|https://git-scm.com/docs/git-status.html ; https://git-scm.com/docs/diff-options|GPLv2 (git binary)|maximal|5|4|3|4|0|H|Untracked absent from diff, shown by porcelain -uall; ACDMRT filter letters; verified 2026-08-25|
|Stored-baseline-SHA protocol per repo + reachability check, FULL fallback|technique|https://git-scm.com/docs/git-cat-file|n/a (internal)|proven pattern (Zoekt compares stored branch+commit metadata)|5|2|4|5|0|H|Zoekt indexserver skips/updates/falls-back on stored commit state (sourcegraph/zoekt main.go, checked 2026-08-25)|
|Content-addressed deterministic IDs sha256(repo\|path\|content) for nodes/files|technique|internal|n/a|in-stack (deterministic-ID rebuilds)|5|3|5|5|1|H|Makes delta upserts idempotent, worktree duplicates dedupe, stale edges detectable as dangling refs|
|Staged transactional refresh: DELETE-by-(repo,path) + INSERT + atomic stage→live swap|technique|(SQLite blessing-like; DuckDB MIT)|public-domain (SQLite)|production-grade|5|2|5|4|1|H|Eliminates torn-state risk; complements existing fixed staging|
|Two-phase symbol-level edge reconciliation over changed-symbol set|technique|internal (cf. arxiv.org/abs/2211.01224 path-stitching model)|n/a|novel-here, standard-in-lit|5|3|5|5|2|M|Design reasoning; stack-graphs paper formalizes per-file subgraph + late stitching|
|GitHub stack-graphs / tree-sitter-stack-graphs|repo|https://github.com/github/stack-graphs|MIT OR Apache-2.0|ARCHIVED 2025-09-09; core v0.14.1, tsg v0.10.0 2024-12-13|3|2|4|3|3|H|Archived read-only Sept 2025 → DO NOT adopt; its blob-ID caching idea (discussion #263) validates design|
|Zoekt `zoekt-git-index -incremental` (default true) + `-delta` mode|tool|https://github.com/sourcegraph/zoekt/blob/main/cmd/zoekt-git-index/main.go|Apache-2.0|active (Sourcegraph maintains; PR #1050 branch-aware delta)|3|3|3|4|1|H|Incremental-by-default trigram indexer; prior art + optional lexical layer; falls back to full rebuild when state diverges|
|Universal Ctags 6.2.1 JSONL per-file shards (`--append` is NOT update-safe)|tool|https://docs.ctags.io/en/latest/man/ctags.1.html|GPL-2.0|mature (rel 2025-10-25)|3|3|2|3|1|H|Docs: append adds without dedup/delete → regenerate changed file's shard; matches our per-file staging|
|Watchman since-cursor file watching|tool|https://github.com/facebook/watchman|MIT|active weekly rels (v2026.08.x verified)|2|1|2|2|2|H|Redundant vs `git status` at ~20 small repos; revisit only for event-driven push refresh|
|GitPython 3.1.59 vs pygit2 1.20.0 vs plain subprocess git|tool|https://pypi.org/project/GitPython/ ; https://pypi.org/project/pygit2/|BSD-3 / GPLv2+linking-exception|current (both rel Aug 2026)|4|1|1|2|0|H|Subprocess git = zero deps, sufficient at scale; GitPython ≥3.1.59 required (≤3.1.58 vulns GHSA-284h-m62q-gf8w)|
|Nightly full-rebuild backstop + drift audit vs `git ls-files`|strategy|https://git-scm.com/docs/git-ls-files|n/a|cheap here (full rebuild ≈ minutes max)|5|1|5|5|0|H|Bounds any delta bug's blast radius to one day; also catches missed-changes class R2/R7|
|Rename awareness `-M` + blob-tree-hash equality for moved identical content|technique|https://git-scm.com/docs/diff-options|n/a|maximal (git built-in)|3|2|1|2|0|H|Similarity-threshold misses degrade safely to delete+add under content-hash IDs|

## Verdict
Top pick: the zero-dependency combo — git plumbing (diff/status union, stored reachable base SHA) + content-hash deterministic IDs + staged delete/upsert/swap + changed-symbol-set edge reconciliation, with nightly full-rebuild drift audit. Why: at our measured scale (~20 small repos, full rebuild ≈ seconds-to-minutes on 16 cores, RAM floor never binding) delta buys freshness latency (~30 s → ~2 s) and bounded blast radius, not throughput — so correctness machinery must be simple; the archived stack-graphs and non-incremental CodeQL confirm no off-the-shelf orchestrator exists. Integration sketch: per repo `changed = diff(prev,HEAD) ∪ status(-uall)`, filter lockfiles, DELETE WHERE (repo,path) in changed∪deleted, re-extract rest via tree-sitter into hash-keyed staging rows, reconcile edges touching changed qualified names, atomic swap, persist SHA; unreachable prev ⇒ full rebuild; nightly audit `graph file_ids vs git ls-files`.

### Key sources (all accessed 2026-08-25)
- git-scm.com/docs/git-status.html, /docs/diff-options (porcelain v1, -uall, ACDMRT, rename detection)
- github.com/github/stack-graphs/releases + commits (archived 2025-09-09); discussion #263; arxiv.org/abs/2211.01224
- github.com/sourcegraph/zoekt cmd/zoekt-git-index/main.go, cmd/zoekt-sourcegraph-indexserver/main.go, LICENSE (Apache-2.0), PR #1050
- docs.ctags.io ctags.1 (--append semantics), releases (6.2.1, 2025-10-25)
- github.com/facebook/watchman/releases (weekly through v2026.08.24.00, MIT)
- pypi.org/project/GitPython (3.1.59, 2026-08-10, BSD-3; GHSA-284h-m62q-gf8w); pypi.org/project/pygit2 (1.20.0, 2026-08-08, GPLv2+linking exception, libgit2 1.9.7)
- github.com/tree-sitter/tree-sitter-rust README benchmark (9.9 MB/s); tree-sitter issue #1277; docs.github.com CodeQL incremental-analysis page (overlay-only)
- Local: directory listing of /home/malcolmjones/Projects (corpus shape, worktree farms, file sizes)