"""Per-step queue measurements for evaluation (PRD FR-10).

Separate from the state collector: controllers sample queues once per cycle,
while evaluation needs every step of the measured period.
"""

from __future__ import annotations

from collections.abc import Sequence


class QueueMonitor:
    """Halting vehicles per approach, and vehicles waiting to enter, in (start_s, end_s]."""

    def __init__(self, edges: Sequence[str], start_s: float, end_s: float) -> None:
        self.edges = tuple(edges)
        self.start_s, self.end_s = start_s, end_s
        self.steps = 0
        self._total = dict.fromkeys(self.edges, 0)
        self._largest = dict.fromkeys(self.edges, 0)
        self._pending_total = 0
        self._pending_largest = 0

    def observe(self, api, time_s: float) -> None:
        """Call once after every simulation step."""
        if not self.start_s < time_s <= self.end_s:
            return
        self.steps += 1
        for edge in self.edges:
            halting = api.edge.getLastStepHaltingNumber(edge)
            self._total[edge] += halting
            self._largest[edge] = max(self._largest[edge], halting)
        pending = len(api.simulation.getPendingVehicles())
        self._pending_total += pending
        self._pending_largest = max(self._pending_largest, pending)

    def summary(self) -> dict[str, float]:
        """`avg_queue_veh` is the time average of the total over all approaches;
        `max_queue_veh` the largest value on any one approach."""
        if self.steps == 0:
            raise ValueError("no steps were observed in the measured period")
        result: dict[str, float] = {
            "avg_queue_veh": sum(self._total.values()) / self.steps,
            "max_queue_veh": max(self._largest.values()),
            "avg_pending_veh": self._pending_total / self.steps,
            "max_pending_veh": self._pending_largest,
        }
        for edge in self.edges:
            result[f"avg_queue_{edge}"] = self._total[edge] / self.steps
            result[f"max_queue_{edge}"] = self._largest[edge]
        return result
