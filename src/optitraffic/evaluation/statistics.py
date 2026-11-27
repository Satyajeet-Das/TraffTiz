"""Paired comparison statistics (Technical Design section 8.2).

SciPy is used here for the t quantile and the Wilcoxon signed-rank test only.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy import stats


@dataclass(frozen=True)
class Interval:
    n: int
    mean: float
    low: float | None  # None with fewer than two values
    high: float | None


@dataclass(frozen=True)
class PairedResult:
    difference: Interval  # proposed minus baseline
    mean_proposed: float
    mean_baseline: float
    percent: float | None  # difference relative to the baseline mean
    p_value: float | None  # two-sided Wilcoxon signed-rank
    better: int  # pairs where proposed is lower
    worse: int


def mean_interval(values: Sequence[float], confidence: float = 0.95) -> Interval:
    """Mean with a Student t confidence interval."""
    data = np.asarray(values, dtype=float)
    if data.ndim != 1 or data.size == 0 or not np.all(np.isfinite(data)):
        raise ValueError("values must be a non-empty list of finite numbers")
    mean = float(data.mean())
    if data.size < 2:
        return Interval(data.size, mean, None, None)
    half = float(stats.t.ppf(0.5 + confidence / 2, data.size - 1)
                 * data.std(ddof=1) / math.sqrt(data.size))
    return Interval(data.size, mean, mean - half, mean + half)


def paired_comparison(
    proposed: Sequence[float], baseline: Sequence[float], confidence: float = 0.95
) -> PairedResult:
    """Compare values paired by position (same scenario and seed)."""
    a, b = np.asarray(proposed, dtype=float), np.asarray(baseline, dtype=float)
    if a.shape != b.shape:
        raise ValueError("paired samples must have the same length")
    difference = a - b
    interval = mean_interval(difference, confidence)
    if difference.size < 2:
        p_value = None
    elif np.all(difference == 0):
        p_value = 1.0  # the test is undefined when every pair is tied
    else:
        p_value = float(stats.wilcoxon(a, b).pvalue)
    base = float(b.mean())
    return PairedResult(
        difference=interval,
        mean_proposed=float(a.mean()),
        mean_baseline=base,
        percent=None if base == 0 else 100.0 * interval.mean / base,
        p_value=p_value,
        better=int(np.sum(difference < 0)),
        worse=int(np.sum(difference > 0)),
    )


def holm(p_values: Sequence[float]) -> list[float]:
    """Holm step-down adjusted p-values, in the given order."""
    values = [float(p) for p in p_values]
    if not all(0 <= p <= 1 for p in values):
        raise ValueError("p-values must lie in [0, 1]")
    order = sorted(range(len(values)), key=values.__getitem__)
    adjusted = [0.0] * len(values)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (len(values) - rank) * values[index]))
        adjusted[index] = running
    return adjusted
