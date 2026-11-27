"""Tables built from run records: tuning choice, means and paired statistics."""

from __future__ import annotations

import math
from collections.abc import Sequence

import pandas as pd

from optitraffic.evaluation.statistics import holm, mean_interval, paired_comparison

LOWER_IS_BETTER = {"throughput_veh": False}  # every other compared metric: lower is better


def tuning_table(runs: pd.DataFrame, metric: str, default: tuple[float, float]) -> pd.DataFrame:
    """One row per (beta, window): per-scenario mean and a relative score.

    The score is the geometric mean over scenarios of mean / mean at the default
    setting, so scenarios with large delays do not dominate. A setting with any
    run that is not "done" has no score and cannot be chosen.
    """
    keys = ["beta", "window_s"]
    done = runs[runs["status"] == "done"]
    means = done.pivot_table(index=keys, columns="scenario", values=metric, aggfunc="mean")
    complete = runs.groupby(keys)["status"].agg(lambda s: bool((s == "done").all()))
    if default not in means.index or not complete.loc[default]:
        raise ValueError(f"the default setting {default} has no complete set of runs")
    reference = means.loc[default]
    scores = {}
    for setting, row in means.iterrows():
        if complete.loc[setting] and row.notna().all():
            ratios = row / reference
            scores[setting] = math.exp(sum(math.log(r) for r in ratios) / len(ratios))
    table = means.copy()
    table["score"] = pd.Series(scores, dtype=float)
    table["complete"] = complete
    return table.reset_index().sort_values("score", na_position="last", kind="stable")


def choose_setting(table: pd.DataFrame, default: tuple[float, float]) -> tuple[float, float]:
    """Smallest score; the default wins ties."""
    scored = table.dropna(subset=["score"])
    best = scored["score"].min()
    tied = scored[scored["score"] <= best + 1e-12]
    for _, row in tied.iterrows():
        if (row["beta"], row["window_s"]) == default:
            return default
    first = tied.iloc[0]
    return (float(first["beta"]), float(first["window_s"]))


def means_table(runs: pd.DataFrame, metrics: Sequence[str], confidence: float) -> pd.DataFrame:
    rows = []
    done = runs[runs["status"] == "done"]
    for (scenario, controller), group in done.groupby(["scenario", "controller"], sort=False):
        for metric in metrics:
            interval = mean_interval(group[metric].to_numpy(), confidence)
            rows.append({
                "scenario": scenario, "controller": controller, "metric": metric,
                "n": interval.n, "mean": interval.mean,
                "ci_low": interval.low, "ci_high": interval.high,
            })
    return pd.DataFrame(rows)


def paired_table(
    runs: pd.DataFrame,
    proposed: str,
    baselines: Sequence[str],
    metrics: Sequence[str],
    confidence: float,
) -> pd.DataFrame:
    """Proposed minus each baseline, per scenario, paired by seed.

    A seed is used only if both runs are "done"; `n_dropped` counts the others.
    Holm correction is applied within each metric over all comparisons.
    """
    rows = []
    for metric in metrics:
        family = []
        for scenario in runs["scenario"].unique():
            part = runs[runs["scenario"] == scenario]
            ours = part[part["controller"] == proposed].set_index("seed")
            for baseline in baselines:
                theirs = part[part["controller"] == baseline].set_index("seed")
                seeds = sorted(set(ours.index) | set(theirs.index))
                both = [
                    s for s in seeds
                    if s in ours.index and s in theirs.index
                    and ours.at[s, "status"] == "done" and theirs.at[s, "status"] == "done"
                ]
                if len(both) < 2:
                    raise ValueError(f"too few valid pairs for {scenario} against {baseline}")
                result = paired_comparison(
                    ours.loc[both, metric], theirs.loc[both, metric], confidence
                )
                lower = LOWER_IS_BETTER.get(metric, True)
                family.append({
                    "metric": metric, "scenario": scenario, "baseline": baseline,
                    "n_pairs": len(both), "n_dropped": len(seeds) - len(both),
                    "mean_proposed": result.mean_proposed,
                    "mean_baseline": result.mean_baseline,
                    "mean_difference": result.difference.mean,
                    "ci_low": result.difference.low, "ci_high": result.difference.high,
                    "percent": result.percent, "p_value": result.p_value,
                    "seeds_better": result.better if lower else result.worse,
                    "seeds_worse": result.worse if lower else result.better,
                })
        adjusted = holm([row["p_value"] for row in family])
        for row, p in zip(family, adjusted):
            row["p_holm"] = p
            row["verdict"] = _verdict(row, p, 1 - confidence)
        rows.extend(family)
    return pd.DataFrame(rows)


def _verdict(row: dict, p: float, alpha: float) -> str:
    """Whether the proposed controller is better, worse or not clearly different."""
    if not p < alpha or row["mean_difference"] == 0:
        return "no clear difference"
    lower = LOWER_IS_BETTER.get(row["metric"], True)
    return "better" if (row["mean_difference"] < 0) == lower else "worse"


def counts_table(runs: pd.DataFrame) -> pd.DataFrame:
    """Every run accounted for, with fallback and incident totals."""
    grouped = runs.groupby(["scenario", "controller"], sort=False)
    table = grouped.agg(
        runs=("status", "size"),
        done=("status", lambda s: int((s == "done").sum())),
        invalid=("status", lambda s: int((s == "invalid").sum())),
        failed=("status", lambda s: int((s == "failed").sum())),
        collisions=("collisions", "sum"),
        teleports=("teleports", "sum"),
        cycles=("cycles", "sum"),
        fallbacks=("fallbacks", "sum"),
        fallbacks_whole_run=("fallbacks_whole_run", "sum"),
        rejected_plans=("rejected_plans", "sum"),
        infeasible_applied=("infeasible_applied", "sum"),
        solver_calls=("solver_calls", "sum"),
        solver_converged=("solver_converged", "sum"),
        solver_max_ms=("solver_max_ms", "max"),
        unfinished_on_road=("unfinished_on_road", "mean"),
        never_entered=("never_entered", "mean"),
    )
    return table.reset_index()
