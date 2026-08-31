# Research ranking and provenance

## Corpus status

- Reviewed input revision: `d1dbac36208b0066fc8907bd9fe9408fc5c51a60`.
- Candidate raw-input revision: `60f6935f26c912a32aac0e1aa0bb6b5dda063c9b`.
- Exact positive selection: only the 21 lanes in
  `research/positive-claims.json` are eligible, and only for the exact claim
  IDs listed there. Each is bound to an immutable Git blob at the candidate
  raw-input revision.
- Other non-missing rows retain reviewed and candidate blob identity for
  provenance only; their presence at the candidate raw-input revision does not
  make them eligible for synthesis.
- Filename inventory: 95 committed lane files; missing L14, L18, L68, L88, and L92.
- Content classification: 21 validated and consumed inputs, 3 qualified but
  unconsumed inputs, 46 inherited inputs excluded as not public-safe for this
  candidate, 14 gap/incomplete inputs, 2 origin-unbound inputs, 9 misrouted
  inputs, and 5 missing inputs.
- A filename count is not an artifact-validity count. This document makes no research-complete or corpus-complete claim.
- Immutable origins for L13 and L19 remain unknown.

Here, `validated` has one narrow meaning: the exact candidate-revision blob was
reviewed as public-safe, aligned to its manifest subject, minimally complete,
and citation-bearing for one or more allowlisted claims. It does not mean that
the sources are current, the claims are independently reproduced, the lane is
complete, or any implementation or deployment is accepted. A validated lane
supports no claim absent from `research/positive-claims.json`.

The machine-readable map also owns the affected-check contract. Run
`python3 tooling/check_research_provenance.py --self-test` for the focused
parser test and `python3 tooling/check_research_provenance.py` for all declared
provenance, count, allowlist, citation, partition, compatibility, and
public-safety groups.

Canonical unknown identifiers are preserved exactly:

- `CAN-U58`: canonical L58 is unavailable; no GraphQL conclusion is accepted.
- `CAN-U59`: canonical L59 is unavailable; DuckPGQ remains an unverified lead.
- `CAN-U74`: canonical L74 is unavailable; the embedded L70-labelled public
  candidate is not reassigned.
- `CAN-U100`: canonical L100 has no usable result because the input is a
  corrupted, misrouted generic article/search dump.

## Inherited exclusion inventory

The following 46 inherited raw blobs remain byte-identical to the reviewed
revision and are not eligible for this candidate:

- Target-host, resource-floor, corpus-scale, deployment, or local-performance
  context: L01, L02, L04–L10, L15–L16, L23, L28, L32, L36, L38–L39, L41,
  L46–L47, L65, L71, L84–L85, L89, L91, and L97–L98.
- Non-public project, artifact, tooling, or repository context: L03,
  L17, L24, L27, L30, L34, L45, L51, L63, L67, L73, L76–L77, and L80.
- Non-public configuration or execution context: L52, L56, L61, and
  L90.

This exclusion means only that a mixed inherited blob is not public-safe and
reproducible as an input to this candidate. It neither accepts nor rejects the
blob's public-source claims. The source-map authority note records the reason
for every excluded row.

## Evidence-bound experiment order

This order is a dependency-aware research sequence, not an adoption or deployment decision.

| Order | Candidate experiment | Validated support | Required gate |
| ---: | --- | --- | --- |
| 1 | <!-- positive-claim: EXP-01 --> Establish a reproducible PostgreSQL hybrid-search run in a public benchmark harness. | L20, L64 | Representative qrels, fixed metrics, and reproducible timing. |
| 2 | <!-- positive-claim: EXP-02 --> Compare SQLite, FalkorDB, and LadybugDB as storage candidates. | L43, L48–L49 | Durability, concurrency, license, memory, and latency measurements on a public fixture. |
| 3 | <!-- positive-claim: EXP-03 --> Evaluate structural code extraction and graph construction. | L29, L33 | Language coverage, reference accuracy, bounded resources, and a public test corpus. |
| 4 | <!-- positive-claim: EXP-04 --> Evaluate a parameterized constrained batch-extraction and quantization comparison. | L37, L40, L42 | Bind the exact runtime/model/prompt/schema/fixture; measure semantic quality separately from syntax, then measure target-host memory, rates, latency, concurrency, and aggregate throughput under declared parameters. |
| 5 | <!-- positive-claim: EXP-05 --> Pilot Splink entity resolution. | L22 | Representative public entity data, clerical labels, precision/recall, and reversible identifiers. |
| 6 | <!-- positive-claim: EXP-06 --> Exercise a small read-only, typed, response-bounded query surface. | L53–L55, L57 | Negative authorization tests, output caps, and public-fixture measurements. |
| 7 | <!-- positive-claim: EXP-07 --> Measure federated aggregation and refresh with bounded scheduling. | L72, L78–L79, L83 | Freshness, partial-result, contention, and failure-recovery tests on public fixtures. |
| 8 | <!-- positive-claim: EXP-08 --> Evaluate token-budgeted traversal. | L86 | Retained-evidence coverage and fixed token-budget tests. |
| 9 | <!-- positive-claim: EXP-09 --> Evaluate frontmatter query behavior without adding a persistence claim. | L93 | Public note fixtures, schema variance tests, and bounded query results. |

Excluded lanes cannot advance an experiment. L60, L66, and L99 contain
qualified public-source material but are not consumed and do not advance this
order. The 46 inherited mixed-context lanes above are also excluded and do not
advance it. The corpus does not support a reranker survey (L21), canonical L58
or L59 conclusions, the L69 A/B protocol, L70 judge-bias conclusions,
canonical L74, or canonical L100.

## Synthesis coverage

| Synthesis | Lane range | Validated and consumed | Qualified, unconsumed | Other, unconsumed | Lanes not consumed |
| --- | --- | ---: | ---: | ---: | --- |
| S-A | L01–L21 | 1 | 0 | 20 | L01–L19, L21 |
| S-B | L22–L42 | 6 | 0 | 15 | L23–L28, L30–L32, L34–L36, L38–L39, L41 |
| S-C | L43–L70 | 8 | 2 | 18 | L44–L47, L50–L52, L56, L58–L63, L65–L70 |
| S-D | L71–L96 | 6 | 0 | 20 | L71, L73–L77, L80–L82, L84–L85, L87–L92, L94–L96 |
| S-E | L97–L100 | 0 | 1 | 3 | L97–L100 |

## Historical finding record

Source review: independent Graphify public-safety review. Every row remains
bound to its finding ID, reviewed revision, severity, and historical effect.

| Finding | Reviewed revision | Severity | Historical effect | Corpus disposition |
| --- | --- | --- | --- | --- |
| GSR-P1-01 | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | P1 | Public-safety blocker. | Only the exact 21-lane positive selection is eligible; 46 inherited mixed-context blobs remain byte-identical and are explicitly excluded. Other inputs are qualified but unconsumed, incomplete, origin-unbound, misrouted, or missing. |
| GSR-P2-01 | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | P2 | Corpus provenance and completeness blocker. | Public research was separated from non-research wrappers; incomplete and misrouted inputs are explicit gaps or excluded. Missing canonical content was not invented. |
| GSR-P2-02 | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | P2 | Reviewed-revision acceptance blocker. | L20 is limited to public evidence. L13/L19 are bound to the reviewed input and clean derivative, but their earlier origins remain unknown and they are excluded. |
| GSR-P2-03 | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | P2 | Research-completeness blocker. | Content classification now records 21 validated/consumed, 3 qualified/unconsumed, 46 excluded-not-public-safe, 14 gap/incomplete, 2 origin-unbound, 9 misrouted, and 5 missing lanes. |
| GSR-P2-04 | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | P2 | Unresolved-prior-effect blocker. | Retained residual: historical R1–R20 downstream implementations may still encode conclusions from the pre-repair mixed-context synthesis. This identity bridge does not revalidate their implementation provenance. |
| GSR-P3-01 | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | P3 | Candidate-validity blocker. | Known whitespace defects are repaired; verification must bind its result to the exact candidate revision. |

### Retained prior-effect residual

`GSR-P2-04` remains open at its original P2 severity and blocking effect. Its
exact scope is any downstream implementation or durable implementation claim
that relied on the historical R1–R20 synthesis before this provenance repair.
The compatibility map below preserves stable identity only; it does not prove
that any such consumer used only currently allowlisted evidence. This residual
blocks a broader claim that downstream implementations are provenance-cleared.
It does not block the bounded research-corpus allowlist, its deterministic
checker, or this documentation-only remediation. Exact consumer-by-consumer
provenance remediation or an authorized owner disposition remains required.

Authority effect: none. No adoption, publication, activation, deployment, or
source-currentness claim is made.

## Historical R1–R20 compatibility map

Downstream `R1`–`R20` references retain the identities originally defined at
`e1c8b4395d135b4dad3bbbbcaef6571f5425db5f:research/RANKING.md`. This table is
an identity bridge only. It does not restore the historical ranking, scores,
implementation sketches, source claims, readiness, or authority. In
particular, it does not make any excluded, incomplete, origin-unbound,
misrouted, missing, or qualified lane validated. Current positive evidence must
come from `research/positive-claims.json`.

| Historical ID | Stable label | Compatibility status |
| --- | --- | --- |
| R1 | Stable federated node identity | `historical_identity_only` |
| R2 | SCIP-to-KG symbol edges | `historical_identity_only` |
| R3 | Hybrid retrieval backbone | `historical_identity_only` |
| R4 | Retrieval evaluation harness and promotion gate | `historical_identity_only` |
| R5 | Unified per-corpus SQLite store | `historical_identity_only` |
| R6 | Consolidated read-only MCP server | `historical_identity_only` |
| R7 | Splink entity-resolution backbone | `historical_identity_only` |
| R8 | Content-addressed incremental refresh | `historical_identity_only` |
| R9 | Cross-corpus RRF scatter-gather | `historical_identity_only` |
| R10 | Token-budget-ledger context packing | `historical_identity_only` |
| R11 | Entity-identity governance package | `historical_identity_only` |
| R12 | Offline embedding model | `historical_identity_only` |
| R13 | Parquet snapshots and SQL surface | `historical_identity_only` |
| R14 | Recall-first blocking engine | `historical_identity_only` |
| R15 | Entity-resolution evaluation and promotion gates | `historical_identity_only` |
| R16 | SQLite freshness and validation ledger | `historical_identity_only` |
| R17 | Layered output and truncation contract | `historical_identity_only` |
| R18 | Shared-server authentication and isolation | `historical_identity_only` |
| R19 | Federate-don't-merge posture | `historical_identity_only` |
| R20 | HTTP-cache freshness envelope | `historical_identity_only` |

## Exact reviewed provenance and candidate eligibility map

The Git blob OID and SHA-256 identify each input at the reviewed revision.
They preserve reviewed provenance without establishing an earlier origin. For
the 21 `validated` rows only, `research/positive-claims.json` binds the source
path and candidate-revision blob to exact claim IDs. Every other row preserves
identity or an explicit gap but grants no synthesis eligibility.

| Lane | Artifact path or gap | Public-safe subject label | Class | Reviewed revision | Input blob OID | Input SHA-256 | Authority note |
| --- | --- | --- | --- | --- | --- | --- | --- |
| L01 | `research/raw/L01-graphrag.md` | Microsoft GraphRAG: architecture, local feasibility without Azure, cost profile | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `fcfc5cf6fb802422ebad379fcb9dc7901dc23ae1` | `b92df844245fafe6618ab2d88f88e4b18c4bca4ad14f23d3b8a2743f27635f12` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L02 | `research/raw/L02-lightrag.md` | LightRAG (HKUDS): incremental GraphRAG claims, local run evidence | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `59e94c7fe113c105bd60db70e8de8b60534af6a5` | `9724b3340c6eb36b0c890e626e4e5a6ef788b309469d3bd3d239ea60e02931cd` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L03 | `research/raw/L03-nano-graphrag.md` | nano-graphrag: minimal implementation worth vendoring? | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `db068f93b0743fbd510aaa38b82877f355259a52` | `4492beda0b78687267dc907d3a8866f7d1acc813788cbd804faced4ea840cfd1` | Inherited blob mixes public-source research with non-public project, artifact, tooling, or repository context; excluded without judging its public claims. |
| L04 | `research/raw/L04-graphiti-temporal-kg.md` | Graphiti (Zep) temporal KG: can it run fully local, what does it add over structural graphs | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `e80d3830f503a3cd77f5c7850c0617821ee07538` | `4e13f91f5d2792964edc6985d1565b5f4c520459cfbc267584e50578c2583bbe` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L05 | `research/raw/L05-community-detection-summarization-no-llm.md` | Community-detection + summarization strategies (Leiden/Louvain offline, no-LLM variants) | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `b97cc36ed7cfa41ac209e43199bc0c1d0f5cd304` | `5391f512bbc27484da9b5e2ac5ed3c9ea2ea92b182729ed30aa3e7a25f0d5260` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L06 | `research/raw/L06-hipporag.md` | HippoRAG/HippoRAG2: PPR-over-KG retrieval effectiveness evidence and local cost | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `6d93e99fb30bf21aad2471a5f1ff5de441ea75fb` | `728b0fc9ae1af99c9fae350200c8b60cdab31de5f0ba31909f1f705a18caf13c` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L07 | `research/raw/L07-graphrag-vs-vector-rag.md` | Evidence comparing KG-based vs vector-only retrieval quality on doc-heavy corpora | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `32cd7d4dd4b1be98d78eaea2a4b9df9e5e4e23d4` | `2f72118c98020c86fbed14aaf50dc71148818555b4833dd84d79eadafdec5a5c` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L08 | `research/raw/L08-sqlite-vec.md` | sqlite-vec maturity, performance, and embedded-store fit | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `17f1fb51894c5aa817bc847ac7998d0aeb365343` | `5af528f28f3355b486555bc507c1c22be5106018d5d736ac4b6ee8db704b42b3` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L09 | `research/raw/L09-lancedb-embedded.md` | LanceDB embedded: perf, licensing, disk format stability | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `d04ab08a67dec1b0fbf1db8b84f8c94f99a00a3e` | `9f8a4b33a02ac8b6f5d9e74ba8a9bd4dc74ec8cf342feb232120d0667067d99f` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L10 | `research/raw/L10-qdrant-local-vs-server.md` | Qdrant local-mode vs server: when is each right | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `d85771a645cd1c5af7d8ee367028b16b4d2aae54` | `071f4057507f579ed3045ac3a7be1dcbf958b825d35af15dfe3cb262c274e237` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L11 | `research/raw/L11-sqlite-vec.md` | usearch/hnswlib: raw index speed and persistence options | `misrouted` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `fef37876b7219adf7911eb5536f7bd4e65ddcc51` | `ece231cf41ddbc7a2a774496e289335092c4df56db50463c0b4ce9959e1a6640` | Duplicate content does not answer the manifest lane. |
| L12 | `research/raw/L12-lancedb.md` | Model2Vec/static-embedding speed-quality envelope | `misrouted` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `6bc026463b5cb3eb53c35e04136df8bf27672588` | `4775bcde339397df184aa35b8dee963ede84a82625f5e7c83240729224727815` | Duplicate content does not answer the manifest lane. |
| L13 | `research/raw/L13-embedding-models.md` | CPU-capable embedding-model comparison for Markdown-heavy documentation | `origin_unbound` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `23b67b449b284dbedc7465edf0289b5073280cce` | `252ca704278e1c13c343b26a1214c93f6e4e80677c228ada895b3b95001bc6b2` | Reviewed input has an unknown pre-d1 origin; the clean derivative remains excluded. |
| L14 | gap (no committed path) | Matryoshka + binary/int8 quantization: storage and recall tradeoffs | `missing` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `-` | `-` | No reviewed input blob. |
| L15 | `research/raw/L15-bm25-backbone.md` | rank-bm25 versus tantivy-py build/query comparison | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `e5161b46d7e8dbfae54eaf6799ff9922131b00af` | `d67ae8392e467f7cb9f7fa460211319750085071a2d5ff6f7fce8b113c814f77` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L16 | `research/raw/L16-tantivy-py-vs-sqlite-fts5.md` | Tantivy full-text in Python: maturity, features vs FTS5 | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `54184cf1ea03785a8684bcbd78d2a66cec140e39` | `629dd7730fb6baffcb5403fec252f1b79a90e6529f3bf00cdd0808aae26feb8a` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L17 | `research/raw/L17-rrf-fusion.md` | Reciprocal Rank Fusion: tuning evidence, alternatives (convex combination) | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `9130408185f298e4fe6451689434b7656ecb0a4b` | `46228627313a99ace6e0b36b8535039823450159a5a8c2fbcf9ea03661cdbf26` | Inherited blob mixes public-source research with non-public project, artifact, tooling, or repository context; excluded without judging its public claims. |
| L18 | gap (no committed path) | ColBERT/PLAID late-interaction CPU feasibility | `missing` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `-` | `-` | No reviewed input blob. |
| L19 | `research/raw/L19-splade-sparse.md` | CPU-capable learned-sparse retrieval comparison | `origin_unbound` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `8efbddbc09cc14b432cad576ba2c6f321c7b7070` | `368fb119b9f39e384dc91cd7f8b1a148b18256e99313778afdf184d2ae46cbd7` | Reviewed input has an unknown pre-d1 origin; the clean derivative remains excluded. |
| L20 | `research/raw/L20-pg17-hybrid-search.md` | PostgreSQL full-text and pgvector hybrid-search comparison | `validated` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `dfb7485b107f40415ea6a619ce29bfc9e834cce2` | `de6bdbc38a0166f7d3618d58600c4a4481113d225df398eb0d4b54f238f3bda0` | Validated content consumed from the sanitized candidate blob. |
| L21 | `research/raw/L21.md` | Local rerankers survey: bge-reranker-base/v2-m3 CPU latency vs quality | `gap_incomplete` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `dc68953987858938512b3f18f65ad6b4ec17f4a9` | `ef8a28bad6201f4a5cb675a8b6cf6b8fcf8976ace4b423f2473b7c18225ef8ca` | Draft plan only; no findings. |
| L22 | `research/raw/L22-splink-entity-resolution.md` | Splink probabilistic ER: fit for person/org entities across repos | `validated` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `a9fbf2d245dbbed9c933ffb5ee5c7cb3fb2ce849` | `39ee840623075d59d74a03ff17213ded4f183385cc99a1e6a85fc3642e8873cd` | Validated content consumed from the sanitized candidate blob. |
| L23 | `research/raw/L23-entity-resolution-dedupe.md` | dedupe library: current state, scaling | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `3f8b0d62f476a41426038b9556229d4a4b20ea9a` | `de05cc28f8d2953f104ed18efb14d7f40519cbd42f695444e0f47b7487c560b3` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L24 | `research/raw/L24-rapidfuzz-blocking.md` | RapidFuzz blocking strategies and public patterns | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `08a69baed718ace9971540e67173cb8ff4ca6fbd` | `6797cd686f7fa841087b53a32d574b1227d47d19ee139b35e05c2eda8acae8b8` | Inherited blob mixes public-source research with non-public project, artifact, tooling, or repository context; excluded without judging its public claims. |
| L25 | `research/raw/L25-gliner-entity-resolution.md` | Wikidata reconciliation: offline dumps vs API patterns for entity anchoring | `misrouted` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `f329117d2bcfc2caabf420427ff061d5dd86904e` | `8a1182aaf804ed61aa2d49c7e740cde2e25f07857a0cfc448dbd58c197aeae90` | Reciprocal lane-identity swap; not reassigned. |
| L26 | `research/raw/L26-wikidata-reconciliation.md` | GLiNER zero-shot NER model-size and quality comparison | `misrouted` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `0e1a63674ea805c94131e9da1265dccc342c69f2` | `b8067b7fe9ddcd339fa11b7b9183bcb16f9002094eae026f55a8f65f7c3173d1` | Reciprocal lane-identity swap; not reassigned. |
| L27 | `research/raw/L27-cross-repo-id-governance.md` | Cross-repo ID join-table patterns (bioguide/FEC-style) governance | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `05611498ef3571a62a68aac3d0ebe0ebf62ac5ce` | `63e93b4656da330be4b0ee4f27cdeed718863ae76805415d64c884d083a895f9` | Inherited blob mixes public-source research with non-public project, artifact, tooling, or repository context; excluded without judging its public claims. |
| L28 | `research/raw/L28-er-eval-methodology.md` | ER evaluation: precision/recall measurement at threshold for entity merges | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `ca731570727197f87b7f116ca23cd4ceaa2aad56` | `69530310520bb01e35e41e6a0756044647f8d0b65207c7db844c7255ac694fd6` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L29 | `research/raw/L29-tree-sitter-grammars.md` | tree-sitter grammar coverage gaps for py/ts/go/swift/md frontmatter | `validated` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `7deb8049d09036e6be550830765cfc818b740027` | `17963ac3bfa3090dc8f7b3a4f44445db459c06c60fe42fbf2fd0807b473e4c5e` | Validated content consumed from the sanitized candidate blob. |
| L30 | `research/raw/L30-glean-feasibility.md` | Glean (Meta) code indexing: self-hosting reality check | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `9ab4ef3cfba397278cd523a0c0cf6e4823f8d48d` | `9c1a049a9c6ed88f4277499d4f2e0e14642cb44db1636941fb425aa08f3b8928` | Inherited blob mixes public-source research with non-public project, artifact, tooling, or repository context; excluded without judging its public claims. |
| L31 | `research/raw/L31-scip-offline.md` | Sourcegraph SCIP indexers offline | `gap_incomplete` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `3bf31f732f05f77ad7b884f51c8ff3350ab05a81` | `2eb506781450ec2ea10c0b04865a2a175db25283791681df6b1379b86fc8dbdf` | Explicit gap; no findings body. |
| L32 | `research/raw/L32-stack-graphs.md` | stack-graphs name resolution: applicability to cross-file refs | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `a1fe954a9f04e6c79ca40857087142a0127a74e1` | `6a55dc2ae9793df49fcad0beebfec5d1ebd671103b51bf89ecc9af8ac72f7d6a` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L33 | `research/raw/L33-joern-cpg.md` | Joern CPG security and flow insight comparison | `validated` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `9b7f2bb2a8a3fe80a914622762854131bccb95cf` | `1f1e3a27d3243799e6737b66ef53dfb548c5aff44c234525fbc094fc099d01fb` | Validated content consumed from the sanitized candidate blob. |
| L34 | `research/raw/L34-lsp-scip-reuse.md` | Reusing LSP/SCIP data in structural graphs | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `aa2d0eec71750a2488c6d6dc49ec9afd48780832` | `6ad76468866b0ec6073bdb01d0292cc1e64efadb93880809dd70d11e73a7bbac` | Inherited blob mixes public-source research with non-public project, artifact, tooling, or repository context; excluded without judging its public claims. |
| L35 | `research/raw/L35-dependency-extractors.md` | Import/dependency graph extractors comparison (grimp, pydeps, madge…) | `gap_incomplete` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `8149f5f1e908bae2539912006e41cdd1e0b80754` | `b5bb2f98eef166df2b69ab4611cad921af4a47eaba7e01cfb70bf8e26a689f0d` | Conclusion-only fragment; scored comparison absent. |
| L36 | `research/raw/L36-ollama-extraction-models.md` | Ollama extraction-model CPU profiles | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `2e16bd5af2e093d15189361462c194a23f196c5f` | `1c3393cf8a6e2a7e06e5822060f1c50e2f701072700e249bbcc1f5707486d876` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L37 | `research/raw/L37-llamacpp-server-profiles.md` | llama.cpp server: concurrency + quant profiles for batch extraction | `validated` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `253eaae7c8c5292225cde3484f4cafff5bfe1bc9` | `016172df17e22085dfcdcb79087b18abd0c1301a6733f21ecab66b24f32209cb` | Validated content consumed from the sanitized candidate blob. |
| L38 | `research/raw/L38-vllm-cpu.md` | vLLM CPU-only: realistic or skip | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `f94a50d9b339d23f4c28b1dc31b8f6abc50a62d0` | `e036ec7900cb00e2893413adec09a24f7f8c0bf8aa7f8c2b1e84443cbd48ff55` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L39 | `research/raw/L39-structured-output-reliability.md` | Structured output reliability: outlines/xgrammar/guidance | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `33a0e425012ad51c5e04318837b9b0e8eb974cce` | `d37e79945e4d66fccd28456826aa9f9b2b2f8dbb5aa57116378cd84b5f8a9e91` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L40 | `research/raw/L40-small-model-extraction-quality.md` | Small-model entity/relation extraction quality: Qwen3-4B, Phi-4-mini, Llama-3.2-3B | `validated` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `29c0100dab529d878470badaa2b8a817efff709e` | `01a3e89ff9aa237c867fb4d701cf103dbe900196007625914feda346bf36893c` | Validated content consumed from the sanitized candidate blob. |
| L41 | `research/raw/L41-nightly-enrichment-budget.md` | Scheduled enrichment resource-control design | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `73f61609242377c517d3c29ffcfbb197d08fcb07` | `67efda1fda292924bd5eae601bbccf4a3cbf26535d4dabce4ef5a3cad921e7e2` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L42 | `research/raw/L42-gguf-quantization-tradeoffs.md` | Quantization tradeoffs (Q4_K_M/Q5/Q8) for extraction fidelity | `validated` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `13a75d80901c1d39deff7a1554d63e1bbf243b7c` | `ff8bef9f0fa321bcf7401509149bf909fb34d2dd7b17f0c05e132ad04b0cdb45` | Validated content consumed from the sanitized candidate blob. |
| L43 | `research/raw/L43-sqlite-unified-store.md` | SQLite unified store pattern: FTS5 + json1 + vec together — schema designs | `validated` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `ddb3fe206e906cd47b2254d706adba323308f411` | `948581cb038aa5edc2724e8b2554accec99b452dd7addafda3494376aa4ca7c6` | Validated content consumed from the sanitized candidate blob. |
| L44 | `research/raw/L44-duckdb-vss-parquet.md` | DuckDB and VSS over Parquet graph snapshots | `gap_incomplete` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `2267fe1b130bbe71c7f700949e72c4b5f26208fb` | `b27abe4ab6ced63f98b2acafe7b893d7075cad984e6d5e3220b9079369e9614a` | Explicit gap; no findings body. |
| L45 | `research/raw/L45-fingerprint-ledgers.md` | KV/fingerprint stores: LMDB vs sqlite vs files for freshness ledgers | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `48a3cc6e58aaf628dd4978f0c065c9f658364b69` | `5df155ee2ef78ae96bd9b6877e97bb1613c2831ea13168da7c8452769f613157` | Inherited blob mixes public-source research with non-public project, artifact, tooling, or repository context; excluded without judging its public claims. |
| L46 | `research/raw/L46-parquet-snapshots.md` | Parquet-backed graph snapshots: conversion + query patterns | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `9cf57d9e5411123c83c9deabfa6395ec9dd6795a` | `f2a80153502148157a60e7d209ada25823f7b33c0f72379e418317f63b6cd739` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L47 | `research/raw/L47-neo4j-community.md` | Neo4j Community versus in-process graph-query patterns | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `ead0998bfd938aaef3923b15361067d3dd1f17c0` | `a5323e1509d49f4f3a5f0d6226a21aae099c754254d4cf8f33c5cbf8bd4d616e` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L48 | `research/raw/L48-falkordb.md` | FalkorDB CPU resource-claim verification | `validated` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `9fb77573d29e0e29cdb0a4815047a5f61a4dbb27` | `55eb114b912e2c0985636aa5e347d84c4302ed65a82410e774f2b040725434ed` | Validated content consumed from the sanitized candidate blob. |
| L49 | `research/raw/L49-kuzu-embedded.md` | Kùzu embedded graph DB: Cypher locally — integration effort + perf | `validated` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `7c976aa7aca308207203bd6e3bb6e31b0b7b96bf` | `ab2d629c8646dae1d13d2ea2c1f2a99255737f82922fd1e330c39b099557f663` | Validated content consumed from the sanitized candidate blob. |
| L50 | `research/raw/L50-mcp-spec-capabilities.md` | MCP spec current capabilities for exposing graph queries (resources/tools/prompts) | `gap_incomplete` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `c2d905d62c98ceb669a3829cf3bdcf157e21b9af` | `23c30f7730e5c3e26f5a22f32e21c475d1f06f847e824e0ef99ee780118846b8` | Blueprint fragment; inventory and verification absent. |
| L51 | `research/raw/L51-graph-mcp-inventory.md` | Existing graph DB MCP servers inventory (kuzu/neo4j/memgraph/graphQL) | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `efdd44b5ead808f4952da77d3adff91b7cf2b8a2` | `32f3bc9496e15a8047359629340c87bffc69452cb23637fe491ca19adbef3d3b` | Inherited blob mixes public-source research with non-public project, artifact, tooling, or repository context; excluded without judging its public claims. |
| L52 | `research/raw/L52-code-search-mcp-survey.md` | Filesystem and code-search MCP server survey | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `a6fecae81fd7b2b9024ff99eb415255cd8c86d80` | `a24d0823bae35ca5ceb51f67080323ebf13db82635e20c7b4f40cb5ffa16710f` | Inherited blob mixes public-source research with non-public configuration or execution context; excluded without judging its public claims. |
| L53 | `research/raw/L53-agent-tool-schema-design.md` | Function/tool schemas for graph traversal | `validated` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `66c7e62a327b50b026988567f4d990fbb240db42` | `54c7be8af2c2b2b8d1192c8cefefd968e767fc7dc266a93fea8a81014dbe4626` | Validated content consumed from the sanitized candidate blob. |
| L54 | `research/raw/L54-truncation-strategies.md` | Truncation strategies for large traversal results in tool payloads | `validated` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `8689fcde9163a05db6d43041ad8bbc9311895d34` | `23df4ae7874332ba344b293f85eac4bac74b972c5aee1790fcd09ce43aa31dde` | Validated content consumed from the sanitized candidate blob. |
| L55 | `research/raw/L55-mcp-auth-isolation.md` | Client isolation and authentication for a shared MCP server | `validated` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `6fb843b50fd5259eb8d13c6709ed1a8eecc3d471` | `ce3dac57d3f0e80bd4d3dc3d0f1ec5f38e4d69c46d013614827caee80d70a8fb` | Validated content consumed from the sanitized candidate blob. |
| L56 | `research/raw/L56-mcp-overhead-vs-cli.md` | MCP round-trip versus direct CLI overhead | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `9b3a6bd5b04252d69a44b291b8237f779da4856d` | `35559c54e2456f18de88720347f089eec0180e231d202259d932d69998fa425c` | Inherited blob mixes public-source research with non-public configuration or execution context; excluded without judging its public claims. |
| L57 | `research/raw/L57-kuzu-cypher-ergonomics.md` | openCypher ergonomics versus custom command interfaces | `validated` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `d8b1aaad156582c50885c288e9af5e02fef43505` | `6917ecb29a8d9779e6d1b5a0123a0058e8129936b22ff96919a2ed5450d68f1b` | Validated content consumed from the sanitized candidate blob. |
| L58 | `research/raw/L58-local-graphql-layer.md` | GraphQL layer over local graphs | `gap_incomplete` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `2caed0e1076b1d90b433269859627e8dd0140aef` | `d041ef81b6d6edb2e95183b26724f723d7c1f6feab4ceb68f93b86235ee6889d` | `CAN-U58`: canonical payload unknown; verdict fragment rejected. |
| L59 | `research/raw/L59-duckdb-sql-surface.md` | DuckDB SQL over graph tables as a query surface | `gap_incomplete` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `05ae2defc489bbd24b9a5aa00030e44b0bf49fe2` | `a59bc08214eed748d0fe78c8d527e81a979ef7d44d7a5493af034326d1c4ff54` | `CAN-U59`: canonical payload unknown; DuckPGQ remains an unverified lead. |
| L60 | `research/raw/L60-nl-template-routing.md` | Non-generative natural-language template routing and abstention | `qualified_unconsumed` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `98bd72a3a9de6d3ec1600185d315447b6c98fb64` | `8a288fd8a26606b74b42c747407999dc8d78b6bc74afc9d51b666f088613a4d9` | Public-source material retained in its candidate-revision blob; qualified but not consumed. |
| L61 | `research/raw/L61-cli-ux-patterns.md` | Best-in-class CLI UX patterns (rg/fzf/jq style) applied to graph nav | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `75490becbafb9e3c86eb544a1500afd1560787c6` | `45cae1d4f88653973b0adc07b6396e2cc9823efa9f70bad65bd7fe88367af2a5` | Inherited blob mixes public-source research with non-public configuration or execution context; excluded without judging its public claims. |
| L62 | `research/raw/L62-saved-queries-skills.md` | Parameterized saved-queries-as-skills pattern design | `gap_incomplete` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `bc2eadbaf501dc354076b44f9557208b9a4a8b1c` | `549a6ae35b3df9e5c8903e9e60ac0a4b95ab7ef58cd71a253d6026024879df6c` | Design lead only; table and citations absent. |
| L63 | `research/raw/L63-graphify-merge-federation.md` | Cross-graph merge and federation mechanics | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `3eafa6bbcb20e8047384762383e0f4a4dd49c1ab` | `aa5f4f3eea28168154efb0902c33183b5f02bca1fa62093809ad5beaa2e430a2` | Inherited blob mixes public-source research with non-public project, artifact, tooling, or repository context; excluded without judging its public claims. |
| L64 | `research/raw/L64-beir-local-harness.md` | BEIR subset evaluation-harness candidates | `validated` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `60f4adb5506b10b826c2061c7a1b1b7f10dd5110` | `5948f8907581fabd3c45e9b365d1e1ac7bdecb76c1f7d0c71bda3f02207b1eab` | Validated content consumed from the sanitized candidate blob. |
| L65 | `research/raw/L65-local-judge-metrics.md` | RAGAS/TruLens metrics runnable without cloud APIs | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `a408982eb44bab917eb7b38d19c349828f56f8be` | `4177f0fdaea92327c7694aad3408549254ff57d337ad5e89a483611014ac59f8` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L66 | `research/raw/L66-golden-set-mining.md` | Question/evidence candidate generation and quality-control patterns | `qualified_unconsumed` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `a5d88220e64360ffa7489dc0d688509144feb7c6` | `64123259b5b6e95009067d64ecc2e4957a2d9751365cf1ee3157ccc85279a0e4` | Public-source material retained in its candidate-revision blob; qualified but not consumed. |
| L67 | `research/raw/L67-recall-tooling.md` | Recall@k tooling for comparing hybrid stacks offline | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `4c49cd1f418e1a324532e452f209193ac076d70e` | `dab29a6ef3ccfeab0a5d5bc0bdfd499ca0947cb3fe2f0e022af408bde9cd2a4b` | Inherited blob mixes public-source research with non-public project, artifact, tooling, or repository context; excluded without judging its public claims. |
| L68 | gap (no committed path) | Search-latency budgets and measurement harness | `missing` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `-` | `-` | No reviewed input blob. |
| L69 | `research/raw/L69-namespace-strategies.md` | Evaluation A/B protocol | `misrouted` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `fd83f817d4c321a180bdd8fec6e7ab0826b533ca` | `0160fd4af8743d25e2e8b6815db308b3cfd94e66027fb018455be967d1eb948c` | Public namespace note retained only as an unassigned lead; canonical L69 absent. |
| L70 | `research/raw/L70-entity-hub-corpus.md` | LLM-judge biases and mitigations for ranking experiments | `misrouted` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `4f51c6320a942644ea5713e446b85a721db4d3be` | `65476569e7643e15826003182d56ab18353c6dc936e7135ce70d49db9b5f9813` | Serialized manifest, not lane research. |
| L71 | `research/raw/L71-merge-graphs-scale.md` | Multi-corpus merge-graphs scale behavior | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `82562ef09296442076dc711a6f03d121ffffecd1` | `2f3995422d2b337c14f58a937e2667a34b51f9c7bf473a712f8eda135290f021` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L72 | `research/raw/L72-scatter-gather.md` | Scatter-gather federated search aggregation patterns | `validated` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `233da95dca626772e6cc1f9afa551497135a1876` | `3e6cc403fa8b403258b5fba2fc6a728230ef51b977e38a801b6f02db60b9e2bc` | Validated content consumed from the sanitized candidate blob. |
| L73 | `research/raw/L73-namespace-strategies.md` | Namespace/prefix strategy for multi-corpus node IDs | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `b129f1d21982bae6eb0caeb0df4b53eca72da1f1` | `61f227499d8a313269422eaf3ba5a57f696cea75bdd8b513d07c10cc2f58a610` | Inherited blob mixes public-source research with non-public project, artifact, tooling, or repository context; excluded without judging its public claims. |
| L74 | `research/raw/L74-entity-hub-federation.md` | Shared entity-hub design pattern | `misrouted` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `3343b2765ca22bdb18dec4db9674c3db543670c7` | `187a49377e1365f7498e12f013bc2b395e1150af251cd219f4a576b361ed0986` | `CAN-U74`: embedded L70-labelled public candidate not reassigned; canonical L74 absent. |
| L75 | `research/raw/L75-provenance.md` | Lightweight provenance standards (PROV-O subset) for graph edges | `gap_incomplete` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `588f541510c900ed19cec9f82d9843a280ef0ea4` | `ec9340f60e228b03d9cea6f1bc4756fd691cd76dacd7da100cdbe9dff6d747cd` | Unverified lead only; claimed evidence body absent. |
| L76 | `research/raw/L76-merge-vs-federate.md` | When NOT to merge corpora: isolation benefit evidence | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `28cd62d8ae656b5357428ede3d13a26e213b2078` | `2b08fb3555b173e5180012e4fc553028ea7414959b6d02a1417399885c6dcabf` | Inherited blob mixes public-source research with non-public project, artifact, tooling, or repository context; excluded without judging its public claims. |
| L77 | `research/raw/L77-cross-corpus-routing.md` | Cross-corpus path-finding UX: routing heuristics for corpus selection | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `9b759b4ea813497fd942c0c301c0711cc84965da` | `881fe266489c0c9f7299ba7a91397f0779af19ce08a0b73732d7c51f09169d98` | Inherited blob mixes public-source research with non-public project, artifact, tooling, or repository context; excluded without judging its public claims. |
| L78 | `research/raw/L78-git-delta-reextraction.md` | Git-delta driven re-extraction: affected-file cost model | `validated` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `b6f7c1b9e2d4a390ce5a9004ea7c670e7fb90ff6` | `0bd6f7f7c00c3a6a4e212739125016361c45beb985d6f4d9c73c5ace959bb30d` | Validated content consumed from the sanitized candidate blob. |
| L79 | `research/raw/L79-watch-vs-cron-refresh.md` | watchdog file-watch vs cron refresh: reliability tradeoffs | `validated` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `a54bda8a474db03ea69fda176fc30aebb50df294` | `c8d4c1894bfd7dfc9228f512604f2f83281f618bf0945406f24c8b649a7ece60` | Validated content consumed from the sanitized candidate blob. |
| L80 | `research/raw/L80-merkle-change-detection.md` | Merkle-tree change detection for staging views | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `eac4ac2efc97340f399a4848b90e722490973b62` | `07171ded38763e2422c77447de7cf9099c8a9820e0329d79364d122448d03784` | Inherited blob mixes public-source research with non-public project, artifact, tooling, or repository context; excluded without judging its public claims. |
| L81 | `research/raw/L81-content-addressed-cache.md` | Partial graph update safety: graphify update --force semantics audit | `misrouted` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `28b0ace7cc8acf90d67b908e65eaa32d98b9c695` | `6f35e571e8e008c298a5087b32334cd110266d98bbc6fd333e88b31729cabfcb` | Manifest identities are swapped; excluded. |
| L82 | `research/raw/L82-update-force-audit.md` | Content-addressed chunk caching designs | `misrouted` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `b829697f17a5b49e1123970bafcbd248e208a3c0` | `48c7ec116af17645092d6e10235091c7a6780a49f35888b108067afdf1dae6d0` | Manifest identities are swapped; excluded. |
| L83 | `research/raw/L83-refresh-scheduling.md` | Parameterized refresh scheduling and resource controls | `validated` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `0665eb18ec88d14eef9f3c1eaf478bd2760d9f15` | `2e7907d66f94eb2d662bf2183309d1efcf18f727d1aabefbb53b96b993eb2502` | Validated content consumed from the sanitized candidate blob. |
| L84 | `research/raw/L84-staleness-signaling.md` | Staleness signaling formats for search clients | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `e06ee934e11eadfac55b2411f82644b07090cafd` | `9d9fa1729828a443b01ef7524da550878566c2612b1415dbfc26ab620054e35b` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L85 | `research/raw/L85-context-packing.md` | Graph-guided context packing: traversal-bounded snippet assembly | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `a33f3e4140f5e1ed81ad6ec645b791c8482157c2` | `2633f62fb44aaa54dd1a308b70f7a3fddfa98a9be4d19299b640b90f92be47c7` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L86 | `research/raw/L86-traversal-depth-budgets.md` | Token-budget-aware traversal depth selection algorithms | `validated` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `39301867585b80651c16b471fc59f50e7573ac0b` | `2ba5ded50c33b2edf5c95a3885976edddbfc608fe5dc8ee300c4b7bd80bdadc6` | Validated content consumed from the sanitized candidate blob. |
| L87 | `research/raw/L87-precomputed-briefs.md` | Precomputed community-summary briefs | `gap_incomplete` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `a7f2c5a5f106e17457a548bf9f740ef24bfcad86` | `edc74030fda7de04b83006b218cdb2675d2d38888ccc1db4d067706b5d4671fd` | Unverified lead only; claimed evidence body absent. |
| L88 | gap (no committed path) | Map-reduce summarization caching layers for repo QA | `missing` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `-` | `-` | No reviewed input blob. |
| L89 | `research/raw/L89-speculative-prefetch.md` | Speculative prefetch patterns and risks | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `ca871ace08e7512d997613be67b5fd090907302b` | `9da70b850abee8cec0e6218a611f2e0750a343d33ef5adff5d484e14fb7ab592` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L90 | `research/raw/L90-prompt-cache-serializations.md` | Prompt-cache-friendly stable serializations of graph results | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `1eaa328e09cca7e33cd93153b5d9cf6c24fa4fd8` | `5858c0359c823c8123f08bb8881b0c73ba133efe05bad8e52dc72fa041d7c906` | Inherited blob mixes public-source research with non-public configuration or execution context; excluded without judging its public claims. |
| L91 | `research/raw/L91-citation-format.md` | Citation format minimizing tokens while preserving spans | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `3d41475ab1304dca2a8d7f13bdd10d3e5bcab2bc` | `093db367df18ea5c2ad79d638aca7b9e9a3bf96591453c611c3343aa6257c303` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L92 | gap (no committed path) | Obsidian vault projection from graphs | `missing` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `-` | `-` | No reviewed input blob. |
| L93 | `research/raw/L93-frontmatter-query-engines.md` | Dataview-class engines over YAML front-matter locally | `validated` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `740a930a6d03365fa6cd79a55f99a4247b5e6d67` | `5e6dcedf7c8feed70e5a968b2ad4ebb64ac82b078860cbe9ddf0a9a8d56587cf` | Validated content consumed from the sanitized candidate blob. |
| L94 | `research/raw/L94-backlink-indexes.md` | Backlink indexes beyond wikilinks | `gap_incomplete` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `3a0c20ebd9e2601bd7658b89085957f81a148f1f` | `3a065d4a9d7643a30eebd3d3e1975804a9ee685dc45fdea9fc88395f793656a7` | File exists, but its internal working analysis is corrupt; no canonical result. |
| L95 | `research/raw/L95-hierarchical-note-mappings.md` | Foam/Dendron hierarchical-note-to-graph mappings | `gap_incomplete` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `58b72fdc05eef733fcec2e2e530ac29253bce0b3` | `057765437e44a679d44b91de973084325e6b81fcc8afba8f28879f51c88fbb27` | File exists, but its internal working analysis is corrupt; no canonical result. |
| L96 | `research/raw/L96-frontmatter-governance.md` | Front-matter schema governance across heterogeneous repositories | `gap_incomplete` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `7449ef7e8080c39bd3decc28c40def730f0b66c3` | `affcc7e334716a4be21ef6822c117da15b9ce7b0e1a3053b77c0b1f691254699` | File exists, but its internal working analysis is corrupt; no canonical result. |
| L97 | `research/raw/L97-reranker-onnx.md` | bge-reranker-base CPU latency/quality on 100-candidate pools | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `54a10070c7fc49c24ac6225389a6bf27cbef1901` | `93400f2aeee3517f62daa483365a813f21857090349cdeebfefa08bf28e9dc60` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L98 | `research/raw/L98-llm-as-reranker.md` | LLM-as-reranker with small local models: reliability data | `excluded_not_public_safe` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `a1b5ca7ee21cd9f0fce32d8af485f117c9478b8e` | `d633e91fec662595bcda93bd951d66f9634da0f463027f708b5f3fc2154bb44d` | Inherited blob mixes public-source research with target-host, resource-floor, corpus-scale, deployment, or local-performance context; excluded without judging its public claims. |
| L99 | `research/raw/L99-ltr-usage-signals.md` | Learning-to-rank from opt-in minimized aggregate signals | `qualified_unconsumed` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `5f3a871283ad4f1e6a433b79e9cc5a5649a72748` | `cef03b7182d23defb19077074081cd2d6d46c1c8602ec04a44e313e1073c460d` | Public-source material retained in its candidate-revision blob; qualified but not consumed. |
| L100 | `research/raw/L100-pagerank-fusion.md` | PageRank and centrality priors in hybrid ranking | `gap_incomplete` | `d1dbac36208b0066fc8907bd9fe9408fc5c51a60` | `56ff40fd5d236fe4b86b2c377bf636f83e7691d7` | `0fbeda12f735c4cd69a0f15687186244dd14a6691b904b3eb1a08a1f047c587b` | `CAN-U100`: corrupted misrouted dump; no usable canonical result. |
