"""Metrics, statistics, tables and the solver study; no SUMO needed."""

import gzip
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

pd = pytest.importorskip("pandas")
scipy_stats = pytest.importorskip("scipy.stats")

from optitraffic.config import ConfigError, load_config  # noqa: E402
from optitraffic.evaluation import analysis, plots, solver_study  # noqa: E402
from optitraffic.evaluation.metrics import (  # noqa: E402
    control_metrics,
    read_tripinfo,
    traffic_metrics,
)
from optitraffic.evaluation.runner import (  # noqa: E402
    RunSpec,
    run_config,
    run_hash,
    source_hash,
)
from optitraffic.evaluation.settings import load_plan  # noqa: E402
from optitraffic.evaluation.statistics import holm, mean_interval, paired_comparison  # noqa: E402
from optitraffic.experiments import evaluation_specs, tuning_specs  # noqa: E402
from optitraffic.integration.queue_monitor import QueueMonitor  # noqa: E402
from optitraffic.simulation.routes import Trip  # noqa: E402
from optitraffic.types import CycleRecord, TimingPlan, TrafficState  # noqa: E402

# The pinned Matplotlib uses names that newer pyparsing releases deprecate.
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "configs" / "experiments.yaml"


def config():
    return load_config(ROOT / "configs" / "default.yaml",
                       ROOT / "configs" / "scenarios" / "medium.yaml")


# -------------------------------------------------------------------- metrics
def trip(vehicle, depart, delay, arrival, duration, waiting, stops, loss):
    return (f'<tripinfo id="{vehicle}" depart="{depart}" departDelay="{delay}" '
            f'arrival="{arrival}" duration="{duration}" waitingTime="{waiting}" '
            f'waitingCount="{stops}" timeLoss="{loss}"/>')


@pytest.fixture
def tripinfo(tmp_path):
    rows = [
        trip("warm", 10, 0, 150, 140, 90, 3, 99),   # scheduled in the warm-up
        trip("a", 101, 1, 141, 40, 10, 1, 15),      # finished
        trip("b", 130, 20, -1, 70, 30, 2, 40),      # still on the road
        trip("c", -1, 60, -1, 0, 0, 0, 0),          # never entered
    ]
    path = tmp_path / "trips.xml.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write("<tripinfos>" + "".join(rows) + "</tripinfos>")
    return path


SCHEDULE = [
    Trip("warm", 10.0, "N_in", "S_out"), Trip("a", 100.0, "N_in", "S_out"),
    Trip("b", 110.0, "E_in", "W_out"), Trip("c", 140.0, "E_in", "W_out"),
]


def test_traffic_metrics_by_hand(tripinfo):
    m = traffic_metrics(read_tripinfo(tripinfo), SCHEDULE, warmup_s=100, end_s=200)
    assert (m["vehicles"], m["finished"], m["unfinished_on_road"], m["never_entered"]) == (3, 1, 1, 1)
    assert m["avg_total_wait_s"] == pytest.approx((11 + 50 + 60) / 3)
    assert m["avg_waiting_s"] == pytest.approx(20)  # vehicles that entered
    assert m["avg_insertion_delay_s"] == pytest.approx(27)
    assert m["avg_travel_time_s"] == 40 and m["avg_travel_time_unfinished_s"] == 70
    assert m["avg_delay_s"] == pytest.approx((16 + 60 + 60) / 3)
    assert m["worst_approach_delay_s"] == pytest.approx(60)
    assert m["stops_per_vehicle"] == pytest.approx(1.5)
    assert m["throughput_veh"] == 2  # arrivals in the period, whenever they started


def test_missing_trip_record_is_an_error(tripinfo):
    schedule = [*SCHEDULE, Trip("lost", 150.0, "N_in", "S_out")]
    with pytest.raises(ValueError, match="lost"):
        traffic_metrics(read_tripinfo(tripinfo), schedule, 100, 200)


def test_empty_averages_are_none_not_nan(tripinfo):
    results = read_tripinfo(tripinfo)
    m = traffic_metrics(results, [SCHEDULE[3]], 100, 200)
    assert m["avg_waiting_s"] is None and m["avg_travel_time_s"] is None


def test_control_metrics():
    state = TrafficState(0, (0, 0), (0, 0), (0, 0), (0, 0), (0, 0), "r", (), True, ())

    def cycle(start, green, source="adaptive", reason=""):
        return CycleRecord(start, state, TimingPlan(green, source, reason), 0.002)

    cycles = [
        cycle(0, (39, 39), "fallback", "invalid state: not ready"),
        cycle(630, (40, 38)),
        cycle(720, (39, 39), "fallback", "controller error: boom"),
    ]
    m = control_metrics(cycles, config().signal, warmup_s=600)
    assert (m["cycles"], m["fallbacks"], m["fallbacks_whole_run"]) == (2, 1, 2)
    assert m["rejected_plans"] == 1 and m["infeasible_applied"] == 0
    assert m["solver_calls"] == 0 and m["solver_mean_ms"] is None


def test_queue_monitor_counts_only_the_measured_period():
    class Edge:
        value = 0

        def getLastStepHaltingNumber(self, name):
            return self.value if name == "a" else 1

    class Simulation:
        def getPendingVehicles(self):
            return ["x", "y"]

    api = type("Api", (), {"edge": Edge(), "simulation": Simulation()})()
    monitor = QueueMonitor(["a", "b"], 10, 12)
    for time_s, value in [(10, 100), (11, 2), (12, 6), (13, 100)]:
        api.edge.value = value
        monitor.observe(api, time_s)
    summary = monitor.summary()
    assert summary["avg_queue_veh"] == 5 and summary["max_queue_veh"] == 6
    assert summary["avg_pending_veh"] == 2 and summary["max_queue_b"] == 1
    with pytest.raises(ValueError):
        QueueMonitor(["a"], 10, 12).summary()


# ----------------------------------------------------------------- statistics
def test_mean_interval_matches_scipy():
    values = [3.0, 5.0, 4.0, 8.0, 6.0]
    interval = mean_interval(values)
    low, high = scipy_stats.t.interval(0.95, 4, loc=np.mean(values),
                                       scale=scipy_stats.sem(values))
    assert (interval.low, interval.high) == pytest.approx((low, high))
    assert mean_interval([2.0]).low is None
    for bad in ([], [np.nan], [1.0, np.inf]):
        with pytest.raises(ValueError):
            mean_interval(bad)


def test_paired_comparison():
    baseline = np.arange(10.0, 30.0)
    result = paired_comparison(baseline - np.linspace(1, 3, 20), baseline)
    assert result.difference.mean == pytest.approx(-2) and result.percent < 0
    assert (result.better, result.worse) == (20, 0) and result.p_value < 1e-3
    same = paired_comparison(baseline, baseline)
    assert same.p_value == 1.0 and same.difference.mean == 0
    with pytest.raises(ValueError):
        paired_comparison([1.0], [1.0, 2.0])


def test_holm_by_hand():
    assert holm([0.01, 0.04, 0.03, 0.005]) == pytest.approx([0.03, 0.06, 0.06, 0.02])
    assert holm([0.5, 0.9]) == [1.0, 1.0]
    assert holm([]) == []
    with pytest.raises(ValueError):
        holm([1.5])


# --------------------------------------------------------------------- tables
def fake_runs():
    rows = []
    for scenario, scale in (("low", 1.0), ("high", 10.0)):
        for seed in range(8):
            for controller, factor in (("adaptive", 0.8), ("fixed_equal", 1.0),
                                       ("worse", 0.5)):
                rows.append({
                    "scenario": scenario, "controller": controller, "seed": seed,
                    "status": "done", "wait": factor * scale * (10 + seed),
                    "throughput_veh": 100 + seed + (5 if controller == "adaptive" else 0),
                })
    return pd.DataFrame(rows)


def test_paired_table_directions_and_dropped_pairs():
    runs = fake_runs()
    bad = (runs["scenario"] == "low") & (runs["seed"] == 0) & (runs["controller"] == "adaptive")
    runs.loc[bad, "status"] = "invalid"
    table = analysis.paired_table(
        runs, "adaptive", ["fixed_equal", "worse"], ["wait", "throughput_veh"], 0.95
    )
    low = table[table["scenario"] == "low"].set_index(["metric", "baseline"])
    assert low.loc[("wait", "fixed_equal"), "verdict"] == "better"
    assert low.loc[("wait", "worse"), "verdict"] == "worse"
    assert low.loc[("throughput_veh", "fixed_equal"), "verdict"] == "better"  # higher is better
    assert (low["n_pairs"] == 7).all() and (low["n_dropped"] == 1).all()
    assert (table["p_holm"] >= table["p_value"]).all()


def test_tuning_choice_uses_relative_scores_and_skips_incomplete_settings():
    rows = []
    for beta, low, high, status in [
        (0.1, 10, 1000, "done"),   # default
        (0.2, 5, 1100, "done"),    # much better on low, a little worse on high
        (0.4, 1, 1, "invalid"),    # cannot be chosen
    ]:
        for scenario, value in (("low", low), ("high", high)):
            rows.append({"beta": beta, "window_s": 180.0, "scenario": scenario,
                         "wait": value, "status": status})
    table = analysis.tuning_table(pd.DataFrame(rows), "wait", (0.1, 180.0))
    assert analysis.choose_setting(table, (0.1, 180.0)) == (0.2, 180.0)
    score = table.set_index("beta").loc[0.2, "score"]
    assert score == pytest.approx((0.5 * 1.1) ** 0.5)
    with pytest.raises(ValueError):
        analysis.tuning_table(pd.DataFrame(rows), "wait", (0.4, 180.0))


# ----------------------------------------------------------------------- plan
def test_experiment_plan():
    plan = load_plan(PLAN, ROOT)
    assert plan.controllers == (
        "fixed_equal", "fixed_calibrated", "queue_proportional", "adaptive")
    specs = evaluation_specs(plan)
    assert len(specs) == 480 and len({s.run_id for s in specs}) == 480
    tuning = tuning_specs(plan)
    assert len(tuning) == 30 * 6 * 5
    assert not {s.seed for s in tuning} & {s.seed for s in specs}


def test_plan_rejects_shared_seeds(tmp_path):
    text = PLAN.read_text(encoding="utf-8").replace("seeds: [101,", "seeds: [1,")
    path = tmp_path / "plan.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match="share seeds"):
        load_plan(path, ROOT)


def test_run_hash_changes_with_configuration_and_code():
    base = [ROOT / "configs" / "default.yaml"]
    spec = RunSpec("medium", "adaptive", 1)
    changed = replace(spec, overrides=(("model", "beta", 0.2),))
    assert run_config(base, changed).model.beta == 0.2
    first = run_hash(run_config(base, spec), spec, "x")
    assert first != run_hash(run_config(base, changed), changed, "x")
    assert first != run_hash(run_config(base, spec), spec, "y")
    assert source_hash() == source_hash()


# --------------------------------------------------------------- solver study
SETTINGS = {
    "seed": 1, "max_iterations": 200, "sgd_states": 2, "curve_states": 4,
    "penalty_rho": [1, 10], "penalty_states": 3, "penalty_max_iterations": 20_000,
    "penalty_grid_checks": 1, "quadratic_dimensions": [2], "quadratic_conditions": [10],
    "quadratic_problems": 2, "rosenbrock_max_iterations": 20_000,
}
STATES = [(20.0, 15.0, 0.2, 0.1), (40.0, 2.0, 0.2, 0.1), (3.0, 9.0, 0.1, 0.2),
          (0.0, 0.0, 0.05, 0.05)]


def test_solver_study_end_to_end(tmp_path):
    t1 = solver_study.reduced_runs(STATES, config(), SETTINGS)
    smooth = t1[(t1["problem"] == "J") & (t1["solver"] != "subgradient")]
    assert len(smooth) == 6 * 4 and smooth["converged"].all()
    assert smooth["integer_plan_optimal"].all() and smooth["error_s"].max() < 1e-3
    assert set(t1["problem"]) == {"J", "J_ns", "expected J"}
    assert (t1[t1["problem"] == "expected J"]["solver"].nunique()) == 2

    curves = solver_study.convergence_curves(STATES, config(), SETTINGS)
    assert (curves["median_gap"] >= 0).all() and curves["iteration"].max() == 200

    t2, checks = solver_study.penalty_runs(STATES, config(), SETTINGS)
    assert checks["reference_ok"].all() and len(t2) == 2 * 3 * 6
    t3 = solver_study.benchmark_runs(SETTINGS)
    assert set(t3["problem"]) == {"quadratic", "rosenbrock"}

    summary = solver_study.summarise(t2, ["rho", "solver"], {"gap_max": ("gap", "max")})
    assert len(summary) == 12 and (summary["problems"] == 3).all()
    for path in (plots.convergence(curves, tmp_path / "c.png"),
                 plots.conditioning(summary, tmp_path / "p.png")):
        assert path.stat().st_size > 0


def test_result_figures_are_written(tmp_path):
    runs = fake_runs()
    runs = runs[runs["controller"] != "worse"].rename(columns={"wait": "avg_total_wait_s"})
    means = analysis.means_table(runs, ["avg_total_wait_s"], 0.95)
    summary = analysis.paired_table(
        runs, "adaptive", ["fixed_equal"], ["avg_total_wait_s"], 0.95)
    settings = pd.DataFrame({"beta": [0.1, 0.2], "window_s": [180.0, 180.0], "score": [1.0, 0.9]})
    for path in (
        plots.controller_means(means, "avg_total_wait_s", tmp_path / "a.png"),
        plots.paired_differences(summary, "avg_total_wait_s", tmp_path / "b.png"),
        plots.sensitivity(settings, tmp_path / "c.png"),
    ):
        assert path.stat().st_size > 0
