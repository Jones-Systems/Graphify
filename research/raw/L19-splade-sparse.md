I now have solid evidence. Note: Cohere sparse — actually Cohere does have "sparse embeddings" via embed-english-v3.0 with `embedding_types=["sparse"]`? The search says Embed v4 doesn't provide native sparse; embed v3 DID have sparse output type (embed-english-v3.0 supports int8/binary/sparse?). Actually yes, embed-english-v3.0 supports "sparse" embedding type per Cohere docs. But the search result focused on v4. I'll keep the row but frame it accurately: cloud API only (no open weights), requires-owner-approval, and note v3 had sparse output type while v4 dropped it — hmm, I don't have direct evidence for v3 sparse from this search. To stay grounded, I'll say: Cohere offers sparse vectors only as a paid cloud API feature on older embed-v3 models (requires-owner-approval), citing docs.cohere.com reference/embed which lists float/int8/binary types for v4 — the search explicitly said v4 has no native sparse. I'll phrase carefully with what's grounded: "Embed v4.0 dense-only output types; no local open weights; enterprise GPU deployment only" and mention sparse-via-API exists on embed-v3 [INFERENCE-free? it's well-known; mark M confidence]. Actually to be safe: mark that row's evidence as the docs pages found, note v3 sparse availability as widely documented but unverified here → Confidence L-M. Or simply drop the v3 claim and present Cohere row as "cloud-only alternative, rejected under offline constraint". Fine.

Also OpenSearch two-phase search — I didn't get dedicated latency evidence. But I have: fastembed issue #648 discussion of inference-free SPLADE: 57ms → 4.3ms median query time, <1.3% relative quality loss (cited benchmark). That covers the inference-free approach quantitatively. And doc-v2-distill + tokenizer query model is exactly this pattern (sbert.net lists doc-v2-distill BEIR-13 50.4 vs BM25 45.6). Good enough without another search round.

One more useful fact I have: ST v5.1.0 ONNX/OpenVINO for SparseEncoder → 2-3x speedups + quantization (2025-08-06).

Now compose findings table. Items (~13):

1. **opensearch-neural-sparse-encoding-doc-v2-distill** (repo/model) — Apache-2.0, 67M, 268MB safetensors, BEIR-13 50.4 vs BM25 45.6, doc-side-only encoding, query = tokenizer (inference-free). StackFit 5, EffGain 3 (query-time ~BM25), EffectGain 4, QualGain 4, AdoptCost 1, Conf H.
2. **opensearch-neural-sparse-encoding-v2-distill** (bi-encoder) — Apache-2.0, 67M, BEIR-13 52.8, needs query-side encoder (~10-30ms CPU ONNX). Conf H.
3. **naver/splade-v3** — CC BY-NC-SA (non-commercial) → blocked unless owner approval; best-in-class MS MARCO 40.2 MRR@10 / BEIR-13 51.7. Conf H. AdoptCost 5 due license.
4. **prithivida/Splade_PP_en_v1 (+v2)** — Apache-2.0, BERT-base 110M, ONNX in fastembed 0.532GB, MRR@10 37.2 ID / 48.7 BEIR OOD, ~113 active tokens/doc low FLOPs. Conf H.
5. **fastembed SparseTextEmbedding** (tool) — Apache-2.0, ONNX Runtime, int8-ready; SPLADE++ 50-100ms/query cited, doc encode can be slow unoptimized (0.55-3s/doc reports); parallel workers option. Conf H.
6. **sentence-transformers ≥5.0 SparseEncoder** (tool/strategy) — Apache-2.0, unified API SPLADE/inference-free-SPLADE/CSR; v5.1.0 ONNX+OpenVINO 2-3x speedup; py3.13 fine. Conf H.
7. **ONNX Runtime dynamic INT8 quantization pipeline** (technique) — MIT, ≥1.20 for cp313 wheels (current 1.28.0 Aug 2026), 1.2-2x typical speedup, more with VNNI (EPYC Genoa has AVX-512 VNNI); memory 4x smaller weights. Conf H.
8. **BGE-M3 sparse head** — MIT but 568M params, ~2.2GB fp32 RAM, CPU heavy (~1-2k tok/s optimized int8 C impl); only worth it if we also want its dense/multilingual. StackFit 2. Conf M-H.
9. **docTTTTTquery/doc2query-T5 expansion** (alternative learned-sparse strategy) — Apache-2.0 checkpoints; MS MARCO test MRR@10 18.6→27.2 (+46% rel); T5-base CPU generation expensive offline (gen 40 queries/doc); retrieval stays BM25-fast. Conf H.
10. **Inference-free/asymmetric SPLADE two-phase pattern** (technique) — neural doc-side expansion + tokenizer-only queries; median query 57ms→4.3ms with <1.3% quality loss (fastembed #648 benchmark); OpenSearch two-phase search implements same idea. EffGain 5. Conf M (numbers from one benchmark).
11. **LanceDB FTS/hybrid (BM25+RRF)** — Apache-2.0; NO native learned-sparse vector index (as of docs checked 2026-08); SPLADE rerank-over-candidates workaround or external inverted index. Critical integration constraint. Conf H.
12. **Cohere embed sparse vectors (cloud)** — requires-owner-approval; API $0.12/M input tokens (dense v4 pricing); no open weights; violates offline preference. Conf M.
13. Maybe **Qdrant sparse index / bm25+bge-m3 style**: skip — Qdrant server adds a service; our stack prefers embedded. Could include BM42 row briefly: Qdrant/bm42-all-minilm-l6-v2-attentions 0.09GB — attention-weighted token weights, lightweight, experimental/abandoned-ish. Add as item 13, Conf M. It gives cheap middle ground. OK include.

That's 13 items. 

Scores calibration (StackFit: fits py3.13/no-GPU/LanceDB/graphifyy stack):
1. OS doc-v2-distill: StackFit 5, EffGain 4 (query≈tokenizer, zero NN at query time), EffectGain 4 (+4.8 BEIR over BM25), QualGain 4, AdoptCost 1, Conf H.
2. OS v2-distill bi: StackFit 4, EffGain 2 (query encoder needed), EffectGain 5 (52.8), QualGain 4, AdoptCost 1, Conf H.
3. splade-v3: StackFit 3 (tech great, license kills), EffGain 1, EffectGain 5 (MS MARCO 40.2 MRR@10), QualGain 5, AdoptCost 5, Conf H.
4. Splade_PP_en_v1: StackFit 4, EffGain 1, EffectGain 3, QualGain 3, AdoptCost 1, Conf H.
5. fastembed: StackFit 4, EffGain 2, EffectGain 2 (depends model), QualGain 2, AdoptCost 1, Conf H.
6. ST SparseEncoder: StackFit 5, EffGain 3 (ONNX/OpenVINO 2-3x), EffectGain n/a—use 2, QualGain 3, AdoptCost 1, Conf H.
7. ORT int8: StackFit 5, EffGain 3, EffectGain 0 (lossless-ish technique)... scale 0-5; use 1. QualGain 1. AdoptCost 1. Conf H.
8. BGE-M3 sparse: StackFit 2, EffGain 0, EffectGain 4 (multilingual lexical strong), QualGain 4, AdoptCost 3, Conf M.
9. docTTTTTquery: StackFit 2 (T5 CPU gen cost, but retrieval stays BM25), EffGain 4 (query-time free), EffectGain 3 (+46% rel on MS MARCO but weaker OOD than SPLADE), QualGain 2 (OOD weak), AdoptCost 2, Conf H.
10. Two-phase/inference-free pattern: StackFit 5, EffGain 5, EffectGain 3 (<1.3% loss claim), QualGain 3, AdoptCost 1, Conf M.
11. LanceDB FTS hybrid: StackFit 5 (already planned backbone adjacency), EffGain 4, EffectGain 1, QualGain 2, AdoptCost 1, Conf H.
12. Cohere: StackFit 0 (cloud), flagged requires-owner-approval. EffGain 2, EffectGain 4, QualGain 4, AdoptCost 4, Conf M.
13. BM42: StackFit 3, EffGain 4, EffectGain 1, QualGain 1, AdoptCost 1, Conf M (experimental, limited validation).

Verdict: top pick = OpenSearch neural-sparse family (doc-v2-distill + tokenizer queries) run via sentence-transformers SparseEncoder exported to ONNX int8 via ORT ≥1.20 on EPYC Genoa; fuse with existing BM25/LanceDB FTS via RRF; store SPLADE postings outside LanceDB vector index (custom inverted index or candidate-pool rerank) since LanceDB lacks native sparse index. RAM: ~270MB fp32 / ~70MB int8 → far below 3072MiB floor; query path can be 100% NN-free (BM25-speed) with doc-side neural expansion.

Integration sketch:
1. Offline: chunk nodes from graphifyy JSON graphs → encode docs with doc-v2-distill (ST SparseEncoder or ORT session) → postings (term_id, weight) → custom inverted index (sqlite table or tantivy-like dict) keyed by node id.
2. Query: tokenize query with BERT tokenizer (ms), look up postings, score dot-product → merge with BM25 + future PPR signals via RRF.
3. Optional phase-2: rerank top-k=100 with bi-encoder v2-distill if quality needed.

Now write file research/raw/L19-splade-sparse-neural-retrieval.md via hub start python3 -c. Content: header, environment constraints recap, table, verdict, integration sketch, sources list with dates.

Careful with hub start: application python3, args ["-c", script]. Script writes file using pathlib. Use triple-quoted string... quoting hell inside JSON args — manageable since args are passed directly as argv (no shell). So I can use a single -c argument containing newlines. In JSON, newlines encoded \n. Avoid f-strings with braces issues — plain string literal write. Keep script simple:

from pathlib import Path
md = """..."""
Path("research/raw").mkdir(parents=True, exist_ok=True)
Path("research/raw/L19-splade-sparse.md").write_text(md)

cwd defaults to session directory — which should be /home/malcolmjones/Projects/Codex-V3. To be safe use absolute paths.

Markdown content includes pipes etc. — fine. Must avoid backslashes issues: LaTeX not needed. Watch out for `"""` inside content — avoid. Also avoid `\n` literals beyond intended.

The table format mandated: |Item|Type|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|

Then ≤3-line verdict. Then extras (integration sketch, sources) — contract says Findings = table + ≤3-line verdict; extra sections presumably allowed ("full findings"). I'll append details after verdict.

Then read back the file head to verify, then yield with summary/files/architecture, final line LANE L19 DONE.

Note the yield schema: files[] entries {path, description}. Include research/raw/L19-splade-sparse.md. architecture = integration sketch string. summary = verdict + key numbers.

Let me build the markdown now. Keep evidence dates: searches conducted 2026-08-25. Versions: onnxruntime 1.28.0 current (PyPI, retrieved 2026-08-25), first cp313 wheels 1.20.0 (Oct 2024). ST v5.0.0 2025-07-01, v5.1.0 2026-08-06? No — August 6, 2025. fastembed issue numbers #539, #648. splade-v3 released 2024-03-11 arXiv 2403.06789. docTTTTTquery paper 2019 Nogueira & Lin. BGE-M3 card. HF cards accessed today via URL reads.

Write the python heredoc. I'll compose md string carefully. Length moderate (~120 lines). Then verify with read :1-40 maybe.

{"command":"python3 - <<'EOF'\nimport json\nsrc = \"/home/malcolmjones/.omp/profiles/ox-alpha/agent/sessions/-Projects-Codex-V3/2026-08-24T21-43-19-749Z_01a035ba-57c5-7140-b5cc-3df817e29c87\"\nd = json.load(open(f\"{src}/L29.md\"))\nr = d.get(\"result\", d)\nif isinstance(r, str): r = json.loads(r)\ncands = [str(v) for v in (r.values() if isinstance(r, dict) else [r]) if isinstance(v, str)]\nopen(\"/home/malcolmjones/Projects/Graphify/research/raw/L29-tree-sitter-grammars.md\",\"w\").write(max(cands, key=len))\nprint(\"L29\", len(max(cands, key=len)))\n\np2 = \"\"\nfor line in open(f\"{src}.jsonl\"):\n    try: dd = json.loads(line)\n    except Exception: continue\n    def scan(o):\n        global p2\n        if isinstance(o, dict):\n            for k, v in o.items():\n                if isinstance(v, str) and \"[PART 2/2]\" in v and \"neural-sparse doc-v2-distill\" in v: p2 = v\n                else: scan(v)\n        elif isinstance(o, list):\n            for x in o: scan(x)\n    scan(dd)\n\nbest = \"\"\nfor line in open(f\"{src}/L19.jsonl\"):\n    try: dd = json.loads(line)\n    except Exception: continue\n    def scan2(o):\n        global best\n        if isinstance(o, dict):\n            for k, v in o.items():\n                vv = v\n                if isinstance(vv, str) and \"doc-v2-distill\" in vv and \"|Item|\" in vv.replace(\" \",\"\") and len(vv) > len(best): best = vv\n                else: scan2(vv)\n        elif isinstance(o, list):\n            for x in o: scan2(x)\n    scan2(dd)\n\ncur = open(\"/home/malcolmjones/Projects/Graphify/research/raw/L19-splade-sparse.md\").read()\nfull = (best + \"\\n\\n\" + p2).strip() if len(best) > len(cur) else (cur + \"\\n\\n\" + p2).strip()\nopen(\"/home/malcolmjones/Projects/Graphify/research/raw/L19-splade-sparse.md\",\"w\").write(full or \"RECOVERY PENDING\\n\")\nprint(\"L19 final:\", len(full), \"| table:\", \"|Item|\" in full.replace(\" \",\"\") or \"| Item\" in full)\nEOF","i":"Persisting L29 and rebuilding L19 fixed scope"