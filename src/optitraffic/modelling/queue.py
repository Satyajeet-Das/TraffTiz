"""Cycle-level queue prediction (PRD FR-04, Technical Design section 5.1).

`green` holds effective green times in seconds with shape (..., 2) in (NS, EW)
order, so many candidate plans can be evaluated at once.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike

from optitraffic.types import ObjectiveData


def raw_queue(data: ObjectiveData, green: ArrayLike) -> np.ndarray:
    """a = q + lambda*C - mu*g in vehicles. Negative means unused green."""
    g = np.asarray(green, dtype=float)
    if g.ndim == 0 or g.shape[-1] != 2 or not np.all(np.isfinite(g)):
        raise ValueError(f"green needs finite values with shape (..., 2); got {g}")
    return (
        np.array(data.queue)
        + np.array(data.arrival_rate) * data.cycle_s
        - np.array(data.discharge_rate_vps) * g
    )


def predict_queue(data: ObjectiveData, green: ArrayLike) -> np.ndarray:
    """Predicted residual queue Q = max(0, a) in vehicles."""
    return np.maximum(0.0, raw_queue(data, green))
