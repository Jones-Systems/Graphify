#!/usr/bin/env python3
"""R12 \u2014 arctic-embed-m-v1.5 embeddings + int8/bit twins in sqlite-vec.

Model registered per fastembed custom-model docs:
``Snowflake/snowflake-arctic-embed-m-v1.5``, CLS pooling, dim 768.
Document embedding is bare text; :func:`query_embed` prepends the
W1-a-spec ``query: `` prefix.  Vectors land in the per-corpus
``search.sqlite`` as a vec0 triplet: vec float[768], vec_int8 int8[768],
vec_bit bit[768].  Every burst guards MemAvailable >= 3072 MiB.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterable, Union

import numpy as np

MODEL_NAME = "Snowflake/snowflake-arctic-embed-m-v1.5"
DIM = 768
BATCH = 256
FLOOR_MIB = 3072
QUERY_PREFIX = "query: "
_GF_ROOT = Path(os.environ.get("GF_ROOT", str(Path.home() / ".agent-references" / "graphify")))

_model = None


def ram_available_mib() -> int:
    with open("/proc/meminfo") as fh:
        for line in fh:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    raise RuntimeError("/proc/meminfo missing MemAvailable")


def mem_guard(phase: str) -> int:
    """Print MemAvailable; halt below the 3072 MiB floor (build-graph.sh pattern)."""
    mib = ram_available_mib()
    print(f"[emb] MemAvailable({phase}): {mib} MiB", flush=True)
    if mib < FLOOR_MIB:
        raise RuntimeError(f"[emb] HALT: floor breach at {phase}: {mib} MiB < {FLOOR_MIB}")
    return mib


def _ensure_model(cache_dir=None):
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        from fastembed.common.model_description import ModelSource, PoolingType

        TextEmbedding.add_custom_model(
            model=MODEL_NAME,
            pooling=PoolingType.CLS,
            normalization=True,
            sources=ModelSource(hf=MODEL_NAME),
            dim=DIM,
            model_file="onnx/model.onnx",
        )
        mem_guard("model-load")
        _model = TextEmbedding(model_name=MODEL_NAME, cache_dir=str(cache_dir) if cache_dir else None)
    return _model


def embed_texts(texts, cache_dir=None):
    """Embed documents in batches of 256; returns float32[n, 768]."""
    texts = list(texts)
    model = _ensure_model(cache_dir)
    mem_guard("embed-start")
    out = np.empty((len(texts), DIM), dtype=np.float32)
    for i in range(0, len(texts), BATCH):
        batch = texts[i : i + BATCH]
        for j, vec in enumerate(model.embed(batch, batch_size=len(batch))):
            out[i + j] = vec
        mem_guard(f"batch {i // BATCH}")
    mem_guard("embed-end")
    return out


def query_embed(text: str, cache_dir=None):
    """Query-side embedding with the 'query: ' prefix; float32[1, 768]."""
    return embed_texts([QUERY_PREFIX + text], cache_dir)


def quantize_int8(vec) -> tuple:
    """Symmetric per-vector int8 twin; returns (int8[768], scale float32)."""
    v = np.asarray(vec, dtype=np.float32)
    scale = np.float32(max(float(np.max(np.abs(v))), 1e-12) / 127.0)
    return np.clip(np.rint(v / scale), -127, 127).astype(np.int8), scale


def quantize_bit(vec):
    """Binary twin: sign bits packed little-endian; uint8[96]."""
    return np.packbits(np.asarray(vec) > 0, axis=-1).astype(np.uint8)


def search_path(target):
    if isinstance(target, Path):
        return target
    return _GF_ROOT / str(target) / "search.sqlite"


def connect_search(target, *, read_only: bool = False) -> sqlite3.Connection:
    """Open per-corpus search.sqlite with the sqlite-vec extension loaded."""
    path = search_path(target)
    if read_only:
        if not path.exists():
            raise FileNotFoundError(path)
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
    import sqlite_vec

    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    if not read_only:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vectors USING vec0("
            "chunk_id TEXT PRIMARY KEY, vec float[768], vec_int8 int8[768], vec_bit bit[768])"
        )
        conn.commit()
    return conn


def store_embeddings(target, pairs) -> int:
    """Store (chunk_id, float32[768]) pairs with both quantized twins."""
    conn = connect_search(target)
    n = 0
    with conn:
        for chunk_id, vec in pairs:
            v = np.ascontiguousarray(vec, dtype=np.float32)
            q8, _scale = quantize_int8(v)
            conn.execute("DELETE FROM chunk_vectors WHERE chunk_id = ?", (str(chunk_id),))
            conn.execute(
                "INSERT INTO chunk_vectors(chunk_id, vec, vec_int8, vec_bit) VALUES(?, ?, vec_int8(?), vec_bit(?))",
                (str(chunk_id), v.tobytes(), q8.tobytes(), quantize_bit(v).tobytes()),
            )
            n += 1
    conn.close()
    return n
