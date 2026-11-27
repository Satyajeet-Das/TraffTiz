"""Reference solutions for the reduced problem (Technical Design section 6.4).

These check the real solvers; they are not among the algorithms being studied.

If the objective is flat over an interval of minimisers, both methods return the
point of that interval nearest to half the green budget.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from optitraffic.optimization.constraints import project_interval
from optitraffic.optimization.problems import ReducedProblem


@dataclass(frozen=True)
class OracleResult:
    x: float  # g_NS
    value: float
    green: tuple[float, float]
    minimiser_interval: tuple[float, float]


def minimize_bisection(problem: ReducedProblem, tolerance: float = 1e-10) -> OracleResult:
    """Bisection on the one-sided derivatives of the convex function phi.

    The minimisers form the interval from the first point whose right derivative
    is >= 0 to the last point whose left derivative is <= 0. Works for J and J_ns.
    """
    _require_positive(tolerance, "tolerance")
    low, high = problem.lower, problem.upper

    start = _first_true(lambda g: problem.one_sided_derivatives(g)[1] >= 0, low, high, tolerance)[1]
    end = _first_true(lambda g: problem.one_sided_derivatives(g)[0] > 0, low, high, tolerance)[0]
    # For a unique minimiser the two estimates may cross by up to the tolerance.
    interval = (min(start, end), max(start, end))
    return _result(problem, project_interval(problem.budget / 2, *interval), interval)


def minimize_grid(problem: ReducedProblem, step: float = 1e-3) -> OracleResult:
    """Dense grid that also contains the kinks and half the budget."""
    _require_positive(step, "step")
    low, high = problem.lower, problem.upper
    count = math.ceil((high - low) / step) + 1
    middle = project_interval(problem.budget / 2, low, high)
    points = np.unique(np.concatenate([np.linspace(low, high, count), problem.kinks(), [middle]]))
    values = problem.values(points)
    best = float(values.min())
    ties = points[values <= best + 1e-12 * max(1.0, abs(best))]
    x = float(ties[np.argmin(np.abs(ties - problem.budget / 2))])
    return _result(problem, x, (float(ties[0]), float(ties[-1])))


def _first_true(
    predicate: Callable[[float], bool], low: float, high: float, tolerance: float
) -> tuple[float, float]:
    """Bracket the switch of a predicate that is False then True on [low, high]."""
    if predicate(low):
        return (low, low)
    if not predicate(high):
        return (high, high)
    while high - low > tolerance:
        middle = 0.5 * (low + high)
        if not low < middle < high:  # reached floating-point resolution
            break
        if predicate(middle):
            high = middle
        else:
            low = middle
    return (low, high)


def _result(problem: ReducedProblem, x: float, interval: tuple[float, float]) -> OracleResult:
    ns, ew = problem.green([x])
    return OracleResult(x, problem.value([x]), (float(ns), float(ew)), interval)


def _require_positive(value: float, name: str) -> None:
    if not (math.isfinite(value) and value > 0):
        raise ValueError(f"{name} must be finite and positive; got {value}")
