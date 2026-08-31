# L72 — Federated search scatter-gather

Date recorded: 2026-08-25.

## Evidence boundary

This record retains only the public comparison of rank fusion, score
normalization, quotas, bounded parallelism, and hedging. Performance, quota,
service, and deployment choices remain benchmark-gated.

## Findings

| Item | Type | URL | License | Maturity | StackFit0-5 | EffGain0-5 | EffectGain0-5 | QualGain0-5 | AdoptCost0-5 (lower=better) | Conf | Key evidence |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| Cross-corpus RRF with k=60 | technique | https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf | paper | established | 5 | 4 | 4 | 4 | 0 | H | RRF combines rank positions without assuming comparable raw scores; the cited study reported gains over its component systems and CombMNZ. |
| Weighted per-corpus RRF | technique | https://qdrant.tech/documentation/search/hybrid-queries/ | method | production implementation | 5 | 3 | 4 | 4 | 1 | M-H | A weight per input can express corpus priority while preserving rank-space fusion. Weights require evaluation data. |
| Normalized score merge | technique | https://docs.opensearch.org/latest/search-plugins/search-pipelines/normalization-processor/ | method | production implementation | 3 | 2 | 3 | 3 | 3 | M | Score fusion can be competitive when scores are calibrated and labelled evaluation data exists; raw cross-corpus BM25 and vector scores are not inherently comparable. |
| Uniform bounded candidate windows | strategy | https://www.elastic.co/docs/reference/elasticsearch/rest-apis/retrievers/rrf-retriever | n/a | common pattern | 5 | 5 | 3 | 2 | 1 | H | Each child is truncated before fusion. Window size must remain stable through pagination and be validated against recall. |
| Resource-selection quotas | strategy | https://cs.cmu.edu/~callan/Papers/ecir05-jielu.pdf | paper | established research | 3 | 2 | 3 | 2 | 3 | M | ReDDE-style allocation uses collection-size and relevance estimates; it adds value only after corpus statistics and evaluation data exist. |
| Bounded-parallel gather with deadlines | strategy | https://docs.python.org/3/library/asyncio-task.html | PSF | stable | 5 | 5 | 5 | 1 | 1 | H | A task group, semaphore, and per-source timeout can return partial results rather than failing the whole query. Concurrency and deadlines require workload measurement. |
| Hedged idempotent reads | strategy | https://barroso.org/publications/TheTailAtScale.pdf | paper | established | 4 | 3 | 5 | 0 | 2 | H | The cited production study shows that carefully triggered duplicate reads can reduce tail latency at modest added load. Apply only to measured stragglers and idempotent reads. |
| ranx fusion evaluation | tool | https://pypi.org/project/ranx/ | MIT | mature on recorded date | 3 | 1 | 1 | 2 | 2 | H | Provides RRF and alternative fusion methods plus parameter optimization against qrels; suitable for offline evaluation, not required at runtime. |
| SQLite ATTACH plus UNION ALL | technique | https://sqlite.org/lang_attach.html | public domain | stable | 4 | 3 | 2 | 1 | 1 | H | Provides a local multi-database query shape; application-level rank fusion remains necessary. |
| PostgreSQL partitioned UNION ALL | technique | https://www.postgresql.org/docs/current/sql-select.html | PostgreSQL License | stable | 4 | 3 | 2 | 2 | 1 | M | A shared deployment can gather partition-limited candidates in SQL, but no such deployment is established by this lane. |

## Verdict

Weighted RRF with bounded-parallel deadline scatter is the recorded candidate because it does not require calibrated raw scores and can degrade to partial results. Start with uniform bounded windows and deterministic identifier deduplication; add corpus weights, resource-selection quotas, or hedging only after labelled relevance and latency measurements. Sequential fan-out and raw score merging are not accepted defaults from this evidence.

## Recorded sources

1. Cormack, Clarke, and Buettcher, RRF, SIGIR 2009: https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf
2. Bruch, Gai, and Ingber, fusion analysis: https://arxiv.org/abs/2210.11934
3. Lu and Callan, federated search: https://cs.cmu.edu/~callan/Papers/ecir05-jielu.pdf
4. Dean and Barroso, tail latency: https://barroso.org/publications/TheTailAtScale.pdf
5. Python asynchronous task documentation: https://docs.python.org/3/library/asyncio-task.html
6. Elasticsearch RRF window semantics: https://www.elastic.co/docs/reference/elasticsearch/rest-apis/retrievers/rrf-retriever
7. OpenSearch normalization: https://docs.opensearch.org/latest/search-plugins/search-pipelines/normalization-processor/
8. ranx: https://pypi.org/project/ranx/
