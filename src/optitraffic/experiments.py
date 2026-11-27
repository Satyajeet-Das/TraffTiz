"""Run the experiments (PRD FR-10, Technical Design section 8).

    python -m optitraffic.experiments --config configs/experiments_m9b.yaml --stage all

Stages, in order:

    tune      each tunable variant on the tuning seeds; writes its settings file
    evaluate  every variant, scenario and evaluation seed (resumable)
    verify    repeat a few evaluation runs and compare their metrics
    solvers   solver comparison, tracks T1 to T3, if the plan includes it
              (run with nothing else going on)
    figures   redraw the figures from the result tables
"""

from __future__ import annotations

import argparse
import datetime
import itertools
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
    run_config,
    source_hash,
)
from optitraffic.evaluation.settings import ExperimentPlan, Variant, load_plan
from optitraffic.simulation.sumo_env import find_binary

STAGES = ("tune", "evaluate", "verify", "solvers", "figures")


def results_folder(plan: ExperimentPlan, root: Path) -> Path:
    return root / "results" / plan.experiment_id


# ------------------------------------------------------------------ tuning
def setting_label(keys: list[str], values: tuple[float, ...]) -> str:
    return "_".join(f"{key}{value:g}" for key, value in zip(keys, values))


def tuned_variants(plan: ExperimentPlan) -> list[Variant]:
    return [v for v in plan.variants.values() if v.tune]


def default_setting(plan: ExperimentPlan, variant: Variant) -> tuple[float, ...]:
    """The tuned keys' values before tuning: base configs plus the variant's overrides."""
    spec = variant_spec(variant, plan.scenarios[0], 0, tuned=False)
    config = run_config(plan.base_configs, spec)
    return tuple(float(getattr(getattr(config, s), k)) for s, k, _ in variant.tune)


def variant_spec(
    variant: Variant,
    scenario: str,
    seed: int,
    label: str = "",
    extra: tuple[tuple[str, str, object], ...] = (),
    tuned: bool = True,
) -> RunSpec:
    """`tuned` merges the variant's settings file; tuning runs leave it out."""
    settings = (variant.settings,) if tuned and variant.settings else ()
    return RunSpec(
        scenario, variant.controller, seed, label, (*variant.overrides, *extra),
        variant.name, settings,
    )


def tuning_grid(plan: ExperimentPlan, variant: Variant) -> list[tuple[float, ...]]:
    """Every combination of the grids, each extended by the default value."""
    default = default_setting(plan, variant)
    axes = [sorted({*grid, value}) for (_, _, grid), value in zip(variant.tune, default)]
    return list(itertools.product(*axes))


def tuning_specs(plan: ExperimentPlan, variant: Variant) -> list[RunSpec]:
    keys = [key for _, key, _ in variant.tune]
    return [
        variant_spec(
            variant, scenario, seed, setting_label(keys, values),
            tuple((s, k, v) for (s, k, _), v in zip(variant.tune, values)), tuned=False,
        )
        for values in tuning_grid(plan, variant)
        for scenario in plan.scenarios
        for seed in plan.tuning["seeds"]
    ]


def tune(plan: ExperimentPlan, root: Path) -> None:
    for variant in tuned_variants(plan):
        folder = results_folder(plan, root) / "tuning" / variant.name
        specs = tuning_specs(plan, variant)
        print(f"tuning {variant.name}", flush=True)
        records = run_batch(plan.base_configs, specs, folder / "runs", plan.workers)
        keys = [key for _, key, _ in variant.tune]
        runs = pd.DataFrame(records)
        for position, (_, key, _) in enumerate(variant.tune):
            runs[key] = [
                dict(((s, k), v) for s, k, v in spec.overrides)[variant.tune[position][:2]]
                for spec in specs
            ]
        runs.to_csv(folder / "runs.csv", index=False)
        default = default_setting(plan, variant)
        table = analysis.tuning_table(runs, plan.evaluation["primary_metric"], keys, default)
        table.to_csv(folder / "settings.csv", index=False)
        chosen = analysis.choose_setting(table, keys, default)
        row = table
        for key, value in zip(keys, chosen):
            row = row[row[key] == value]
        score = float(row["score"].iloc[0])
        overlay: dict[str, dict[str, float]] = {}
        for (section, key, _), value in zip(variant.tune, chosen):
            overlay.setdefault(section, {})[key] = value
        described = ", ".join(f"{k} {v:g}" for k, v in zip(keys, default))
        header = (
            f"# Chosen for variant '{variant.name}' by the tuning stage of experiment "
            f"'{plan.experiment_id}'\n# on seeds {plan.tuning['seeds']}. Score {score:.4f} "
            f"relative to {described} (lower is better).\n"
            "# Do not edit after evaluation runs exist.\n"
        )
        variant.settings.write_text(
            header + yaml.safe_dump(overlay, sort_keys=False), encoding="utf-8", newline="\n"
        )
        picked = ", ".join(f"{k} {v:g}" for k, v in zip(keys, chosen))
        print(f"chosen: {picked}, score {score:.4f} -> {variant.settings}", flush=True)


# -------------------------------------------------------------- evaluation
def check_settings(plan: ExperimentPlan) -> None:
    for name in plan.controllers:
        settings = plan.variants[name].settings
        if settings and not settings.is_file():
            raise SystemExit(f"{settings} is missing; run the tune stage first")


def evaluation_specs(plan: ExperimentPlan) -> list[RunSpec]:
    return [
        variant_spec(plan.variants[name], scenario, seed)
        for scenario in plan.scenarios
        for seed in plan.evaluation["seeds"]
        for name in plan.controllers
    ]


def evaluate(plan: ExperimentPlan, root: Path) -> None:
    folder = results_folder(plan, root)
    check_settings(plan)
    save_provenance(plan, folder)
    records = run_batch(
        plan.base_configs, evaluation_specs(plan), folder / "evaluation", plan.workers
    )
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
    check_settings(plan)
    paths = plan.base_configs
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
    """States seen by the study's variant at its chosen setting, on tuning seeds."""
    variant = plan.variants[plan.solver_study["variant"]]
    config = run_config(plan.base_configs, variant_spec(variant, plan.scenarios[0], 0))
    chosen = [float(getattr(getattr(config, s), k)) for s, k, _ in variant.tune]
    label = setting_label([key for _, key, _ in variant.tune], tuple(chosen))
    runs = results_folder(plan, root) / "tuning" / variant.name / "runs"
    states = []
    for spec in tuning_specs(plan, variant):
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
    if plan.solver_study is None:
        print("no solver study in this plan; skipped")
        return
    check_settings(plan)
    folder = results_folder(plan, root) / "solvers"
    folder.mkdir(parents=True, exist_ok=True)
    variant = plan.variants[plan.solver_study["variant"]]
    config = run_config(plan.base_configs, variant_spec(variant, plan.scenarios[0], 0))
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
    proposed = plan.evaluation["proposed"]
    made = []
    if (folder / "means.csv").is_file():
        means = pd.read_csv(folder / "means.csv")
        summary = pd.read_csv(folder / "summary.csv")
        for metric in (primary, "worst_approach_delay_s"):
            made.append(plots.controller_means(
                means, metric, out / f"means_{metric}.png", plan.labels, proposed))
        made.append(plots.paired_differences(
            summary, primary, out / "paired_primary.png", plan.labels, proposed))
    for variant in tuned_variants(plan):
        path = folder / "tuning" / variant.name / "settings.csv"
        if not path.is_file() or len(variant.tune) != 2:
            continue
        keys = [key for _, key, _ in variant.tune]
        made.append(plots.sensitivity(
            pd.read_csv(path), out / f"sensitivity_{variant.name}.png", keys[0], keys[1],
            variant.label, dict(zip(keys, default_setting(plan, variant))),
        ))
    if (folder / "solvers" / "t2_summary.csv").is_file():
        curves = pd.read_csv(folder / "solvers" / "t1_curves.csv")
        made.append(plots.convergence(curves, out / "t1_convergence.png"))
        t2 = pd.read_csv(folder / "solvers" / "t2_summary.csv")
        made.append(plots.conditioning(t2, out / "t2_conditioning.png"))
    print(f"{len(made)} figures in {out}")


# -------------------------------------------------------------- provenance
def save_provenance(plan: ExperimentPlan, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    resolved = {
        name: {
            scenario: config_to_dict(run_config(
                plan.base_configs, variant_spec(plan.variants[name], scenario, 0)))
            for scenario in plan.scenarios
        }
        for name in plan.controllers
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
    parser.add_argument("--config", default=ROOT / "configs" / "experiments_m9b.yaml")
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
