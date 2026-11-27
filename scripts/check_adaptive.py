"""Check the adaptive controller in full simulation runs (milestone M8).

Run:  python scripts/check_adaptive.py [--seed 1]        (takes a few minutes)

Part 1 runs every scenario with the configured solver. Part 2 runs one scenario
with each solver. It reports run validity, fallbacks and decision times, not
traffic performance, which is milestone M9. Exits non-zero if a run is invalid
or a fallback has no reason. Decision times depend on the machine.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
from collections import Counter
from dataclasses import replace
from pathlib import Path

from optitraffic.config import load_config
from optitraffic.control.controllers import make_controller
from optitraffic.control.validator import FALLBACK
from optitraffic.run import RunResult, simulate
from optitraffic.types import SOLVER_NAMES

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ("low", "medium", "high", "ns_dominant", "ew_dominant", "changing")
SOLVER_SCENARIO = "changing"


def run(scenario: str, solver: str | None, seed: int, folder: Path) -> RunResult:
    config = load_config(ROOT / "configs" / "default.yaml",
                         ROOT / "configs" / "scenarios" / f"{scenario}.yaml")
    if solver:
        config = replace(config, solver=replace(config.solver, name=solver))
    return simulate(config, make_controller("adaptive", config, seed), seed,
                    folder / f"{scenario}_{config.solver.name}")


def report(label: str, result: RunResult) -> bool:
    decided = [c for c in result.cycles if c.plan.solver is not None]
    times = [1000 * c.decision_s for c in decided]
    statuses = Counter(c.plan.solver.status for c in decided)
    summary = ", ".join(f"{name} {count}" for name, count in sorted(statuses.items()))
    print(f"  {label:<20}{'yes' if result.valid else 'NO':>6}{len(result.cycles):>7}"
          f"{result.fallbacks:>10}{statistics.median(times):>10.1f}{max(times):>9.1f}   {summary}")
    explained = True
    for cycle in result.cycles:
        if cycle.plan.source == FALLBACK:
            print(f"      fallback at t = {cycle.start_s:.0f} s: {cycle.plan.reason or 'NO REASON'}")
            explained = explained and bool(cycle.plan.reason)
    return result.valid and explained


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the adaptive controller in SUMO.")
    parser.add_argument("--seed", type=int, default=1, help="use a tuning seed (1-5)")
    seed = parser.parse_args().seed
    heading = (f"  {'':<20}{'valid':>6}{'cycles':>7}{'fallbacks':>10}{'median ms':>10}"
               f"{'max ms':>9}   solver status")
    passed = True
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        print(f"Every scenario, configured solver, seed {seed}\n{heading}")
        for scenario in SCENARIOS:
            passed &= report(scenario, run(scenario, None, seed, folder))
        print(f"\nEvery solver on '{SOLVER_SCENARIO}', seed {seed}\n{heading}")
        for solver in SOLVER_NAMES:
            passed &= report(solver, run(SOLVER_SCENARIO, solver, seed, folder))
    print("\nPASS" if passed else "\nFAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
