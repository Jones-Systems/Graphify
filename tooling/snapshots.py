#!/usr/bin/env python3
"""R13 \u2014 snapshot node-link graphs as zstd parquet pairs + duckdb RO views.

Writes ``nodes.parquet`` / ``edges.parquet`` (zstd) under
``~/.agent-references/graphify/<corpus>/snapshots/<utc>-<sha8>/`` plus a
MANIFEST.json (per-file sha256, created_utc), then atomically repoints
the ``latest`` symlink.  :func:`connect_ro` exposes the pair as duckdb
views with a 2 GiB memory limit.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Union

_GF_ROOT = Path(os.environ.get("GF_ROOT", str(Path.home() / ".agent-references" / "graphify")))


def _utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _table(rows):
    """Arrow table from node/link dicts; flatten nested attrs on clash."""
    import pyarrow as pa

    try:
        return pa.Table.from_pylist(rows)
    except (pa.ArrowInvalid, pa.ArrowTypeError):
        def flat(d):
            return {
                k: (json.dumps(v, sort_keys=True) if isinstance(v, (dict, list, tuple, set)) else v)
                for k, v in d.items()
            }
        return pa.Table.from_pylist([flat(r) for r in rows])


def node_link_data(G, edges: str = "links", *, corpus: str = None, root: Path = None) -> Path:
    """Serialize a NetworkX graph to a parquet snapshot pair.

    Returns the created snapshot directory
    ``<root>/<corpus>/snapshots/<utc>-<sha8>/``; ``G.graph['corpus']`` is
    consulted when *corpus* is omitted.
    """
    import networkx as nx
    import pyarrow.parquet as pq

    corpus = corpus or (G.graph or {}).get("corpus")
    if not corpus:
        raise ValueError("snapshot target corpus: pass corpus= or set G.graph['corpus']")
    data = nx.node_link_data(G, edges=edges)
    nodes, links = data.get("nodes", []), data.get(edges, [])

    snap_root = (Path(root) if root else _GF_ROOT) / str(corpus) / "snapshots"
    snap_root.mkdir(parents=True, exist_ok=True)
    tmp = snap_root / f".tmp-{os.getpid()}"
    if tmp.exists():
        os.rename(tmp, tmp.with_name(tmp.name + "-old"))
    tmp.mkdir()
    try:
        n_path, e_path = tmp / "nodes.parquet", tmp / "edges.parquet"
        pq.write_table(_table(nodes), n_path, compression="zstd")
        pq.write_table(_table(links), e_path, compression="zstd")
        files = {"nodes.parquet": _sha256(n_path), "edges.parquet": _sha256(e_path)}
        manifest = {
            "corpus": str(corpus),
            "created_utc": _utc_iso(),
            "edges_key": edges,
            "node_count": len(nodes),
            "edge_count": len(links),
            "files": files,
        }
        sha8 = hashlib.sha256((files["nodes.parquet"] + files["edges.parquet"]).encode()).hexdigest()[:8]
        final = snap_root / f"{_utc_compact()}-{sha8}"
        if final.exists():
            for p in tmp.iterdir():
                p.unlink()
            tmp.rmdir()
            latest = snap_root / "latest"
            tmpl = snap_root / f".latest-{os.getpid()}"
            if tmpl.is_symlink() or tmpl.exists():
                tmpl.unlink()
            os.symlink(final.name, tmpl)
            os.replace(tmpl, latest)
            return final
        (tmp / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
        os.rename(tmp, final)
    finally:
        if tmp.exists():
            for p in tmp.iterdir():
                if p.is_file():
                    p.unlink()
            if not any(tmp.iterdir()):
                tmp.rmdir()

    latest = snap_root / "latest"
    tmpl = snap_root / f".latest-{os.getpid()}"
    if tmpl.is_symlink() or tmpl.exists():
        tmpl.unlink()
    os.symlink(final.name, tmpl)
    os.replace(tmpl, latest)
    return final


def connect_ro(db: Union[str, Path]):
    """DuckDB in-memory connection with nodes/edges views over the parquet.

    *db* is a snapshot directory (containing nodes.parquet) or a
    snapshots root whose ``latest`` symlink selects the pair.
    """
    import duckdb

    d = Path(db)
    if not (d / "nodes.parquet").exists():
        d = (d / "latest").resolve()
    n_path, e_path = (d / "nodes.parquet").resolve(), (d / "edges.parquet").resolve()
    con = duckdb.connect(database=":memory:", config={"memory_limit": "2GB"})
    for view, p in (("nodes", n_path), ("edges", e_path)):
        lit = str(p).replace("'", "''")
        con.execute(f"CREATE VIEW {view} AS SELECT * FROM read_parquet('{lit}')")
    return con
