# L10 — Qdrant local-mode (in-process) vs standalone server for ~1–5M vectors

Lane L10 · T2 embeddings · investigated 2026-08-25 · Debian VPS, 16 CPU cores, NO GPU, 64 GB RAM, hard floor MemAvailable ≥ 3072 MiB during bursts, Python 3.13, offline/self-hostable, Apache/MIT-class licenses.

## Versions verified (primary sources)

| Component | Version | License | Checked |
|---|---|---|---|
| Qdrant server | v1.19.0 (2026-08-05, commit 74f3e85) | Apache-2.0 | GitHub releases, 2026-08-25 |
| qdrant-client (PyPI) | 1.19.0 | Apache-2.0, Python >=3.10 (3.13 OK) | PyPI JSON API, 2026-08-25 |
| qdrant-edge-py (embedded Rust engine) | 0.8.0 (pre-1.0) | Apache-2.0 | PyPI JSON API, 2026-08-25 |

## Ground truth: what "local mode" actually is

`QdrantClient(":memory:")` and `QdrantClient(path=...)` are **not** the Rust engine embedded. They run `QdrantLocal`, a **pure Python + NumPy reimplementation** inside qdrant-client (`qdrant_client/local/qdrant_local.py`, `local_collection.py`). Verified properties (client master, Aug 2026):

- Search is **exact brute force**, O(N×D) per query; no HNSW index is built; `hnsw_ef`, `exact`, quantization and ACORN parameters are silently ignored.
- Dense vectors live as **NumPy arrays fully resident in process RAM**; `path=` persists to disk but reloads everything into RAM on client construction. Memory-placement arguments are accepted for API compatibility but are "meaningless in local mode" per source comments.
- Source defines `LARGE_DATA_THRESHOLD = 20_000` and emits: *"Local mode is not recommended for collections with more than 20,000 points"* — recommends Docker/server beyond that.
- Persistent path takes an **exclusive lock**: a second client/process on the same dir fails outright (single-process only; known thread-safety races e.g. issue #1193).
- No server snapshots, no auth/API keys, no gRPC, none of the server's optimizer/segment machinery.

## Resource profiles at replication_factor=1, m=16 (official capacity-planning formulas)

Formulas (https://qdrant.tech/documentation/capacity-planning/, retrieved 2026-08-25):
- `dense = N × dims × bytes_per_dim` (float32=4, uint8/scalar-int8=1, turbo4=0.5)
- `hnsw = N × m × 2 × 4 B × 1.2` (m=16 → N×153.6 B)
- `id_tracker = N × 52 B` (always RAM-resident)
- payload disk `N × avg × 1.5`; payload defaults `cold`; headroom ×1.2
- Server always mmaps vectors to disk; memory tier `cached` (default) preloads to RAM, `cold` reads on demand via page cache, `pinned` heap-resident. Rule of thumb: halve the RAM-resident vectors → roughly double search latency.

Computed for 768-dim float32, 1 KB payload:

| Deployment config | 1M vecs RAM | 5M vecs RAM | Query behavior |
|---|---|---|---|
| Local mode `path=` (NumPy) | ~3.0 GB+ (raw dense 2.86 GB + per-point Python/payload overhead) | ~14.3 GB+ (raw dense alone) | Exact scan O(N·D): sub-second @1M×768 under BLAS, seconds-level @5M; degrades linearly |
| Server default (`cached`, float32) | (2.86+0.15+0.05)×1.2 ≈ **3.7 GB** | (14.31+0.74+0.26)×1.2 ≈ **18.4 GB** | HNSW ANN, ms-level |
| Server low-RAM: vectors `cold` + TurboQuant-4bit `pinned`, HNSW `cached` | (0.36+0.15+0.05)×1.2 ≈ **0.7 GB** | (1.84+0.74+0.26)×1.2 ≈ **3.4 GB** | HNSW over quantized copy + rescore top-k from disk |

At 1536-dim × 5M: default-cached ≈ 35.5 GB RAM (unsafe next to other bursts on a shared 64 GB box); cold+turbo4 ≈ 5.6 GB. Scalar int8 sits between (÷4 vs ÷8; docs report <1% accuracy loss; TurboQuant 4-bit claims comparable recall at 2× compression).

Floor compliance: the 3072 MiB MemAvailable floor is only comfortably satisfiable at 1–5M vectors with the server's cold/on-disk + quantization profile (page cache is reclaimable, so OS pressure stays elastic). Local mode's fixed in-process arrays are the worst possible fit for the floor.

## Decision matrix

- **< 20k vectors, unit tests / CI / notebooks** → local mode (`:memory:` or `path=`). Exact recall, zero infra, trivially offline. This is its designed purpose.
- **20k – ~500k, single-process batch jobs** → local mode *technically* works (small dims, spare RAM) but is already past the vendor's own warning line; prefer server unless you refuse any daemon.
- **1–5M vectors** → standalone server, single node, non-negotiable: local mode needs 3–15 GB pinned inside your Python process AND serves seconds-level brute-force queries; Edge is promising but pre-1.0.
- **Multi-process access / concurrent writers / durability** → server only (exclusive lock kills local mode).
- Ops for standalone on this VPS: Docker (`qdrant/qdrant`) or release binary under systemd; ports 6333 (REST)/6334 (gRPC — "typically much faster", use for bulk upload); bind 127.0.0.1 or set API key; POSIX block FS required (no NFS); SSD/NVMe strongly recommended for `cold` tiers; snapshots for backup; verify actual residency with the Memory Usage API (v1.18+).

## Findings table

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|QdrantClient(":memory:") local mode|tool|https://github.com/qdrant/qdrant-client/blob/master/qdrant_client/local/qdrant_local.py|Apache-2.0|Mature for dev/test (ships in client 1.19.0)|2|1|1|1|0|H|Source: NumPy brute force, LARGE_DATA_THRESHOLD=20_000 warning; README: "development, prototyping and testing" (checked 2026-08-25)|
|QdrantClient(path=...) persistent local mode|tool|https://pypi.org/project/qdrant-client/|Apache-2.0|Mature for dev/test|2|1|1|1|0|H|Persists to disk but reloads all vectors into process RAM; exclusive lock, single process (qdrant_local.py, Aug 2026)|
|Qdrant standalone server v1.19.0 (Docker/binary, single node)|tool|https://qdrant.tech/documentation/installation/|Apache-2.0|Production-grade; v1.19.0 released 2026-08-05|5|5|5|4|1|H|x86_64 OK; REST+gRPC 6333/6334; POSIX block FS; official recommendation for scale beyond local mode|
|Memory tiers cold/cached/pinned (server, unified `memory` param v1.18+)|technique|https://qdrant.tech/documentation/manage-data/storage/|Apache-2.0|Stable|5|5|4|0|1|H|Vectors always mmap'd; `cold` = page-cache on demand, docs-recommended for large collections on fast disks; halving RAM-resident vectors ≈ doubles latency|
|Quantization: TurboQuant 4-bit (v1.18+) or scalar int8, quantized copy pinned + rescoring|technique|https://qdrant.tech/documentation/manage-data/quantization/|Apache-2.0|Scalar stable since v1.1; TurboQuant newer (v1.18, Jun-Jul 2026)|5|4|4|3|1|H|Scalar int8: 4×, "usually less than 1%" error; TurboQuant bits4: 8×, similar recall; v1.19 adds 4-bit primary storage|
|Official capacity-planning formulas + sizing calculator|strategy|https://qdrant.tech/documentation/capacity-planning/|docs (Apache-2.0 site)|Current (retrieved 2026-08-25)|4|3|2|1|0|H|dense/hnsw/id_tracker formulas + ×1.2 headroom reproduce the 0.7→3.4 GB cold+turbo4 profile for 1–5M×768|
|qdrant-edge-py 0.8.0 — real Rust engine embedded in-process|tool|https://pypi.org/project/qdrant-edge-py/|Apache-2.0|Young: pre-1.0, ~7k weekly downloads (2026-08-25)|4|3|3|3|2|M|In-process Rust engine: supports on_disk vectors, payload indexes, BM25 sparse, ALL quantization methods incl. TurboQuant; "minimal memory footprint, no background services"|
|Edge-shard ↔ server synchronization (snapshots/dual-write)|strategy|https://qdrant.tech/documentation/edge/edge-synchronization-guide/|Apache-2.0|Documented pattern for Edge 0.x|3|2|2|2|2|M|Lets embedded shards stay syncable to a central server later — migration path if we start embedded and outgrow it|

## Verdict

Top pick: **standalone Qdrant server v1.19.0, single node** (Docker or systemd binary, localhost-bound) — local mode is disqualified at 1–5M vectors on three independent grounds (RAM-resident NumPy arrays ≈ raw corpus size, seconds-level brute-force O(N·D) queries, vendor's own >20k-point warning). Why: only the server's `cold` vector tier + TurboQuant-bits4-pinned + HNSW-cached profile lands 5M×768 at ≈3.4 GB RAM (≈5.6 GB at 1536-d), keeping MemAvailable far above the 3072 MiB floor while retaining ms-level HNSW latency. Integration sketch: pin `qdrant-client==1.19.0` with `prefer_grpc=True`; create collection with `VectorParams(memory=COLD)` + `TurboQuantization(memory=PINNED)` + HNSW `cached`, `indexing_threshold=20000`; reserve `QdrantClient(":memory:")` strictly for CI tests; re-evaluate `qdrant-edge-py` as an embedded option once it reaches 1.0.
