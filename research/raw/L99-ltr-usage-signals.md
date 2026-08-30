# L99 — Learning-to-rank from usage signals

Date recorded: 2026-08-25.

## Evidence boundary

This file retains the lane's public learning-to-rank literature and tool comparison. Private traffic estimates, local fleet claims, raw prompt or path capture, and operational rollout assertions are removed. Any future signal collection must be opt-in, minimized, aggregated where possible, and separately reviewed before implementation.

## Public comparison

| Item | Type | URL | License | Recorded maturity | Evidence or tradeoff |
| --- | --- | --- | --- | --- | --- |
| Impression and interaction joins | strategy | https://github.com/metarank/metarank/blob/master/doc/configuration/overview.md | exemplar Apache-2.0 | established pattern | Ranking evaluation requires knowing which candidates were shown and their order before an interaction can be interpreted. This does not require retaining query text, document content, or filesystem paths. |
| LightGBM ranking objectives | tool | https://lightgbm.readthedocs.io/en/latest/Parameters.html | MIT | mature on recorded date | `rank_xendcg` and `lambdarank` support grouped ranking data and graded labels on CPU. A target model still requires sufficient labelled groups and time-ordered validation. |
| XGBoost `rank:ndcg` | tool | https://xgboost.readthedocs.io/en/stable/tutorials/learning_to_rank.html | Apache-2.0 | mature on recorded date | Provides a LambdaMART-family alternative with grouped ranking data and top-k pair construction. Adopt at most one boosting stack after evaluation. |
| Inverse propensity weighting | technique | https://www.cs.cornell.edu/people/tj/publications/joachims_etal_17a.pdf | paper | established research | Position-biased interaction data requires propensity correction; estimated propensities are not a substitute for a representative evaluation set. |
| Tail exploration | technique | https://arxiv.org/abs/1608.04468 | paper | established research | A bounded randomized intervention can estimate propensities, but it changes served order and therefore requires explicit opt-in and an acceptance design. |
| Team-draft interleaving | technique | https://dl.acm.org/doi/10.1145/2433396.2433428 | paper | established research | Interleaving can compare two rankings with less traffic than a conventional split test. It remains an online experiment and requires consent and stopping criteria. |
| Group-level downstream credit | technique | https://dl.acm.org/doi/10.1145/1526709.1526711 | paper | established research | Downstream interactions can be assigned to an earlier ranked list with decay and uncertainty; absence of interaction is not a hard negative. |
| Bayesian-smoothed priors | strategy | https://www.evanmiller.org/bayesian-average-ratings.html | article | established pattern | Shrinkage can stabilize sparse item-level rates. Feature weight and decay require offline validation. |
| Metarank | reference implementation | https://github.com/metarank/metarank | Apache-2.0 | active on recorded date | Demonstrates event-to-judgment and ranking pipelines, but its service architecture need not be adopted. |
| Neural listwise frameworks | reference | https://github.com/allegro/allRank | Apache-2.0 | research-oriented | Adds a large runtime and typically needs more data than compact tabular ranking; no target need is established. |

## Data-minimization boundary

A permissible evaluation record should use opaque, rotating identifiers and aggregate features only:

- Record the candidate's rank and already-produced numeric scores, not raw query text.
- Record a coarse candidate class or content-independent identifier, not a filesystem path, document body, code excerpt, or repository name.
- Use an opaque interaction-group identifier with bounded retention; remove direct account, machine, and person identifiers.
- Store coarse action categories only when explicitly enabled; do not capture typed text, editor buffers, command arguments, or content payloads.
- Materialize aggregate training rows and delete source events on a defined schedule; provide disable and deletion controls.
- Keep exploration and interleaving off by default. Enabling either is a distinct experimental effect with explicit scope, duration, and stop conditions.

## Candidate feature families

- Existing retrieval scores and rank positions.
- Content-independent document statistics computed at index time, expressed in coarse buckets.
- Query-shape aggregates such as token-count bucket or identifier-token presence, computed ephemerally without retaining the text.
- Aggregate interaction rates with minimum-count thresholds and Bayesian shrinkage.

## Verdict

LightGBM's ranking objectives remain a plausible CPU-only offline candidate if a minimized, opt-in dataset reaches a predeclared sample threshold and beats the static ranking on a held-out time split. No traffic volume, training readiness, feature weight, retraining cadence, or promotion decision is established by this lane. Static fusion and reranking remain the fallback when evidence is sparse.
