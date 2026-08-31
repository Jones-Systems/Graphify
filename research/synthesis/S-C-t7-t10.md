# S-C — T7–T10 partial synthesis

## Source binding

- Exact raw-input revision: `c4ed36dc8394cc58a69bb553fc0d3f5e05b13ed0`.
- Lane range: L43–L70.
- Content-validated and consumed inputs: 8 of 28 lanes.
- Qualified but unconsumed inputs: 2 of 28 lanes.
- This is a partial synthesis, not a completeness claim.
- Every consumed lane below is bound only to the exact eligible Git selector
  `c4ed36dc8394cc58a69bb553fc0d3f5e05b13ed0:<mapped artifact path>` in
  `research/RANKING.md`; reviewed-input hashes preserve provenance only.

Validated and consumed inputs: L43, L48–L49, L53–L55, L57, and L64.

Qualified but unconsumed inputs: L60 retains public routing and abstention
research without a representative labelled corpus; L66 retains public
candidate-generation and quality-control research without validated target
precision, throughput, or yield.

Excluded inputs: L45–L47, L51–L52, L56, L61, L63, L65, and L67 are inherited
mixed-context blobs that are not public-safe inputs to this candidate. L44,
L50, L58, L59, and L62 are incomplete; L68 is missing; L69 and L70 are
misrouted. The public L69 namespace note is an unassigned design lead, not
canonical L69 evidence.

## Supported synthesis

| Supported statement | Inputs | Boundary |
| --- | --- | --- |
| SQLite, FalkorDB, and LadybugDB are documented storage candidates for a public-fixture comparison. | L43, L48–L49 | L44 cannot support a DuckDB-VSS conclusion; durability, concurrency, license, memory, and latency must be measured. |
| A small read-only graph/search surface can use typed schemas, response-size bounds, explicit isolation controls, and an openCypher-style interface candidate. | L53–L55, L57 | The base capability inventory is incomplete; GraphQL and DuckDB-SQL surface verdicts are unknown; no engine or transport is selected. |
| BEIR datasets and run formats can anchor a public evaluation harness. | L64 | Dataset choice, qrels, metrics, downloads, and target-system integration require a separately reproducible harness. |

## Unsupported or unknown

No conclusion is accepted from the inherited mixed-context lanes. No canonical
conclusion is accepted for DuckDB VSS over Parquet, the base MCP capability
inventory, local GraphQL, DuckDB SQL as the tool surface, natural-language
routing coverage, saved-query skills, generated golden-set quality, target
latency budgets, the L69 A/B protocol, or judge-bias mitigation.

## Synthesis conclusion

The supported evidence is limited to a public-fixture storage comparison, a
bounded read-only query-surface experiment, and a BEIR-based evaluation
harness. Storage, routing, interface, and evaluation-policy selections remain
open.
