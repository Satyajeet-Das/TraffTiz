"""Reproduce one headline result of the second experiment from scratch.

    python scripts/reproduce_headline.py          # 40 runs, a few minutes

In high demand, reading each queue just before its own green lowers the adaptive
controller's mean waiting from about 35.6 s to 24.6 s (docs/M9B_RESULTS.md).
This reruns those 40 evaluation runs into results/reproduce/ and compares the
means with the published ones in docs/m9b/means.csv. Runs already there are
reused; delete the folder to start again.

A decision has 0.1 s of wall-clock time, so on a busy computer a run can differ.
Runs in which that limit was hit are reported and repeated one at a time.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from optitraffic.evaluation.runner import run_batch
from optitraffic.evaluation.settings import load_plan
from optitraffic.experiments import check_settings, evaluation_specs

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = "high"
VARIANTS = ("adaptive", "adaptive_own_green")
METRIC = "avg_total_wait_s"
TOLERANCE_S = 1e-6
ATTEMPTS = 3


def main() -> int:
    plan = load_plan(ROOT / "configs" / "experiments_m9b.yaml", ROOT)
    check_settings(plan)
    specs = [s for s in evaluation_specs(plan) if s.scenario == SCENARIO and s.name in VARIANTS]
    folder = ROOT / "results" / "reproduce"
    records = run_batch(plan.base_configs, specs, folder, plan.workers)
    for _ in range(ATTEMPTS - 1):
        late = [s.run_id for s in specs if timed_out(folder / s.run_id)]
        if not late:
            break
        print(f"{len(late)} run(s) hit the decision time limit; repeating: {', '.join(late)}")
        for run_id in late:
            (folder / run_id / "metrics.json").unlink()
        records = run_batch(plan.base_configs, specs, folder, workers=1)
    runs = pd.DataFrame(records)
    if not (runs["status"] == "done").all():
        print("some runs did not finish; see results/reproduce/", file=sys.stderr)
        return 1
    published = pd.read_csv(ROOT / "docs" / "m9b" / "means.csv")
    published = published[
        (published["scenario"] == SCENARIO) & (published["metric"] == METRIC)
    ].set_index("controller")["mean"]

    print(f"\nWaiting per vehicle in {SCENARIO} demand, mean over {len(specs) // 2} seeds (s)")
    print(f"{'controller':22}{'published':>11}{'reproduced':>12}")
    matched = True
    for name in VARIANTS:
        mean = runs.loc[runs["controller"] == name, METRIC].mean()
        print(f"{name:22}{published[name]:11.3f}{mean:12.3f}")
        matched &= abs(mean - published[name]) <= TOLERANCE_S
    if matched:
        print("reproduced exactly")
        return 0
    late = [s.run_id for s in specs if timed_out(folder / s.run_id)]
    cause = (f"{len(late)} run(s) still hit the time limit; close other programs and repeat."
             if late else "No run hit the time limit, so the code, settings or software differ.")
    print(f"DIFFERENT. {cause}", file=sys.stderr)
    return 1


def timed_out(run_folder: Path) -> bool:
    log = run_folder / "cycles.csv"
    return log.is_file() and bool((pd.read_csv(log)["status"] == "time_budget").any())


if __name__ == "__main__":
    sys.exit(main())
