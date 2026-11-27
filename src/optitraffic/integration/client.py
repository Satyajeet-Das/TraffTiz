"""The only place that starts, steps and closes a SUMO simulation."""

from __future__ import annotations

import uuid
from collections.abc import Sequence


class TraciClient:
    """Context manager around one TraCI connection.

    >>> with TraciClient(command) as sim:
    ...     sim.step()
    ...     sim.api.simulation.getTime()
    """

    def __init__(self, command: Sequence[str]) -> None:
        self.command = list(command)
        self.api = None

    def __enter__(self) -> TraciClient:
        import traci

        label = uuid.uuid4().hex
        traci.start(self.command, label=label)
        self.api = traci.getConnection(label)
        return self

    def step(self) -> None:
        self.api.simulationStep()

    @property
    def time(self) -> float:
        return self.api.simulation.getTime()

    def __exit__(self, *exc_info) -> None:
        if self.api is None:
            return
        try:
            self.api.close()
        finally:
            self.api = None
