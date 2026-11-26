import numpy as np
import pytest

from optitraffic.optimization.constraints import (
    feasible_interval,
    is_feasible,
    project_interval,
    split_green,
)


@pytest.mark.parametrize(
    ("g_min", "g_max", "budget", "expected"),
    [
        (10, 70, 80, (10, 70)),
        (10, 60, 80, (20, 60)),  # g_max limits the other phase
        (30, 70, 80, (30, 50)),
        (40, 70, 80, (40, 40)),  # single feasible point
        (10, 40, 80, (40, 40)),
    ],
)
def test_feasible_interval(g_min, g_max, budget, expected):
    assert feasible_interval(g_min, g_max, budget) == expected


@pytest.mark.parametrize(("g_min", "g_max", "budget"), [(41, 70, 80), (10, 39, 80), (50, 40, 90)])
def test_infeasible_limits_rejected(g_min, g_max, budget):
    with pytest.raises(ValueError):
        feasible_interval(g_min, g_max, budget)


@pytest.mark.parametrize(("x", "expected"), [(-5, 10), (10, 10), (33.3, 33.3), (70, 70), (500, 70)])
def test_projection(x, expected):
    assert project_interval(x, 10, 70) == expected
    assert project_interval(project_interval(x, 10, 70), 10, 70) == expected


def test_projection_of_array():
    np.testing.assert_allclose(project_interval(np.array([0.0, 40.0, 90.0]), 10, 70), [10, 40, 70])


def test_projection_rejects_nan():
    with pytest.raises(ValueError):
        project_interval(float("nan"), 10, 70)


def test_projected_plans_satisfy_all_constraints():
    rng = np.random.default_rng(4)
    for _ in range(1000):
        g_min, g_max = sorted(rng.uniform(5, 75, 2))
        budget = rng.uniform(2 * g_min, 2 * g_max)
        low, high = feasible_interval(g_min, g_max, budget)
        green = split_green(project_interval(rng.uniform(-50, 150), low, high), budget)
        assert is_feasible(green, g_min, g_max, budget)


@pytest.mark.parametrize(
    "green",
    [(9, 71), (71, 9), (40, 41), (40, 39), (float("nan"), 40), (40,), (20, 20, 40)],
)
def test_infeasible_plans_detected(green):
    assert not is_feasible(green, 10, 70, 80)
