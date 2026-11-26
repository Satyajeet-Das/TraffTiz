"""The optimization-based controller; no SUMO needed."""

import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from optitraffic.config import load_config
from optitraffic.control.adaptive import AdaptiveController, round_green
from optitraffic.control.controllers import make_controller
from optitraffic.control.validator import FALLBACK, Validator
from optitraffic.optimization.problems import ReducedProblem, StochasticProblem
from optitraffic.optimization.solvers import create_solver
from optitraffic.types import SOLVER_NAMES, ObjectiveData, TrafficState

ROOT = Path(__file__).resolve().parents[1]
EXACT = ("gradient_descent", "projected_gradient", "momentum", "newton", "bfgs",
         "conjugate_gradient")


def load(solver="projected_gradient", **settings):
    """The medium scenario with a generous time budget, so timing cannot matter."""
    config = load_config(ROOT / "configs" / "default.yaml",
                         ROOT / "configs" / "scenarios" / "medium.yaml")
    settings = {"time_budget_s": 30.0, **settings}
    return replace(config, solver=replace(config.solver, name=solver, **settings))


def make_state(queue, rate=(0.12, 0.12), time_s=90.0, valid=True):
    return TrafficState(
        sim_time=time_s, queue=queue, arrival_rate=rate, vehicle_count=(0, 0),
        waiting_time=(0.0, 0.0), pending=(0, 0), signal_state="rrrr", approaches=(),
        valid=valid, issues=() if valid else ("injected",),
    )


def random_states(count, seed=8):
    rng = np.random.default_rng(seed)
    return [
        make_state(
            tuple(float(q) for q in rng.integers(0, 80, 2)),
            tuple(float(r) for r in rng.uniform(0, 0.35, 2)),
            90.0 * i,
        )
        for i in range(count)
    ]


def best_integer(problem):
    """Brute force over every whole-second plan."""
    return min(range(int(problem.lower), int(problem.upper) + 1),
               key=lambda g: problem.value([g]))


def decide(config, controller, state):
    validator = Validator(config.signal, config.solver.time_budget_s)
    return validator.decide(controller, state)[0]


# ------------------------------------------------------------------- rounding
def interior_problem():
    data = ObjectiveData((20, 15), (0.2, 0.1), (0.5, 0.5), (1, 1), 0.1, 90)
    return ReducedProblem(data, 10, 70, 80)  # minimiser 57.4 / 1.06 = 54.15


@pytest.mark.parametrize(("x", "expected"), [(54.15, 54), (54.9, 54), (53.2, 54), (54.0, 54)])
def test_rounding_takes_the_better_neighbour(x, expected):
    assert round_green(interior_problem(), [x]) == (expected, 80 - expected)


@pytest.mark.parametrize(("x", "expected"), [(-5.0, 10), (200.0, 70), (69.8, 69), (10.2, 11)])
def test_rounding_stays_inside_the_bounds(x, expected):
    assert round_green(interior_problem(), [x]) == (expected, 80 - expected)


def test_rounding_a_flat_objective_prefers_the_nearest_then_equal_split():
    data = ObjectiveData((0, 0), (0, 0), (0.5, 0.5), (1, 1), 0.1, 90)
    problem = ReducedProblem(data, 10, 70, 78)
    assert round_green(problem, [39.0]) == (39, 39)
    assert round_green(problem, [30.4]) == (30, 48)
    assert round_green(problem, [38.5]) == (39, 39)  # equally near: the equal split wins


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_rounding_rejects_non_finite(value):
    with pytest.raises(ValueError):
        round_green(interior_problem(), [value])


# ----------------------------------------------------------------- the plans
@pytest.mark.parametrize("name", EXACT)
def test_plan_is_the_best_whole_second_plan(name):
    config = load(name)
    controller = AdaptiveController(config)
    for state in random_states(60):
        plan = decide(config, controller, state)
        assert plan.source == "adaptive" and plan.solver_name == name, plan.reason
        problem = controller.problem(state)
        expected = best_integer(problem)
        assert problem.value([plan.green[0]]) == pytest.approx(
            problem.value([expected]), rel=1e-9, abs=1e-9
        )
        assert sum(plan.green) == config.signal.green_budget_s


@pytest.mark.parametrize(("name", "excess"), [("subgradient", 0.01), ("sgd", 0.02)])
def test_inexact_solvers_give_near_optimal_plans(name, excess):
    config = load(name)
    controller = AdaptiveController(config, seed=3)
    for state in random_states(15):
        plan = decide(config, controller, state)
        assert plan.source == "adaptive", plan.reason
        problem = controller.problem(state)
        best = problem.value([best_integer(problem)])
        assert problem.value([plan.green[0]]) <= best * (1 + excess) + 1.0


def test_every_solver_is_covered():
    assert set(EXACT) | {"subgradient", "sgd"} == set(SOLVER_NAMES)


def test_long_queue_gets_the_maximum_green():
    config = load()
    plan = decide(config, AdaptiveController(config), make_state((40.0, 2.0)))
    assert plan.green == (68, 10)


def test_no_demand_gives_an_equal_split():
    config = load()
    plan = decide(config, AdaptiveController(config), make_state((0.0, 0.0), (0.0, 0.0)))
    assert plan.green == (39, 39) and plan.solver.converged


def test_continuous_and_integer_solutions_are_both_kept():
    config = load()
    plan = decide(config, AdaptiveController(config), make_state((20.0, 15.0), (0.2, 0.1)))
    assert abs(plan.solver.x[0] - plan.green[0]) < 1
    assert isinstance(plan.green[0], int) and plan.solver.x[0] != plan.green[0]


def test_sgd_uses_the_expected_objective():
    assert isinstance(AdaptiveController(load("sgd")).problem(make_state((5.0, 5.0))),
                      StochasticProblem)


def test_sgd_is_reproducible_and_varies_between_decisions():
    config = load("sgd", max_iterations=60)
    state = make_state((18.0, 16.0), (0.2, 0.15))

    def solution(seed, time_s=90.0):
        controller = AdaptiveController(config, seed=seed)
        return float(controller.plan(replace(state, sim_time=time_s)).solver.x[0])

    assert solution(1) == solution(1)
    assert solution(1) != solution(2)
    assert solution(1) != solution(1, 180.0)


def test_solver_gets_only_part_of_the_decision_budget():
    seen = []

    def factory(params, **options):
        seen.append(params)
        return create_solver(params, **options)

    config = load(time_budget_s=0.1, solver_budget_fraction=0.5)
    AdaptiveController(config, solver_factory=factory).plan(make_state((5.0, 5.0)))
    assert seen[0].time_budget_s == pytest.approx(0.05)


def test_make_controller_passes_the_seed():
    assert make_controller("adaptive", load(), seed=9).seed == 9


def test_invalid_state_gives_the_fallback():
    config = load()
    plan = decide(config, AdaptiveController(config), make_state((9.0, 1.0), valid=False))
    assert plan.source == FALLBACK and "injected" in plan.reason


@pytest.mark.parametrize("queue", [(float("nan"), 1.0), (-1.0, 1.0)])
def test_impossible_measurement_gives_the_fallback(queue):
    config = load()
    plan = decide(config, AdaptiveController(config), make_state(queue))
    assert plan.source == FALLBACK and "ValueError" in plan.reason


# ---------------------------------------------------------- solver failures
class Broken:
    """A solver factory whose solver misbehaves in the requested way."""

    def __init__(self, change=None, error=None, delay=0.0):
        self.change, self.error, self.delay = change or {}, error, delay

    def __call__(self, params, **options):
        self.real = create_solver(params, **options)
        return self

    def solve(self, problem, x0):
        if self.error is not None:
            raise self.error
        time.sleep(self.delay)
        return replace(self.real.solve(problem, x0), **self.change)


@pytest.mark.parametrize(
    ("factory", "reason"),
    [
        (Broken(error=ArithmeticError("injected")), "injected"),
        (Broken(change={"converged": False, "status": "numerical_error"}), "numerical_error"),
        (Broken(change={"feasible": False}), "infeasible"),
        (Broken(change={"x": np.array([np.nan])}), "non-finite"),
        (Broken(change={"converged": False, "status": "max_iter", "objective": np.inf}),
         "did not converge"),
    ],
)
def test_solver_failure_gives_the_fallback(factory, reason):
    config = load()
    controller = AdaptiveController(config, solver_factory=factory)
    plan = decide(config, controller, make_state((20.0, 15.0)))
    assert plan.source == FALLBACK and plan.green == (39, 39)
    assert reason in plan.reason


def test_timeout_gives_the_fallback_and_keeps_the_result():
    config = load(time_budget_s=0.05)
    controller = AdaptiveController(config, solver_factory=Broken(delay=0.1))
    plan = decide(config, controller, make_state((20.0, 15.0)))
    assert plan.source == FALLBACK and "budget" in plan.reason
    assert plan.solver is not None and plan.solver_name == "projected_gradient"
