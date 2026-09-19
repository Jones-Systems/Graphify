# Lane L89 — T13 Context Efficiency: Speculative Prefetch During Agent Turns

Scope: predict which files/nodes an agent touches next from graph adjacency (graphifyy==0.9.16), prefetch into a warm cache; honest value assessment for a single-user local VPS (Debian 13, 16 cores, no GPU, 64 GB RAM, MemAvailable floor ≥3072 MiB, Python 3.13). Evidence collected 2026-08-25 via primary sources.

## Headline finding
Speculative prefetch here is Amdahl-bound into near-irrelevance. Per-step latency is dominated by the remote model round-trip (~700–2500 ms; no local LLM permitted); the harness I/O slice is tens of ms warm, and local NVMe miss penalties are sub-millisecond because the whole-corpus working set fits in page cache. Nearly all attainable gain is captured deterministically by a warm-resident runtime (long-lived tantivy readers, persistent sqlite conns, preloaded graphifyy graph), not by a predictor. Agent-side speculation survives only as an optional once-per-turn batch warmer, gated by measurement.

## Latency math (core deliverable)
Assumptions: turn ≈ 25 tool-call steps; model step median ~1 s [INFERENCE, typical API RTT].

| Component | Warm | Cold (once/session) | Prefetchable? |
|---|---|---|---|
| Source-file read (10–200 KB) | 20–60 µs (page-cache copy) | +0.3–0.8 ms (NVMe 4K @ 50–150 µs) | yes, ≤0.8 ms |
| Tantivy BM25 query | 1–10 ms | reader open+mmap faults 20–100 ms | open/faults only |
| sqlite-vec KNN (100k×768 f32 ≈300 MB scan) | 35–60 ms (bandwidth-bound) | +100–150 ms first-touch faults | no — compute-bound warm |
| PPR over KG (scipy sparse, ~20 iters) | 5–30 ms | ≈ same | no — compute-bound |
| graphifyy adjacency walk (k=2) | µs–ms (if preloaded) | 50–500 ms graph load [INFERENCE] | n/a |

- Perfect speculation ceiling: ≤40–110 ms/step ⇒ ≤4% of step time; ≤~1–2.75 s per 25-step turn.
- Realistic adjacency prefetch (h≈0.3–0.55, ≤0.5 ms/hit): 6–12 ms/turn — noise.
- Session cold start: 0.3–1.5 s once, amortized over hundreds of turns.
- Anchors: Lei & Duchamp USENIX'97 ~90% accuracy but 40% latency cut derived from high network-FS miss costs; benefit scales with OUR miss penalty (~0.5 ms). Kroeger & Long USENIX'01: 31–90% I/O cut, 11–16% elapsed — remote-dominated. Speculative Actions (arXiv:2510.04371): ≤55% top-1 next-action accuracy. Local EV: E[save] = h×0.5 ms − (walk+syscall ≈0.1–1 ms) ≈ zero or negative per step.
- Risk asymmetry: mispredictions cost only wasted reads/trivial pollution (corpus ≪ 64 GB RAM) — cheap warmers harmless, but upside equally tiny.

## Candidate items

| Item | Type | URL | License | Maturity | StackFit | EffGain | EffectGain | QualGain | AdoptCost | Conf | KeyEvidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Warm-resident runtime: long-lived tantivy IndexReader (ReloadPolicy::OnCommitWithDelay), persistent sqlite conns, preloaded graphifyy graph | strategy | https://docs.rs/tantivy/latest/tantivy/struct.IndexReader.html | MIT/Apache-2.0 (components) | mature | 5 | 3 | 3 | 1 | 1 | H | tantivy 0.26.1 default OnCommitWithDelay; searcher() cheap per request (docs.rs, 2026-08-25) |
| posix_fadvise/madvise WILLNEED batch warmer (stdlib os.posix_fadvise) | technique | https://docs.python.org/3/library/os.html#os.posix_fadvise | PSF (stdlib) | decades-stable | 5 | 2 | 1 | 0.5 | 0.5 | H | kernel-level prefetch, zero deps, Linux-only acceptable |
| vmtouch (page-cache inspect/touch/pin) | tool | https://github.com/hoytech/vmtouch | BSD-3-Clause | stable 1.3.x | 4 | 1.5 | 1 | 0.5 | 1 | H | -t warm, -l mlock-pin, mincore audit (repo README, 2026-08-25) |
| tmpfs (/dev/shm) staging of hottest index shards | strategy | https://man7.org/linux/man-pages/man5/tmpfs.5.html | OS feature | mature | 4 | 2 | 1.5 | 0 | 1 | M | effective; must budget vs MemAvailable ≥3072 MiB floor |
| Co-change Markov/access-tree predictor fused with graphifyy adjacency (turn-start batch warmer) | strategy | https://www.usenix.org/conference/usenix-1997-annual-technical-conference/analytical-approach-file-prefetching | own code (MIT) | literature-proven, unused here | 4 | 2 | 1 | 1 | 2 | M | Lei&Duchamp'97 ~90% acc on high-miss-cost FS; Kroeger&Long USENIX'01 31–90% I/O cut — gain ∝ miss penalty (tiny here) |
| SpecAgent: index-time speculative repo-context caching | prior-art/technique | https://arxiv.org/abs/2510.17925 | research paper (no impl license stated) | early research (Oct 2025) | 3 | 2 | 1.5 | 2 | 3.5 | M | 9–11 pp over strong retrieval baselines for completion; needs LLM forecasting → requires-owner-approval |
| Lossless speculative next-tool-call execution | strategy | https://arxiv.org/abs/2510.04371 | research paper | early research (Oct 2025) | 2 | 1.5 | 1 | 0.5 | 4 | M | ≤55% top-1 action accuracy; assumes fast predictor + safe replay; predictor unavailable offline |
| watchdog (inotify cache-coherence) | library | https://pypi.org/project/watchdog/ | Apache-2.0 | very mature (6.0.0, 2024-11-01) | 5 | 1.5 | 0.5 | 1 | 1 | H | invalidates warmed set on writes; complements tantivy auto-reload |
| bcc fileslower/biosnoop/cachetop measure-gate | technique | https://github.com/iovisor/bcc | Apache-2.0 | mature | 3 | 1 | 0.5 | 0.5 | 1.5 | H | prove/disprove storage stalls (>50 ms criterion) before building |
| Aider personalized-PageRank repo-map | prior-art/validation | https://aider.chat/docs/repomap.html | Apache-2.0 | mature product | 4 | 1 | 0.5 | 1.5 | 0 (superseded) | H | validates adjacency+personalization ranking; graphifyy+PPR covers; borrow sqrt(ref-count) weighting |

Refuted folklore (do not pursue): upstream SQLite has NO io_uring VFS / SQLITE_ENABLE_IOURING in any released version (checked src/os_unix.c + compile.html, 2026-08-25); custom VFS unjustified since sqlite-vec scans are bandwidth-bound warm.

## Verdict
Top pick: warm-resident runtime (#1) + fadvise/vmtouch garnish (#2/#3) — captures the entire reachable win (0.3–1.5 s one-time cold start; µs steady-state reads) at near-zero complexity, zero deps, zero misprediction risk; per-step speculative prefetch is negative-EV because ~1 s model RTT dwarfs a ≤0.8 ms NVMe miss and sqlite-vec/PPR are compute-bound warm. If any speculation ships: #5 as a once-per-turn batch warmer (top-K≈32 files, graphifyy k≤2 adjacency + git co-change scoring, background posix_fadvise WILLNEED), adopted only after bcc (#9) shows >50 ms cumulative storage stalls/session.

Integration sketch: long-lived search-service process → preload graphifyy graph; open tantivy IndexReader once (default OnCommitWithDelay; fresh Searcher per query); persistent sqlite/sqlite-vec conns; optional `vmtouch -t -l -m 512M` on index dirs behind MemAvailable ≥3072 MiB guard (memlock ulimit); optional turn-start warmer; watchdog InotifyObserver for warmed-set coherence. Skip per-step speculation (SpecAgent / Speculative Actions) until a local fast predictor exists.