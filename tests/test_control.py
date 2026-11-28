"""Controllers, validation, fallback and the signal sequence; no SUMO needed."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from optitraffic.config import load_config
from optitraffic.control.controllers import (
    CONTROLLERS,
    make_controller,
    proportional_plan,
    whole_second_plan,
)
from optitraffic.control.signal_controller import PhaseError, SignalController
from optitraffic.control.validator import FALLBACK, Validator
from optitraffic.simulation.signals import STAGES
from optitraffic.types import SignalParams, SolverResult, TimingPlan, TrafficState

ROOT = Path(__file__).resolve().parents[1]
SIGNAL = SignalParams(cycle_s=90, yellow_s=3, all_red_s=2, g_min_s=10, g_max_s=70, green_lost_s=1)
STATES = {
    "ns_green": "GrGr", "ns_yellow": "yryr", "all_red_1": "rrrr",
    "ew_green": "rGrG", "ew_yellow": "ryry", "all_red_2": "rrrr",
}


def load(name="medium"):
    return load_config(ROOT / "configs" / "default.yaml",
                       ROOT / "configs" / "scenarios" / f"{name}.yaml")


def make_state(queue=(10.0, 5.0), valid=True, issues=()):
    return TrafficState(
        sim_time=90.0, queue=queue, arrival_rate=(0.1, 0.1), vehicle_count=(0, 0),
        waiting_time=(0.0, 0.0), pending=(0, 0), signal_state="rrrr", approaches=(),
        valid=valid, issues=issues,
    )


class Fixed:
    """A controller that returns whatever it is given."""

    name = "test"
    needs_state = True

    def __init__(self, answer):
        self.answer = answer

    def plan(self, state):
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def solver_result(status, feasible=True, objective=1.0, start=2.0):
    return SolverResult(
        x0=np.zeros(1), x=np.zeros(1), objective=objective, gradient=np.zeros(1), residual=0.0,
        iterations=1, converged=status == "converged", status=status, runtime_s=0.0,
        feasible=feasible, history=(start, objective),
    )


# ------------------------------------------------------------------ controllers
@pytest.mark.parametrize(
    ("desired", "expected"),
    [(39.4, 39), (39.5, 40), (-100, 10), (500, 68), (10, 10), (68.4, 68)],
)
def test_whole_second_plan(desired, expected):
    assert whole_second_plan(desired, SIGNAL) == (expected, 78 - expected)


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_whole_second_plan_rejects_non_finite(value):
    with pytest.raises(ValueError):
        whole_second_plan(value, SIGNAL)


def test_proportional_plan():
    assert proportional_plan(0, 0, SIGNAL) == (39, 39)
    assert proportional_plan(2, 1, SIGNAL) == (52, 26)
    assert proportional_plan(1, 0, SIGNAL) == (68, 10)
    for bad in [(-1, 1), (float("nan"), 1), (float("inf"), 1)]:
        with pytest.raises(ValueError):
            proportional_plan(*bad, SIGNAL)


def test_fixed_equal_ignores_state():
    controller = make_controller("fixed_equal", load("ns_dominant"))
    assert controller.plan(make_state((50, 0))).green == (39, 39)
    assert not controller.needs_state


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [("medium", (39, 39)), ("ns_dominant", (57, 21)), ("ew_dominant", (21, 57)),
     ("changing", (39, 39))],
)
def test_fixed_calibrated_follows_average_demand(scenario, expected):
    assert make_controller("fixed_calibrated", load(scenario)).plan(make_state()).green == expected


def test_queue_proportional():
    controller = make_controller("queue_proportional", load())
    assert controller.plan(make_state((30, 10))).green == (59, 19)  # 0.75 * 78 = 58.5 rounds up
    assert controller.plan(make_state((0, 0))).green == (39, 39)
    assert controller.needs_state


def test_every_controller_gives_feasible_plans():
    rng = np.random.default_rng(14)
    for name, cls in CONTROLLERS.items():
        if getattr(cls, "external_program", False):
            continue  # SUMO runs it; there is no plan
        config = load("changing")
        controller = make_controller(name, config)
        validator = Validator(config.signal, 0.1)
        for _ in range(200):
            state = make_state(tuple(float(q) for q in rng.integers(0, 200, 2)))
            assert validator.plan_problems(controller.plan(state).green) == []


def test_unknown_controller_rejected():
    with pytest.raises(ValueError):
        make_controller("magic", load())


# -------------------------------------------------------- validation, fallback
def test_good_plan_is_applied():
    plan, elapsed = Validator(SIGNAL, 0.1).decide(Fixed(TimingPlan((50, 28), "test")), make_state())
    assert plan == TimingPlan((50, 28), "test") and elapsed >= 0


@pytest.mark.parametrize(
    "green",
    [(50, 29), (50, 27), (9, 69), (69, 9), (39.0, 39.0), (float("nan"), 39),
     (float("inf"), 39), (True, 77), (78,), [39, 39], None],
)
def test_invalid_plan_triggers_fallback(green):
    plan, _ = Validator(SIGNAL, 0.1).decide(Fixed(TimingPlan(green, "test")), make_state())
    assert plan.source == FALLBACK and plan.green == (39, 39) and plan.reason


@pytest.mark.parametrize("answer", [RuntimeError("boom"), ZeroDivisionError(), None, (39, 39)])
def test_controller_fault_triggers_fallback(answer):
    plan, _ = Validator(SIGNAL, 0.1).decide(Fixed(answer), make_state())
    assert plan.source == FALLBACK and plan.reason


def test_invalid_state_triggers_fallback_only_if_state_is_needed():
    state = make_state(valid=False, issues=("arrival rate not ready",))
    controller = Fixed(TimingPlan((50, 28), "test"))
    validator = Validator(SIGNAL, 0.1)
    plan, _ = validator.decide(controller, state)
    assert plan.source == FALLBACK and "arrival rate not ready" in plan.reason
    controller.needs_state = False
    assert validator.decide(controller, state)[0].source == "test"


def test_slow_decision_triggers_fallback():
    plan, elapsed = Validator(SIGNAL, 1e-12).decide(
        Fixed(TimingPlan((50, 28), "test")), make_state()
    )
    assert plan.source == FALLBACK and "budget" in plan.reason and elapsed > 1e-12


@pytest.mark.parametrize(
    ("result", "accept", "applied"),
    [
        (solver_result("converged"), True, True),
        (solver_result("max_iter"), True, True),
        (solver_result("time_budget"), True, True),
        (solver_result("max_iter"), False, False),
        (solver_result("max_iter", objective=3.0), True, False),  # worse than the start
        (solver_result("stalled", feasible=False), True, False),
        (solver_result("numerical_error"), True, False),
    ],
)
def test_solver_status_rules(result, accept, applied):
    validator = Validator(SIGNAL, 0.1, accept_unconverged=accept)
    proposed = TimingPlan((50, 28), "test", solver=result)
    plan, _ = validator.decide(Fixed(proposed), make_state())
    assert (plan.source == "test") == applied
    assert plan.solver is result  # kept for the log either way


def test_infeasible_fallback_is_detected_at_startup():
    with pytest.raises(ValueError):
        Validator(SignalParams(90, 3, 2, 45, 70), 0.1)


# ------------------------------------------------------------- signal sequence
def run_cycle(controller, green):
    controller.load(TimingPlan(green, "test"))
    stages = []
    while not controller.at_boundary:
        stages.append(controller.next_state())
    return stages


def test_cycle_follows_the_sequence_with_correct_durations():
    controller = SignalController(STATES, SIGNAL)
    stages = run_cycle(controller, (49, 29))
    assert len(stages) == 90
    expected = [s for s, n in zip(STAGES, (50, 3, 2, 30, 3, 2)) for _ in range(n)]
    assert [s for s, _ in stages] == expected
    assert all(state == STATES[stage] for stage, state in stages)
    assert controller.at_boundary


def test_half_second_steps():
    stages = run_cycle(SignalController(STATES, SIGNAL, step_s=0.5), (39, 39))
    assert len(stages) == 180


def test_step_that_does_not_divide_durations_rejected():
    with pytest.raises(ValueError):
        SignalController(STATES, SIGNAL, step_s=0.7)


def test_plan_cannot_change_during_a_cycle():
    controller = SignalController(STATES, SIGNAL)
    controller.load(TimingPlan((49, 29), "test"))
    for _ in range(89):
        controller.next_state()
        with pytest.raises(PhaseError):
            controller.load(TimingPlan((10, 68), "late"))
    assert controller.plan.green == (49, 29)
    controller.next_state()
    controller.load(TimingPlan((10, 68), "next"))  # allowed at the boundary


def test_no_state_without_a_plan():
    with pytest.raises(PhaseError):
        SignalController(STATES, SIGNAL).next_state()


@pytest.mark.parametrize("green", [(50, 29), (5, 73), (39.0, 39.0)])
def test_signal_controller_refuses_infeasible_plan(green):
    controller = SignalController(STATES, SIGNAL)
    with pytest.raises(ValueError):
        controller.load(TimingPlan(green, "test"))
    assert controller.at_boundary


@pytest.mark.parametrize(
    "change",
    [
        {"ns_green": "GGGr"},  # conflicting greens
        {"all_red_1": "Grrr"},
        {"ns_yellow": "rrrr"},  # yellow missing
        {"ew_yellow": "yryr"},
        {"ew_green": "GrGr"},
        {"ns_green": "rrrr"},
        {"ns_green": "GrG"},
    ],
)
def test_unsafe_state_strings_rejected(change):
    with pytest.raises(ValueError):
        SignalController({**STATES, **change}, SIGNAL)


def test_missing_stage_rejected():
    states = dict(STATES)
    del states["all_red_2"]
    with pytest.raises(ValueError):
        SignalController(states, SIGNAL)


def test_apply_writes_to_the_traffic_light():
    written = []

    class Light:
        def setRedYellowGreenState(self, tls, state):
            written.append((tls, state))

    api = type("Api", (), {"trafficlight": Light()})()
    controller = SignalController(STATES, replace(SIGNAL))
    controller.load(TimingPlan((39, 39), "test"))
    assert controller.apply(api, "C") == "ns_green"
    assert written == [("C", "GrGr")]
