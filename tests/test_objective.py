import numpy as np
import pytest
from conftest import make_data, random_data

from optitraffic.modelling.queue import raw_queue
from optitraffic.optimization import objective


def central(f, x, h=1e-5):
    x = np.asarray(x, float)
    return np.array([(f(x + h * e) - f(x - h * e)) / (2 * h) for e in np.eye(len(x))])


def smooth_points(n=300, seed=2):
    """Random problems and plans at least 0.01 veh away from any queue kink."""
    rng = np.random.default_rng(seed)
    while n:
        data, green = random_data(rng), rng.uniform(10, 70, 2)
        if np.all(np.abs(raw_queue(data, green)) > 0.01):
            n -= 1
            yield data, green


def relative_error(approx, exact):
    return np.max(np.abs(approx - exact) / np.maximum(1.0, np.abs(exact)))


def test_case_a_values(case):
    data, green = case("A"), (40.0, 40.0)
    assert objective.value(data, green) == pytest.approx(1519)
    np.testing.assert_allclose(objective.gradient(data, green), (-40, -1))
    np.testing.assert_allclose(objective.hessian(data, green), np.diag([0.54, 0.02]))


def test_case_b_and_c_values(case):
    assert objective.value(case("B"), (40, 40)) == pytest.approx(415)
    assert objective.ns_value(case("C"), (40, 40)) == pytest.approx(93)
    v = objective.subgradient(case("C"), (40, 40))
    assert v[0] - v[1] == pytest.approx(-1.5)


def test_value_broadcasts(case):
    plans = np.array([[40.0, 40.0], [70.0, 10.0]])
    np.testing.assert_allclose(objective.value(case("A"), plans), [1519, 797])
    assert objective.ns_value(case("C"), plans).shape == (2,)


def test_gradient_matches_central_difference():
    for data, green in smooth_points():
        numeric = central(lambda g: objective.value(data, g), green)
        assert relative_error(numeric, objective.gradient(data, green)) < 1e-6


def test_hessian_matches_central_difference():
    for data, green in smooth_points():
        numeric = np.array(
            [central(lambda g, i=i: objective.gradient(data, g)[i], green) for i in range(2)]
        )
        assert relative_error(numeric, objective.hessian(data, green)) < 1e-6


def test_nonsmooth_subgradient_matches_central_difference_away_from_kinks():
    for data, green in smooth_points():
        numeric = central(lambda g: objective.ns_value(data, g), green)
        assert relative_error(numeric, objective.subgradient(data, green)) < 1e-6


def test_gradient_is_continuous_at_kink(case):
    data = case("B")  # EW queue reaches zero at g_EW = 48
    below = objective.gradient(data, (32, 48 - 1e-9))
    above = objective.gradient(data, (32, 48 + 1e-9))
    np.testing.assert_allclose(below, above, atol=1e-8)


def test_hessian_at_kink_uses_inactive_value(case):
    data = case("B")
    assert objective.hessian(data, (32, 48))[1, 1] == pytest.approx(0.02)
    assert objective.hessian(data, (32, 47.999))[1, 1] == pytest.approx(0.52)


@pytest.mark.parametrize("theta", [0.0, 0.3, 1.0])
def test_subgradient_inequality_at_kinks(theta):
    rng = np.random.default_rng(3)
    for _ in range(2000):
        base = random_data(rng)
        x, y = rng.uniform(10, 70, 2), rng.uniform(10, 70, 2)
        # Choose the queue so that one approach sits on its kink at x.
        i = int(rng.integers(2))
        queue = list(base.queue)
        queue[i] = base.discharge_rate_vps[i] * x[i] - base.arrival_rate[i] * base.cycle_s
        if queue[i] < 0:
            continue
        data = make_data(queue, base.arrival_rate, base.beta, base.discharge_rate_vps, base.queue_weight)
        v = objective.subgradient(data, x, theta_at_kink=theta)
        assert objective.ns_value(data, y) >= objective.ns_value(data, x) + v @ (y - x) - 1e-8


def test_theta_selects_the_element_at_a_kink(case):
    data = case("C")  # EW queue is exactly zero at g_EW = 20
    low = objective.subgradient(data, (60, 20), theta_at_kink=0.0)
    high = objective.subgradient(data, (60, 20), theta_at_kink=1.0)
    assert low[1] - high[1] == pytest.approx(0.5)
    assert low[0] == high[0]


@pytest.mark.parametrize("theta", [-0.1, 1.1, float("nan")])
def test_theta_outside_unit_interval_rejected(case, theta):
    with pytest.raises(ValueError):
        objective.subgradient(case("C"), (60, 20), theta_at_kink=theta)
