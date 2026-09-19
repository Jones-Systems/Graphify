#!/usr/bin/env python3
"""R16 \u2014 freshness + validation-evidence ledger per corpus (SQLite).

``freshness`` records per-run source fingerprints with a CHECKed
classification; ``validation_evidence`` stores validator verdicts
(PASS / PASS_WITH_WARNINGS / BLOCKED + fatals_json).  Writers run with
``PRAGMA synchronous=FULL``; navigators use :func:`connect`
in read-only mode.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Union

_GF_ROOT = Path(os.environ.get("GF_ROOT", str(Path.home() / ".agent-references" / "graphify")))
CLASSIFICATIONS = ("valid", "stale", "unknown")
STATUSES = ("PASS", "PASS_WITH_WARNINGS", "BLOCKED")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS freshness(
  run_id TEXT NOT NULL,
  corpus TEXT NOT NULL,
  source_fingerprint TEXT NOT NULL,
  classification TEXT NOT NULL CHECK(classification IN ('valid','stale','unknown')),
  checked_utc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_freshness_recent ON freshness(corpus, checked_utc);
CREATE TABLE IF NOT EXISTS validation_evidence(
  run_id TEXT NOT NULL PRIMARY KEY,
  status TEXT NOT NULL CHECK(status IN ('PASS','PASS_WITH_WARNINGS','BLOCKED')),
  fatals_json TEXT NOT NULL DEFAULT '[]',
  recorded_utc TEXT NOT NULL);
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ledger_path(target):
    if isinstance(target, Path):
        return target
    return _GF_ROOT / str(target) / "freshness.sqlite"


def connect(target, *, read_only: bool = False) -> sqlite3.Connection:
    """Open the ledger; writers get synchronous=FULL + schema, ro for navigators."""
    path = ledger_path(target)
    if read_only:
        if not path.exists():
            raise FileNotFoundError(path)
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA synchronous=FULL")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


def fingerprint(paths) -> str:
    """Order-stable blake3 hex over sorted file paths + contents."""
    import blake3

    h = blake3.blake3()
    for f in sorted(Path(p) for p in paths):
        h.update(str(f).encode())
        with f.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()


def record(target, run_id, corpus, source_fingerprint, classification, *, status=None, fatals=None) -> str:
    """Append a freshness row (+ optional validation_evidence row)."""
    if classification not in CLASSIFICATIONS:
        raise ValueError(f"bad classification {classification!r}; want {CLASSIFICATIONS}")
    if status is not None and status not in STATUSES:
        raise ValueError(f"bad status {status!r}; want {STATUSES}")
    conn = connect(target)
    try:
        with conn:
            conn.execute(
                "INSERT INTO freshness(run_id, corpus, source_fingerprint, classification, checked_utc)"
                " VALUES(?, ?, ?, ?, ?)",
                (run_id, corpus, source_fingerprint, classification, _now()),
            )
            if status is not None:
                conn.execute(
                    "INSERT OR REPLACE INTO validation_evidence(run_id, status, fatals_json, recorded_utc)"
                    " VALUES(?, ?, ?, ?)",
                    (run_id, status, json.dumps(list(fatals or [])), _now()),
                )
    finally:
        conn.close()
    return run_id


def classify(target, current_fp: str, corpus: str = None) -> str:
    """Compare current fingerprint with the newest recorded entry."""
    if not ledger_path(target).exists():
        return "unknown"
    conn = connect(target, read_only=True)
    try:
        q = "SELECT source_fingerprint FROM freshness"
        args = []
        if corpus is not None:
            q += " WHERE corpus = ?"
            args.append(corpus)
        q += " ORDER BY checked_utc DESC, rowid DESC LIMIT 1"
        row = conn.execute(q, args).fetchone()
    finally:
        conn.close()
    if row is None:
        return "unknown"
    return "valid" if row[0] == current_fp else "stale"


def evidence(target, run_id: str):
    """Validation verdict for a run: {status, fatals} or None."""
    if not ledger_path(target).exists():
        return None
    conn = connect(target, read_only=True)
    try:
        row = conn.execute(
            "SELECT status, fatals_json FROM validation_evidence WHERE run_id = ?", (run_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {"status": row[0], "fatals": json.loads(row[1])}
