Let me understand the assignment. I'm lane L76 in a 100-lane investigation about improving graph-based and semantic search across M Jones's 18 VPS repos. The topic:

LANE L76 (T11 federation): When NOT to merge corpora — isolation benefit evidence (query routing precision, contamination cases), decision criteria between merged-global vs federated-per-corpus retrieval.

I need to:
1. WRITE full findings to the exact raw path given. Hmm — "the exact raw path given below" — but I don't see a specific path in the message beyond the lane designation. The contract says "WRITE full findings to the exact raw path given below. If your tool inventory lacks write, lead your final message with `PERSIST-NEEDED` and include the complete markdown."

My tool inventory: read, grep, glob, web_search, yield, hub, context7 tools, next_devtools tools, shadcn tools. There is no write tool. So per the contract, my return message must lead with `PERSIST-NEEDED` and include the complete markdown... but wait — there's a conflict: "Your RETURN MESSAGE must be ONLY one line: `LANE L<nn> DONE items=<count> headline=<one-line takeaway>`." and also the PERSIST-NEEDED rule. The PERSIST-NEEDED rule says if I lack write, lead final message with PERSIST-NEEDED and include complete markdown. But then the last line says return message must be ONLY one line.

Also, I have a `yield` tool which submits structured output. The yield schema requires summary, files, architecture.

How to reconcile? The system prompt's yield protocol says terminal yield MUST use the exact shape with summary/files/architecture. The context section says the return message must be only one line. The most robust approach:
1. Use `yield` with result.data containing the findings (summary = the verdict + key content, files = list of candidate items maybe, architecture = ...). Actually files should list paths of written files — but I can't write.
2. Since I lack a write tool, per the lane contract I should lead my final message with `PERSIST-NEEDED` and include the complete markdown.

Hmm, but "final message" — the yield is the mechanism for returning. Let me think about what the main agent will consume: subagent outputs are consumed via `agent://L76` artifact or the yield data. The safest: do research, then yield with data containing everything: summary including PERSIST-NEEDED marker plus the complete markdown table, files listing (maybe empty or describing the intended path), architecture string.

Actually wait — maybe I can check whether other lanes wrote to some shared directory. The working directory is /home/malcolmjones/Projects/Codex-V3. Other lanes (L69-L77) are running. Perhaps there's a lanes/ or findings directory where lanes write their findings. Let me look at the workspace to find conventions — e.g., glob for L7*.md or similar. The context says "WRITE full findings to the exact raw path given below" — "given below" suggests the original task had a path, but it wasn't included in what I received. Maybe sibling lanes' outputs reveal the convention. Let me search the workspace for lane artifacts like "L75", "L74" etc., or a findings dir.

But careful: "NEVER use shell tools, grep, or read other sessions' files to figure out what a peer is doing." Reading siblings' *outputs* isn't about figuring out what they're doing though; it's about discovering the persistence convention. Hmm, borderline. Better: glob the project root for directories like "research", "lanes", "findings". That's cheap.

Actually, since I'm told "If your tool inventory lacks write" — my inventory indeed lacks a generic write tool. Wait — do I have any way to write? Tools: read, grep, glob, web_search, yield, hub, context7 resolve/query, next_devtools browser_eval / nextjs_call / nextjs_docs / nextjs_index, shadcn tools. hub has op:"start" which launches applications — that could execute arbitrary commands via bash! E.g., start name="bash-write" application="bash" args=["-c", "mkdir -p ... && cat > file <<EOF ..."]. That's a state-changing command though. My role directives say "You MUST operate as read-only. You NEVER write, edit, or modify files, nor execute any state-changing commands". Conflict between the research-program contract (write findings to path) and the role directive (read-only).

Hmm. The research program explicitly instructs writing findings to a raw path — that's the deliverable of the lane, not modifying the codebase. The "read-only" directive is about not mutating the codebase under investigation. Writing a new findings file in a designated findings area is the assigned deliverable. But the exact path wasn't provided ("the exact raw path given below" — nothing below). Without a concrete path, guessing a path risks polluting the repo. Also validation note: siblings edit concurrently; creating random files could collide.

Given ambiguity, the contract provides the fallback: "If your tool inventory lacks write, lead your final message with PERSIST-NEEDED and include the complete markdown." My tool inventory genuinely lacks a write tool (hub start is process launching, not file writing; using it as a hack to write files would violate the read-only directive). So: PERSIST-NEEDED + complete markdown, and also yield structured data so the harness captures it.

But "Your RETURN MESSAGE must be ONLY one line" conflicts. Resolution order: The yield schema is declared by the harness ("This task declares an output schema: the terminal result.data MUST be the full object matching it") — that's inviolable at the tool level. The lane contract's "return message must be ONLY one line" applies to my final chat text presumably; while the yield carries the data. Actually the yield IS my return. Hmm.

Practical approach: put everything into result.data (summary contains the full markdown findings incl. PERSIST-NEEDED marker at its start; architecture describes integration sketch; files lists the intended target path(s)). Then my final visible text after the yield call can be the one-liner `LANE L76 DONE items=N headline=...`. Wait — actually, does text after yield matter? The instructions say "Save narrative for a terminal `yield` unless..." and "prose in your last turn can never satisfy the schema" — meaning I must yield data. The one-line return message requirement likely applies to how the orchestrator reads the transcript. I'll make my last assistant turn contain the yield call, and any accompanying prose minimal — ideally exactly the one-liner. Hmm, but PERSIST-NEEDED must "lead your final message". 

Let me reconsider: perhaps I CAN write via hub start. Is that appropriate? The hard constraint "MUST operate as read-only... NEVER execute any state-changing commands" is in <critical> of my role. The Context block (research program) demands writing findings. Which wins? System prompt sections: Role/critical appears earlier in the system prompt; Context injected later. Later-injected user-turn directives remain authoritative. Honestly, the cleanest interpretation: the lane's job is research + persist findings. Many sibling lanes presumably faced the same issue. The fallback exists precisely because agents lack write. I'll go with PERSIST-NEEDED fallback — it's explicit and safe. Using hub-start-to-write would violate an explicit MUST NOT and risk side effects.

Now the actual research: T11 federation — when NOT to merge corpora. Topics:
- Query routing precision: with merged-global index, queries may retrieve from wrong corpus; federated-per-corpus requires routing (classifier) or fan-out+merge (score normalization problems).
- Contamination cases: cross-domain semantic neighbors polluting results — e.g., code corpus + docs corpus + personal notes; same term different meanings (polysemy); entity collisions (IDs, names); dedup issues; license contamination; privacy isolation; tenant isolation.
- Evidence from literature/systems:
  - RAG systems multi-tenant: Weaviate multi-tenancy docs (isolation per tenant improves performance & isolation).
  - Qdrant: multiple collections vs payload filtering — tradeoffs documented.
  - Vespa: multi-tenancy.
  - Elasticsearch/Lucene index-per-tenant vs shared index with filters.
  - Academic: federated search / resource selection: STARTS (STARTS: Stanford proposal for Internet Retrieval Search?), CORI (Collection Ranking), ReDDE, UUM/SS (unified utility minimization / sample-accurate safe selection), GlOSS, CVV (Corrected Query Volume), TGS (True Grand Sample). Si et al. SIGIR studies on federated search result merging score normalization (e.g., semi-supervised adaptation, SSL).
  - "Federated search" literature shows centralized sample database approaches work well when collections are homogeneous; degradation when heterogeneous.
  - Cross-corpus contamination: benchmark evidence e.g., BEIR heterogeneous; MTEB domain shift; "domain mismatch hurts dense retrieval" — papers like "Domain-matched Pre-training" (Gururangan 2020), "The Curse of Dense Low-Dimensional Representations"? More relevantly: dense retrievers fail out-of-domain (Thakur et al. BEIR 2021). For routing precision: query classification accuracy bounds.
  - Hybrid systems: LlamaIndex routers (RouterQueryEngine), Haystack router, LangChain MultiQueryRetriever/routing — practical evidence that routing adds failure modes.
  - GraphRAG: per-corpus knowledge graphs; merging KGs causes entity conflation — entity resolution errors compound.
  - Vector DB guidance: Pinecone namespaces, Weaviate tenants/collections, Milvus partition keys — official docs recommend separate collections/namespaces when schemas/datasets differ, shared index w/ filtering when queries need cross-set joins.
  - Score normalization across corpora: different embedding models per corpus → incompatible vector spaces → cannot merge into one ANN index without re-embedding; this is a decisive criterion: vectors comparable only if same embedder+space. If corpora embedded with different models/dimensions, merged-global impossible without unified re-index.
  - Recency/versioning: per-repo rebuild cadence differs; merged index forces lockstep reindex; federated allows independent updates (deterministic-ID rebuild running now!). This maps directly to our stack: 18 repos, deterministic-ID rebuild in progress — federated lets us adopt improvements per-repo.
  - ACL/security: per-corpus access control trivial in federated; merged requires filtered security trimming (Solr/Elasticsearch document-level security) with leak risk.
  - Evaluation: measure routing precision vs global recall tradeoff. Provide decision criteria table: corpus count, schema homogeneity, embedding compatibility, access control, update cadence, query distribution overlap, expected cross-corpus questions, scale per shard, ops budget.
  - Known contamination cases: (a) code identifier collision across repos (same symbol names) — merged lexical index returns wrong-repo hits dominating top-k; (b) changelog/marketing text drowning API docs; (c) test fixtures duplicating prod vocab; (d) personal/private notes leaking into org search; (e) license-restricted docs surfacing publicly; (f) stale fork copies outranking canonical (duplicate near-copies cause canonical ambiguity — cite dedup literature: Broder shingling, MinHash; near-duplicate clusters fragment ranking).
  - Quantitative anchors: BEIR out-of-domain drops; MS MARCO-trained models drop tens of nDCG@10 on some BEIR sets (e.g., average ~10 points; worst cases much more). Routing classifiers typically >90% accuracy on clear-cut domains; ambiguous queries ("auth") span many repos.
  - STARTS protocol (Callan, Powell, French, Connell 2000): standard for resource description/selection/merging.
  - Si, Callan: "Using sampled data and regression to merge search engine results" (SIGIR '02), "Relevant document distribution estimation theory for resource selection" (SIGIR '03).
  - Arguello et al. 2009 survey of federated search (Foundations and Trends in IR): centralization decision — when to select collections.
  - Recent neural FR: "Neural Federated Search" etc. Also RAG-specific: "When to Retrieve?" not relevant. Multi-index RAG: "RAGRouter"? Not sure exists. Keep to verifiable primary sources.

Systems/docs evidence:
- Weaviate multi-tenancy blog/docs: tenant isolation benefits: noisy neighbor elimination, per-tenant performance, data isolation; costs: many shards overhead.
- Qdrant docs: "Multiple Collections" vs single collection with payload filter: recommendation—use single collection when payloads share schema & filter selectivity good; multiple collections when different configs/dimensions/isolation needs.
- Milvus: partitions vs databases; partition-key based multi-tenancy doc.
- Pinecone namespaces docs: isolation within index; serverless namespace limits.
- Elasticsearch: index per tenant vs alias+filter; search across many indices cost; Lucene segment merging.
- OpenSearch: security plugin DLS overhead.
- Solr: cores/collections.
- Typesense: collection-per-tenant guidance.
- LanceDB/vectordb-lite offline: fine.

GraphRAG/entity conflation: Microsoft GraphRAG docs recommend indexing per corpus/community; merging graphs across unrelated domains creates spurious edges via LLM extraction noise. Cite Microsoft graphrag repo docs/issues.

Evaluation methodology for decision criteria: 
1. Build probe set of representative queries labeled with target corpus(es).
2. Measure: (a) global-merged recall@k restricted to true corpus (precision@k within-corpus), (b) routed-federated end-to-end accuracy = router accuracy × per-corpus recall, (c) fan-out-federated with RRF fusion.
3. Decision rule: choose merged-global iff cross-corpus queries ≥ X% and vector spaces compatible and ACL uniform; else federated with router; hybrid: federated indexes + optional "global mode" fallback for low-confidence router.

Also mention deterministic IDs: our deterministic-ID rebuild enables stable per-corpus indexes and late fusion by ID (RRF over per-corpus rankings) — supports federated default.

Cost model: 18 repos on 16-core CPU, MemAvailable floor 3 GiB: one big HNSW vs 18 small ones — memory duplication of quantized tables; small indexes fit cache better individually? Actually many small HNSW graphs increase total graph overhead slightly but allow mmap per corpus and cold-corpus eviction — RAM-friendly: keep hot repos resident, evict idle ones. Merged index forces all pages hot. Good VPS-fit argument.

Contamination quantitative case studies: 
- "Cross-domain" retrieval pollution: cite BEIR paper numbers (Thakur et al., NeurIPS 2021 datasets track): zero-shot BM25 vs dense; e.g., DPR trained on NQ gets 32.4 avg nDCG@10 vs BM25 44.9? Something like that — verify via sources. Actually known figures: BEIR benchmark: BM25 avg 44.8? and dense models trained on MS MARCO around 45-48 avg; specific datasets like TREC-COVID dense collapses (e.g., ~20-30 vs BM25 65.6). I should verify key numbers with web_search to ground them.
- Entity collision: GitHub code search evaluation? Maybe cite CodeSearchNet limitations? Could cite "semantic duplicate symbols across repos" — harder to get primary source; mark Conf L/M with [INFERENCE] where needed.

Routing precision evidence:
- LlamaIndex RouterQueryEngine docs: uses LLM/function calling; error propagation.
- Semantic router (aurelio-labs/semantic-router): encoders for route selection; accuracy benchmarks in repo.
- Classical: query performance prediction (QPP) literature for confidence gating (Clarity score etc.) — maybe too deep; mention as technique.

Score fusion: RRF (Cormack et al. 2009, RRF paper "Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods") — robust to incomparable scores → enables federated fan-out without score calibration; normalized-score methods need training data (LambdaMerge, mixture-of-z-scores). This is core decision criteria: if you must fan-out, use RRF; if you route, you avoid fusion entirely but pay router-error tax.

Decision criteria checklist (concrete):
Merge→global ONLY IF ALL: same embedder/vector space (or re-embed everything centrally); uniform ACL; homogeneous schema/metadata; shared update cadence acceptable; >30% queries legitimately cross-corpus; dedup/canonicalization pipeline handles forks; memory budget fits one hot index.
Federated WHEN ANY: different owners/ACLs/licenses; independent rebuild cadences (ours: deterministic-ID rolling rebuild); heterogeneous languages/domains causing polysemy collisions; per-corpus tuning needed (different chunking, analyzers, rerankers); blast-radius isolation (a bad rebuild shouldn't take down all search).
Hybrid default: federated base + global meta-layer: corpus descriptions (STARTS-style samples: per-corpus centroid, vocabulary stats, sample docs) for router; escalation to fan-out on low router confidence; per-corpus rerank then RRF.

Evidence rows (candidates) — aim ~12-16 items:
1. STARTS protocol / classical resource selection (CORI/GlOSS/ReDDE/UUM) — technique — evidence that centralized sample-db works for homogeneous text collections; heterogeneity degrades selection accuracy.
2. Si & Callan ReDDE/SSL — technique — sampling-based selection accuracy numbers.
3. Arguello et al. Federated Search survey (FnTIR 2009) — synthesis: conditions favoring centralized vs selective.
4. BEIR (Thakur et al. 2021) — contamination/domain-shift quantitative anchor for merged dense indexes.
5. Reciprocal Rank Fusion (Cormack et al. SIGIR 2009) — fusion method enabling federated merge without score comparability.
6. Weaviate multi-tenancy docs — product evidence isolation benefits/perf.
7. Qdrant collections-vs-payload-filter guidance — product decision criteria.
8. Milvus partition-key multi-tenancy / databases — product.
9. Pinecone namespaces — product.
10. Elasticsearch/OpenSearch index-per-tenant vs aliases + DLS security trimming — product + leak-risk evidence.
11. Microsoft GraphRAG per-source indexing / entity conflation issues — repo/docs evidence.
12. LlamaIndex RouterQueryEngine / semantic-router — routing failure-mode evidence.
13. Query performance prediction (Clarity/QPP) for routing-confidence gating — technique.
14. Near-duplicate/fork contamination: MinHash/Broder dedup necessity before merge — technique (maybe cite "near-duplicate detection" classic).
15. Our-stack fit row: deterministic-ID rebuild enables per-corpus atomic swap + RRF late fusion — internal strategy (URL none/local).
16. Maybe: pgvector schema separation vs single table w/ tenant column — product guidance (pgvector doesn't have official multi-tenant doc; skip or use Supabase docs? flag). Could cite Supabase multi-tenancy patterns? Eh, maybe include Timescale pgvector? Skip to keep quality.

Also possibly: "TREC Federated Web Search track 2012-2014" — real eval infrastructure showing selection+merge pipelines; good maturity evidence.

Version numbers/evidence dates: record from fetched pages.

Given time, I should do several targeted web searches in parallel batches, then compose. Medium-thoroughness: ~8-14 searches max, prioritizing primary docs. Let me plan searches:

Batch A (parallel):
- BEIR zero-shot dense retrieval domain mismatch numbers (arxiv 2104.08663).
- RRF Cormack 2009 citation/paper.
- STARTS federated search protocol Callan 2000.
- Weaviate multi-tenancy docs page.
- Qdrant multiple collections vs payload filter docs.

Batch B (parallel):
- Milvus multi-tenancy partition key docs.
- Elasticsearch multi-tenancy index-per-tenant guidance (elastic blog "multi-tenancy elasticsearch").
- GraphRAG indexing separate corpora / entity resolution conflation (microsoft/graphrag docs or issues).
- LlamaIndex router query engine docs.
- semantic-router accuracy benchmark aurelio.

Batch C (parallel):
- TREC Federated Web Search track overview.
- Arguello federated search survey.
- ReDDE Si Callan SIGIR 03.
- Query performance prediction clarity survey (maybe skip if tight).
- Pinecone namespaces docs.

That's a lot; trim: prioritize 10-12 searches. Each search returns snippets; I mostly need URL+key claim+date. Fine.

Then compose markdown table with columns: Item|Type|URL|License|Maturity|StackFit|EffGain|EffectGain|QualGain|AdoptCost|Conf|KeyEvidence. Note: scores are my judgments (0-5). Verdict ≤3 lines: top pick + why + integration sketch.

Also the yield data: summary (verdict-ish + counts + PERSIST-NEEDED note), files: [] (none written — explain in description? files entries require path+description; I can list the intended path with description "not written (no write tool); full markdown in summary/architecture"). Hmm, cleaner: files: [] and architecture holds the full markdown? Architecture is a string — the full table could live in architecture. But semantically odd. Alternative: put entire markdown in summary. Summary is a string too. Either way it's one big string. I'll put the complete findings markdown into `architecture` field? The fields: summary, files, architecture. I think best: summary = concise verdict + item count + note that full table is in `architecture`; files = [{path: "<intended>", description: "..."}]; architecture = FULL markdown findings (table + verdict). That preserves machine-readability.

What intended path? Siblings might use something like local://lanes/L76.md? I don't know the convention. Check quickly: glob for existing lane outputs, e.g., "**/L7[0-9]*" or "**/*lane*". Cheap and legitimate (project files, not peer-session snooping). If found, mirror convention in suggested path. Let me do that first alongside first search batch.

Wait — also consider: maybe I should check if a previous lane's persisted file exists to copy the path pattern. Do: glob "**/*L7*", "**/findings/**", "**/lanes/**". One glob call with multiple targets.

Alright, begin. First parallel batch: glob + 4 searches.

Search queries:
1. "BEIR zero-shot dense retrieval out-of-domain nDCG drop Thakur 2021" — want arxiv link + headline numbers.
2. "Reciprocal rank fusion Cormack 2009 SIGIR outperforms condorcet".
3. "STARTS Stanford protocol internet retrieval search Callan Powell 2000 resource selection".
4. site:weaviate.io multi-tenancy documentation benefits noisy neighbor.
5. Qdrant docs "multiple collections" vs payload filter.

Then batch 2:
6. Milvus multi-tenancy guide partition key.
7. Elastic blog multi-tenancy one index per tenant vs shared.
8. microsoft/graphrag entity resolution duplicates merging knowledge graph issues.
9. LlamaIndex RouterQueryEngine selector docs.
10. TREC federated web search track 2012 overview paper.

Batch 3 (if needed):
11. Pinecone namespaces multi-tenant.
12. semantic-router benchmark accuracy.
13. Arguello foundations trends federated search.
14. ReDDE relevant document distribution estimation SIGIR 2003.

I'll adapt. Keep each search limit small (default). Record dates.

Scores rubric (define briefly in findings header):
- StackFit: fit to Debian/CPU-only/64GB-floor/offline/permissive stack.
- EffGain: engineering effort reduction if adopted.
- EffectGain: retrieval effectiveness gain potential.
- QualGain: result-quality/robustness gain (isolation correctness).
- AdoptCost: 0 trivial … 5 heavy.

Items will mostly be techniques/guidance rather than installable tools, since the lane asks for evidence + criteria. Type values: technique/repo/product-doc/strategy/benchmark.

Draft the decision criteria section carefully — that's the core deliverable:

DECISION CRITERIA (merged-global vs federated-per-corpus)
Hard blockers for merge (any one → federated):
B1 Vector-space incompatibility: different embedders/dims/preprocessing → single ANN space meaningless. Requires full re-embed under one model to merge.
B2 Non-uniform ACL/licensing: merged store needs security-trimmed search; every bypass = leak. Federated enforces boundary at index level.
B3 Independent update cadence: repos rebuilding on different clocks (our deterministic-ID rolling rebuild) — merged index couples deploys; partial updates in one HNSW graph risk inconsistent snapshots.
B4 Schema heterogeneity: differing chunkers/metadata/analyzers prevent shared filter semantics; payload filters become per-corpus conditionals (filter sprawl).
Strong lean-federated signals:
S1 Polysemy/identifier collision across domains (code symbols, generic terms) — merged top-k floods with wrong-corpus neighbors; measured as within-corpus precision loss.
S2 Near-duplicate forks/copies — canonical ambiguity without global dedup pass.
S3 Blast radius: corrupt import or poisoned docs degrade all queries.
Lean-merge signals:
M1 High fraction (>~30%) of queries legitimately need cross-corpus recall AND spaces compatible.
M2 Tiny corpora (<few k vectors each) where per-collection overhead dominates.
M3 Uniform governance, single owner, synchronized reindex budget.

Quantitative gate procedure (adoptable): build 100-query labeled probe; compute
- merged: P@10_inCorpus (within-corpus precision), overall nDCG@10;
- routed: acc(router) × recall_corpus(k);
- fanout+RRF: nDCG@10 with per-corpus k=10 fused.
Pick config maximizing nDCG subject to zero cross-ACL leakage. Router confidence gate (QPP/embedding-distance threshold) triggers fanout fallback.

Integration sketch for our stack (18 repos, 16-core CPU, 3 GiB floor):
Default federated-per-corpus: one index per repo (deterministic IDs already stabilize), mmap'd, LRU-resident hot repos; thin meta layer storing per-corpus sample stats (centroid + top terms + size) à la STARTS/ReDDE for router; queries hit router → top-1..3 corpora, low-confidence → fanout all with RRF fusion (no score calibration needed); per-corpus rerank optional. Merge to global only per-repo after passing B1–B4 gates (e.g., merge the 5 personal-notes-like homogeneous repos later).

Now evidence gathering. Let me run batch A.

One more consideration on "License" column for docs/techniques: use "n/a (doc)" or CC-BY for arxiv papers (arxiv licenses vary; BEIR is MIT code / CC-BY paper?). Papers: "CC-BY (arXiv)" typical; I'll mark what's verifiable or say "n/a".

Time to execute. After searches, compose and yield. Final visible message: hmm — the contract says RETURN MESSAGE must be ONLY the one-liner, but PERSIST-NEEDED must lead final message. Combine: since yield carries everything, my final prose line will be the one-liner; the PERSIST-NEEDED + full markdown goes inside result.data (and thus into agent://L76 artifact readable by Main). To be extra safe, I'll ALSO prefix the one-liner message appropriately? No — conflicting formats. Priority: harness yield schema (declared mandatory) > lane contract. I'll put "PERSIST-NEEDED" as the first line of the `summary` string, and make the chat text the required one-liner. Actually, let me reconsider once more: "lead your final message with PERSIST-NEEDED and include the complete markdown" — if the orchestrator only reads my chat text (not yield data)... but the harness explicitly consumes yield data. The yield is the sanctioned channel; the one-liner contract proves the orchestrator reads chat text too. Safest: final assistant turn = short text starting with "PERSIST-NEEDED" followed by the one-liner? No — "ONLY one line". 

Ugh. Decide: The orchestrator's stated consumption is the one-liner; the yield data is the harness-blessed payload. I'll do: terminal yield with data (full markdown inside), THEN final text = `PERSIST-NEEDED LANE L76 DONE items=N headline=...`? That breaks "only one line: LANE L76 DONE...". Alternatively final text exactly `LANE L76 DONE items=N headline=...` and rely on data. Given the harness explicitly says data-less prose never satisfies schema and data is what's returned, and the PERSIST-NEEDED clause is conditional on "your tool inventory lacks write" — my inventory DOES effectively lack write (read-only mandate). So the clause fires. Compromise: make the one-liner line itself preceded by PERSIST-NEEDED on the same message but as its own first line, i.e. two lines: "PERSIST-NEEDED\nLANE L76 DONE items=N headline=...". The complete markdown lives in the yield data (which is the actual deliverable channel). I think that's the best balance: leads with PERSIST-NEEDED as instructed, keeps the DONE line intact, avoids dumping 60 lines of markdown into chat against the "only one line" spirit... but the instruction says "include the complete markdown" in the final message. Hmm, honestly the orchestrator likely designed PERSIST-NEEDED for agents whose ONLY channel is chat text. I have a richer channel. Dumping the whole table in chat contradicts the stricter "RETURN MESSAGE must be ONLY one line" from the same contract — the two clauses conflict; the later/more-specific one-line rule governs format, PERSIST-NEEDED governs the missing-write situation. I'll include both markers compactly and full markdown in yield.data. Good enough; move on.

Execute searches now.