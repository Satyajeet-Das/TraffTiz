"""Line searches. Both return the new point, or None if no acceptable step exists."""

from __future__ import annotations

import math

import numpy as np

SUFFICIENT_DECREASE = 1e-4


def sufficient_decrease(problem, x, f, g, candidate, value) -> bool:
    """Armijo test f(x+) <= f(x) + c * g.(x+ - x), safe near machine precision.

    When the predicted decrease is too small to be measured in f, subtracting two
    objective values is meaningless and would accept steps that make no progress.
    The decrease is then estimated from gradients with the trapezoidal rule,
    0.5 * (g + g+).(x+ - x), which is exact for a quadratic.
    """
    step = candidate - x
    slope = float(g @ step)
    if not (slope < 0 and math.isfinite(value)):
        return False
    noise = 16.0 * np.finfo(float).eps * abs(f)
    if -slope > 1000.0 * noise:
        return value <= f + SUFFICIENT_DECREASE * slope
    estimate = 0.5 * (slope + float(problem.gradient(candidate) @ step))
    return value <= f + noise and estimate <= SUFFICIENT_DECREASE * slope


def armijo_search(
    problem,
    x: np.ndarray,
    f: float,
    g: np.ndarray,
    direction: np.ndarray,
    initial_step: float = 1.0,
    shrink: float = 0.5,
    max_backtracks: int = 60,
) -> tuple[np.ndarray, float] | None:
    """Backtracking along the projection arc P(x + t*direction).

    Accepts t when `sufficient_decrease` holds. Returns (x+, t).
    """
    step = initial_step
    for _ in range(max_backtracks):
        candidate = problem.project(x + step * direction)
        if sufficient_decrease(problem, x, f, g, candidate, problem.value(candidate)):
            return candidate, step
        step *= shrink
    return None


def exact_search(
    problem,
    x: np.ndarray,
    f: float,
    g: np.ndarray,
    direction: np.ndarray,
    tolerance: float = 1e-10,
) -> np.ndarray | None:
    """Find t > 0 where the directional derivative vanishes (ignoring bounds).

    The step is bracketed by doubling, then refined by the Illinois form of
    regula falsi, which is exact in one interpolation when the derivative is
    linear (a quadratic objective). The result may lie outside the bounds; the
    caller must check. Returns None if the direction is not a descent direction
    or the point found does not decrease the objective sufficiently.
    """
    start_slope = float(g @ direction)
    if not start_slope < 0:
        return None

    def slope(t: float) -> float:
        value = float(problem.gradient(x + t * direction) @ direction)
        return value if math.isfinite(value) else -start_slope  # too far: treat as uphill

    low, low_slope = 0.0, start_slope
    high, high_slope = 1.0, slope(1.0)
    for _ in range(60):
        if high_slope >= 0:
            break
        low, low_slope = high, high_slope
        high *= 2.0
        high_slope = slope(high)

    step, side = high, 0
    if high_slope > 0:
        for _ in range(200):
            step = high - high_slope * (high - low) / (high_slope - low_slope)
            if not low < step < high:
                step = 0.5 * (low + high)
            if not low < step < high:
                break
            current = slope(step)
            if abs(current) <= tolerance * abs(start_slope):
                break
            if current < 0:
                low, low_slope = step, current
                if side == -1:
                    high_slope *= 0.5
                side = -1
            else:
                high, high_slope = step, current
                if side == 1:
                    low_slope *= 0.5
                side = 1

    candidate = x + step * direction
    if not sufficient_decrease(problem, x, f, g, candidate, problem.value(candidate)):
        return None
    return candidate
