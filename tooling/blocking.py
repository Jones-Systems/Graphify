"""R14 - recall-first multi-pass blocking + fuzzy verification.

Candidate generation unions four complementary passes (each targets a
different error model, per the blocking-survey doctrine that blocking
recall upper-bounds final ER recall):

  1. normalize           - lowercase, strip punctuation, collapse whitespace
  2. token-sort keys     - exact blocks, transposition-robust
  3. char-trigram inverted index - typo-robust; postings > BLOCK_CAP skipped
  4. sorted-neighborhood - window w=10 over the normalized sort order
  5. metaphone keys      - sound-alikes; jellyfish if importable, else skipped

Pairs are deduplicated into int32 L/R arrays and verified in one GIL-free
multicore sweep: rapidfuzz.process.cpdist with
JaroWinkler.normalized_similarity. Pairs scoring >= JW_CUTOFF (0.85) are
accepted outright; the borderline 0.80-0.85 band gets an Indel second
opinion and survives only when Indel >= INDEL_CUTOFF (0.80).

The sweep runs at the band floor so the borderline cohort stays observable;
the 0.85 acceptance gate is applied exactly, in numpy.

Skew discipline: count_comparisons_before_run previews per-pass volume
BEFORE running (Splink doctrine) and every block/posting larger than
BLOCK_CAP is skipped rather than exploded.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence

import numpy as np
from rapidfuzz import process
from rapidfuzz.distance import Indel, JaroWinkler

try:  # optional phonetic pass - degrade gracefully when absent
    from jellyfish import metaphone as _metaphone
except ImportError:  # pragma: no cover
    _metaphone = None

BLOCK_CAP = 500      # max members per block / posting list (skew guard)
SNM_WINDOW = 10      # sorted-neighborhood window
JW_CUTOFF = 0.85     # primary acceptance gate
BAND_LOW = 0.80      # lower edge of the second-opinion band
INDEL_CUTOFF = 0.80  # second-opinion acceptance gate

_PUNCT = re.compile(r"[^\w\s]+")
_WS = re.compile(r"\s+")


def normalize(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    return _WS.sub(" ", _PUNCT.sub(" ", name.lower())).strip()


def _token_sort_key(norm: str) -> str:
    return " ".join(sorted(norm.split()))


def _trigrams(norm: str) -> set[str]:
    return {norm[i : i + 3] for i in range(max(0, len(norm) - 2))}


def _index_pairs(index: dict[str, list[int]]):
    """Yield within-block index pairs, skipping empty/oversized blocks."""
    for members in index.values():
        if len(members) < 2 or len(members) > BLOCK_CAP:
            continue
        members.sort()
        for a in range(len(members) - 1):
            for b in range(a + 1, len(members)):
                yield members[a], members[b]


def _passes(norms: list[str]):
    """Union of all blocking passes as raw (i, j) index pairs."""
    n = len(norms)

    tok: dict[str, list[int]] = defaultdict(list)
    tri: dict[str, list[int]] = defaultdict(list)
    pho: dict[str, list[int]] = defaultdict(list)
    for i, s in enumerate(norms):
        tok[_token_sort_key(s)].append(i)
        for g in _trigrams(s):
            tri[g].append(i)
        if _metaphone is not None:
            pho[_metaphone(s)].append(i)

    yield from _index_pairs(tok)
    yield from _index_pairs(tri)
    if _metaphone is not None:
        yield from _index_pairs(pho)

    order = sorted(range(n), key=norms.__getitem__)  # SNM pass, w=10
    for pos in range(n):
        for j in range(pos + 1, min(pos + 1 + SNM_WINDOW, n)):
            yield order[pos], order[j]


def count_comparisons_before_run(names: Sequence[str]) -> dict[str, int]:
    """Preview per-pass comparison volume BEFORE running (skew doctrine).

    Blocks/postings above BLOCK_CAP contribute 0 because they are skipped.
    The trigram figure counts shared-gram postings pre-dedup, so it is an
    upper bound on that pass's generated comparisons.
    """
    norms = [normalize(s) for s in names]
    n = len(norms)

    def keyed_volume(key_of) -> int:
        d: dict[str, int] = defaultdict(int)
        for s in norms:
            k = key_of(s)
            if k:
                d[k] += 1
        return sum(c * (c - 1) // 2 for c in d.values() if 2 <= c <= BLOCK_CAP)

    post: dict[str, int] = defaultdict(int)
    for s in norms:
        for g in _trigrams(s):
            post[g] += 1
    trigram = sum(c * (c - 1) // 2 for c in post.values() if 2 <= c <= BLOCK_CAP)

    snm = sum(min(SNM_WINDOW, n - pos - 1) for pos in range(n - 1))
    metaphone = keyed_volume(_metaphone) if _metaphone is not None else 0

    out = {
        "token_sort": keyed_volume(_token_sort_key),
        "trigram": trigram,
        "sorted_neighborhood": snm,
        "metaphone": metaphone,
    }
    out["total"] = sum(out.values())
    return out


def blocked_pairs(names: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
    """Deduplicated candidate pairs as int32 (L, R) arrays with L < R."""
    norms = [normalize(s) for s in names]
    n = max(len(norms), 1)
    seen: set[int] = set()
    left: list[int] = []
    right: list[int] = []
    for a, b in _passes(norms):
        if a == b:
            continue
        lo, hi = (a, b) if a < b else (b, a)
        key = lo * n + hi
        if key not in seen:
            seen.add(key)
            left.append(lo)
            right.append(hi)
    if not left:
        return np.empty(0, np.int32), np.empty(0, np.int32)
    return np.asarray(left, np.int32), np.asarray(right, np.int32)


def candidates(names: Sequence[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Verified near-duplicate pairs.

    Returns (L, R, scores): int32 index arrays into ``names`` with L < R,
    and float64 JaroWinkler normalized similarities for the kept pairs
    (>= JW_CUTOFF, plus band-rescued pairs whose Indel >= INDEL_CUTOFF).
    """
    L, R = blocked_pairs(names)
    if L.size == 0:
        return L, R, np.empty(0, np.float64)

    left = [names[i] for i in L]
    right = [names[i] for i in R]
    jw = np.asarray(
        process.cpdist(
            left,
            right,
            scorer=JaroWinkler.normalized_similarity,
            score_cutoff=BAND_LOW,  # zero out hopeless pairs cheaply
            workers=-1,
        ),
        dtype=np.float64,
    )

    strong = jw >= JW_CUTOFF
    band = (jw >= BAND_LOW) & ~strong
    if band.any():
        bidx = np.flatnonzero(band)
        indel = np.asarray(
            process.cpdist(
                [left[i] for i in bidx],
                [right[i] for i in bidx],
                scorer=Indel.normalized_similarity,
                workers=-1,
            ),
            dtype=np.float64,
        )
        strong[bidx[indel >= INDEL_CUTOFF]] = True

    keep = np.flatnonzero(strong)
    order = np.lexsort((R[keep], L[keep]))  # canonical (L, R) ordering
    sel = keep[order]
    return L[sel], R[sel], jw[sel]
