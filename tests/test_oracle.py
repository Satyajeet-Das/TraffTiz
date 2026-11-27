import numpy as np
import pytest
from conftest import make_data, random_data

from optitraffic.optimization.problems import ReducedProblem
from optitraffic.optimization.solvers.oracle import minimize_bisection, minimize_grid

BOTH = [minimize_bisection, minimize_grid]


def reduced(data, nonsmooth=False, g_min=10, g_max=70, budget=80):
    return ReducedProblem(data, g_min, g_max, budget, nonsmooth=nonsmooth)


@pytest.mark.parametrize("oracle", BOTH)
@pytest.mark.parametrize(
    ("name", "nonsmooth", "x", "value"),
    [("A", False, 70.0, 797.0), ("B", False, 57.4 / 1.06, 308.867925), ("C", True, 60.0, 75.0)],
)
def test_reference_cases(case, oracle, name, nonsmooth, x, value):
    result = oracle(reduced(case(name), nonsmooth))
    assert result.x == pytest.approx(x, abs=1e-3)
    assert result.value == pytest.approx(value, abs=1e-5)
    np.testing.assert_allclose(result.green, (result.x, 80 - result.x))


def test_bisection_is_accurate_to_tolerance(case):
    assert minimize_bisection(reduced(case("B"))).x == pytest.approx(57.4 / 1.06, abs=1e-9)
    assert minimize_bisection(reduced(case("C"), True)).x == pytest.approx(60, abs=1e-9)


@pytest.mark.parametrize("oracle", BOTH)
def test_lower_bound_optimum(oracle):
    result = oracle(reduced(make_data((0, 60))))
    assert result.x == pytest.approx(10)


@pytest.mark.parametrize("oracle", BOTH)
def test_single_feasible_point(case, oracle):
    assert oracle(reduced(case("B"), g_min=40)).x == 40


@pytest.mark.parametrize("nonsmooth", [False, True])
@pytest.mark.parametrize("oracle", BOTH)
def test_flat_objective_returns_half_budget(oracle, nonsmooth):
    data = make_data((0, 0), arrival_rate=(0, 0))
    result = oracle(reduced(data, nonsmooth))
    assert result.x == pytest.approx(40)
    assert result.minimiser_interval == pytest.approx((10, 70))


@pytest.mark.parametrize("oracle", BOTH)
def test_flat_interval_not_containing_half_budget(oracle):
    # NS queue clears only from g = 60; EW has nothing to clear.
    data = make_data((30, 0), arrival_rate=(0, 0))
    result = oracle(reduced(data))
    assert result.x == pytest.approx(60, abs=1e-3)
    assert result.minimiser_interval == pytest.approx((60, 70), abs=1e-3)


@pytest.mark.parametrize("queue", [(0, 15), (15, 0), (0, 0)])
@pytest.mark.parametrize("nonsmooth", [False, True])
def test_empty_queues(queue, nonsmooth):
    problem = reduced(make_data(queue), nonsmooth)
    assert minimize_bisection(problem).value <= minimize_grid(problem).value + 1e-9


@pytest.mark.parametrize("nonsmooth", [False, True])
def test_bisection_agrees_with_grid_on_random_problems(nonsmooth):
    rng = np.random.default_rng(6)
    for _ in range(200):
        g_min, g_max = float(rng.uniform(5, 35)), float(rng.uniform(45, 75))
        problem = reduced(random_data(rng), nonsmooth, g_min, g_max)
        exact, grid = minimize_bisection(problem), minimize_grid(problem)
        assert problem.lower <= exact.x <= problem.upper
        # Bisection is never worse, and the grid is within its spacing.
        assert exact.value <= grid.value + 1e-8
        slope = max(abs(d) for x in (problem.lower, problem.upper)
                    for d in problem.one_sided_derivatives(x))
        assert grid.value - exact.value <= slope * 1e-3 + 1e-8
        start = rng.uniform(problem.lower, problem.upper)
        assert exact.value <= problem.value([start]) + 1e-8


@pytest.mark.parametrize("argument", [0.0, -1.0, float("nan")])
def test_invalid_resolution_rejected(case, argument):
    problem = reduced(case("A"))
    with pytest.raises(ValueError):
        minimize_grid(problem, step=argument)
    with pytest.raises(ValueError):
        minimize_bisection(problem, tolerance=argument)
