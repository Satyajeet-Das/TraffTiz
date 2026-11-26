"""Timing constraints and projection (PRD section 6.5, Technical Design section 5.4).

    g_NS + g_EW = G,    g_min <= g_i <= g_max

With g = g_NS and g_EW = G - g these reduce to g in [lower, upper].
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike


def feasible_interval(g_min: float, g_max: float, budget: float) -> tuple[float, float]:
    """Feasible range of g_NS; raises ValueError if no plan exists."""
    lower, upper = max(g_min, budget - g_max), min(g_max, budget - g_min)
    if not lower <= upper:  # also catches NaN
        raise ValueError(f"no feasible plan for g_min={g_min}, g_max={g_max}, budget={budget}")
    return (lower, upper)


def project_interval(x: ArrayLike, lower: float, upper: float):
    """Nearest point of [lower, upper]. Accepts a number or an array."""
    values = np.asarray(x, dtype=float)
    if np.any(np.isnan(values)):
        raise ValueError("cannot project NaN")
    result = np.clip(values, lower, upper)
    return float(result) if result.ndim == 0 else result


def split_green(g_ns: float, budget: float) -> np.ndarray:
    """Full plan (NS, EW) from the reduced variable."""
    return np.array([g_ns, budget - g_ns], dtype=float)


def is_feasible(
    green: ArrayLike, g_min: float, g_max: float, budget: float, tolerance: float = 1e-9
) -> bool:
    g = np.asarray(green, dtype=float)
    return bool(
        g.shape == (2,)
        and np.all(np.isfinite(g))
        and np.all(g >= g_min - tolerance)
        and np.all(g <= g_max + tolerance)
        and abs(g.sum() - budget) <= tolerance
    )
