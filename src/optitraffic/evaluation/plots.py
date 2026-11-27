"""Report figures, drawn from the result tables (PNG, light background).

Most figures are small multiples in one hue, so identity comes from titles and
axis labels. Only the sensitivity figure uses three series colours (validated
as colour-blind safe for all pairs); it also varies the marker shape. Every
plotted number is also in the CSV file the figure is made from.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # draw to files only

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

INK, MUTED, GRID = "#191919", "#666666", "#e6e6e6"
ACCENT, BASE = "#257de0", "#8c8c8c"
SERIES = ("#257de0", "#f47230", "#00b894")
MARKERS = ("o", "s", "^")
SCENARIOS = {
    "low": "Low", "medium": "Medium", "high": "High",
    "ns_dominant": "NS dominant", "ew_dominant": "EW dominant", "changing": "Changing",
}
SOLVERS = {
    "gradient_descent": "Gradient descent", "projected_gradient": "Projected gradient",
    "momentum": "Momentum", "newton": "Newton", "bfgs": "BFGS",
    "conjugate_gradient": "Conjugate gradient", "subgradient": "Subgradient",
}
NAMES = {
    "beta": "β", "window_s": "window (s)", "max_gap_s": "max gap (s)",
    "detector_gap_s": "detector gap (s)",
}
METRIC_LABELS = {
    "avg_total_wait_s": "Waiting per vehicle, including waiting to enter (s)",
    "worst_approach_delay_s": "Delay per vehicle on the worst approach (s)",
}


def _style() -> None:
    plt.rcParams.update({
        "font.size": 9, "text.color": INK, "axes.labelcolor": INK,
        "axes.edgecolor": GRID, "xtick.color": MUTED, "ytick.color": MUTED,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
        "axes.axisbelow": True, "axes.titlesize": 10, "axes.titlelocation": "left",
        "figure.facecolor": "white", "savefig.dpi": 200,
    })


def _save(figure, path: Path) -> Path:
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)
    return path


def controller_means(
    means: pd.DataFrame, metric: str, path: Path, labels: Mapping[str, str], proposed: str
) -> Path:
    """One panel per scenario: mean and 95% interval for each controller.

    `labels` gives the controllers in drawing order; `proposed` is highlighted.
    """
    _style()
    data = means[means["metric"] == metric]
    scenarios = [s for s in SCENARIOS if s in set(data["scenario"])]
    order = [c for c in labels if c in set(data["controller"])]
    figure, axes = plt.subplots(
        2, 3, figsize=(10, 2.2 + 0.42 * len(order)), sharey=True, layout="constrained"
    )
    for axis, scenario in zip(axes.flat, scenarios):
        part = data[data["scenario"] == scenario].set_index("controller")
        for row, controller in enumerate(order):
            if controller not in part.index:
                continue
            item = part.loc[controller]
            colour = ACCENT if controller == proposed else BASE
            axis.errorbar(
                item["mean"], row, xerr=[[item["mean"] - item["ci_low"]],
                                         [item["ci_high"] - item["mean"]]],
                fmt="o", color=colour, markersize=6, elinewidth=2, capsize=3,
            )
            axis.annotate(f"{item['mean']:.1f}", (item["ci_high"], row), xytext=(5, 0),
                          textcoords="offset points", va="center", color=MUTED, fontsize=8)
        axis.set_title(SCENARIOS[scenario])
        axis.set_xlim(left=0, right=float(part["ci_high"].max()) * 1.22)
        axis.set_yticks(range(len(order)), [labels[c] for c in order])
        axis.set_ylim(len(order) - 0.5, -0.5)
        axis.grid(axis="y", visible=False)
    figure.supxlabel(METRIC_LABELS.get(metric, metric) + ", mean and 95% interval; lower is better",
                     fontsize=9)
    return _save(figure, path)


def paired_differences(
    summary: pd.DataFrame, metric: str, path: Path, labels: Mapping[str, str], proposed: str
) -> Path:
    """Proposed minus each baseline, per scenario, with 95% intervals."""
    _style()
    data = summary[summary["metric"] == metric]
    baselines = [c for c in labels if c in set(data["baseline"])]
    scenarios = [s for s in SCENARIOS if s in set(data["scenario"])]
    columns = min(3, len(baselines))
    rows = -(-len(baselines) // columns)
    figure, axes = plt.subplots(
        rows, columns, figsize=(10, 0.8 + 2.4 * rows), sharey=True, layout="constrained",
        squeeze=False,
    )
    for axis, baseline in zip(axes.flat, baselines):
        part = data[data["baseline"] == baseline].set_index("scenario")
        for row, scenario in enumerate(scenarios):
            item = part.loc[scenario]
            clear = item["verdict"] != "no clear difference"
            axis.errorbar(
                item["mean_difference"], row,
                xerr=[[item["mean_difference"] - item["ci_low"]],
                      [item["ci_high"] - item["mean_difference"]]],
                fmt="o", color=ACCENT, markerfacecolor=ACCENT if clear else "white",
                markersize=6, elinewidth=2, capsize=3,
            )
        axis.axvline(0, color=INK, linewidth=1)
        axis.set_title(f"vs {labels[baseline]}")
        axis.set_yticks(range(len(scenarios)), [SCENARIOS[s] for s in scenarios])
        axis.set_ylim(len(scenarios) - 0.5, -0.5)
        axis.grid(axis="y", visible=False)
        axis.margins(x=0.15)
    for axis in axes.flat[len(baselines):]:
        axis.set_visible(False)
    figure.supxlabel(
        f"{labels[proposed]} minus baseline: {METRIC_LABELS.get(metric, metric).lower()}. "
        f"Left of zero is better for {labels[proposed]}.\nHollow marker: no clear difference "
        "after Holm correction. Scales differ between panels.", fontsize=9)
    return _save(figure, path)


def sensitivity(
    table: pd.DataFrame, path: Path, x: str, line: str, title: str,
    default: Mapping[str, float],
) -> Path:
    """Tuning score against the first tuned key, one line per value of the second."""
    _style()
    figure, axis = plt.subplots(figsize=(7, 3.8), layout="constrained")
    values = sorted(table[x].unique())
    lines = sorted(table[line].unique())
    if len(lines) > len(SERIES):
        raise ValueError(f"at most {len(SERIES)} lines can be told apart; got {len(lines)}")
    for index, level in enumerate(lines):
        part = table[table[line] == level].set_index(x).reindex(values)
        axis.plot(range(len(values)), part["score"], color=SERIES[index], linewidth=2,
                  marker=MARKERS[index], markersize=7,
                  label=f"{NAMES.get(line, line)} {level:g}")
    axis.axhline(1.0, color=MUTED, linewidth=1)
    axis.set_xticks(range(len(values)), [f"{v:g}" for v in values])
    axis.set_xlabel(f"{NAMES.get(x, x)} (values spaced evenly, not to scale)")
    described = ", ".join(f"{NAMES.get(k, k)} {v:g}" for k, v in default.items())
    axis.set_ylabel(f"Waiting relative to\n{described}")
    axis.set_title(f"{title}, tuning seeds; lower is better")
    axis.legend(frameon=False)
    return _save(figure, path)


def convergence(curves: pd.DataFrame, path: Path, floor: float = 1e-12) -> Path:
    """Median objective gap per iteration, one panel per solver."""
    _style()
    solvers = [s for s in SOLVERS if s in set(curves["solver"])]
    figure, axes = plt.subplots(2, 4, figsize=(10, 4.8), sharex=True, sharey=True,
                                layout="constrained")
    states = int(curves["states"].iloc[0])
    for axis, solver in zip(axes.flat, solvers):
        part = curves[curves["solver"] == solver]
        axis.plot(part["iteration"] + 1, part["median_gap"].clip(lower=floor),
                  color=ACCENT, linewidth=2)
        axis.set(xscale="log", yscale="log")
        axis.set_title(SOLVERS[solver])
    for axis in axes.flat[len(solvers):]:
        axis.set_visible(False)
    figure.supxlabel("Iteration + 1", fontsize=9)
    figure.supylabel(f"Median objective gap over {states} states (floor {floor:g})", fontsize=9)
    return _save(figure, path)


def conditioning(summary: pd.DataFrame, path: Path) -> Path:
    """Median iterations against the penalty parameter, one panel per solver."""
    _style()
    solvers = [s for s in SOLVERS if s in set(summary["solver"])]
    figure, axes = plt.subplots(2, 3, figsize=(8.5, 4.8), sharex=True, sharey=True,
                                layout="constrained")
    for axis, solver in zip(axes.flat, solvers):
        part = summary[summary["solver"] == solver].sort_values("rho")
        axis.plot(part["rho"], part["iterations_median"], color=ACCENT, linewidth=2,
                  marker="o", markersize=6)
        for _, row in part.iterrows():
            axis.annotate(f"{row['iterations_median']:g}", (row["rho"], row["iterations_median"]),
                          xytext=(0, 6), textcoords="offset points", ha="center",
                          color=MUTED, fontsize=8)
        axis.set(xscale="log", yscale="log")
        axis.set_title(SOLVERS[solver])
        axis.set_xticks(part["rho"], [f"{r:g}" for r in part["rho"]])
        axis.margins(x=0.15, y=0.2)
    figure.supxlabel("Penalty parameter ρ", fontsize=9)
    figure.supylabel("Median iterations to tolerance", fontsize=9)
    return _save(figure, path)
