"""How much of the second experiment's improvement is the queue measurement?

    python scripts/ablation.py          # 240 extra runs; uses results/m9b/

The corrected adaptive controller differs from the original in two ways: when it
reads the queues, and its tuned settings (beta, window). This completes the 2x2
design on the same evaluation traffic by running the two missing combinations:

    cycle start, beta 1.6, window  90 s   in m9b ("adaptive")
    own green,   beta 0,   window 360 s   in m9b ("adaptive_own_green")
    own green,   beta 1.6, window  90 s   added here
    cycle start, beta 0,   window 360 s   added here

This is a follow-up analysis made after the results were known. Nothing is tuned
or selected with it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from optitraffic.evaluation.runner import RunSpec, run_batch
from optitraffic.evaluation.settings import load_plan
from optitraffic.evaluation.statistics import holm, paired_comparison

ROOT = Path(__file__).resolve().parents[1]
METRIC = "avg_total_wait_s"
SETTINGS = {"old": (1.6, 90.0), "new": (0.0, 360.0)}
# name -> (queue sampling, settings); existing names are variants of the m9b plan
CELLS = {
    "adaptive": ("cycle_start", "old"),
    "adaptive_own_green": ("own_green", "new"),
    "own_green_old_settings": ("own_green", "old"),
    "cycle_start_new_settings": ("cycle_start", "new"),
}
ADDED = ("own_green_old_settings", "cycle_start_new_settings")


def specs(plan) -> list[RunSpec]:
    result = []
    for name in ADDED:
        sampling, settings = CELLS[name]
        beta, window = SETTINGS[settings]
        overrides = (
            ("estimation", "queue_sampling", sampling),
            ("estimation", "window_s", window),
            ("model", "beta", beta),
        )
        result += [
            RunSpec(scenario, "adaptive", seed, overrides=overrides, variant=name)
            for scenario in plan.scenarios
            for seed in plan.evaluation["seeds"]
        ]
    return result


def main() -> int:
    plan = load_plan(ROOT / "configs" / "experiments_m9b.yaml", ROOT)
    main_runs = ROOT / "results" / "m9b" / "runs.csv"
    if not main_runs.is_file():
        print("run the m9b experiment first", file=sys.stderr)
        return 1
    folder = ROOT / "results" / "m9b" / "ablation"
    added = pd.DataFrame(
        run_batch(plan.base_configs, specs(plan), folder / "runs", plan.workers)
    )
    original = pd.read_csv(main_runs)
    runs = pd.concat([original[original["controller"].isin(CELLS)], added], ignore_index=True)
    if not (runs["status"] == "done").all():
        print("some runs did not finish", file=sys.stderr)
        return 1
    wait = runs.pivot_table(index=["scenario", "seed"], columns="controller", values=METRIC)

    # The change split into steps, each measured on identical traffic.
    comparisons = {
        "measurement, at old settings": ("own_green_old_settings", "adaptive"),
        "measurement, at new settings": ("adaptive_own_green", "cycle_start_new_settings"),
        "settings, at cycle start": ("cycle_start_new_settings", "adaptive"),
        "settings, at own green": ("adaptive_own_green", "own_green_old_settings"),
        "both together": ("adaptive_own_green", "adaptive"),
    }
    rows = []
    for label, (after, before) in comparisons.items():
        for scenario in plan.scenarios:
            part = wait.loc[scenario]
            result = paired_comparison(part[after], part[before])
            rows.append({
                "comparison": label, "scenario": scenario, "n": result.difference.n,
                "mean_before": result.mean_baseline, "mean_after": result.mean_proposed,
                "mean_difference": result.difference.mean,
                "ci_low": result.difference.low, "ci_high": result.difference.high,
                "p_value": result.p_value,
            })
    table = pd.DataFrame(rows)
    table["p_holm"] = holm(list(table["p_value"]))
    table.to_csv(folder / "summary.csv", index=False)
    runs.to_csv(folder / "runs.csv", index=False)

    means = runs.pivot_table(index="scenario", columns="controller", values=METRIC)
    means = means.loc[list(plan.scenarios), list(CELLS)]
    means.to_csv(folder / "means.csv")
    print(means.round(1).to_string())
    print()
    print(table.pivot(index="scenario", columns="comparison", values="mean_difference")
          .loc[list(plan.scenarios), list(comparisons)].round(2).to_string())
    late = sum(
        bool((pd.read_csv(f)["status"] == "time_budget").any())
        for f in (folder / "runs").glob("*/cycles.csv")
    )
    print(f"\nadded runs that hit the decision time limit: {late} of {len(added)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
