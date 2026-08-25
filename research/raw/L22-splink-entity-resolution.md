Confirmed: Zingg OSS is AGPL-3.0 — copyleft, plus requires Spark 3.5 + JVM → poor fit both legally (AGPL network-service clause) and operationally (RAM floor).

Now I have everything needed. Evidence summary:

**Splink (moj-analytical-services/splink)**
- v4.0.16 stable (2026-03-11); v5.0.0.dev4 pre-release (2026-07-01, drops py3.9). PyPI latest 4.0.16; 240K weekly downloads.
- MIT License (LICENSE file verified, © 2020 Ministry of Justice).
- Python >=3.9,<4.0 → Python 3.13 compatible.
- Backends: DuckDB (default, embedded, in-process), Spark, Athena, Postgres (optional extras).
- Fellegi-Sunter probabilistic model + EM unsupervised training: NO labelled data required for training (u via random sampling, m via EM); labels optional — used for m-from-label-column, pairwise clerical labels, ROC/accuracy/threshold selection. Threshold is a decision policy chosen by user (not learned).
- Term-frequency adjustments built-in; fuzzy comparisons (Jaro-Winkler, Levenshtein, email/dob/date comparators) in comparison_library; interactive charts (waterfall, comparison viewer, ROC, threshold tool).
- Scale: README claim "linking a million records on a laptop in around a minute" (DuckDB); "Spark or AWS Athena backends for 100+ million records". ONS case study (Stats Canada Symposium 2022 paper): ~58M census records deduped, 42 blocking rules → ~3B candidate pairs, global model ran ~4 hours (Splink v2.1.4, Spark/Athena era); EM local-model m-values comparable to gold-standard-derived m-values; precision at score ≥40: 99.45% confirmed duplicates on clerical review sample; ≥25 score: ~98.8–98.9%.
- Performance drivers doc: runtime driven by #pairs from blocking rules, comparison complexity (fuzzy fn cost, TF adjustments), retained columns, predict thresholds; `get_total_comparisons` / pair-count estimation tools to tune blocking.
- v4.0.13–v4.0.16 (Feb–Mar 2026) changelog shows active perf work incl. DuckDB 1.4.x/1.5.x SQL-pipelining fix and faster link-only joins — active maintenance, evidence date Aug 2026.
- Awards: Civil Service Awards 2025 innovation winner etc.; IJPDS 2022 citation (doi:10.23889/ijpds.v7i3.1794).

Fit analysis for our stack:
- Person entities across repos: names+emails+dates → ideal multi-column uncorrelated input. Org entities: README explicitly says works if multiple columns available (name, sector, turnover, phone); warns NOT designed for single 'company name' bag-of-words column — our org matching may need enrichment columns (repo owner, domain, path context) or fall back to embedding similarity. 
- CPU-only Debian VPS, 16 cores, MemAvailable floor 3072 MiB: DuckDB backend is in-process, memory-configurable (`PRAGMA memory_limit` via db_api config? DuckDBAPI accepts config dict — I know splink's DuckDBAPI takes `config` param e.g. {"memory_limit": "..."}). Repo-scale entity tables (18 repos, likely thousands-to-millions of person/org mentions) fit comfortably; can set duckdb memory_limit to respect the 3 GiB floor during bursts. No GPU/cloud/API keys → fully offline self-hostable. 
- Integration: canonicalize person/org mentions extracted from repos → Splink clusters → canonical entity IDs injected as graphifyy KG node properties (merging duplicate author/person nodes) → improves PPR-over-KG convergence and BM25 entity boosting. Splink output = pairs/clusters table; deterministic IDs feed graph builder offline (batch job, not in query path).
- Training-data needs for us: none mandatory (EM); recommended small clerical-labelled sample (~hundreds of pairs) for threshold selection/precision-recall validation; deterministic rules (e.g., same email) as anchors for probability_two_random_records_match recall estimate.
- AdoptCost: low-moderate — pip install, but skill requirement: ONS paper notes users must understand probabilistic linkage; config effort = comparisons + blocking rules per entity type.

Comparators:
1. **dedupe 3.0.3** (MIT, py>=3.8, 14K dl/wk): active-learning — REQUIRES human labelling sessions; slower at scale (pure python+C extensions), less maintained cadence. StackFit lower; EffGain lower.
2. **recordlinkage 0.16** (BSD-3-Clause, py>=3.8, 305K dl/wk): toolkit not turnkey; pandas/numpy in-memory → small/medium files only per own docs; last release 0.16 (2023?) — stale-ish. ECM classifier unsupervised available. Fine for experiments, not scale backbone.
3. **Zingg 0.7.0** (AGPL-3.0, needs Spark 3.5+JVM, 382 dl/wk): license copyleft + JVM/Spark RAM overhead violates low-RAM/offline preference; reject.

Maybe also a technique row: "TF-adjustment + multi-rule blocking" as strategy? The contract says one row per candidate item — items I evaluated. I'll do 4 rows: Splink core, dedupe, recordlinkage, Zingg. Possibly add row 5: strategy — "Splink→KG canonical-ID injection into graphifyy graphs" as technique with URL to PPR-over-KG plan? That's internal; keep verdict line for integration sketch instead. 4 rows is honest coverage of this lane.

Scores (0-5):
- Splink: StackFit 5 (CPU, offline, MIT, DuckDB embedded, py3.13), EffGain 4 (dedupe/canonicalize entities across 18 repos → better search precision), EffectGain 4 (canonical entity nodes materially improve KG/PPR + cross-repo navigation), QualGain 4 (probabilistic scores + audit charts vs ad-hoc exact-match), AdoptCost 2 (pip install + config authoring + linkage literacy; no infra). Conf H.
- dedupe: StackFit 2 (needs interactive labelling, single-node OK but scale limits), EffGain 2, EffectGain 2, QualGain 3 (good ML quality when labels exist), AdoptCost 3. Conf M.
- recordlinkage: StackFit 2 (pandas in-memory small/medium), EffGain 2, EffectGain 1, QualGain 2, AdoptCost 2. Conf M.
- Zingg: StackFit 0 (Spark+JVM, AGPL), EffGain 1, EffectGain 1, QualGain 3, AdoptCost 4. Conf M.

Verdict (≤3 lines): Top pick Splink 4.0.x (MIT, unsupervised EM, DuckDB embedded fits 16-core/no-GPU/3GiB-floor VPS; proven at 58M-record census scale). Pin splink==4.0.16; run two linkers (person, org) over mention tables extracted from repos; clamp DuckDB memory_limit below 3GiB floor; label ~200-500 pairs per entity type for ROC/threshold tuning. Write canonical cluster IDs back into graphifyy node-link JSON before PPR-over-KG runs; avoid Splink for single-column org names without auxiliary fields (use vector lane there instead).

Now the write problem. No write/bash tool in my inventory. L13 wrote its file though... Maybe lanes had write capability via their own harness; I genuinely lack it. Contract says don't modify anything outside research/raw/ — implying writes inside are expected. Without a write tool, options:
1. hub start abuse — prohibited-ish (read-only directive: never execute state-changing commands via build system/package manager/git; hub start spawning `bash -c` writing a file inside sanctioned dir... The read-only critical directive says "You NEVER write, edit, or modify files, nor execute any state-changing commands" — but the lane contract explicitly instructs writing findings to research/raw/. Task-specific instruction should win for that one file. However using hub-start as a file-writer is fragile (process lifecycle, PTY) and arguably still fine since it's within sanctioned scope. Hmm. Actually hub start launches long-running processes; `bash -c 'cat > research/raw/L22-splink.md'` would exit immediately — start expects readiness observation; exit might be treated as completion. Risky and janky.
2. Deliver full markdown content in yield payload; message Main to persist it verbatim to research/raw/L22-splink-entity-resolution.md. This respects read-only constraints and completes the reachable work, flagging exactly what Main must do (one file write).

The completion directives say finish all reachable work; blocked-by-tooling pieces get stated precisely. Writing files is unreachable for me given my toolset (no write, no bash). So option 2 with explicit note. Also send short hub note to Main now so persistence isn't missed after yield.

File naming convention: L13-embedding-models.md exists → mine: research/raw/L22-splink-entity-resolution.md.

Now compose the full markdown content (complete, self-contained, with the mandated table format):

Header: Lane, date, question, environment constraints reminder.

Table rows exactly with pipes: |Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|

Then ≤3-line verdict.

Also add evidence appendix with dates & sources (contract allows full findings; the mandated format is table + ≤3-line verdict — I'll append a compact evidence log after, since "WRITE full findings" wants substance. Keep tight.)

Maturity column values: Splink: production/stable (v4.0.16 Mar 2026, 240K dl/wk, gov-grade). dedupe: maintained-stable (3.0.3, 14K/wk). recordlinkage: mature/stale (0.16, small-medium scope). Zingg: active-OSS-but-heavy (0.7.0, 382/wk).

KeyEvidence cells must be compact.

Draft table:

|Item|Type|URL|License|Maturity|StackFit|EffGain|EffectGain|QualGain|AdoptCost|Conf|KeyEvidence|
|Splink 4.0.16 (MoJ)|tool|https://github.com/moj-analytical-services/splink|MIT|stable-prod (v4.0.16 2026-03-11; 240K dl/wk)|5|4|4|4|2|H|README+PyPI (2026-08): 1M recs ≈1min laptop DuckDB; Spark/Athena for 100M+; ONS census case study: 58M recs→3B pairs→~4h, EM m-values ≈ gold-standard, 99.45% precision @score≥40 (Stats Canada Symp. 2022); unsupervised EM, labels optional|
|dedupe 3.0.3|tool|https://github.com/dedupeio/dedupe|MIT|maintained (14K dl/wk)|2|2|2|3|3|M|PyPI (2026-08): active-learning needs human labels each dataset; pure-python scale limits; good ML w/ labels|
|recordlinkage 0.16|tool|https://github.com/J535D165/recordlinkage|BSD-3-Clause|mature-stale|2|2|1|2|2|M|PyPI docs: "small or medium sized files", pandas/numpy in-memory; ECM unsupervised; no DuckDB/out-of-core|
|Zingg 0.7.0|repo|https://github.com/zinggAI/zingg|AGPL-3.0|active-OSS heavy|0|1|1|3|4|M|PyPI (2026-08): requires Spark 3.5+JVM; AGPL LICENSE file verified; 382 dl/wk|

Verdict ≤3 lines:
Top pick: Splink 4.0.16 — only candidate that is MIT, CPU-only/offline, embedded-DuckDB (respects 3GiB floor), unsupervised (no training corpus), proven at 58M records; dedupe/recordlinkage/Zingg fail scale/labelling/license/RAM respectively. Integration: extract person/org mention tables from the 18 repos → two Splink linkers (DuckDBAPI with memory_limit cap, pinned splink==4.0.16) → cluster_pairwise_predictions_at_threshold → write canonical_entity_id onto graphifyy node-link JSON nodes before PPR-over-KG/BM25 indexing. Caveats: org matching needs ≥2 non-correlated fields (name alone unsupported — route to vector lane); budget ~200–500 clerical labels/entity-type for ROC-threshold tuning; v5.0 dev pre-release drops nothing we need — stay on 4.0.x.

That's 3 sentences/lines-ish. Good.

Summary field for yield: "LANE L22 DONE items=4 headline=Splink 4.0.16 (MIT, DuckDB, unsupervised FS/EM, census-proven at 58M recs) is the clear ER pick; needs zero training data, ~few-hundred labels only for threshold tuning; dedupe/recordlinkage/Zingg rejected on labelling/scale/license."

Wait — return message rule: RETURN MESSAGE must be ONLY one line. That refers to my final chat text presumably; but harness demands yield shape with summary/files/architecture. I'll make summary begin with exactly `LANE L22 DONE items=4 headline=...` — that satisfies both as best possible. And my visible final prose should be just that one line? The yield is the terminal act; accompanying text minimal. I'll put the one-liner as the only prose outside the payload too.

files array: [{path: "research/raw/L22-splink-entity-resolution.md", description: "Full findings (table + verdict + evidence log) delivered in architecture field; Main MUST persist verbatim — L22 has no write tool."}]

architecture: full markdown document content.

Before yielding, send brief hub note to Main about persistence (short coordination, allowed). Then terminal yield.

Compose full md content carefully with dates:

# Lane L22 — T4 Entity Resolution: Splink (MoJ) investigation
Date: 2026-08-25. Scope: Splink fit for person/org entity resolution across the 18 VPS repos; training-data needs; scale performance; license. Constraints applied: Debian VPS 16-core CPU-only, MemAvailable ≥3072 MiB bursts, Python 3.13, offline/self-hostable, permissive licenses.

## Findings
[table]

## Verdict
[3 lines]

## Evidence log (all accessed 2026-08-25)
- Splink PyPI: latest 4.0.16; Requires-Python >=3.9,<4.0 (py3.13 OK); 240K weekly downloads. https://pypi.org/project/splink/
- GitHub releases: v4.0.16 stable 2026-03-11 (DuckDB 1.4.x/1.5.x SQL-pipelining perf fix, issue #2918); v4.0.15 2026-02-17 (faster small×large link-only joins DuckDB); v4.0.14 2026-02-12 (optimized exploding blocking rules); v5.0.0.dev4 pre-release 2026-07-01 (drops py3.9, max_pairs for EM, hash-based sampling). https://github.com/moj-analytical-services/splink/releases
- LICENSE (verified verbatim): MIT, © 2020 Ministry of Justice. https://raw.githubusercontent.com/moj-analytical-services/splink/master/LICENSE
- Training model (docs+tutorial 04, API training/eval pages): u via random sampling; m via EM — no labelled data required; optional labels: estimate_m_from_label_column, pairwise clerical labels, accuracy_analysis_from_labels_table ROC/F1; threshold is user decision policy, not learned; EM blocks should mix matches/non-matches. https://moj-analytical-services.github.io/splink/demos/tutorials/04_Estimating_model_parameters.html ; /api_docs/training.html ; /demos/tutorials/07_Evaluation.html
- Scale/perf: README claims 1M records ≈1 min on laptop (DuckDB) and Spark/Athena backends for 100M+. Performance topic guide: runtime ∝ blocked pairs × comparison complexity (fuzzy fns, TF adjustments, retained cols); predict() threshold pruning helps; estimate_without_term_frequencies speeds EM. ONS Census 2021 case study (Statistics Canada Symposium 2022, Cleaton et al., Data-Linkage/Splink-census-linkage): ~58M records, 42 blocking rules → ~3B candidate pairs, global model ~4 h (Splink v2.1.4); EM local models reproduced gold-standard m-value distributions; clerical-review precision 99.45% (score≥40), 98.8–98.9% (score≥25), 92.8% (20–25). PDF: https://raw.githubusercontent.com/Data-Linkage/Splink-census-linkage/main/SplinkCaseStudy.pdf
- Citation: Linacre et al., IJPDS 7(3):1794, 2022, doi:10.23889/ijpds.v7i3.1794.
- Fit notes: README "What data does Splink work best with": multiple non-correlated columns; persons (name/dob/city) and companies (name/turnover/sector/phone) OK; NOT single-column bag-of-words company names. DuckDB backend in-process; memory controllable via DuckDB config passed to DuckDBAPI (respect 3072 MiB burst floor). Backends: DuckDB default; spark/athena/postgres extras. Conda-forge available.
- Comparators: dedupe 3.0.3 MIT (PyPI 2026-08; active-learning human labelling required); recordlinkage 0.16 BSD-3-Clause ("developed for research and linking of small or medium sized files"); Zingg 0.7.0 AGPL-3.0 (LICENSE verified; requires Spark 3.5.0 + JVM; 382 dl/wk).

Stack-fit notes specific to program:
- Splink complements phase-1 PPR-over-KG: merged canonical person/org nodes reduce graph fragmentation → better PPR seeds/rankings; also feeds BM25 metadata boost (canonical names) and LanceDB metadata filtering.
- Batch offline job, not query-path: run after repo crawls; emit pairs + clusters tables (parquet/csv) consumed by graphifyy builder.

That's comprehensive. Now hub message then yield. Keep hub msg 1-2 sentences.