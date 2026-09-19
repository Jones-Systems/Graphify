# LANE L05 — Community detection + summarization WITHOUT LLM (T1 graphrag)

Checked: 2026-08-25. Stack context: graphifyy==0.9.16 structural graphs exported as NetworkX node-link JSON; Python 3.13, Debian 13 (glibc 2.41), 16 cores CPU-only, MemAvailable floor 3072 MiB. No LLM, no cloud APIs.

Scope: partition our link-graphs into communities (Leiden/Louvain/LP/map-equation) and produce deterministic, LLM-free community summaries usable for navigation.

## Findings

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|NetworkX louvain_communities|tool|https://networkx.org/documentation/stable/reference/algorithms/community.html|BSD-3|mature (native since NX 2.7)|5|3|2|3|0|H|Native impl with seed param, reproducible run-to-run on same NX version + node order; pure Python so slow past ~100k edges; Louvain gives no well-connected-community guarantee; zero new deps — already in our pipeline.|
|NetworkX leiden_communities (3.7 native)|tool|https://networkx.org/documentation/latest/reference/algorithms/generated/networkx.algorithms.community.leiden.leiden_communities.html|BSD-3|RC (docs 3.7rc0.dev0, 2026-08-21)|5|4|2|4|0|M|Stable 3.6.1 is backend-only (raises NotImplementedError without backend); native implementation PR #8509 merged 2026-05-12, adds metric=cpm/modularity + seed + theta. Zero-dep Leiden once 3.7 stable ships; watch, do not block on it.|
|leidenalg 0.12.0 + igraph 0.11.8|tool|https://github.com/vtraag/leidenalg|GPL-3.0-or-later|mature (rel. 2026-05-24)|5|4|5|5|1|H|find_partition(seed=N, n_iterations=-1) is deterministic given fixed vertex/edge ordering (docs + reference); C-speed; RBConfigurationVertexPartition (resolution gamma) and CPM partitions; cp38-abi3 manylinux_2_28 x86_64 wheel installs on py3.13 (verified PyPI 2026-08-25; glibc>=2.28 OK on Debian 13).|
|python-igraph / igraph 0.11.8 community suite|tool|https://python.igraph.org|GPL-2.0-or-later (LICENSE raw = GPLv2 text, checked 2026-08-25)|mature|5|4|5|4|1|H|One import covers Leiden (community_leiden), Louvain (community_multilevel), label_propagation, fastgreedy, edge_betweenness, infomap; Graph.DictList/TupleList adapters from sorted edge lists; cp39-abi3 manylinux wheel runs on py3.13 (PyPI, uploaded 2024-10-28).|
|NetworKit 11.2.1|tool|https://networkit.github.io|MIT|mature (cp313 wheels since 11.1, 2025-03-10)|4|4|5|4|2|H|ParallelLeiden + PLM (parallel Louvain) + PLP (parallel label prop) exploit all 16 cores; manylinux cp313 wheels confirmed on PyPI; right choice only when graphs exceed single-core igraph comfort (~>5-10M edges); heavier install, parallel reductions need seed discipline for bit-reproducibility.|
|graspologic hierarchical_leiden 3.4.4|tool|https://github.com/graspologic-org/graspologic|MIT|maintained-ish (rel. 2025-09-08)|2|5|4|5|2|M|Rust core (graspologic-native 1.2.5, cp38-abi3); hierarchical_leiden(max_cluster_size, random_seed) returns node/cluster/parent_cluster/level records — exactly the Microsoft GraphRAG hierarchy shape. BLOCKER: package metadata pins Python <3.13; only --ignore-requires-python workaround exists => not adoptable cleanly on our stack.|
|infomap 2.12.0 (map equation)|tool|https://www.mapequation.org/infomap|GPL-3.0-or-later (dual commercial)|mature|3|3|4|5|2|M|Flow/random-walk optimal partitions — communities defined by how a walker moves, which matches navigation semantics best; two-level and hierarchical modes; NOTE: Linux wheels only exist from v2.9.2 onward (earlier releases mac/win only); cp313 manylinux wheel confirmed at 2.12.0 (PyPI simple index, 2026-08-25).|
|Top-node representative summaries|technique|https://arxiv.org/abs/2404.16130|n/a (in-house)|proven pattern|5|4|3|3|1|H|Per community: rank members by PageRank (or in-cluster degree/eigenvector centrality), take top-k names + counts as the summary/title. Fully deterministic with tie-broken sort; replaces GraphRAG's LLM community summaries with ranked entity lists; O(V+E) after one PageRank pass.|
|Seeded label-propagation labeling|technique|https://arxiv.org/abs/0709.2938|n/a|classic (Raghavan et al. 2007)|5|4|4|2|0|H|LP detects communities in near-linear time with no objective function (validated on known structures); reused as semi-supervised naming: few hand-assigned seed labels propagate so every community gets a human-readable tag; shipped in nx.community.label_propagation_communities, igraph community_label_propagation, NetworKit PLP. Needs fixed update order/seed for determinism; partitions can oscillate => prefer as labeler, not primary detector.|
|Hierarchical Leiden drill-down index|strategy|https://arxiv.org/abs/2404.16130|n/a|validated structure (GraphRAG)|5|4|3|4|2|M|Recursively re-run Leiden on each community until size threshold -> level tree persisted next to node-link JSON. GraphRAG demonstrates this hierarchy scales corpus-level sensemaking (1M-token range, comprehensiveness/diversity gains over flat RAG); we reuse the structure with statistical summaries instead of LLM prose. Navigation = descend levels, never global scan.|
|Partition fitness + pruning gate|technique|https://networkx.org/documentation/stable/reference/algorithms/community.html|n/a|standard practice|5|3|2|4|1|H|Score each candidate partition with modularity/coverage/performance (nx built-ins) plus per-community conductance; drop communities below min_size and reassign orphans to nearest accepted neighbor. Deterministic thresholds; keeps tiny noise clusters out of the navigation index.|
|Community-aware routing via bridges|strategy|https://arxiv.org/abs/0707.0609|n/a|established theory (Rosvall & Bergstrom 2008, PNAS)|4|3|3|4|2|M|Map-equation literature: flow-optimal partitions encode how trajectories traverse a network. Route pattern: query hits node -> its community -> cross-community high-betweenness bridge nodes -> neighbor community. Gives breadcrumb-style hops with bounded branching factor; Infomap flow levels provide the ordering if adopted.|

## Verdict (top pick)

Adopt **leidenalg 0.12.0 + igraph 0.11.8** (GPL note: fine for internal VPS use, flag if ever redistributed) as the engine behind a thin node-link-JSON adapter; summaries = top-k PageRank representatives + LP-seeded labels + conductance/min-size pruning; hierarchy via recursive Leiden. Skip graspologic (Python <3.13 metadata cap makes it a workaround, not a dependency); revisit NX-native Leiden when 3.7 goes stable; add NetworKit 11.2.1 only if graphs exceed ~10M edges.

## Integration sketch (graphifyy node-link JSON -> navigable communities)

```python
import json, igraph as ig, leidenalg as la

def load_sorted(nl_path):
    d = json.load(open(nl_path))                      # graphifyy node-link export
    ids = [n["id"] for n in d["nodes"]]
    idx = {v: i for i, v in enumerate(sorted(ids))}   # SORT: determinism requirement
    edges = sorted((idx[u], idx[v]) for u, v in d["links"])
    return ig.Graph(n=len(ids), edges=edges)          # attrs reattached via idx

parts = la.find_partition(g, la.RBConfigurationVertexPartition,
                          resolution_parameter=1.0, seed=42, n_iterations=-1)
```

Pipeline: (1) sorted-edge load; (2) find_partition seeded; (3) recursive Leiden inside communities > max_size -> level tree; (4) per-community stats {size, modularity share, conductance, top-k PageRank names}; (5) LP pass to propagate curated seed labels onto whole communities; (6) prune min_size<3; (7) emit communities.json consumed by navigate.md breadcrumbs.

Determinism checklist: sort vertices AND edges before construction; fix seed everywhere; pin igraph==0.11.8, leidenalg==0.12.0; compare partitions canonicalized (label-order-free); record versions+params alongside output.

RAM/scale: igraph C core ~ (16V + 24E) bytes ballpark — a 1M-node/10M-edge repo graph sits far under 1 GB, safely above the 3072 MiB MemAvailable floor; single-core runtime seconds-to-minutes at that size, so NetworKit's parallelism is deferred headroom, not a day-one need.
