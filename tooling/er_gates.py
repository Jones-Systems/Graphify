"""R15 - promotion gates without ground truth (B6/L28).

Three gates protect every threshold change (Splink config, GLiNER theta,
quantization downgrades):

  * auto_merge_tier           - the Wilson95 lower bound on observed
                                precision must reach 0.99 before
                                auto-merges are allowed to ship.
  * paired_cluster_bootstrap  - paired delta-F1 confidence interval over
                                CLUSTERS (B resamples); a change is
                                rejected when the CI lower bound falls
                                below -0.005.
  * stratified_clerical_sample- deterministic band-stratified clerical
                                review plan (default 150 items/band).

Pure stdlib + numpy.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np

Z95 = 1.96
AUTO_MERGE_PRECISION_LB = 0.99
BOOTSTRAP_RESAMPLES = 1000
REJECT_DELTA_F1_LB = -0.005
CLERICAL_N_PER_BAND = 150


def wilson_lb(p: float, n: int, z: float = Z95) -> float:
    """Wilson score interval LOWER bound for a binomial proportion."""
    if n <= 0:
        return 0.0
    p = min(1.0, max(0.0, float(p)))
    denom = 1.0 + z * z / n
    center = p + z * z / (2.0 * n)
    margin = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return (center - margin) / denom


def auto_merge_tier(precision_samples: Sequence[float], z: float = Z95) -> bool:
    """True iff the Wilson95 lower bound on precision reaches 0.99.

    ``precision_samples`` are per-decision outcomes (1.0 correct / 0.0
    wrong; fractional values are averaged into a Bernoulli-style rate).
    """
    arr = np.asarray(list(precision_samples), dtype=np.float64)
    if arr.size == 0:
        return False
    return wilson_lb(float(arr.mean()), int(arr.size), z) >= AUTO_MERGE_PRECISION_LB


def paired_cluster_bootstrap(
    delta_f1: Sequence[float],
    *,
    B: int = BOOTSTRAP_RESAMPLES,
    seed: int | None = 0,
) -> dict[str, float | bool]:
    """Percentile bootstrap CI for mean paired delta-F1 over clusters.

    Resamples clusters (not decisions) B times; ``reject`` is True when
    the 95% CI lower bound drops below REJECT_DELTA_F1_LB (-0.005).
    """
    arr = np.asarray(list(delta_f1), dtype=np.float64)
    if arr.size == 0:
        return {"lower": 0.0, "upper": 0.0, "mean": 0.0, "reject": False}
    rng = np.random.default_rng(seed)
    draws = arr[rng.integers(0, arr.size, size=(B, arr.size))].mean(axis=1)
    lower, upper = (float(x) for x in np.percentile(draws, [2.5, 97.5]))
    return {
        "lower": lower,
        "upper": upper,
        "mean": float(arr.mean()),
        "reject": bool(lower < REJECT_DELTA_F1_LB),
    }


def stratified_clerical_sample(
    bands: Mapping[str, Sequence],
    n_per_band: int = CLERICAL_N_PER_BAND,
) -> dict:
    """Emit a deterministic clerical-review plan: n_per_band items per band.

    Selection is systematic (evenly spaced strides over each band in given
    order), so plans are reproducible and span the full band including its
    edges. Bands smaller than n_per_band are taken whole.
    """
    out_bands: dict[str, dict] = {}
    total_avail = 0
    total_review = 0
    for band, items in bands.items():
        pool = list(items)
        k = min(n_per_band, len(pool))
        if 0 < k < len(pool):
            stride = len(pool) / k
            picked = [pool[min(len(pool) - 1, int(i * stride))] for i in range(k)]
        else:
            picked = pool[:]
        out_bands[band] = {
            "n_available": len(pool),
            "n_to_review": k,
            "items": picked,
        }
        total_avail += len(pool)
        total_review += k
    return {
        "bands": out_bands,
        "total_available": total_avail,
        "total_to_review": total_review,
    }
