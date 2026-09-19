#!/usr/bin/env python3
"""R1 \u2014 stable CURIE identities for Graphify nodes (id_scheme 'r1-v1').

Node id scheme (SPEC L73): ``{corpus}:{relpath}#{slug}`` for every
file-derived node.  The slug is the normalized file stem plus a kind
suffix (optionally preceded by the normalized qualname for intra-file
definitions).  Surrogate integer PKs are assigned at insert time via
:func:`intern_pk`; the ``id_aliases`` table ships day 1 so renamed
slugs keep their history.

Pure stdlib.
"""
from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Union

ID_SCHEME = "r1-v1"
_GF_ROOT = Path(os.environ.get("GF_ROOT", str(Path.home() / ".agent-references" / "graphify")))
_NONALNUM = re.compile(r"[^a-z0-9]+")
_CURIE = re.compile(r"^(?P<corpus>[^:#]+):(?P<relpath>[^#]+)#(?P<slug>.+)$")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS _meta(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL);
INSERT OR IGNORE INTO _meta(key, value) VALUES('id_scheme', 'r1-v1');
CREATE TABLE IF NOT EXISTS node_ids(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  curie TEXT NOT NULL UNIQUE,
  created_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS id_aliases(
  alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
  old_curie TEXT NOT NULL,
  new_curie TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_utc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_id_aliases_old ON id_aliases(old_curie);
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify(text: str) -> str:
    slug = _NONALNUM.sub("-", text.lower()).strip("-")
    return slug or "x"


def mint(corpus: str, relpath: str, kind: str, qualname: str = "") -> str:
    """Mint the CURIE for a file-derived node.

    slug := normalize(stem) [+ '-' + normalize(qualname)] + '-' + kind.
    """
    parts = [_slugify(Path(relpath).stem)]
    if qualname:
        parts.append(_slugify(qualname))
    parts.append(_slugify(kind))
    return f"{corpus}:{relpath}#{'-'.join(parts)}"


def decompose(curie: str) -> dict:
    """Split a CURIE into {corpus, relpath, slug, kind}; raises ValueError."""
    m = _CURIE.match(curie)
    if not m:
        raise ValueError(f"malformed curie: {curie!r}")
    d = m.groupdict()
    slug = d["slug"]
    d["kind"] = slug.rsplit("-", 1)[-1] if "-" in slug else ""
    return d


def ledger_path(target: Union[str, Path]) -> Path:
    """Identity ledger for a corpus name, or an explicit sqlite path."""
    if isinstance(target, Path):
        return target
    return _GF_ROOT / str(target) / "identity.sqlite"


def connect(target: Union[str, Path]) -> sqlite3.Connection:
    """Open (creating if needed) the identity ledger for a corpus."""
    path = ledger_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


def intern_pk(conn: sqlite3.Connection, curie: str) -> int:
    """Assign (exactly once) and return the surrogate integer PK."""
    decompose(curie)  # validate shape before touching the table
    row = conn.execute("SELECT id FROM node_ids WHERE curie = ?", (curie,)).fetchone()
    if row is not None:
        return int(row[0])
    cur = conn.execute(
        "INSERT INTO node_ids(curie, created_utc) VALUES(?, ?)", (curie, _now())
    )
    conn.commit()
    return int(cur.lastrowid)


def alias(old: str, new: str, reason: str) -> int:
    """Record an old->new identity rename; returns the alias_id.

    The ledger is selected from the OLD curie's corpus segment, keeping
    this a pure function of its arguments.
    """
    d_old, d_new = decompose(old), decompose(new)
    if old == new:
        raise ValueError("alias requires old != new")
    conn = connect(d_old["corpus"])
    try:
        cur = conn.execute(
            "INSERT INTO id_aliases(old_curie, new_curie, reason, created_utc)"
            " VALUES(?, ?, ?, ?)",
            (old, new, reason, _now()),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def resolve_pk(conn: sqlite3.Connection, curie: str) -> Optional[int]:
    """PK for a curie, following alias chains (newest link first)."""
    seen = set()
    while True:
        row = conn.execute("SELECT id FROM node_ids WHERE curie = ?", (curie,)).fetchone()
        if row is not None:
            return int(row[0])
        seen.add(curie)
        row = conn.execute(
            "SELECT new_curie FROM id_aliases WHERE old_curie = ?"
            " ORDER BY alias_id DESC LIMIT 1",
            (curie,),
        ).fetchone()
        if row is None or row[0] in seen:
            return None
        curie = row[0]
