"""Reduce approach measurements to one value per phase (design decision D3).

The approaches of a phase move together, so a phase is represented by its
critical approach: the one with the largest expected queue q + rate * C.
"""

from __future__ import annotations

from collections.abc import Sequence


def critical_approach(
    queues: Sequence[float], rates: Sequence[float], cycle_s: float
) -> tuple[float, float]:
    """(queue, arrival rate) of the critical approach; ties go to the first."""
    if not queues or len(queues) != len(rates):
        raise ValueError("need the same non-zero number of queues and rates")
    index = max(range(len(queues)), key=lambda i: (queues[i] + rates[i] * cycle_s, -i))
    return (queues[index], rates[index])
