# T13 context-eff — Citation formats minimizing tokens while preserving source spans

Investigated 2026-08-25 via primary sources (provider docs, W3C specs, arXiv, GitHub repos). Stack context: graphifyy==0.9.16 structural graphs + tantivy BM25 + sqlite-vec/LanceDB (arctic-embed-m-v1.5) + PPR-over-KG fusion, gated 3-way RRF; consumers are hosted coding-agent LLMs (no local LLM, no GPU, MemAvailable floor 3072 MiB). Question: how should graph-derived answers cite evidence so agent context carries maximal evidence per token while staying machine-re-verifiable?

## Token-cost math

Grounded anchors: BPE tokens average about 4 bytes of English prose (tiktoken README, checked 2026-08-25); o200k/cl100k-class BPEs split decimal digit runs into <=3-digit tokens, so long numeric offsets are disproportionately expensive; Anthropic excludes returned cited_text from output billing ('returned for convenience'), i.e. even the provider treats quote echo as overhead to discount.

| Format | Example (per citation) | Est. tokens/cite | 10-cite answer | vs baseline |
|---|---|---|---|---|
| Full inline quote (baseline) | '...25-35-word supporting passage...' | 30-40 | 300-400 | — |
| Quote + attribution marker | [1] '...passage...' (repo/src.py:L40) | 38-50 | 380-500 | worse |
| Sentence index into pre-segmented chunk | [u412:s3-s5] | 7-10 | 70-100 | -72..-80% |
| Hash node-id + char span | [k3x91@844-901] | 9-12 | 90-120 | -70..-75% |
| Session-dict int + char span (repeat cites) | [17@844-901] | 6-8 | 60-80 | -80..-85% |
| Int + sentence idx, delta-encoded repeats | [17@s3-5] then [17@s6-7] | 5-7 | 50-70 | -83..-88% |

Assumptions: brackets/punct ~1-2 tok; 5-char base36 id ~2-3 tok; a 3-4-digit decimal offset ~2-3 tok (<=3-digit digit-run grouping); sentence indices are shorter than char offsets but presuppose stable segmentation, while char spans survive re-segmentation and are what substring checks and rerankers consume. Input-side bonus: pointers let us replace fully pasted evidence chunks with header rows + resolve-on-demand, freeing context budget for more evidence rows (packing itself is L85/L87 scope).

## Agent re-verification workflow (design)

1. Emit — generator tags every claim with compact citations [nid@s-e]; nid resolves to the chunk/text-unit row (SQLite PK) that produced it; spans are half-open [s,e), zero-based, Unicode-code-point based (W3C + Anthropic convention).
2. Resolve — deterministic, no model: parse -> SELECT text FROM chunks WHERE id=? (<0.1 ms per PK lookup; 50 cites < 5 ms) -> slice [s:e].
3. Tier-1 check (free) — normalized exact-substring anchor test; prefix/suffix disambiguation on duplicate matches (W3C TextQuoteSelector semantics). On miss (post re-chunk/index refresh) fuzzy re-anchor via diff-match-patch-style approximate match with offset hint (Hypothesis-client pattern) and rewrite offsets in the ledger.
4. Tier-2 check (local, no LLM) — batched bge-reranker-base cross-encoder scores (claim, span) pairs; threshold calibrated on golden set (L66/L65 harnesses). ~110M params, ONNX/int8 across 16 CPU cores: tens of ms per 50 pairs, few hundred MB RSS — respects the MemAvailable floor.
5. Repair loop — regenerate only failed statements with their spans re-injected; never retry the whole answer.
6. Ledger — persist (claim_id, node_id, span_hash, verdict, score, ts) keyed by content hashes (L45 fingerprint-ledger / L81 content-addressed-cache patterns) for audit + cross-turn cache reuse.

Cost comparison: one extra hosted-LLM verification turn costs seconds plus billed tokens; the local pipeline above is <50 ms total.

## Findings

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|Compact pointer grammar [nid@s-e]: half-open, zero-based, code-point offsets into node canonical text|technique|https://www.w3.org/TR/annotation-model/#text-position-selector|n/a (pattern)|conventions proven by W3C Rec + both major provider APIs|5|5|3|4|2|H|W3C TextPositionSelector is half-open text[start:end], non-negative ints; Anthropic char_location zero-based with exclusive end_char_index (both checked 2026-08-25)|
|Full-quote citations (baseline to beat)|technique|n/a|n/a|universal default|5|0|4|5|0|H|Anthropic docs: cited_text 'returned for convenience and does not count toward output-token usage' — providers themselves discount quote echo; quotes self-verify but cost 30-40 tok/cite|
|Sentence-index citations over pre-segmented units (LongCite statement+[23]/[31-32] scheme)|technique/repo|https://arxiv.org/abs/2409.02897|repo license unverified|research -> ACL 2025 Findings pp.5098-5122; LongCite-8B/9B + LongCite-45k released (v1 2024-09-04)|4|4|4|4|2|H|LongCite-8B outperforms GPT-4o citation F1 by +6.4 pts on LongBench-Cite; shortest, most precise spans win — validates index-style citing|
|ALCE-style automatic citation precision/recall verification loop|strategy/benchmark|https://arxiv.org/abs/2305.14627|Apache-2.0 per princeton-nlp/ALCE [not re-verified]|mature benchmark, EMNLP 2023|4|2|5|5|2|H|Statement-level NLI judging (TRUE model): auto recall 75.3 vs human 74.7 on ASQA — tracks human judgment; defines recall (fully supported) + precision (non-superfluous citations)|
|Dual-selector anchoring: TextPositionSelector + TextQuoteSelector (exact/prefix/suffix)|standard|https://www.w3.org/TR/annotation-model/|W3C Document License (free to implement)|W3C Recommendation 2017-02-23|4|3|4|5|2|H|W3C flags position selectors as brittle when the resource changes and recommends pairing with a quote selector (+State) — blueprint for our drift-tolerant citation records|
|Fuzzy span re-anchoring: diff-match-patch approximate match + prefix/suffix + offset hint|tool/reference impl|https://github.com/hypothesis/dom-anchor-text-quote|MIT|mature; powers Hypothesis client; JS — reimplement ~100 LOC in Python (rapidfuzz) or port|4|2|5|4|2|M|README checked 2026-08-25: approximate matching via diff-match-patch, 32-char prefix/suffix context, integer hint prioritizes nearest match|
|Anthropic Citations API (server-assigned char/page/content-block locations)|tool/evidence|https://docs.anthropic.com/en/docs/build-with-claude/citations|n/a (provider feature; cloud key => requires-owner-approval)|GA; plain text, PDF, custom-content documents|2|3|4|4|3|H|Plain-text docs auto-split into sentence-level citable units; custom content blocks NOT re-chunked (built for RAG chunks); incompatible with structured outputs; streaming via citations_delta (checked 2026-08-25)|
|OpenAI Responses annotations (url_citation.start_index/end_index)|evidence/reference|https://platform.openai.com/docs/api-reference/responses-streaming/response/refusal/delta|n/a (provider feature)|GA|2|2|3|3|2|H|Indices point INTO THE GENERATED OUTPUT TEXT (inverted vs source-span citing); current Responses file_citation carries NO span indices — source-span resolution stays caller-side in every mainstream design|
|GraphRAG text-unit provenance chain (entities.text_unit_ids -> text_units.text -> documents.id)|strategy precedent|https://microsoft.github.io/graphrag/index/outputs/|MIT|production (Microsoft GraphRAG)|4|3|3|4|1|H|Claims carry source_text + text_unit_id; human_readable_id for display citations vs durable UUID id for joins — exactly the two-tier ID policy our node ids need (ties L27 governance)|
|Content-hash node ids (xxhash64 -> base36, 11-13 chars) for reindex-stable citations|technique|https://github.com/Cyan4973/xxHash|BSD-2-Clause|mature, ubiquitous|5|2|2|4|1|H|Stability holds only while chunking is deterministic; pair with stored quote anchor so post-refactor drift is repairable rather than fatal|
|Session integer dictionary (map hash->small int on first mention, reuse thereafter)|technique|derived; tiktoken digit-run behavior|n/a (pattern)|trivial|5|3|2|3|1|M|Digit runs tokenize <=3 digits per token on o200k/cl100k-class BPEs; amortized pointer ~6-8 tok vs 9-12 for raw hash form|
|Reranker-as-NLI-proxy verification tier (bge-reranker-base batched CPU scoring replaces TRUE/GPT judge)|strategy|https://arxiv.org/abs/2305.14627 (judge-role substitution; impl = sibling lane L97)|n/a (internal pattern)|internal pattern; calibration required|5|2|4|4|1|M|Cross-encoder is trained for relevance, not entailment — calibrate accept-threshold against golden set before gating; CPU-only, respects RAM floor, no cloud keys|
|Hybrid render: compact pointers in agent context, deterministic footnote expansion at presentation layer|strategy|n/a (pattern)|n/a|pattern|5|4|3|5|1|H|Expansion is pure post-hoc string substitution (resolve->slice->render) with ZERO extra model tokens; humans get readable quotes, agent context stays compact|
|TOON serialization for citation bibliography blocks at the LLM boundary|adjacent tool|https://github.com/toon-format/spec|MIT|young: spec v4.1 Working Draft 2026-07-26; python impl toon-format/toon-python|3|3|2|2|2|M|Official o200k_base benchmark: -42.6% tokens vs pretty JSON but only -14.5% vs COMPACT JSON — marginal unless bibliography tables dominate; detailed further in L90|

## Verdict
Top pick: fuse #1+#11+#13 — ASCII pointers [nid@s-e] (half-open, zero-based) inline in agent context with a session-int dictionary for repeat mentions, expanded deterministically to readable footnotes only at the presentation layer: ~70-85% citation-token cut (math above) with zero information loss, since every span resolves via SQLite PK lookup.
Why: the wire shape mirrors W3C selectors and Anthropic char_location so hosted models already parse it; drift is handled by stored quote anchors plus diff-match-patch re-anchoring (#5/#6/#10); verification runs fully locally (#4/#12) with no cloud calls.
Integration sketch: emit [nid@s-e] in search-service results; add a verify_citations(answer) CLI/MCP tool (parse -> PK lookup -> rapidfuzz re-anchor fallback -> batched bge-reranker-base score -> ledger row); gate acceptance on tier-1 pass + tier-2 >= calibrated threshold and regenerate only failed statements.
