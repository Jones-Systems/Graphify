# LANE L48 — FalkorDB (T7 storage) findings
*Evidence collected 2026-08-25 from primary sources (GitHub repo/LICENSE/releases, docs.falkordb.com, benchmark.falkordb.com, PyPI).*

## Findings table

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|FalkorDB server v4.20.4 (Redis-module graph DB, GraphBLAS/SuiteSparse sparse-matrix engine)|tool/repo|https://github.com/FalkorDB/FalkorDB|SSPL-1.0 (LICENSE file read verbatim, "Server Side Public License VERSION 1")|High — 5.6k stars / 434 forks / 2,377 commits; active release train v4.18→v4.20.4 (releases.atom, 2026-08)|4|3|3|2|2|H|Repo meta + releases feed show v4.20.4 latest (checked 2026-08-25); successor to deprecated RedisGraph (2023)|
|SSPL-1.0 license posture|strategy|https://raw.githubusercontent.com/FalkorDB/FalkorDB/main/LICENSE ; https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=915537|SSPL-1.0 (source-available, not OSI-approved)|n/a (legal)|3|0|1|3|1|H|The recorded sources show that Debian excludes SSPL software from `main` and the license contains a managed-service condition. License fit and any service exposure require separate legal review; deployment packaging is not established.|
|CPU-only execution model: query concurrency plus an OpenMP worker-thread setting for GraphBLAS operations|technique|https://docs.falkordb.com/getting-started/configuration.html|—|Stable documented config|4|3|2|1|1|H|Docs confirm two-level parallelism, pure CPU/OpenMP; zero GPU dependency anywhere in stack (GraphBLAS CPU reference backend); single Redis-style process|
|Memory footprint claims|technique/evidence|https://benchmark.falkordb.com/ ; https://www.falkordb.com/news-updates/v4-8-7x-more-efficient/|—|Vendor benchmark (treat as marketing until reproduced)|4|3|2|1|1|M|Official public bench: 10k nodes / 121,716 edges → **~15–17 MB** FalkorDB RAM (≈1.5–1.7 KB/node incl. matrices+attrs at that density); v4.8 announcement claims 7× less memory than Neo4j (~100 MB vs ~600 MB same dataset); vendor FAQ: 4 GB min eval, 16 GB recommended production|
|openCypher-v9 subset compatibility|technique|https://docs.falkordb.com/cypher/cypher-support.html ; https://docs.falkordb.com/cypher/known-limitations.html|—|Documented coverage page, actively maintained|4|3|3|2|2|H|Supported: MATCH/OPTIONAL MATCH, WHERE, WITH/RETURN/ORDER BY/SKIP/LIMIT, CREATE/MERGE/SET/REMOVE/DELETE(=DETACH), UNWIND, FOREACH, CALL{} subqueries, UNION [ALL], LOAD CSV, registered procedures (algos), vector functions. Gaps: no `=~` regex, no label expressions `(n:A\|B)`, no pattern `exists()`, no temporal arithmetic, no hex/octal literals, no schema-retrieval queries, no standard UDFs (Flex UDF ext only), Neo4j procedures absent. Semantic traps: unreferenced rel vars may not multiply rows; LIMIT does not short-circuit eager writes; `<>` predicates unindexed; no aggregations inside pattern comprehensions|
|Sizing and memory measurement|strategy|https://docs.falkordb.com/commands/graph.memory.html|—|documented interface|5|3|3|2|1|H|The in-memory model requires the graph and indexes to fit the selected resource budget. Vendor examples are not a target estimate; deployment memory must be measured with `GRAPH.MEMORY USAGE` and an explicit limit. Persistence uses Redis RDB/AOF machinery.|
|falkordb-py client 1.7.1|tool|https://pypi.org/project/FalkorDB/|MIT|Production/Stable classifier; sync+async APIs|4|2|2|1|1|H|PyPI JSON (2026-08-25): v1.7.1, MIT, `requires_python >=3.10`, classifiers through CPython 3.14, deps `redis>=8,<9`; `g.query/ro_query`, connection-pool async concurrency|

## Verdict
The recorded report identifies FalkorDB as a CPU-only graph-store candidate
with an openCypher subset and a separately licensed Python client. Vendor
memory claims require reproduction, and SSPL-1.0 plus the stateful service
model require separate license and operational review. No target size,
resource limit, packaging path, migration, or adoption decision is
established.
