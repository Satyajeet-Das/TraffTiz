"""Signal safety verified from the states observed in real SUMO runs."""

import csv
import itertools
import time
from dataclasses import replace
from pathlib import Path

import pytest

from optitraffic.config import load_config
from optitraffic.control.adaptive import AdaptiveController
from optitraffic.control.controllers import CONTROLLERS, make_controller
from optitraffic.control.validator import FALLBACK
from optitraffic.integration.state_collector import StateCollector
from optitraffic.optimization.solvers import create_solver
from optitraffic.run import main, simulate
from optitraffic.simulation.network import signal_links
from optitraffic.simulation.signals import stage_states
from optitraffic.types import SOLVER_NAMES, TimingPlan

pytestmark = pytest.mark.sumo

ROOT = Path(__file__).resolve().parents[2]


def load(name="ns_dominant", duration=900.0):
    config = load_config(ROOT / "configs" / "default.yaml",
                         ROOT / "configs" / "scenarios" / f"{name}.yaml")
    return replace(
        config, simulation=replace(config.simulation, warmup_s=0.0, duration_s=duration)
    )


def run_and_record(config, controller, folder):
    observed = []
    result = simulate(
        config, controller, seed=1, folder=folder,
        on_step=lambda sim, stage: observed.append(
            sim.api.trafficlight.getRedYellowGreenState(config.network.tls_id)
        ),
    )
    states = stage_states(
        signal_links(Path(folder) / "intersection.net.xml", config.network.tls_id), config.network
    )
    return result, observed, states


def assert_signals_match_plans(config, result, observed, states):
    """The observed log equals exactly what the applied plans prescribe."""
    s = config.signal
    expected = []
    for cycle in result.cycles:
        ns, ew = (s.displayed_green_s(g) for g in cycle.plan.green)
        for stage, seconds in zip(
            ("ns_green", "ns_yellow", "all_red_1", "ew_green", "ew_yellow", "all_red_2"),
            (ns, s.yellow_s, s.all_red_s, ew, s.yellow_s, s.all_red_s),
        ):
            expected += [states[stage]] * seconds
    assert observed == expected[: len(observed)]
    assert [c.start_s for c in result.cycles] == [s.cycle_s * i for i in range(len(result.cycles))]
    # Between any two greens of different phases there is yellow and then all-red.
    runs = [state for state, _ in itertools.groupby(observed)]
    pattern = [states[k] for k in (
        "ns_green", "ns_yellow", "all_red_1", "ew_green", "ew_yellow", "all_red_2")]
    assert runs == [pattern[i % 6] for i in range(len(runs))]


@pytest.mark.parametrize("name", sorted(CONTROLLERS))
def test_controller_runs_safely(name, tmp_path):
    config = load()
    result, observed, states = run_and_record(config, make_controller(name, config), tmp_path)
    assert result.valid, result
    assert len(observed) == 900 and len(result.cycles) == 10
    assert_signals_match_plans(config, result, observed, states)
    fallbacks = [c for c in result.cycles if c.plan.source == FALLBACK]
    if name in ("queue_proportional", "adaptive"):
        # Only the first decision, before any rate estimate exists.
        assert [c.start_s for c in fallbacks] == [0.0]
        assert len({c.plan.green for c in result.cycles}) > 1
    else:
        assert fallbacks == []


class Faulty:
    """Cycles through good plans and every kind of fault."""

    name = "faulty"
    needs_state = False

    def __init__(self):
        self.calls = 0

    def plan(self, state):
        self.calls += 1
        answers = [
            TimingPlan((58, 20), self.name),
            TimingPlan((90, -12), self.name),
            TimingPlan((float("nan"), 39), self.name),
            TimingPlan((40, 40), self.name),
            None,
            TimingPlan((20, 58), self.name),
        ]
        answer = answers[(self.calls - 1) % len(answers)]
        if self.calls == 7:
            raise RuntimeError("injected failure")
        return answer


def test_injected_faults_fall_back_and_signals_stay_safe(tmp_path):
    config = load("medium")
    result, observed, states = run_and_record(config, Faulty(), tmp_path)
    assert result.valid
    sources = [c.plan.source for c in result.cycles]
    assert sources == ["faulty", FALLBACK, FALLBACK, FALLBACK, FALLBACK, "faulty",
                       FALLBACK, FALLBACK, FALLBACK, FALLBACK]
    assert result.fallbacks == 8
    assert all(c.plan.reason for c in result.cycles if c.plan.source == FALLBACK)
    assert "injected failure" in result.cycles[6].plan.reason
    assert_signals_match_plans(config, result, observed, states)


@pytest.mark.parametrize("name", ["queue_proportional", "adaptive"])
def test_same_seed_gives_same_run(name, tmp_path):
    config = load("high", duration=450.0)
    runs = [
        simulate(config, make_controller(name, config), 3, tmp_path / str(i))
        for i in range(2)
    ]
    assert [c.state for c in runs[0].cycles] == [c.state for c in runs[1].cycles]
    assert [c.plan.green for c in runs[0].cycles] == [c.plan.green for c in runs[1].cycles]
    assert (runs[0].departed, runs[0].arrived) == (runs[1].departed, runs[1].arrived)


def test_lost_connection_marks_the_run_failed(tmp_path):
    config = load("low", duration=180.0)

    def cut(sim, stage):
        if sim.time == 20:
            from traci.exceptions import FatalTraCIError

            raise FatalTraCIError("injected disconnect")

    result = simulate(config, make_controller("fixed_equal", config), 1, tmp_path, on_step=cut)
    assert not result.valid and "injected disconnect" in result.failure


def test_command_line_run(tmp_path, capsys):
    code = main(["--scenario", "low", "--controller", "fixed_calibrated", "--out", str(tmp_path)])
    assert code == 0
    with open(tmp_path / "cycles.csv", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 47  # 4200 s of 90 s cycles, the last one partial
    assert {r["source"] for r in rows} == {"fixed_calibrated"}
    assert "fallback cycles: 0" in capsys.readouterr().out


# ------------------------------------------------------------ adaptive control
SCENARIOS = ("low", "medium", "high", "ns_dominant", "ew_dominant", "changing")


@pytest.mark.parametrize("name", SCENARIOS)
def test_adaptive_full_run(name, tmp_path):
    config = load_config(ROOT / "configs" / "default.yaml",
                         ROOT / "configs" / "scenarios" / f"{name}.yaml")
    result, observed, states = run_and_record(
        config, make_controller("adaptive", config), tmp_path
    )
    assert result.valid, result
    assert result.end_time_s == config.simulation.end_s and len(result.cycles) == 47
    assert_signals_match_plans(config, result, observed, states)
    # Only the first decision, before any rate estimate exists.
    assert [c.start_s for c in result.cycles if c.plan.source == FALLBACK] == [0.0]
    assert all(c.plan.reason or c.state.issues for c in result.cycles[:1])
    assert all(c.plan.solver.converged for c in result.cycles[1:])


@pytest.mark.parametrize("solver", SOLVER_NAMES)
def test_adaptive_runs_safely_with_each_solver(solver, tmp_path):
    config = load()
    config = replace(config, solver=replace(config.solver, name=solver))
    result, observed, states = run_and_record(
        config, make_controller("adaptive", config, seed=1), tmp_path
    )
    assert result.valid, result
    assert_signals_match_plans(config, result, observed, states)
    # Wall-clock fallbacks are possible for the iterative methods on a slow machine.
    assert all(c.plan.reason for c in result.cycles if c.plan.source == FALLBACK)
    assert any(c.plan.source == "adaptive" for c in result.cycles)


class FailingSolvers:
    """Solver factory that fails differently on successive decisions."""

    faults = {2: "error", 3: "slow", 4: "numerical", 6: "infeasible"}

    def __init__(self):
        self.calls = 0

    def __call__(self, params, **options):
        self.calls += 1
        fault = self.faults.get(self.calls)
        real = create_solver(params, **options)

        class Solver:
            def solve(self, problem, x0):
                if fault == "error":
                    raise ArithmeticError("injected solver error")
                if fault == "slow":
                    time.sleep(0.15)
                result = real.solve(problem, x0)
                if fault == "numerical":
                    return replace(result, converged=False, status="numerical_error")
                if fault == "infeasible":
                    return replace(result, feasible=False)
                return result

        return Solver()


def test_adaptive_failure_injection(tmp_path, monkeypatch):
    config = load("medium")
    read = StateCollector.read

    def sometimes_invalid(self):
        state = read(self)
        if state.sim_time == 720:
            return replace(state, valid=False, issues=("injected invalid state",))
        return state

    monkeypatch.setattr(StateCollector, "read", sometimes_invalid)
    controller = AdaptiveController(config, solver_factory=FailingSolvers())
    result, observed, states = run_and_record(config, controller, tmp_path)
    assert result.valid
    reasons = {c.start_s: c.plan.reason for c in result.cycles if c.plan.source == FALLBACK}
    # Cycle 0 has no estimate, so solver calls 1, 2, ... happen from t = 90 s.
    expected = {
        0: "not ready", 180: "injected solver error", 270: "budget", 360: "numerical_error",
        540: "infeasible", 720: "injected invalid state",
    }
    assert sorted(reasons) == sorted(expected)
    for start, text in expected.items():
        assert text in reasons[start]
    assert_signals_match_plans(config, result, observed, states)


def test_command_line_adaptive_run(tmp_path, capsys):
    code = main(["--scenario", "low", "--controller", "adaptive", "--solver", "newton",
                 "--out", str(tmp_path)])
    assert code == 0
    with open(tmp_path / "cycles.csv", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["source"] == FALLBACK and rows[0]["status"] == ""
    for row in rows[1:]:
        assert (row["source"], row["solver"], row["status"]) == ("adaptive", "newton", "converged")
        assert abs(float(row["solution_ns"]) - int(row["green_ns"])) < 1
    assert "name: newton" in (tmp_path / "config.yaml").read_text(encoding="utf-8")
    assert "solver newton: converged" in capsys.readouterr().out


def test_command_line_rejects_solver_for_a_baseline(capsys):
    with pytest.raises(SystemExit):
        main(["--controller", "fixed_equal", "--solver", "newton"])
