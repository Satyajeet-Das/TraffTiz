"""Compare estimated arrival rates with the generated demand (M4 exit check).

At every cycle boundary the estimate for each approach is compared with
  - the vehicles scheduled to depart in the same window (the exact demand), and
  - the scenario's underlying rate (which differs by Poisson sampling noise).

Run:  python scripts/check_estimates.py
Signals use the fixed equal split, which overloads the dominant scenarios.
"""

from __future__ import annotations

import math
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

import numpy as np

from optitraffic.config import load_config
from optitraffic.integration.state_collector import StateCollector
from optitraffic.simulation.fixed_run import run_fixed
from optitraffic.simulation.routes import generate_trips
from optitraffic.types import Config

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ("low", "medium", "high", "ns_dominant", "ew_dominant", "changing")
SEEDS = (1, 2, 3)


def collect(config: Config, seed: int) -> list:
    """TrafficState at every cycle boundary of one fixed-time run."""
    states, holder = [], {}

    def on_step(sim) -> None:
        if "collector" not in holder:
            holder["collector"] = StateCollector(sim.api, config)
        holder["collector"].observe()
        if sim.time % config.signal.cycle_s == 0:
            states.append(holder["collector"].read())

    with tempfile.TemporaryDirectory() as folder:
        summary = run_fixed(config, seed, folder, on_step=on_step)
    if not summary.valid:
        raise RuntimeError(f"invalid run: {summary}")
    return states


def errors(config: Config, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """(estimate - scheduled demand, estimate - scenario rate) over valid states.

    SUMO inserts a vehicle in the step that starts at or after its departure time
    and it is visible when that step ends, at ceil(depart / step) * step + step.
    The scheduled demand of a window is counted at those visible times.
    """
    trips = generate_trips(config.scenario, config.network, config.simulation, seed)
    step = config.simulation.step_length_s
    departures = {}
    for trip in trips:
        visible = math.ceil(trip.depart_s / step) * step + step
        departures.setdefault(trip.origin, []).append(visible)
    phase_of = {o: p for p, ms in enumerate(config.network.phase_movements) for o, _ in ms}
    sim = config.simulation
    switches = [sim.warmup_s + s.start_fraction * sim.duration_s
                for s in config.scenario.segments[1:]]

    against_trips, against_rate = [], []
    for state in collect(config, seed):
        if not state.valid:
            continue
        window = min(config.estimation.window_s, state.sim_time)
        start = state.sim_time - window
        segment = sum(state.sim_time > s for s in switches)
        steady = not any(start < s < state.sim_time for s in switches)
        for approach in state.approaches:
            times = np.array(departures.get(approach.edge, []))
            demand = np.sum((times > start) & (times <= state.sim_time)) / window
            against_trips.append(approach.arrival_rate - demand)
            if steady:
                rate = config.scenario.segments[segment].arrival_rate[phase_of[approach.edge]]
                against_rate.append(approach.arrival_rate - rate)
    return np.array(against_trips), np.array(against_rate)


def main() -> int:
    base = load_config(ROOT / "configs" / "default.yaml")
    print("Arrival-rate error in veh/s, all approaches, seeds " + ", ".join(map(str, SEEDS)))
    print(f"{'scenario':>12}{'waiting':>9}{'vs demand: mean':>17}{'max abs':>9}"
          f"{'vs rate: mean':>15}{'rms':>8}")
    for name in SCENARIOS:
        config = load_config(ROOT / "configs" / "default.yaml",
                             ROOT / "configs" / "scenarios" / f"{name}.yaml")
        for include in (True, False):
            variant = replace(config, estimation=replace(base.estimation, include_pending=include))
            results = [errors(variant, seed) for seed in SEEDS]
            demand = np.concatenate([r[0] for r in results])
            rate = np.concatenate([r[1] for r in results])
            print(f"{name:>12}{'counted' if include else 'ignored':>9}{demand.mean():>17.4f}"
                  f"{np.abs(demand).max():>9.4f}{rate.mean():>15.4f}"
                  f"{np.sqrt(np.mean(rate ** 2)):>8.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
