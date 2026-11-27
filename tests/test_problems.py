import numpy as np
import pytest
from conftest import random_data

from optitraffic.optimization.problems import ReducedProblem
from optitraffic.types import SignalParams

SIGNAL = SignalParams(cycle_s=90, yellow_s=3, all_red_s=2, g_min_s=10, g_max_s=70)


def reduced(data, nonsmooth=False):
    return ReducedProblem.from_signal(data, SIGNAL, nonsmooth=nonsmooth)


def test_bounds_and_plan(case):
    problem = reduced(case("A"))
    assert (problem.lower, problem.upper) == (10, 70)
    np.testing.assert_allclose(problem.green([55.0]), (55, 25))


def test_case_a_derivatives(case):
    problem = reduced(case("A"))
    assert problem.value([40.0]) == pytest.approx(1519)
    np.testing.assert_allclose(problem.gradient([40.0]), [-39])
    assert problem.hessian([40.0]).shape == (1, 1)
    assert problem.lipschitz_constant() == pytest.approx(1.06)


def test_residual_is_zero_at_a_bound_optimum_with_nonzero_gradient(case):
    problem = reduced(case("A"))
    assert problem.gradient([70.0])[0] == pytest.approx(-8.2)
    assert problem.residual([70.0]) == 0
    assert problem.residual([40.0]) > 0


def test_vectorised_values_match_single_values(case):
    for nonsmooth in (False, True):
        problem = reduced(case("C"), nonsmooth)
        xs = np.linspace(10, 70, 13)
        np.testing.assert_allclose(problem.values(xs), [problem.value([x]) for x in xs])


def test_derivative_matches_central_difference():
    rng = np.random.default_rng(5)
    h = 1e-5
    for _ in range(300):
        problem = reduced(random_data(rng))
        x = rng.uniform(11, 69)
        if any(abs(x - k) < 0.1 for k in problem.kinks()):
            continue
        numeric = (problem.value([x + h]) - problem.value([x - h])) / (2 * h)
        exact = problem.gradient([x])[0]
        assert abs(numeric - exact) / max(1, abs(exact)) < 1e-6
        second = (problem.gradient([x + h])[0] - problem.gradient([x - h])[0]) / (2 * h)
        assert second == pytest.approx(problem.hessian([x])[0, 0], rel=1e-5, abs=1e-6)


def test_one_sided_derivatives_at_kink(case):
    problem = reduced(case("C"), nonsmooth=True)
    left, right = problem.one_sided_derivatives(60.0)
    assert left == pytest.approx(-0.3)
    assert right == pytest.approx(0.2)
    assert 60.0 in problem.kinks()


def test_one_sided_derivatives_agree_for_smooth_objective(case):
    problem = reduced(case("B"))
    left, right = problem.one_sided_derivatives(32.0)
    assert left == pytest.approx(right)
    assert left == pytest.approx(-23.48)


def test_nonsmooth_problem_has_no_hessian(case):
    with pytest.raises(NotImplementedError):
        reduced(case("C"), nonsmooth=True).hessian([40.0])


def test_project(case):
    np.testing.assert_allclose(reduced(case("A")).project([99.0]), [70])


@pytest.mark.parametrize("x", [40.0, [40.0, 40.0], [float("nan")]])
def test_wrong_shape_or_nan_rejected(case, x):
    with pytest.raises(ValueError):
        reduced(case("A")).value(x)
