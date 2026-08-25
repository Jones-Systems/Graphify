## Promising research direction

**Query-aware call-graph reranking for code search using personalized PageRank**, evaluated by MRR on CodeSearchNet and a repository-level benchmark.

A strong system would combine:

1. **Lexical retrieval** — BM25 over identifiers, comments, signatures, and API names.
2. **Dense retrieval** — code/query embeddings.
3. **Call/dependency graph** — caller, callee, import, inheritance, implementation, and test relationships.
4. **Graph-based reranking** — personalized PageRank seeded by the initially retrieved candidates.
5. **Optional learned fusion** — train the weights of semantic and structural signals rather than adding raw PageRank directly.

This is closely related to Sourcegraph’s production use of a PageRank-like score over a source-symbol graph, although global PageRank alone is not query-specific. ([sourcegraph.com](https://sourcegraph.com/blog/new-search-ranking?utm_source=openai))

### Suggested scoring model

Let \(R(q,c)\) be the initial retrieval score for query \(q\) and code node \(c\). Construct a directed heterogeneous graph \(G=(V,E)\), where edges may represent:

- `calls`
- `called_by`
- `imports`
- `inherits`
- `implements`
- `references`
- `tested_by`

Compute a query-conditioned graph score:

\[
P_q = \alpha M^\top P_q + (1-\alpha)s_q
\]

where:

- \(M\) is the normalized graph-transition matrix;
- \(s_q\) is a seed distribution derived from the top-\(K\) lexical/dense results;
- \(\alpha\) is typically around 0.85 in PageRank-style formulations, but should be tuned;
- \(P_q\) is personalized PageRank.

Then rerank candidates with:

\[
S(q,c) =
w_r \,\hat R(q,c)
+ w_p \,\widehat{P_q(c)}
+ w_d \,\widehat{D_q(c)}
+ w_t \,\widehat{T(c)}
\]

where:

- \(\hat R\): normalized lexical/dense relevance;
- \(\widehat{P_q}\): personalized PageRank;
- \(D_q\): graph distance from highly relevant seed nodes;
- \(T(c)\): node-type or code-role features, such as public API, implementation, test, generated file, or documentation.

Do **not** use global PageRank as the dominant feature. It tends to favor popular utility functions, framework entry points, and heavily referenced modules even when they are not relevant to the query. Query-seeded PageRank or graph distance is more appropriate.

## API shape

A practical API could expose both graph construction and reranking:

```http
POST /v1/graph/index
```

```json
{
  "repository_id": "repo-123",
  "revision": "abc123",
  "nodes": [
    {
      "id": "src/auth.py::authenticate",
      "type": "function",
      "language": "python"
    }
  ],
  "edges": [
    {
      "source": "src/api.py::login",
      "target": "src/auth.py::authenticate",
      "type": "calls",
      "weight": 1.0
    }
  ]
}
```

```http
POST /v1/search/rerank
```

```json
{
  "query": "refresh an expired OAuth token",
  "candidates": [
    {
      "id": "src/auth.py::refresh_token",
      "retrieval_score": 0.91
    },
    {
      "id": "src/client.py::request",
      "retrieval_score": 0.88
    }
  ],
  "graph": {
    "mode": "personalized_pagerank",
    "seed_from": "candidates",
    "hops": 2,
    "edge_weights": {
      "calls": 1.0,
      "called_by": 0.7,
      "imports": 0.2,
      "implements": 0.8,
      "tested_by": 0.3
    }
  },
  "top_k": 10
}
```

Response:

```json
{
  "results": [
    {
      "id": "src/auth.py::refresh_token",
      "rank": 1,
      "score": 0.943,
      "features": {
        "retrieval": 0.91,
        "personalized_pagerank": 0.38,
        "graph_distance": 0,
        "in_degree": 12
      },
      "explanations": [
        "semantic match",
        "seed result",
        "called by src/client.py::request"
      ]
    }
  ]
}
```

A graph-reranking API pattern is already emerging in commercial graph-search systems, but the research opportunity is to make the graph specifically code-aware and evaluate it rigorously rather than treating the graph as a generic knowledge graph. ([platform.papr.ai](https://platform.papr.ai/apis/arazzo/v1/graph_rerank_v1_graph_rerank_post?utm_source=openai))

## SIGIR-style research question

> **Does query-aware call-graph propagation improve the ranking of semantically relevant code over lexical and dense retrieval baselines, and under what query types does it help or hurt?**

Useful hypotheses:

- **H1:** Personalized PageRank improves MRR over BM25 and dense retrieval alone.
- **H2:** Call-graph features help more for behavioral queries—“where is retry logic implemented?”—than for exact API-name queries.
- **H3:** Learned fusion of retrieval and graph features outperforms a fixed PageRank boost.
- **H4:** Graph expansion improves Recall@10 but can reduce MRR if it introduces structurally related yet semantically irrelevant nodes.
- **H5:** Edge-type-specific weighting is better than treating all dependencies identically.

## Evaluation design

Use at least these baselines:

1. BM25
2. Dense retrieval
3. BM25 + dense fusion, such as RRF
4. Retrieval + global PageRank
5. Retrieval + graph-distance reranking
6. Retrieval + personalized PageRank
7. Learned reranker using retrieval and graph features

CodeSearchNet is a natural starting point: it contains roughly six million functions across six languages and includes expert annotations for 99 queries. ([arxiv.org](https://arxiv.org/abs/1909.09436?utm_source=openai)) However, its commonly reported MRR protocol uses batches of 1,000 candidates as distractors, so results are not equivalent to ranking against the entire repository or corpus. ([github.com](https://github.com/wandb/codesearchnet?utm_source=openai))

Report:

- MRR
- Recall@1, @5, @10
- nDCG@10
- per-language results
- per-query-type results
- latency and graph-construction cost
- percentage of queries whose relevant result moved upward
- percentage that were harmed by graph reranking

MRR is appropriate when the first relevant result is especially important:

\[
MRR = \frac{1}{|Q|}
\sum_{q\in Q}
\frac{1}{\operatorname{rank}_q}
\]

But because code search often has multiple valid implementations, also report nDCG and Recall@10. Recent code-search work commonly reports MRR, and strong two-stage models have reported approximately 0.78 MRR on CodeSearchNet, so a graph method should be compared against a capable reranking baseline rather than only BM25. ([arxiv.org](https://arxiv.org/abs/2110.07811?utm_source=openai))

## Important experimental safeguards

- Split by **repository**, not randomly by function, to prevent near-duplicate leakage.
- Build graphs only from the training/index revision available to the search system.
- Separate **intra-file calls** from cross-file calls.
- Test incomplete or unresolved graphs, since real repositories often do not compile.
- Evaluate global PageRank, personalized PageRank, and local \(k\)-hop expansion separately.
- Tune graph weights on validation repositories only.
- Include ablations for calls, imports, inheritance, tests, and reference edges.
- Measure latency: PageRank may improve relevance but be impractical if recomputed per query over a large repository.

## Likely contribution

The most defensible contribution is not simply “PageRank improves code search.” A stronger paper claim would be:

> **A query-conditioned, edge-type-aware call-graph reranker improves top-ranked code retrieval, with gains concentrated on behavioral and cross-file queries, while global centrality produces weaker or sometimes negative results.**

Prior work already supports the general importance of graph structure in code retrieval: graph matching, AST/data-flow representations, CFG/PDG features, and dependency-based concept location have all been explored. ([doaj.org](https://doaj.org/article/dd1cecba9a3a441eb71e195ed190afd7?utm_source=openai)) The novelty should therefore come from the **reranking formulation, query-conditioned propagation, API implementation, and controlled MRR analysis**, not merely from adding a call graph.

## Sources
64 sources
[1] https://www.vectorian.be/articles/2026-03-05/all-i-wanted-was-a-simple-code-search/
    https://www.vectorian.be/articles/2026-03-05/all-i-wanted-was-a-simple-code-search/
[2] Rethinking search results ranking on Sourcegraph.com | Sourcegraph
    https://sourcegraph.com/blog/new-search-ranking
    geRank-like score over a source-symbol graph, although global PageRank alone is not query-specific. (sourcegraph.com)

### Suggested scoring model

Let \(R(q,c)\) be the initial retrieval score for query \(q\) and cod
[3] https://en.wikipedia.org/wiki/Mean_reciprocal_rank
    https://en.wikipedia.org/wiki/Mean_reciprocal_rank
[4] https://www.sigir.org/sigir2012/tutorial/LargeScaleGraphMining.php
    https://www.sigir.org/sigir2012/tutorial/LargeScaleGraphMining.php
[5] https://marc.najork.org/papers/sigir2007.pdf
    https://marc.najork.org/papers/sigir2007.pdf
[6] https://github.com/hrayleung/Cocode
    https://github.com/hrayleung/Cocode
[7] https://sigir.org/sigir2022/program/program-sigir22.pdf
    https://sigir.org/sigir2022/program/program-sigir22.pdf
[8] https://www.npmjs.com/package/%40iceinvein/code-intelligence-mcp
    https://www.npmjs.com/package/%40iceinvein/code-intelligence-mcp
[9] https://www.microsoft.com/en-us/research/wp-content/uploads/2016/07/sigir2008-gao-msra.pdf
    https://www.microsoft.com/en-us/research/wp-content/uploads/2016/07/sigir2008-gao-msra.pdf
[10] https://data-exploration.eu/pdf/SIGIR2019-ExploratoryMethods.pdf
    https://data-exploration.eu/pdf/SIGIR2019-ExploratoryMethods.pdf
[11] https://sigir.org/sigir2018/toc.html
    https://sigir.org/sigir2018/toc.html
[12] Rerank documents
    https://platform.papr.ai/apis/arazzo/v1/graph_rerank_v1_graph_rerank_post
    code-aware and evaluate it rigorously rather than treating the graph as a generic knowledge graph. (platform.papr.ai)

## SIGIR-style research question

> **Does query-aware call-graph propagation improve the ranking
[13] https://www.cs.cmu.edu/~wcohen/postscript/sigir-2006-draft.pdf
    https://www.cs.cmu.edu/~wcohen/postscript/sigir-2006-draft.pdf
[14] https://arxiv.org/abs/2208.11274
    https://arxiv.org/abs/2208.11274
[15] https://socket.dev/npm/package/codeseek/overview/0.1.30
    https://socket.dev/npm/package/codeseek/overview/0.1.30
[16] https://pypi.org/project/trelix/2.1.0/
    https://pypi.org/project/trelix/2.1.0/
[17] https://github.com/AutomatosAI/automatos-ai/blob/main/docs/knowledge-base-rag/codegraph-code-repository-indexing.md
    https://github.com/AutomatosAI/automatos-ai/blob/main/docs/knowledge-base-rag/codegraph-code-repository-indexing.md
[18] https://help.getzep.com/v2/searching-the-graph
    https://help.getzep.com/v2/searching-the-graph
[19] https://arxiv.org/abs/2607.17139
    https://arxiv.org/abs/2607.17139
[20] https://pkg.go.dev/github.com/whykusanagi/celeste-cli%40v1.10.0/cmd/celeste/codegraph
    https://pkg.go.dev/github.com/whykusanagi/celeste-cli%40v1.10.0/cmd/celeste/codegraph
[21] https://www.reddit.com/r/learnmachinelearning/comments/1viv073/d_i_measured_pagerank_vs_bm25_for_code_retrieval/
    https://www.reddit.com/r/learnmachinelearning/comments/1viv073/d_i_measured_pagerank_vs_bm25_for_code_retrieval/
[22] https://www.reddit.com/r/opensource/comments/1u76012/hybrid_retrieval_dependencygraph_expansion_beats/
    https://www.reddit.com/r/opensource/comments/1u76012/hybrid_retrieval_dependencygraph_expansion_beats/
[23] https://www.reddit.com/r/OpenSourceeAI/comments/1u75zx7/hybrid_retrieval_dependencygraph_expansion_beats/
    https://www.reddit.com/r/OpenSourceeAI/comments/1u75zx7/hybrid_retrieval_dependencygraph_expansion_beats/
[24] https://en.wikipedia.org/wiki/Ranking_%28information_retrieval%29
    https://en.wikipedia.org/wiki/Ranking_%28information_retrieval%29
[25] https://www.reddit.com/r/Rag/comments/1v3bngu/our_monitoring_said_62_of_retrievals_were_failing/
    https://www.reddit.com/r/Rag/comments/1v3bngu/our_monitoring_said_62_of_retrievals_were_failing/
[26] https://en.wikipedia.org/wiki/PageRank
    https://en.wikipedia.org/wiki/PageRank
[27] https://arxiv.org/abs/1602.05100
    https://arxiv.org/abs/1602.05100
[28] https://www.reddit.com/r/Rag/comments/1qhvzy7/compiled_a_list_of_%F0%9D%90%9A%F0%9D%90%B0%F0%9D%90%9E%F0%9D%90%AC%F0%9D%90%A8%F0%9D%90%A6%F0%9D%90%9E_%F0%9D%90%AB%F0%9D%90%9E%F0%9D%90%AB%F0%9D%90%9A%F0%9D%90%A7%F0%9D%90%A4%F0%9D%90%9E%F0%9D%90%AB%F0%9D%90%AC/
    https://www.reddit.com/r/Rag/comments/1qhvzy7/compiled_a_list_of_%F0%9D%90%9A%F0%9D%90%B0%F0%9D%90%9E%F0%9D%90%AC%F0%9D%90%A8%F0%9D%90%A6%F0%9D%90%9E_%F0%9D%90%AB%F0%9D%90%9E%F0%9D%90%AB%F0%9D%90%9A%F0%9D%90%A7%F0%9D%90%A4%F0%9D%90%9E%F0%9D%90%AB%F0%9D%90%AC/
[29] https://arxiv.org/abs/1807.08798
    https://arxiv.org/abs/1807.08798
[30] https://www.reddit.com/r/Rag/comments/1fu9u5r
    https://www.reddit.com/r/Rag/comments/1fu9u5r
[31] https://www.reddit.com/r/Rag/comments/1j8winn
    https://www.reddit.com/r/Rag/comments/1j8winn
[32] https://www.reddit.com/r/Rag/comments/1ot4btm/rerankers_in_production/
    https://www.reddit.com/r/Rag/comments/1ot4btm/rerankers_in_production/
[33] https://www.reddit.com/r/LocalLLaMA/comments/1rxzmcd/benchmarked_5_rag_retrieval_strategies_on_code/
    https://www.reddit.com/r/LocalLLaMA/comments/1rxzmcd/benchmarked_5_rag_retrieval_strategies_on_code/
[34] GitHub - wandb/codesearchnet · GitHub
    https://github.com/wandb/codesearchnet
    s as distractors, so results are not equivalent to ranking against the entire repository or corpus. (github.com)

Report:

- MRR
- Recall@1, @5, @10
- nDCG@10
- per-language results
- per-query-type results
- lat
[35] Cascaded Fast and Slow Models for Efficient Semantic Code Search
    https://arxiv.org/abs/2110.07811
    t, so a graph method should be compared against a capable reranking baseline rather than only BM25. (arxiv.org)

## Important experimental safeguards

- Split by **repository**, not randomly by function, to prev
[36] Enhancing Semantic Code Search With Deep Graph Matching – DOAJ
    https://doaj.org/article/dd1cecba9a3a441eb71e195ed190afd7
    ow representations, CFG/PDG features, and dependency-based concept location have all been explored. (doaj.org) The novelty should therefore come from the **reranking formulation, query-conditioned propagation,
[37] https://www.mdpi.com/2076-3417/16/1/12
    https://www.mdpi.com/2076-3417/16/1/12
[38] https://papers.ssrn.com/sol3/Delivery.cfm/7068138.pdf?abstractid=7068138&mirid=1&type=2
    https://papers.ssrn.com/sol3/Delivery.cfm/7068138.pdf?abstractid=7068138&mirid=1&type=2
[39] https://link.springer.com/article/10.1186/s13677-024-00629-5
    https://link.springer.com/article/10.1186/s13677-024-00629-5
[40] https://pmc.ncbi.nlm.nih.gov/articles/PMC11589884/
    https://pmc.ncbi.nlm.nih.gov/articles/PMC11589884/
[41] CodeSearchNet Challenge: Evaluating the State of Semantic Code Search
    https://arxiv.org/abs/1909.09436
    roughly six million functions across six languages and includes expert annotations for 99 queries. (arxiv.org) However, its commonly reported MRR protocol uses batches of 1,000 candidates as distractors, so res
[42] https://github.blog/engineering/infrastructure/introducing-the-codesearchnet-challenge/
    https://github.blog/engineering/infrastructure/introducing-the-codesearchnet-challenge/
[43] https://www.researchgate.net/publication/251290062_A_Study_of_Ranking_Schemes_in_Internet-Scale_Code_Search
    https://www.researchgate.net/publication/251290062_A_Study_of_Ranking_Schemes_in_Internet-Scale_Code_Search
[44] https://pmc.ncbi.nlm.nih.gov/articles/PMC10007218/
    https://pmc.ncbi.nlm.nih.gov/articles/PMC10007218/
[45] https://snap.stanford.edu/class/cs224w-2019/project/26424995.pdf
    https://snap.stanford.edu/class/cs224w-2019/project/26424995.pdf
[46] https://www.researchgate.net/publication/221554538_Portfolio_Finding_relevant_functions_and_their_usage
    https://www.researchgate.net/publication/221554538_Portfolio_Finding_relevant_functions_and_their_usage
[47] https://smusg.elsevierpure.com/en/publications/efficient-text-to-code-retrieval-with-cascaded-fast-and-slow-tran/
    https://smusg.elsevierpure.com/en/publications/efficient-text-to-code-retrieval-with-cascaded-fast-and-slow-tran/
[48] https://www.sciencedirect.com/science/article/abs/pii/S0950584912002078
    https://www.sciencedirect.com/science/article/abs/pii/S0950584912002078
[49] https://arxiv.org/abs/2211.16490
    https://arxiv.org/abs/2211.16490
[50] https://arxiv.org/abs/2201.11313
    https://arxiv.org/abs/2201.11313
[51] https://aclanthology.org/2025.coling-main.482.pdf
    https://aclanthology.org/2025.coling-main.482.pdf
[52] https://wssun.github.io/papers/2024-TOSEM-CodeSearchSurvey.pdf
    https://wssun.github.io/papers/2024-TOSEM-CodeSearchSurvey.pdf
[53] https://people.cs.pitt.edu/~chang/seke/seke22paper/paper078.pdf
    https://people.cs.pitt.edu/~chang/seke/seke22paper/paper078.pdf
[54] https://openreview.net/pdf?id=EPTVoeaz7Y
    https://openreview.net/pdf?id=EPTVoeaz7Y
[55] https://dspacemainprd01.lib.uwaterloo.ca/server/api/core/bitstreams/59c99986-b24c-4970-8d45-1b702d7ee792/content
    https://dspacemainprd01.lib.uwaterloo.ca/server/api/core/bitstreams/59c99986-b24c-4970-8d45-1b702d7ee792/content
[56] https://www.reddit.com/r/OpenSourceAI/comments/1u75zvp/hybrid_retrieval_dependencygraph_expansion_beats/
    https://www.reddit.com/r/OpenSourceAI/comments/1u75zvp/hybrid_retrieval_dependencygraph_expansion_beats/
[57] https://www.reddit.com/r/AI_Agents/comments/1u75zur/hybrid_retrieval_dependencygraph_expansion_beats/
    https://www.reddit.com/r/AI_Agents/comments/1u75zur/hybrid_retrieval_dependencygraph_expansion_beats/
[58] https://www.reddit.com/r/MachineLearning/comments/d9rprl
    https://www.reddit.com/r/MachineLearning/comments/d9rprl
[59] https://www.reddit.com/r/coolgithubprojects/comments/1s80l2e/how_i_solved_ai_hallucinating_function_names_on/
    https://www.reddit.com/r/coolgithubprojects/comments/1s80l2e/how_i_solved_ai_hallucinating_function_names_on/
[60] https://www.reddit.com/r/algotrading/comments/da0y18
    https://www.reddit.com/r/algotrading/comments/da0y18
[61] https://www.reddit.com/r/datasets/comments/d9ycp1
    https://www.reddit.com/r/datasets/comments/d9ycp1
[62] https://www.reddit.com/r/MachineLearning/comments/da0urk
    https://www.reddit.com/r/MachineLearning/comments/da0urk
[63] https://www.reddit.com/r/ClaudeCode/comments/1u7rofp/i_built_a_graphbased_alternative_to_embedding/
    https://www.reddit.com/r/ClaudeCode/comments/1u7rofp/i_built_a_graphbased_alternative_to_embedding/
[64] https://www.reddit.com/r/u_Scared_End_3626/comments/1ssuanh/i_got_tired_of_ai_guessing_what_breaks_when_i/
    https://www.reddit.com/r/u_Scared_End_3626/comments/1ssuanh/i_got_tired_of_ai_guessing_what_breaks_when_i/