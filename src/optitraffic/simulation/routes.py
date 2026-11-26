"""Reproducible vehicle demand (Technical Design section 4.2).

Every approach receives an independent Poisson process with explicit departure
times generated here, so all controllers see exactly the same vehicles for a
given scenario and seed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from optitraffic.types import NetworkParams, ScenarioParams, SimulationParams


@dataclass(frozen=True)
class Trip:
    vehicle_id: str
    depart_s: float
    origin: str
    destination: str


def generate_trips(
    scenario: ScenarioParams, network: NetworkParams, simulation: SimulationParams, seed: int
) -> list[Trip]:
    """Trips over [0, warm-up + duration), sorted by departure time."""
    starts = [0.0] + [
        simulation.warmup_s + s.start_fraction * simulation.duration_s
        for s in scenario.segments[1:]
    ]
    ends = starts[1:] + [simulation.end_s]
    movements = [(phase, m) for phase in (0, 1) for m in network.phase_movements[phase]]
    streams = np.random.SeedSequence(seed).spawn(len(movements))

    trips: list[Trip] = []
    for (phase, (origin, destination)), stream in zip(movements, streams):
        rng = np.random.default_rng(stream)
        count = 0
        for segment, start, end in zip(scenario.segments, starts, ends):
            rate = segment.arrival_rate[phase]
            if rate == 0:
                continue
            # Exponential gaps are memoryless, so each segment can start afresh.
            time = start + rng.exponential(1.0 / rate)
            while time < end:
                depart = round(time, 2)
                if depart < simulation.end_s:
                    trips.append(Trip(f"{origin}.{count}", depart, origin, destination))
                    count += 1
                time += rng.exponential(1.0 / rate)
    return sorted(trips, key=lambda t: (t.depart_s, t.vehicle_id))


def write_route_file(path: str | Path, trips: list[Trip]) -> None:
    """Write a SUMO route file; the same trips always give identical bytes."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<routes>",
        '    <vType id="car" vClass="passenger"/>',
    ]
    for trip in trips:
        lines.append(
            f'    <vehicle id="{trip.vehicle_id}" type="car" depart="{trip.depart_s:.2f}" '
            f'departLane="best" departSpeed="max">'
            f'<route edges="{trip.origin} {trip.destination}"/></vehicle>'
        )
    lines.append("</routes>")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
