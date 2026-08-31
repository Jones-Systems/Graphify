# S-B — T4–T6 partial synthesis

## Source binding

- Exact raw-input revision: `60f6935f26c912a32aac0e1aa0bb6b5dda063c9b`.
- Lane range: L22–L42.
- Content-validated and consumed inputs: 6 of 21 lanes.
- This is a partial synthesis, not a completeness claim.
- Every consumed lane below is bound only to the exact eligible Git selector
  `60f6935f26c912a32aac0e1aa0bb6b5dda063c9b:<mapped artifact path>` in
  `research/positive-claims.json`; reviewed-input hashes preserve provenance
  only.

Validated and consumed inputs: L22, L29, L33, L37, L40, and L42.

Excluded inputs: L23–L24, L27–L28, L30, L32, L34, L36, L38–L39, and L41
are inherited mixed-context blobs that are not public-safe inputs to this
candidate. L25 and L26 are reciprocally misrouted; L31 is an explicit gap
without a findings body; L35 lacks its comparison table and sources.

## Supported synthesis

| Supported statement | Inputs | Boundary |
| --- | --- | --- |
| <!-- positive-claim: SB-01 --> Splink is a public-source entity-resolution candidate. | L22 | Representative public data, clerical labels, blocking choices, precision/recall, scale, and identifier governance remain unvalidated. |
| <!-- positive-claim: SB-02 --> Tree-sitter and Joern are documented structural-code extraction candidates. | L29, L33 | Language coverage, reference accuracy, resource use, and graph-schema fit require a public benchmark; no SCIP or dependency-extractor conclusion is available. |
| <!-- positive-claim: SB-03 --> Public comparisons of bounded llama.cpp profiles, small-model candidates, and quantization formats can frame a batch-extraction experiment. | L37, L40, L42 | Bind the exact runtime/model/prompt/schema/fixture first. Measure semantic quality and abstention separately from syntax validity, then measure target-host memory, prompt rate, generation rate, p50/p95 latency, concurrency, and aggregate throughput under declared parameters. |

## Unsupported or unknown

No conclusion is accepted from the inherited mixed-context lanes. Canonical
L31 and L35 reports are unavailable, and the manifest identities for L25 and
L26 are not repaired by swapping their claims in synthesis.

## Synthesis conclusion

- Supported: <!-- positive-claim: SB-04 --> Splink, structural-code extraction, and bounded batch-extraction experiments have limited public-source support.
- Unsupported/unknown: No identifier-governance scheme, dependency extractor, SCIP pipeline, model, or deployment profile is accepted as ready.
