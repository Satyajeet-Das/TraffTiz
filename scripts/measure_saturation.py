"""Measure the saturation flow of one approach in SUMO (design decision D6).

The NS approaches are flooded with traffic so a queue is waiting at every green.
For several green durations, the vehicles crossing the stop line per cycle are
counted. A straight-line fit  vehicles = rate * green + intercept  gives

    saturation flow  s = 3600 * rate                      (veh/h)
    effective green  = displayed green + intercept / rate (tests decision D4)

Run:  python scripts/measure_saturation.py
"""

from __future__ import annotations

import sys
import tempfile
from dataclasses import replace
from pathlib import Path

import numpy as np

from optitraffic.config import load_config
from optitraffic.simulation.fixed_run import run_fixed
from optitraffic.types import DemandSegment, ScenarioParams

ROOT = Path(__file__).resolve().parents[1]
GREENS = (15, 25, 35, 45, 55)
SEEDS = (1, 2, 3, 4, 5)
CYCLE_S = 150
SATURATING_RATE = 0.8  # veh/s per approach, far above capacity
SKIP_CYCLES = 3  # let the queue build up first


def discharge_counts(green: int, seed: int) -> list[int]:
    """Vehicles leaving N_in in each cycle in which all of them had queued."""
    config = load_config(ROOT / "configs" / "default.yaml")
    other = CYCLE_S - 10 - green
    config = replace(
        config,
        # green_lost_s=0: the measurement is in terms of displayed green.
        signal=replace(config.signal, cycle_s=CYCLE_S, g_min_s=10, g_max_s=130, green_lost_s=0),
        scenario=ScenarioParams("saturated", (DemandSegment(0.0, (SATURATING_RATE, 0.0)),)),
        simulation=replace(config.simulation, warmup_s=0.0, duration_s=float(CYCLE_S * 15)),
    )
    previous: set[str] = set()
    halted: set[str] = set()
    cycles: dict[int, list[bool]] = {}

    def record(sim) -> None:
        nonlocal previous
        edge = sim.api.edge
        current = set(edge.getLastStepVehicleIDs("N_in"))
        halted.update(v for v in current if sim.api.vehicle.getSpeed(v) < 0.1)
        # The program starts with NS green at t = 0.
        cycle = int((sim.time - config.simulation.step_length_s) // CYCLE_S)
        for vehicle in previous - current:
            cycles.setdefault(cycle, []).append(vehicle in halted)
        previous = current

    with tempfile.TemporaryDirectory() as folder:
        summary = run_fixed(config, seed, folder, green=(green, other), on_step=record)
    if not summary.valid:
        raise RuntimeError(f"invalid run (green={green}, seed={seed})")
    return [len(flags) for cycle, flags in sorted(cycles.items())
            if cycle >= SKIP_CYCLES and all(flags)]


def main() -> int:
    greens, counts = [], []
    print(f"{'green s':>8}{'cycles':>8}{'mean vehicles':>15}")
    for green in GREENS:
        sample = [n for seed in SEEDS for n in discharge_counts(green, seed)]
        if not sample:
            print(f"{green:>8}   no fully queued cycle", file=sys.stderr)
            continue
        greens += [green] * len(sample)
        counts += sample
        print(f"{green:>8}{len(sample):>8}{np.mean(sample):>15.2f}")
    rate, intercept = np.polyfit(greens, counts, 1)
    residual = np.array(counts) - (rate * np.array(greens) + intercept)
    print(f"\nfit: vehicles = {rate:.4f} * green + {intercept:.3f}   "
          f"(residual std {residual.std():.2f} veh)")
    print(f"saturation flow: {3600 * rate:.0f} veh/h per lane")
    print(f"effective green - displayed green: {intercept / rate:+.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
