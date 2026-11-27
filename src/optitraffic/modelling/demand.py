"""Sliding-window arrival-rate estimation (PRD FR-03, Technical Design 4.4).

    rate_i = N_i / dt

N_i is the number of arrivals on approach i in the last `dt` seconds, where dt
is the window length, or the elapsed time while the first window is filling.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Sequence
from numbers import Integral


class DemandEstimator:
    def __init__(
        self, approaches: int, window_s: float, min_elapsed_s: float, start_s: float = 0.0
    ) -> None:
        """No estimate is given until `min(min_elapsed_s, window_s)` has passed."""
        if approaches < 1:
            raise ValueError("approaches must be at least 1")
        for value, name in ((window_s, "window_s"), (min_elapsed_s, "min_elapsed_s")):
            if not (math.isfinite(value) and value > 0):
                raise ValueError(f"{name} must be finite and positive; got {value}")
        self.approaches = approaches
        self.window_s = float(window_s)
        self.min_elapsed_s = min(float(min_elapsed_s), self.window_s)
        self.reset(start_s)

    def reset(self, start_s: float) -> None:
        """Forget all history and start measuring at `start_s`."""
        if not math.isfinite(start_s):
            raise ValueError(f"start time must be finite; got {start_s}")
        self._start = self._latest = float(start_s)
        self._events: deque[tuple[float, tuple[int, ...]]] = deque()
        self._totals = [0] * self.approaches

    def record(self, time_s: float, arrivals: Sequence[int]) -> None:
        """Arrivals observed since the previous call, one count per approach."""
        self._check_time(time_s)
        counts = tuple(arrivals)
        if len(counts) != self.approaches or not all(
            isinstance(n, Integral) and n >= 0 for n in counts
        ):
            raise ValueError(f"need {self.approaches} non-negative integer counts; got {counts}")
        self._latest = float(time_s)
        if any(counts):
            self._events.append((self._latest, counts))
            self._totals = [total + n for total, n in zip(self._totals, counts)]
        self._discard_old(self._latest)

    def rates(self, time_s: float) -> tuple[float, ...] | None:
        """Arrival rates in veh/s over (time - dt, time], or None if not ready."""
        self._check_time(time_s)
        elapsed = float(time_s) - self._start
        if elapsed < self.min_elapsed_s:
            return None
        self._latest = float(time_s)
        self._discard_old(self._latest)
        duration = min(self.window_s, elapsed)
        return tuple(total / duration for total in self._totals)

    def _check_time(self, time_s: float) -> None:
        if not (math.isfinite(time_s) and time_s >= self._latest):
            raise ValueError(f"time must be finite and not go backwards; got {time_s}")

    def _discard_old(self, now: float) -> None:
        cutoff = now - self.window_s
        while self._events and self._events[0][0] <= cutoff:
            _, counts = self._events.popleft()
            self._totals = [total - n for total, n in zip(self._totals, counts)]
