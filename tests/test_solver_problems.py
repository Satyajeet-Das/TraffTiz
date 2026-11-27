"""Penalty, stochastic and test-function problems (tracks T2, T3 and SGD)."""

import numpy as np
import pytest
from conftest import make_data

from optitraffic.optimization.problems import PenaltyProblem, StochasticProblem
from optitraffic.optimization.test_functions import Quadratic, Rosenbrock


def central(f, x, h=1e-6):
    return np.array([(f(x + h * e) - f(x - h * e)) / (2 * h) for e in np.eye(len(x))])


def check_derivatives(problem, x, hessian=True):
    np.testing.assert_allclose(central(problem.value, x), problem.gradient(x), rtol=1e-5, atol=1e-5)
    if hessian:
        numeric = np.array([central(lambda p, i=i: problem.gradient(p)[i], x) for i in range(len(x))])
        np.testing.assert_allclose(numeric, problem.hessian(x), rtol=1e-5, atol=1e-5)


@pytest.mark.parametrize("rho", [1.0, 10.0, 100.0])
def test_penalty_values_and_derivatives(case, rho):
    problem = PenaltyProblem(case("B"), 10, 70, 80, rho)
    x = np.array([40.0, 45.0])
    assert problem.violation(x) == 5
    plain = PenaltyProblem(case("B"), 10, 70, 80, 0.0)
    assert problem.value(x) == pytest.approx(plain.value(x) + rho / 2 * 25)
    check_derivatives(problem, x)
    np.testing.assert_allclose(problem.project(np.array([0.0, 99.0])), [10, 70])
    assert np.linalg.eigvalsh(problem.hessian(x))[-1] <= problem.lipschitz_constant() + 1e-12


def test_penalty_rejects_negative_rho(case):
    with pytest.raises(ValueError):
        PenaltyProblem(case("B"), 10, 70, 80, -1)


def test_quadratic():
    problem = Quadratic([[3.0, 1.0], [1.0, 2.0]], [1.0, 1.0])
    check_derivatives(problem, np.array([0.3, -0.7]))
    np.testing.assert_allclose(problem.gradient(problem.minimiser()), 0, atol=1e-12)
    assert problem.lipschitz_constant() == pytest.approx(np.linalg.eigvalsh([[3, 1], [1, 2]])[-1])


@pytest.mark.parametrize("matrix", [[[1.0, 2.0], [0.0, 1.0]], [[1.0, 0.0], [0.0, -1.0]]])
def test_quadratic_requires_symmetric_positive_definite(matrix):
    with pytest.raises(ValueError):
        Quadratic(matrix, [0.0, 0.0])


def test_rosenbrock():
    problem = Rosenbrock()
    assert problem.value(np.ones(4)) == 0
    np.testing.assert_allclose(problem.gradient(np.ones(4)), 0)
    check_derivatives(problem, np.array([-1.2, 1.0, 0.5, 0.8]))


def test_stochastic_expected_value_matches_sampling(case):
    data = case("B")
    problem = StochasticProblem(data, 10, 70, 80)
    rng = np.random.default_rng(7)
    arrivals = rng.poisson(np.array(data.arrival_rate) * data.cycle_s, size=(400_000, 2))
    green = problem.green([50.0])
    queues = np.maximum(0, np.array(data.queue) + arrivals - 0.5 * green)
    sampled = np.mean(np.sum(queues**2, axis=1)) + 0.1 * np.sum(
        np.array(data.arrival_rate) * (90 - green) ** 2
    )
    assert problem.value([50.0]) == pytest.approx(sampled, rel=5e-3)
    check_derivatives(problem, np.array([50.0]), hessian=False)


def test_stochastic_gradient_is_unbiased_and_seeded(case):
    problem = StochasticProblem(case("B"), 10, 70, 80)
    x = np.array([45.0])
    first = problem.sample_gradient(x, np.random.default_rng(1), 8)
    np.testing.assert_array_equal(first, problem.sample_gradient(x, np.random.default_rng(1), 8))
    mean = problem.sample_gradient(x, np.random.default_rng(2), 400_000)
    np.testing.assert_allclose(mean, problem.gradient(x), atol=0.05)


def test_expected_value_is_at_least_deterministic(case):
    problem = StochasticProblem(case("B"), 10, 70, 80)
    deterministic = problem.deterministic()
    for x in np.linspace(10, 70, 13):
        assert problem.value([x]) >= deterministic.value([x]) - 1e-9


def test_zero_arrivals_have_no_randomness():
    problem = StochasticProblem(make_data((20, 15), arrival_rate=(0, 0)), 10, 70, 80)
    assert problem.value([40.0]) == pytest.approx(problem.deterministic().value([40.0]))
