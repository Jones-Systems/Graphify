# S-A — T1–T3 partial synthesis

## Source binding

- Exact raw-input revision: `60f6935f26c912a32aac0e1aa0bb6b5dda063c9b`.
- Lane range: L01–L21.
- Content-validated and consumed inputs: 1 of 21 lanes.
- This is a partial synthesis, not a claim that the theme or corpus is complete.
- Every consumed lane below is bound only to the exact eligible Git selector
  `60f6935f26c912a32aac0e1aa0bb6b5dda063c9b:<mapped artifact path>` in
  `research/positive-claims.json`; reviewed-input hashes preserve provenance
  only.

Validated and consumed input: L20.

Excluded inputs: L01–L10 and L15–L17 are inherited mixed-context blobs that
are not public-safe inputs to this candidate. L11 and L12 are misrouted
duplicates; L13 and L19 have unknown immutable origins; L14 and L18 are
missing; L21 contains no completed findings.

## Supported synthesis

| Supported statement | Inputs | Boundary |
| --- | --- | --- |
| <!-- positive-claim: SA-01 --> PostgreSQL full-text plus pgvector is a public-source hybrid-search candidate. | L20 | No live database, workload, backup posture, extension install, target quality gain, or deployment readiness is established. |

## Unsupported or unknown

No synthesis claim is accepted here for graph-oriented retrieval, community
methods, vector-store selection, a lexical backbone, rank fusion, embedding
selection or quantization, ColBERT/PLAID, SPLADE adoption, or a local
reranker. Those topics depend on inherited mixed-context, misrouted,
origin-unbound, missing, or incomplete lanes.

## Synthesis conclusion

- Supported: <!-- positive-claim: SA-02 --> PostgreSQL full-text plus pgvector may be evaluated as a hybrid-search candidate.
<!-- negative-boundary: BND-SA-CONCLUSION status=unsupported_or_unknown claims=SA-02 -->
- Unsupported/unknown: Only the registered conclusion claim SA-02 is supported; every other conclusion in this section is unsupported or unknown.
