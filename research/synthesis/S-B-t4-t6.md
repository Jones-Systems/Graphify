# S-B — T4–T6 partial synthesis

## Source binding

- Exact raw-input revision: `c4ed36dc8394cc58a69bb553fc0d3f5e05b13ed0`.
- Lane range: L22–L42.
- Content-validated and consumed inputs: 6 of 21 lanes.
- This is a partial synthesis, not a completeness claim.
- Every consumed lane below is bound only to the exact eligible Git selector
  `c4ed36dc8394cc58a69bb553fc0d3f5e05b13ed0:<mapped artifact path>` in
  `research/RANKING.md`; reviewed-input hashes preserve provenance only.

Validated and consumed inputs: L22, L29, L33, L37, L40, and L42.

Excluded inputs: L23–L24, L27–L28, L30, L32, L34, L36, L38–L39, and L41
are inherited mixed-context blobs that are not public-safe inputs to this
candidate. L25 and L26 are reciprocally misrouted; L31 is an explicit gap
without a findings body; L35 lacks its comparison table and sources.

## Supported synthesis

| Supported statement | Inputs | Boundary |
| --- | --- | --- |
| Splink is a public-source entity-resolution candidate. | L22 | Representative public data, clerical labels, blocking choices, precision/recall, scale, and identifier governance remain unvalidated. |
| Tree-sitter and Joern are documented structural-code extraction candidates. | L29, L33 | Language coverage, reference accuracy, resource use, and graph-schema fit require a public benchmark; no SCIP or dependency-extractor conclusion is available. |
| Bounded llama.cpp profiles, small-model comparisons, and quantization gates can frame a batch-extraction experiment. | L37, L40, L42 | Model licenses, held-out extraction accuracy, structured-output reliability, throughput, and resource limits must be measured on public fixtures. |

## Unsupported or unknown

No conclusion is accepted from the inherited mixed-context lanes. Canonical
L31 and L35 reports are unavailable, and the manifest identities for L25 and
L26 are not repaired by swapping their claims in synthesis.

## Synthesis conclusion

Splink, structural-code extraction, and bounded batch-extraction experiments
have limited public-source support. No identifier-governance scheme, dependency
extractor, SCIP pipeline, model, or deployment profile is accepted as ready.
