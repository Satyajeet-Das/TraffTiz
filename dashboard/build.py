"""Build the results dashboard: one self-contained HTML file, no server needed.

    python dashboard/build.py                 # every finished experiment in results/
    python dashboard/build.py m9 m9b --open

It only reads the result tables written by `optitraffic.experiments`. It sits
outside `src/` so that changing it does not change the code fingerprint of the
experiments.
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = Path(__file__).with_name("template.html")
PLACEHOLDER = "/*DATA*/null"

SCENARIOS = ("low", "medium", "high", "ns_dominant", "ew_dominant", "changing")
DEFAULT_LABELS = {  # for plans written before controllers had labels
    "fixed_equal": "Fixed equal", "fixed_calibrated": "Fixed calibrated",
    "queue_proportional": "Queue-proportional", "adaptive": "Adaptive",
}
TABLES = ("means.csv", "summary.csv", "counts.csv", "cycles.csv", "config.yaml")


def is_finished(folder: Path) -> bool:
    return all((folder / name).is_file() for name in TABLES)


def load_experiment(folder: Path) -> dict:
    """Everything the page needs about one evaluated experiment."""
    if not is_finished(folder):
        missing = [name for name in TABLES if not (folder / name).is_file()]
        raise FileNotFoundError(f"{folder} has no finished evaluation; missing {missing}")
    resolved = yaml.safe_load((folder / "config.yaml").read_text(encoding="utf-8"))
    plan = resolved["experiment"]
    evaluation = plan["evaluation"]
    names = [*evaluation["baselines"], evaluation["proposed"]]
    variants = plan.get("variants", {})
    labels = {
        name: variants.get(name, {}).get("label", DEFAULT_LABELS.get(name, name))
        for name in names
    }
    means = pd.read_csv(folder / "means.csv")
    summary = pd.read_csv(folder / "summary.csv")
    counts = pd.read_csv(folder / "counts.csv")
    scenarios = [s for s in SCENARIOS if s in set(means["scenario"])]
    scenarios += sorted(set(means["scenario"]) - set(scenarios))

    # A default configuration of any one run gives the measured period.
    first = next(iter(next(iter(resolved["resolved"].values())).values()))
    # Plans without variants saved one configuration per scenario.
    simulation = first.get("simulation") or next(iter(resolved["resolved"].values()))["simulation"]

    data = {
        "id": plan["experiment_id"],
        "proposed": evaluation["proposed"],
        "primary": evaluation["primary_metric"],
        "controllers": names,
        "labels": labels,
        "scenarios": scenarios,
        "seeds": evaluation["seeds"],
        "metrics": evaluation["metrics"],
        "warmup_s": simulation["warmup_s"],
        "means": _records(means, ["scenario", "controller", "metric", "n", "mean",
                                  "ci_low", "ci_high"]),
        "paired": _records(summary, ["scenario", "baseline", "metric", "mean_difference",
                                     "ci_low", "ci_high", "p_holm", "verdict", "n_pairs"]),
        "counts": _records(counts, ["scenario", "controller", "runs", "done", "invalid",
                                    "failed", "collisions", "teleports", "fallbacks",
                                    "infeasible_applied"]),
        "runs": _runs(folder),
        "verify": None,
    }
    if (folder / "verify.csv").is_file():
        verify = pd.read_csv(folder / "verify.csv")
        data["verify"] = {"checked": len(verify), "reproduced": int(verify["reproduced"].sum())}
    return data


def _records(table: pd.DataFrame, columns: list[str]) -> list[dict]:
    """Rows as dictionaries, with missing values as None."""
    part = table[columns].astype(object)
    return part.where(part.notna(), None).to_dict("records")


def _runs(folder: Path) -> dict[str, dict]:
    """Per run, keyed "scenario|controller|seed": one row per signal cycle.

    Controller runs give [start s, NS queue, EW queue, NS green, EW green,
    fallback]; the actuated signal records only greens, so its queues are None.
    """
    runs: dict[str, dict] = {}
    cycles = pd.read_csv(folder / "cycles.csv")
    for (scenario, controller, seed), group in cycles.groupby(
        ["scenario", "controller", "seed"], sort=False
    ):
        rows = [
            [float(r.start_s),
             round(float(r.queue_ns), 1) if r.valid else None,
             round(float(r.queue_ew), 1) if r.valid else None,
             int(r.green_ns), int(r.green_ew), int(r.source == "fallback")]
            for r in group.itertuples(index=False)
        ]
        runs[f"{scenario}|{controller}|{seed}"] = {"kind": "planned", "rows": rows}

    table = pd.read_csv(folder / "runs.csv")
    lost = _green_lost(folder)
    for record in table.itertuples(index=False):
        path = folder / "evaluation" / record.run_id / "greens.csv"
        if path.is_file():
            runs[f"{record.scenario}|{record.controller}|{record.seed}"] = {
                "kind": "actuated", "rows": _actuated_rows(pd.read_csv(path), lost)
            }
    return runs


def _green_lost(folder: Path) -> int:
    """Seconds by which a displayed green exceeds the effective green."""
    resolved = yaml.safe_load((folder / "config.yaml").read_text(encoding="utf-8"))["resolved"]
    node = next(iter(resolved.values()))
    if "signal" not in node:
        node = next(iter(node.values()))
    return int(node["signal"]["green_lost_s"])


def _actuated_rows(greens: pd.DataFrame, lost: int) -> list[list]:
    """Pair each NS green with the EW green that follows it, as effective greens."""
    rows: list[list] = []
    for green in greens.itertuples(index=False):
        effective = float(green.displayed_s) - lost
        if green.phase == "NS":
            rows.append([float(green.start_s), None, None, effective, None, 0])
        elif rows and rows[-1][4] is None:
            rows[-1][4] = effective
    return rows


def render(experiments: list[dict]) -> str:
    if not experiments:
        raise ValueError("there is no finished experiment to show")
    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count(PLACEHOLDER) != 1:
        raise ValueError("the template must contain the data placeholder exactly once")
    payload = json.dumps(experiments, separators=(",", ":"), allow_nan=False)
    # Keep the data from closing the surrounding <script> element.
    return template.replace(PLACEHOLDER, payload.replace("</", "<\\/"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the OptiTraffic results dashboard.")
    parser.add_argument("experiments", nargs="*", help="experiment ids (default: all finished)")
    parser.add_argument("--results", type=Path, default=ROOT / "results")
    parser.add_argument("--out", type=Path, help="default: <results>/dashboard.html")
    parser.add_argument("--open", action="store_true", help="open it in the browser")
    args = parser.parse_args(argv)
    if args.experiments:
        folders = [args.results / name for name in args.experiments]
    else:
        folders = sorted(f for f in args.results.glob("*") if is_finished(f))
    try:
        page = render([load_experiment(f) for f in folders])
    except (FileNotFoundError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    out = args.out or args.results / "dashboard.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8", newline="\n")
    print(f"dashboard with {', '.join(f.name for f in folders)}: {out} "
          f"({out.stat().st_size / 1e6:.1f} MB)")
    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
