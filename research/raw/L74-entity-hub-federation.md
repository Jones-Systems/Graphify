# L74 — Shared entity-hub corpus design

## Evidence status

- Classification: gap (misrouted input).
- Reviewed input revision: `d1dbac36208b0066fc8907bd9fe9408fc5c51a60`.
- The committed input identifies its embedded content as L70 rather than L74.
- Canonical L74 content is unavailable and no embedded claim is reassigned to L74.
- This lane is excluded from synthesis; its research result remains unknown.

## Unassigned public-source candidate from the misrouted payload

The embedded report recorded the following public-source comparisons on
2026-08-25. They are retained only as an unassigned design candidate. They do
not answer canonical L74, establish source currentness after that date, or
establish a shared entity hub design.

| Candidate element | Public source | Recorded point | Boundary |
| --- | --- | --- | --- |
| Statement-based entity vocabulary | https://followthemoney.tech/docs/statements/ | FollowTheMoney models property values as source-bearing statements and supports interstitial relationship entities. | Vocabulary reuse and schema fit require separate evaluation. |
| Deterministic UUID namespace | https://www.rfc-editor.org/rfc/rfc9562.html | RFC 9562 documents UUID version 5 name-based identifiers. | Determinism does not by itself provide identity governance, merge safety, or erasure semantics. |
| Transactional outbox | https://microservices.io/patterns/data/transactional-outbox.html | A source write and its outbound event can be committed atomically, with consumers applying idempotent effects. | Transport, retention, replay, and failure recovery remain design work. |
| Probabilistic entity resolution | https://moj-analytical-services.github.io/splink/topic_guides/splink_fundamentals/backends/backends.html | The recorded Splink documentation included a SQLite backend. | Backend currentness, representative accuracy, scale, and review thresholds are unverified. |
| Review-gated entity proposals | https://github.com/opensanctions/nomenklatura | Nomenklatura is a public reference for keeping proposed matches distinct from accepted identity state. | No target data, queue, or approval model is established. |
| Personalized PageRank and relation-aware retrieval | https://snap.stanford.edu/class/cs224w-readings/Haveliwala02Topicsenitive.pdf; https://users.cs.duke.edu/~bdhingra/papers/graft-net.pdf | The cited work provides public precedents for personalized and relation-aware graph ranking. | The payload's degree penalties and fusion formulas are unvalidated design hypotheses. |
| High-dimensional nearest-neighbor hubness | http://www.jmlr.org/papers/v11/radovanovic10a.html | The cited paper documents concentration of neighbor occurrences in high-dimensional spaces. | It does not validate a mitigation or target effect. |

The misrouted candidate suggests separating canonical identity statements from
repository-local records, using immutable identifiers and review-gated links,
and measuring graph/vector hub effects. That outline remains non-authoritative
until assigned to a new lane with canonical sources and tests.
