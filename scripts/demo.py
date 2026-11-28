"""Demonstration: the same traffic under two signal controllers in sumo-gui.

    python scripts/demo.py                       # fixed equal split, then the corrected adaptive controller
    python scripts/demo.py --scenario changing --controllers actuated adaptive_own_green
    python scripts/demo.py --headless            # no windows, numbers only

Each controller opens its own sumo-gui window; the next starts when the previous
run ends (close the window to move on sooner). Both see the identical vehicles.
The printed numbers come from this single run, not from the experiments.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from optitraffic.config import load_config
from optitraffic.control.controllers import make_controller
from optitraffic.run import simulate

ROOT = Path(__file__).resolve().parents[1]
# name -> (controller, configuration overlays, overrides)
CHOICES = {
    "fixed_equal": ("fixed_equal", (), {}),
    "fixed_calibrated": ("fixed_calibrated", (), {}),
    "queue_proportional": ("queue_proportional", (), {}),
    "actuated": ("actuated", ("frozen_m9b_actuated.yaml",), {}),
    "adaptive": ("adaptive", ("frozen.yaml",), {}),
    "adaptive_own_green": (
        "adaptive", ("frozen_m9b_adaptive_own_green.yaml",),
        {"estimation": {"queue_sampling": "own_green"}},
    ),
}


def demo_config(name: str, scenario: str):
    """The settings used in the experiments for this choice."""
    _, overlays, overrides = CHOICES[name]
    paths = [ROOT / "configs" / "default.yaml"]
    paths += [ROOT / "configs" / f for f in overlays if (ROOT / "configs" / f).is_file()]
    missing = [f for f in overlays if not (ROOT / "configs" / f).is_file()]
    if missing:
        print(f"note: {', '.join(missing)} not found; {name} uses default settings")
    paths.append(ROOT / "configs" / "scenarios" / f"{scenario}.yaml")
    return load_config(*paths, overrides=overrides or None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenario", default="changing")
    parser.add_argument("--controllers", nargs="+", choices=sorted(CHOICES),
                        default=["fixed_equal", "adaptive_own_green"])
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--headless", action="store_true", help="no sumo-gui windows")
    args = parser.parse_args(argv)

    results = []
    for name in args.controllers:
        config = demo_config(name, args.scenario)
        halting = [0, 0]  # vehicle-steps spent halted, steps

        def watch(sim, stage, edges=tuple(
            o for phase in config.network.phase_movements for o, _ in phase
        )):
            halting[0] += sum(sim.api.edge.getLastStepHaltingNumber(e) for e in edges)
            halting[1] += 1

        print(f"running {name} on {args.scenario}, seed {args.seed} ...", flush=True)
        controller = make_controller(CHOICES[name][0], config, args.seed)
        folder = ROOT / "results" / "demo" / f"{args.scenario}_{name}_seed{args.seed}"
        result = simulate(config, controller, args.seed, folder,
                          gui=not args.headless, on_step=watch)
        stopped = result.end_time_s < config.simulation.end_s
        results.append((name, result, halting[0] / max(halting[1], 1), stopped))

    print(f"\n{'controller':22} {'avg halted veh':>14} {'left':>6} {'safe':>5}")
    for name, result, queue, stopped in results:
        note = "  (stopped early)" if stopped else ""
        print(f"{name:22} {queue:14.1f} {result.arrived:6d} "
              f"{'yes' if result.valid else 'NO':>5}{note}")
    return 0 if all(r.valid for _, r, _, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
