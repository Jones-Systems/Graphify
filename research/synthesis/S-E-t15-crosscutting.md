# S-E — T15 and cross-cutting partial synthesis

## Source binding

- Exact raw-input revision: `c4ed36dc8394cc58a69bb553fc0d3f5e05b13ed0`.
- Lane range: L97–L100.
- Content-validated and consumed inputs: 0 of 4 lanes.
- Qualified but unconsumed inputs: 1 of 4 lanes.
- This is a partial synthesis, not a completeness claim.
- Any future consumed lane must bind to an exact eligible Git selector recorded
  in `research/RANKING.md`; reviewed-input hashes preserve provenance only.

Qualified but unconsumed input: L99 exists and retains only opt-in, minimized,
aggregate-signal learning-to-rank research; this synthesis does not consume it.

Excluded inputs: L97 and L98 are inherited mixed-context blobs that are not
public-safe inputs to this candidate. L100 exists, but its corrupted,
misrouted input supplies no usable canonical result (`CAN-U100`).

## Supported synthesis

No supported synthesis statement remains in this lane range.

## Unsupported or unknown

No reranking conclusion is accepted from L97 or L98. L99 is qualified but not
consumed, so no learning-to-rank experiment is supported here. L100 cannot
support PageRank or centrality-prior fusion.

## Synthesis conclusion

This range supplies no validated, consumed conclusion. Static and generative
reranking, learned usage signals, and centrality priors all remain unsupported
or unknown for this candidate.
