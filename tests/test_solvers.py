"""All algorithms against the oracle or a known optimum (FR-06)."""

import numpy as np
import pytest
from conftest import CASE_QUEUES, make_data, random_data

from optitraffic.optimization.problems import PenaltyProblem, ReducedProblem, StochasticProblem
from optitraffic.optimization.solvers import (
    BFGS,
    SGD,
    ConjugateGradient,
    GradientDescent,
    Momentum,
    Newton,
    ProjectedGradient,
    Subgradient,
    create_solver,
)
from optitraffic.optimization.solvers.oracle import minimize_bisection
from optitraffic.optimization.test_functions import Quadratic, Rosenbrock
from optitraffic.types import SOLVER_NAMES, SolverParams

SMOOTH = [GradientDescent, ProjectedGradient, Momentum, Newton, BFGS, ConjugateGradient]
MONOTONE = [GradientDescent, ProjectedGradient, Newton, BFGS, ConjugateGradient]
LINE_SEARCH = [ProjectedGradient, Newton, BFGS, ConjugateGradient]


def reduced(data, nonsmooth=False):
    return ReducedProblem(data, 10, 70, 80, nonsmooth=nonsmooth)


def assert_solved(problem, result, value_gap=1e-6):
    best = minimize_bisection(problem)
    assert result.status == "converged", result.status
    assert result.converged and result.feasible
    assert result.residual <= 1e-6
    assert result.objective - best.value <= value_gap
    assert problem.lower <= result.x[0] <= problem.upper


@pytest.mark.parametrize("solver", SMOOTH)
@pytest.mark.parametrize("name", ["A", "B"])
@pytest.mark.parametrize("start", [40.0, 10.0, 70.0, -100.0, 500.0])
def test_reference_cases_from_any_start(case, solver, name, start):
    problem = reduced(case(name))
    result = solver().solve(problem, [start])
    assert_solved(problem, result)
    np.testing.assert_array_equal(result.x0, [start])


@pytest.mark.parametrize("solver", SMOOTH)
@pytest.mark.parametrize(
    "queue", [(0, 60), (60, 0), (0, 15), (15, 0), (0, 0), (50, 50)]
)
def test_bounds_and_empty_queues(solver, queue):
    problem = reduced(make_data(queue))
    assert_solved(problem, solver().solve(problem, [40.0]))


@pytest.mark.parametrize("solver", SMOOTH)
def test_zero_arrival_rates(solver):
    for queue in [(30, 25), (0, 0)]:
        problem = reduced(make_data(queue, arrival_rate=(0, 0)))
        assert_solved(problem, solver().solve(problem, [40.0]))


@pytest.mark.parametrize("solver", SMOOTH)
def test_flat_objective_keeps_the_start(solver):
    result = solver().solve(reduced(make_data((0, 0), arrival_rate=(0, 0))), [40.0])
    assert result.converged and result.iterations == 0
    assert result.x[0] == 40


@pytest.mark.parametrize("solver", SMOOTH)
def test_random_problems_match_oracle(solver):
    rng = np.random.default_rng(8)
    for _ in range(100):
        problem = reduced(random_data(rng))
        start = rng.uniform(10, 70)
        result = solver(max_iterations=20_000).solve(problem, [start])
        assert_solved(problem, result, value_gap=1e-4)
        assert result.objective <= problem.value([start]) + 1e-9


@pytest.mark.parametrize("solver", MONOTONE)
def test_monotone_solvers_never_increase_the_objective(solver):
    rng = np.random.default_rng(9)
    for _ in range(50):
        problem = reduced(random_data(rng))
        history = np.array(solver().solve(problem, [rng.uniform(10, 70)]).history)
        assert np.all(np.diff(history) <= 1e-9 * np.maximum(1, np.abs(history[:-1])))


@pytest.mark.parametrize("solver", SMOOTH)
def test_result_fields(case, solver):
    problem = reduced(case("B"))
    result = solver().solve(problem, [40.0])
    assert result.iterations == len(result.history) - 1
    assert result.history[0] == pytest.approx(415)
    assert result.history[-1] == result.objective
    assert result.runtime_s >= 0
    np.testing.assert_allclose(result.gradient, problem.gradient(result.x))


@pytest.mark.parametrize("start", [10.0, 39.0, 70.0])
def test_projected_gradient_on_a_flat_objective(start):
    """Recorded in simulation (low demand, seed 1): both queues clear, so only the
    small red-time term remains. A weak Armijo constant accepted steps of almost
    2/L here and needed hundreds of iterations."""
    data = make_data((7, 0), arrival_rate=(13 / 180, 1 / 12),
                     discharge_rate=(1860 / 3600, 1860 / 3600))
    problem = ReducedProblem(data, 10, 70, 78)
    result = ProjectedGradient().solve(problem, [start])
    assert result.converged and result.iterations <= 20
    assert abs(result.x[0] - minimize_bisection(problem).x) < 1e-4


@pytest.mark.parametrize("value", [0.0, -0.1, 0.6, float("nan")])
def test_projected_gradient_rejects_bad_decrease_constant(value):
    with pytest.raises(ValueError):
        ProjectedGradient(armijo_c=value)


def test_worked_iteration_counts(case):
    problem = reduced(case("B"))
    assert Newton().solve(problem, [40.0]).iterations == 1
    assert Newton().solve(problem, [20.0]).iterations == 2
    assert ConjugateGradient().solve(problem, [40.0]).iterations == 1
    assert ProjectedGradient().solve(reduced(case("A")), [40.0]).iterations <= 7
    history = GradientDescent(step=0.5).solve(problem, [40.0]).history
    expected = [problem.value([g]) for g in (40, 47.5, 51.025, 52.68175)]
    np.testing.assert_allclose(history[:4], expected)
    momentum = Momentum(step=0.5, momentum=0.3).solve(problem, [40.0]).history
    np.testing.assert_allclose(momentum[:4], [problem.value([g]) for g in (40, 47.5, 53.275, 55.47175)])


@pytest.mark.parametrize("solver", SMOOTH)
def test_max_iterations_status(case, solver):
    problem = PenaltyProblem(case("B"), 10, 70, 80, 100.0)
    result = solver(max_iterations=1, tolerance=1e-12).solve(problem, [40.0, 40.0])
    if solver is Newton:
        assert result.iterations == 1
    else:
        assert result.status == "max_iter" and not result.converged
    assert result.iterations <= 1


@pytest.mark.parametrize("solver", SMOOTH)
def test_time_budget_status(case, solver):
    result = solver(time_budget_s=1e-12).solve(reduced(case("B")), [40.0])
    assert result.status == "time_budget" and not result.converged
    assert result.feasible


def test_divergence_is_reported_as_numerical_error():
    problem = Quadratic(np.eye(2) * 10, np.zeros(2))
    result = GradientDescent(step=10.0, max_iterations=1000).solve(problem, [1.0, 1.0])
    assert result.status == "numerical_error" and not result.converged
    assert np.all(np.isfinite(result.x)) and np.isfinite(result.objective)


@pytest.mark.parametrize("solver", SMOOTH + [Subgradient])
@pytest.mark.parametrize("start", [[float("nan")], [float("inf")], [[40.0]]])
def test_bad_start_rejected(case, solver, start):
    with pytest.raises(ValueError):
        solver().solve(reduced(case("B"), nonsmooth=solver is Subgradient), start)


@pytest.mark.parametrize("solver", SMOOTH)
def test_smooth_solvers_refuse_nonsmooth_problem(case, solver):
    with pytest.raises(ValueError):
        solver().solve(reduced(case("C"), nonsmooth=True), [40.0])


@pytest.mark.parametrize(
    "make",
    [
        lambda: GradientDescent(step=0),
        lambda: Momentum(momentum=1.0),
        lambda: Subgradient(initial_step=-1),
        lambda: SGD(decay=0.4),
        lambda: SGD(batch_size=0),
        lambda: BFGS(line_search="guess"),
        lambda: Newton(tolerance=0),
        lambda: Newton(max_iterations=0),
    ],
)
def test_invalid_parameters_rejected(make):
    with pytest.raises(ValueError):
        make()


# ------------------------------------------------------------ higher dimensions
def random_quadratic(n, condition, seed):
    rng = np.random.default_rng(seed)
    basis, _ = np.linalg.qr(rng.normal(size=(n, n)))
    matrix = basis @ np.diag(np.geomspace(1, condition, n)) @ basis.T
    return Quadratic((matrix + matrix.T) / 2, rng.normal(size=n))


@pytest.mark.parametrize("solver", SMOOTH)
@pytest.mark.parametrize("n", [2, 5, 10])
def test_convex_quadratics(solver, n):
    problem = random_quadratic(n, condition=20, seed=n)
    result = solver(max_iterations=5000).solve(problem, np.zeros(n))
    assert result.converged, result.status
    np.testing.assert_allclose(result.x, problem.minimiser(), atol=1e-5)


@pytest.mark.parametrize("solver", [ConjugateGradient, BFGS])
@pytest.mark.parametrize("n", [2, 5, 10])
def test_finite_termination_on_quadratics(solver, n):
    result = solver().solve(random_quadratic(n, condition=100, seed=n), np.zeros(n))
    assert result.converged and result.iterations <= n


@pytest.mark.parametrize("solver", [Newton, BFGS, ConjugateGradient, ProjectedGradient])
def test_rosenbrock_two_dimensions(solver):
    result = solver(max_iterations=50_000).solve(Rosenbrock(), [-1.2, 1.0])
    assert result.converged, result.status
    np.testing.assert_allclose(result.x, [1, 1], atol=1e-4)


@pytest.mark.parametrize("solver", [Newton, BFGS])
def test_rosenbrock_five_dimensions(solver):
    result = solver(max_iterations=2000).solve(Rosenbrock(), np.full(5, 0.5))
    assert result.converged
    np.testing.assert_allclose(result.x, 1, atol=1e-4)


@pytest.mark.parametrize("solver", LINE_SEARCH)
def test_box_constrained_quadratic(solver):
    # Unconstrained minimiser (3, -2); with the box [0, 1]^2 it is (1, 0).
    problem = Quadratic([[2.0, 0.5], [0.5, 1.0]], [5.0, -0.5], lower=0.0, upper=1.0)
    result = solver().solve(problem, [0.5, 0.5])
    assert result.converged and result.feasible
    np.testing.assert_allclose(result.x, [1, 0], atol=1e-6)


@pytest.mark.parametrize("solver", LINE_SEARCH)
def test_random_box_constrained_quadratics(solver):
    rng = np.random.default_rng(10)
    for _ in range(100):
        base = random_quadratic(4, 30, int(rng.integers(1_000_000)))
        problem = Quadratic(base.matrix, 5 * base.vector, lower=-0.5, upper=0.5)
        result = solver(max_iterations=5000).solve(problem, rng.uniform(-0.5, 0.5, 4))
        assert result.converged and result.feasible, result.status


# ------------------------------------------------------------------ penalty form
@pytest.mark.parametrize("solver", SMOOTH)
@pytest.mark.parametrize(
    ("rho", "expected"),
    [(1, (58.943914, 30.826372)), (10, (54.741563, 26.462392)), (100, (54.211410, 25.911849))],
)
def test_penalty_form(case, solver, rho, expected):
    problem = PenaltyProblem(case("B"), 10, 70, 80, rho)
    result = solver(max_iterations=100_000).solve(problem, [40.0, 40.0])
    assert result.converged, result.status
    np.testing.assert_allclose(result.x, expected, atol=1e-4)


@pytest.mark.parametrize("rho", [1, 10, 100])
def test_penalty_finite_termination(case, rho):
    problem = PenaltyProblem(case("B"), 10, 70, 80, rho)
    assert Newton().solve(problem, [40.0, 40.0]).iterations == 1
    assert ConjugateGradient().solve(problem, [40.0, 40.0]).iterations == 2
    assert BFGS().solve(problem, [40.0, 40.0]).iterations == 2


def test_penalty_with_active_bounds(case):
    problem = PenaltyProblem(case("A"), 10, 70, 80, 100.0)
    reference = ProjectedGradient(max_iterations=100_000, tolerance=1e-9).solve(problem, [40.0, 40.0])
    axis = np.linspace(10, 70, 601)
    grid_best = min(problem.value(np.array([a, b])) for a in axis for b in axis)
    assert reference.converged and reference.objective <= grid_best + 1e-9
    for solver in SMOOTH:
        result = solver(max_iterations=100_000).solve(problem, [40.0, 40.0])
        assert result.converged, (solver.name, result.status)
        assert result.objective == pytest.approx(reference.objective, abs=1e-4)


# ------------------------------------------------------------------- nonsmooth
@pytest.mark.parametrize("start", [40.0, 10.0, 70.0, 500.0])
def test_subgradient_reaches_kink_optimum(case, start):
    problem = reduced(case("C"), nonsmooth=True)
    result = Subgradient(max_iterations=5000).solve(problem, [start])
    assert result.feasible and result.status in ("stalled", "max_iter", "converged")
    assert result.objective - 75 <= 1e-2
    assert result.x[0] == pytest.approx(60, abs=0.1)
    assert result.objective == pytest.approx(min(result.history))


def test_subgradient_worked_iterations(case):
    problem = reduced(case("C"), nonsmooth=True)
    history = Subgradient(initial_step=10, max_iterations=3).solve(problem, [40.0]).history
    expected = [problem.value([g]) for g in (40, 55, 59.242641, 61.237048)]
    np.testing.assert_allclose(history, expected, rtol=1e-6)


def test_subgradient_on_random_problems():
    rng = np.random.default_rng(11)
    for _ in range(50):
        problem = reduced(random_data(rng), nonsmooth=True)
        best = minimize_bisection(problem)
        start = rng.uniform(10, 70)
        result = Subgradient(max_iterations=5000).solve(problem, [start])
        # Relative gap: J_ns varies in scale with the random weights.
        assert result.objective - best.value <= 0.01 * max(1.0, best.value)
        assert result.objective <= problem.value([start]) + 1e-9


def test_subgradient_stalls_when_best_value_stops_improving(case):
    result = Subgradient(max_iterations=100_000, patience=50).solve(
        reduced(case("C"), nonsmooth=True), [40.0]
    )
    assert result.status == "stalled" and result.iterations < 100_000


# ------------------------------------------------------------------ stochastic
def test_sgd_is_reproducible(case):
    problem = StochasticProblem(case("B"), 10, 70, 80)
    first, second = (SGD(seed=3).solve(problem, [40.0]) for _ in range(2))
    np.testing.assert_array_equal(first.x, second.x)
    assert first.history == second.history
    assert SGD(seed=4).solve(problem, [40.0]).x[0] != first.x[0]


@pytest.mark.parametrize("name", ["A", "B", "C"])
def test_sgd_approaches_expected_optimum(case, name):
    problem = StochasticProblem(make_data(CASE_QUEUES[name]), 10, 70, 80)
    best = minimize_bisection(problem)
    results = [SGD(seed=s, max_iterations=2000).solve(problem, [40.0]) for s in range(10)]
    errors = [abs(r.x[0] - best.x) for r in results]
    assert np.mean(errors) < 0.25 and max(errors) < 1.0
    assert all(r.feasible and r.status == "max_iter" for r in results)


def test_sgd_needs_a_stochastic_problem(case):
    with pytest.raises(TypeError):
        SGD().solve(reduced(case("B")), [40.0])


# -------------------------------------------------------------------- registry
@pytest.mark.parametrize("name", SOLVER_NAMES)
def test_every_configured_solver_can_be_created(name):
    solver = create_solver(SolverParams(name, 1e-5, 123, 0.5))
    assert solver.name == name
    assert (solver.tolerance, solver.max_iterations, solver.time_budget_s) == (1e-5, 123, 0.5)


def test_unknown_solver_rejected():
    with pytest.raises(ValueError):
        create_solver(SolverParams("simplex", 1e-5, 10, 0.5))
