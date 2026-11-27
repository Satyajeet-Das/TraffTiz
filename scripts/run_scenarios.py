"""Run the intersection under an equal-split fixed-time signal.

Examples:
    python scripts/run_scenarios.py                          # all scenarios, 3 seeds
    python scripts/run_scenarios.py --scenario medium --gui  # watch one in sumo-gui

Exit status is non-zero if any run has a collision or teleport.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from optitraffic.config import load_config
from optitraffic.simulation.fixed_run import run_fixed

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ("low", "medium", "high", "ns_dominant", "ew_dominant", "changing")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenario", choices=SCENARIOS, action="append")
    parser.add_argument("--seed", type=int, action="append")
    parser.add_argument("--gui", action="store_true", help="show the run in sumo-gui")
    args = parser.parse_args()

    print(f"{'scenario':>12}{'seed':>5}{'sched':>7}{'entered':>8}{'left':>6}{'waiting':>8}"
          f"{'maxQ NS':>8}{'maxQ EW':>8}{'coll':>5}{'tele':>5}")
    valid = True
    for name in args.scenario or SCENARIOS:
        config = load_config(ROOT / "configs" / "default.yaml",
                             ROOT / "configs" / "scenarios" / f"{name}.yaml")
        for seed in args.seed or (1, 2, 3):
            folder = ROOT / "sumo" / "generated" / f"{name}_seed{seed}"
            r = run_fixed(config, seed, folder, gui=args.gui)
            valid &= r.valid
            print(f"{name:>12}{seed:>5}{r.scheduled:>7}{r.departed:>8}{r.arrived:>6}"
                  f"{r.still_waiting_to_enter:>8}{r.max_halting[0]:>8}{r.max_halting[1]:>8}"
                  f"{r.collisions:>5}{r.teleports:>5}")
    print("all runs valid" if valid else "INVALID runs present")
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
