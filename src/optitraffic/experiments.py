"""Run the experiments (PRD FR-10, Technical Design section 8).

    python -m optitraffic.experiments --config configs/experiments.yaml --stage all

Stages, in order:

    tune      adaptive parameters on the tuning seeds; writes the frozen config
    evaluate  every controller, scenario and evaluation seed (resumable)
    verify    repeat a few evaluation runs and compare their metrics
    solvers   solver comparison, tracks T1 to T3 (run with nothing else going on)
    figures   redraw the figures from the result tables
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from optitraffic.config import config_to_dict, load_config
from optitraffic.evaluation import analysis, plots, solver_study
from optitraffic.evaluation.metrics import TIMING_METRICS
from optitraffic.evaluation.runner import (
    ROOT,
    RunSpec,
    execute_run,
    read_record,
    run_batch,
    source_hash,
)
from optitraffic.evaluation.settings import ExperimentPlan, load_plan
from optitraffic.simulation.sumo_env import find_binary

STAGES = ("tune", "evaluate", "verify", "solvers", "figures")


def results_folder(plan: ExperimentPlan, root: Path) -> Path:
    return root / "results" / plan.experiment_id


# ------------------------------------------------------------------ tuning
def default_setting(plan: ExperimentPlan) -> tuple[float, float]:
    config = load_config(*plan.base_configs,
                         ROOT / "configs" / "scenarios" / f"{plan.scenarios[0]}.yaml")
    return (config.model.beta, config.estimation.window_s)


def setting_label(beta: float, window: float) -> str:
    return f"b{beta:g}_w{window:g}"


def tuning_specs(plan: ExperimentPlan) -> list[RunSpec]:
    default = default_setting(plan)
    betas = sorted({*map(float, plan.tuning["beta"]), default[0]})
    windows = sorted({*map(float, plan.tuning["window_s"]), default[1]})
    return [
        RunSpec(
            scenario, "adaptive", seed, setting_label(beta, window),
            (("model", "beta", beta), ("estimation", "window_s", window)),
        )
        for beta in betas
        for window in windows
        for scenario in plan.scenarios
        for seed in plan.tuning["seeds"]
    ]


def tune(plan: ExperimentPlan, root: Path) -> None:
    folder = results_folder(plan, root) / "tuning"
    records = run_batch(plan.base_configs, tuning_specs(plan), folder / "runs", plan.workers)
    runs = pd.DataFrame(records)
    runs.to_csv(folder / "runs.csv", index=False)
    default = default_setting(plan)
    table = analysis.tuning_table(runs, plan.evaluation["primary_metric"], default)
    table.to_csv(folder / "settings.csv", index=False)
    beta, window = analysis.choose_setting(table, default)
    score = float(table[(table["beta"] == beta) & (table["window_s"] == window)]["score"].iloc[0])
    header = (
        f"# Chosen by the tuning stage of experiment '{plan.experiment_id}' on seeds "
        f"{plan.tuning['seeds']}.\n# Score {score:.4f} relative to beta {default[0]:g}, window "
        f"{default[1]:g} s (lower is better).\n# Do not edit after evaluation runs exist.\n"
    )
    plan.frozen_config.write_text(
        header + yaml.safe_dump(
            {"model": {"beta": beta}, "estimation": {"window_s": window}}, sort_keys=False
        ),
        encoding="utf-8", newline="\n",
    )
    print(f"chosen: beta {beta:g}, window {window:g} s, score {score:.4f} "
          f"-> {plan.frozen_config}")


# -------------------------------------------------------------- evaluation
def final_configs(plan: ExperimentPlan) -> list[Path]:
    if not plan.frozen_config.is_file():
        raise SystemExit(f"{plan.frozen_config} is missing; run the tune stage first")
    return [*plan.base_configs, plan.frozen_config]


def evaluation_specs(plan: ExperimentPlan) -> list[RunSpec]:
    return [
        RunSpec(scenario, controller, seed)
        for scenario in plan.scenarios
        for seed in plan.evaluation["seeds"]
        for controller in plan.controllers
    ]


def evaluate(plan: ExperimentPlan, root: Path) -> None:
    folder = results_folder(plan, root)
    paths = final_configs(plan)
    save_provenance(plan, folder, paths)
    records = run_batch(paths, evaluation_specs(plan), folder / "evaluation", plan.workers)
    runs = pd.DataFrame(records)
    runs.to_csv(folder / "runs.csv", index=False)
    cycles = []
    for record in records:
        path = folder / "evaluation" / record["run_id"] / "cycles.csv"
        if path.is_file():
            table = pd.read_csv(path)
            for position, key in enumerate(("scenario", "controller", "seed")):
                table.insert(position, key, record[key])
            cycles.append(table)
    pd.concat(cycles, ignore_index=True).to_csv(folder / "cycles.csv", index=False)

    settings = plan.evaluation
    counts = analysis.counts_table(runs)
    counts.to_csv(folder / "counts.csv", index=False)
    analysis.means_table(runs, settings["metrics"], settings["confidence"]).to_csv(
        folder / "means.csv", index=False
    )
    analysis.paired_table(
        runs, settings["proposed"], settings["baselines"], settings["metrics"],
        settings["confidence"],
    ).to_csv(folder / "summary.csv", index=False)
    totals = runs["status"].value_counts().to_dict()
    print(f"evaluation runs by status: {totals}; tables in {folder}")


def verify(plan: ExperimentPlan, root: Path) -> None:
    """Repeat a random sample of evaluation runs; every metric but timing must match."""
    folder = results_folder(plan, root)
    paths = final_configs(plan)
    specs = evaluation_specs(plan)
    rng = np.random.default_rng(plan.verify["seed"])
    chosen = rng.choice(len(specs), size=min(plan.verify["runs"], len(specs)), replace=False)
    rows = []
    source = source_hash()
    for index in sorted(chosen):
        spec = specs[index]
        original = read_record(folder / "evaluation" / spec.run_id)
        if original is None:
            raise SystemExit(f"{spec.run_id} has not been run; run the evaluate stage first")
        repeat = execute_run(paths, spec, folder / "verify" / spec.run_id, source)
        ignored = {*TIMING_METRICS, "wall_s"}
        differing = sorted(
            k for k in set(original) | set(repeat)
            if k not in ignored and original.get(k) != repeat.get(k)
        )
        rows.append({
            "run_id": spec.run_id, "compared": len(set(original) - ignored),
            "reproduced": not differing, "differing": ";".join(differing),
        })
        print(f"  {spec.run_id}: {'reproduced' if not differing else 'DIFFERS: ' + str(differing)}")
    pd.DataFrame(rows).to_csv(folder / "verify.csv", index=False)
    if not all(r["reproduced"] for r in rows):
        raise SystemExit("some runs were not reproduced")


# ------------------------------------------------------------- solver study
def recorded_states(plan: ExperimentPlan, root: Path) -> list[solver_study.State]:
    """States seen by the adaptive controller, chosen setting, on tuning seeds."""
    config = load_config(*final_configs(plan),
                         ROOT / "configs" / "scenarios" / f"{plan.scenarios[0]}.yaml")
    label = setting_label(config.model.beta, config.estimation.window_s)
    runs = results_folder(plan, root) / "tuning" / "runs"
    states = []
    for spec in tuning_specs(plan):
        if spec.label != label:
            continue
        path = runs / spec.run_id / "cycles.csv"
        if not path.is_file():
            raise SystemExit(f"{path} is missing; run the tune stage first")
        table = pd.read_csv(path)
        table = table[table["valid"]]
        columns = table[["queue_ns", "queue_ew", "rate_ns", "rate_ew"]]
        states += [tuple(float(v) for v in row) for row in columns.itertuples(index=False)]
    return states


def solvers(plan: ExperimentPlan, root: Path) -> None:
    folder = results_folder(plan, root) / "solvers"
    folder.mkdir(parents=True, exist_ok=True)
    config = load_config(*final_configs(plan),
                         ROOT / "configs" / "scenarios" / f"{plan.scenarios[0]}.yaml")
    settings = plan.solver_study
    states = recorded_states(plan, root)
    pd.DataFrame(states, columns=["queue_ns", "queue_ew", "rate_ns", "rate_ew"]).to_csv(
        folder / "states.csv", index=False
    )
    print(f"T1: {len(states)} recorded states")
    t1 = solver_study.reduced_runs(states, config, settings)
    t1.to_csv(folder / "t1_runs.csv", index=False)
    solver_study.summarise(t1, ["problem", "solver"], {
        "error_s_median": ("error_s", "median"), "error_s_max": ("error_s", "max"),
        "gap_median": ("gap", "median"), "gap_max": ("gap", "max"),
        "integer_plan_optimal": ("integer_plan_optimal", "sum"),
    }).to_csv(folder / "t1_summary.csv", index=False)
    solver_study.convergence_curves(states, config, settings).to_csv(
        folder / "t1_curves.csv", index=False
    )
    print("T2: penalty form")
    t2, checks = solver_study.penalty_runs(states, config, settings)
    t2.to_csv(folder / "t2_runs.csv", index=False)
    checks.to_csv(folder / "t2_reference_checks.csv", index=False)
    solver_study.summarise(t2, ["rho", "solver"], {
        "gap_max": ("gap", "max"),
        "violation_s_median": ("violation_s", "median"),
        "violation_s_max": ("violation_s", "max"),
    }).to_csv(folder / "t2_summary.csv", index=False)
    print("T3: test functions")
    t3 = solver_study.benchmark_runs(settings)
    t3.to_csv(folder / "t3_runs.csv", index=False)
    solver_study.summarise(t3, ["problem", "n", "condition", "solver"], {
        "error_median": ("error", "median"), "error_max": ("error", "max"),
    }).to_csv(folder / "t3_summary.csv", index=False)
    if len(checks) and not checks["reference_ok"].all():
        raise SystemExit("a penalty reference solution is worse than the grid; see the checks")
    print(f"solver tables in {folder}")


# ------------------------------------------------------------------ figures
def figures(plan: ExperimentPlan, root: Path) -> None:
    folder = results_folder(plan, root)
    out = folder / "figures"
    out.mkdir(parents=True, exist_ok=True)
    primary = plan.evaluation["primary_metric"]
    made = []
    if (folder / "means.csv").is_file():
        means = pd.read_csv(folder / "means.csv")
        summary = pd.read_csv(folder / "summary.csv")
        for metric in (primary, "worst_approach_delay_s"):
            made.append(plots.controller_means(means, metric, out / f"means_{metric}.png"))
        made.append(plots.paired_differences(summary, primary, out / "paired_primary.png"))
    if (folder / "tuning" / "settings.csv").is_file():
        table = pd.read_csv(folder / "tuning" / "settings.csv")
        made.append(plots.sensitivity(table, out / "sensitivity.png"))
    if (folder / "solvers" / "t2_summary.csv").is_file():
        curves = pd.read_csv(folder / "solvers" / "t1_curves.csv")
        made.append(plots.convergence(curves, out / "t1_convergence.png"))
        t2 = pd.read_csv(folder / "solvers" / "t2_summary.csv")
        made.append(plots.conditioning(t2, out / "t2_conditioning.png"))
    print(f"{len(made)} figures in {out}")


# -------------------------------------------------------------- provenance
def save_provenance(plan: ExperimentPlan, folder: Path, paths: list[Path]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    resolved = {
        name: config_to_dict(load_config(*paths, ROOT / "configs" / "scenarios" / f"{name}.yaml"))
        for name in plan.scenarios
    }
    (folder / "config.yaml").write_text(
        yaml.safe_dump(
            {"experiment": yaml.safe_load(plan.source.read_text(encoding="utf-8")),
             "resolved": resolved}, sort_keys=False,
        ), encoding="utf-8",
    )
    environment = {
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "sumo": _command([find_binary("sumo"), "--version"]).splitlines()[:1],
        "packages": {
            name: version(name)
            for name in ("numpy", "pandas", "scipy", "matplotlib", "PyYAML", "traci", "sumolib")
        },
        "source_hash": source_hash(),
        "git_commit": _command(["git", "rev-parse", "HEAD"]).strip(),
        "git_uncommitted_files": _command(["git", "status", "--porcelain"]).splitlines(),
    }
    (folder / "environment.json").write_text(json.dumps(environment, indent=1), encoding="utf-8")


def _command(command: list[str]) -> str:
    try:
        return subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, timeout=60, check=True
        ).stdout
    except (OSError, subprocess.SubprocessError) as error:
        return f"unavailable: {type(error).__name__}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the OptiTraffic experiments.")
    parser.add_argument("--config", default=ROOT / "configs" / "experiments.yaml")
    parser.add_argument("--stage", choices=(*STAGES, "all"), required=True)
    parser.add_argument("--workers", type=int, help="override the number of parallel runs")
    args = parser.parse_args(argv)
    plan = load_plan(args.config, ROOT)
    if args.workers:
        object.__setattr__(plan, "workers", args.workers)
    functions = {"tune": tune, "evaluate": evaluate, "verify": verify,
                 "solvers": solvers, "figures": figures}
    for stage in STAGES if args.stage == "all" else (args.stage,):
        print(f"== {stage}", flush=True)
        functions[stage](plan, ROOT)
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
