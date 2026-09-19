#!/usr/bin/env python3
"""Layered output/truncation contract — R17 (master-ranking rank 17, C6/L54).

Framework-neutral middleware hooks for the mj-graph-search server (R6,
docs/MCP-SURFACE.md). Every truncation is explicit and resumable:

  cap_results(items)      -> {items, truncated, total_estimate, next_cursor, hint}
  artifact_spill(payload) -> {ref, path, bytes, sha256} for over-cap payloads
  gist_first_ordering(h)  -> best evidence first + 2-line aggregate gist LAST
                             (Lost-in-the-Middle countermeasure)

Cursors are opaque keysets over (score, node_id): callers sort by
(-score, node_id) and hand `next_cursor` back to resume exactly after the
last emitted hit — no offsets, stable under concurrent inserts.
Pure stdlib; fastembed/fastmcp are NOT imported here (the DEC-9-gated server
lands in R6 and wires these hooks as its middleware).
"""

import base64
import hashlib
import json
import os

MAX_NODES = 200         # hard node ceiling per page
MAX_CHARS = 8192        # serialized-size ceiling per page (~8 KiB)
MAX_TOKENS = 25_000     # whole-response estimated-token ceiling
CHARS_PER_TOKEN = 4     # offline estimator; tiktoken ledger (R10) supersedes
SPILL_DIR = os.path.join(os.path.expanduser("~"),
                         ".agent-references", "graphify", "spills")


def _rtok(score):
    """Round scores to 6dp so cursor keysets compare stably."""
    return round(float(score), 6)


def _key(item):
    """Canonical sort key: score DESC, node_id ASC."""
    return (-_rtok(item.get("score", 0.0)), str(item.get("node_id", "")))


def _estimate_tokens(text):
    return max(1, len(text) // CHARS_PER_TOKEN)


def encode_cursor(score, node_id):
    """Opaque keyset cursor: base64url(JSON [score, node_id])."""
    raw = json.dumps([_rtok(score), str(node_id)], separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor):
    """Inverse of encode_cursor; raises ValueError on malformed input."""
    pad = "=" * (-len(cursor) % 4)
    score, node_id = json.loads(base64.urlsafe_b64decode(cursor + pad))
    return float(score), str(node_id)


def cap_results(items, max_nodes=MAX_NODES, max_chars=MAX_CHARS,
                max_tokens=MAX_TOKENS, cursor=None):
    """Page `items` under stacked node/char/token budgets.

    `items` are hit dicts carrying at least {"score", "node_id"}; they are
    (defensively) sorted by the canonical key first. Returns
    {items, truncated, total_estimate, next_cursor, hint}: total_estimate
    approximates tokens for the FULL uncapped set; when truncated, the page
    stops at the first exhausted budget and next_cursor resumes strictly
    after the last emitted hit. An oversized lone item is still admitted so a
    page never starves — spill it via artifact_spill instead.
    """
    ordered = sorted(items, key=_key)
    total_estimate = _estimate_tokens(json.dumps(ordered, default=str))

    start = 0
    if cursor:
        c_score, c_node = decode_cursor(cursor)
        while start < len(ordered) and _key(ordered[start]) <= (-c_score, c_node):
            start += 1

    page, used_chars, used_tokens = [], 0, 0
    i = start
    while i < len(ordered) and len(page) < max_nodes:
        chunk = json.dumps(ordered[i], default=str, separators=(",", ":"))
        cost_c, cost_t = len(chunk), _estimate_tokens(chunk)
        if page and used_chars + cost_c > max_chars:
            break
        if page and used_tokens + cost_t > max_tokens:
            break
        page.append(ordered[i])
        used_chars += cost_c
        used_tokens += cost_t
        i += 1

    truncated = i < len(ordered)
    if truncated:
        hint = (f"{len(ordered) - i} further hits beyond this page; "
                "re-call with cursor=next_cursor to continue")
        next_cursor = encode_cursor(page[-1].get("score", 0.0),
                                    page[-1].get("node_id", ""))
    else:
        hint, next_cursor = "", None
    return {"items": page, "truncated": truncated,
            "total_estimate": total_estimate, "next_cursor": next_cursor,
            "hint": hint}


def artifact_spill(payload, min_chars=MAX_CHARS):
    """Content-addressed spill for over-cap payloads.

    Writes ~/.agent-references/graphify/spills/<sha256>.json atomically and
    returns {spilled:True, ref, path, bytes, sha256}; sub-threshold payloads
    return {spilled:False, bytes} and are left untouched.
    """
    blob = json.dumps(payload, default=str, separators=(",", ":"),
                      sort_keys=True).encode()
    if len(blob) <= min_chars:
        return {"spilled": False, "bytes": len(blob)}
    digest = hashlib.sha256(blob).hexdigest()
    os.makedirs(SPILL_DIR, exist_ok=True)
    path = os.path.join(SPILL_DIR, f"{digest}.json")
    if not os.path.exists(path):
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "wb") as fh:
            fh.write(blob)
        os.replace(tmp, path)
    return {"spilled": True, "ref": digest, "path": path,
            "bytes": len(blob), "sha256": digest}


def gist_first_ordering(reranked):
    """Lost-in-the-Middle countermeasure.

    Sorts hits by the canonical key (score DESC, node_id ASC) so top evidence
    leads deterministically, then appends a 2-line aggregate gist as the FINAL
    element — the model meets the strongest evidence at both primacy and
    recency positions. Never mutates the input.
    """
    hits = sorted(reranked, key=_key)
    scores = sorted((_rtok(h.get("score", 0.0)) for h in hits), reverse=True)
    kinds = {}
    for h in hits:
        k = str(h.get("kind", "unknown"))
        kinds[k] = kinds.get(k, 0) + 1
    mix = ", ".join(f"{k}x{v}" for k, v in
                    sorted(kinds.items(), key=lambda kv: (-kv[1], kv[0])))
    if not mix:
        mix = ", ".join(str(h.get("node_id", "")) for h in hits[:3]) or "empty"
    mid = scores[len(scores) // 2] if scores else 0.0
    top = scores[0] if scores else 0.0
    gist = {"type": "gist",
            "text": f"gist: {len(hits)} hits | top {top:.3f} | median {mid:.3f}\n"
                    f"mix: {mix}"}
    return hits + [gist]
