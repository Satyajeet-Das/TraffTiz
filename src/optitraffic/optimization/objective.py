"""Objectives and derivatives (PRD section 6.4, Technical Design section 5.2).

    J(g)    = sum w Q^2 + beta * sum lambda (C - g)^2    convex, C1
    J_ns(g) = sum w Q   + beta * sum lambda (C - g)^2    convex, nonsmooth

Both are functions of the two green times (NS, EW), before the cycle constraint
is applied. J and J_ns have different units and must not be compared.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike

from optitraffic.modelling.queue import predict_queue, raw_queue
from optitraffic.types import ObjectiveData


def _red_time_term(data: ObjectiveData, g: np.ndarray) -> np.ndarray:
    return data.beta * np.sum(np.array(data.arrival_rate) * (data.cycle_s - g) ** 2, axis=-1)


def _red_time_gradient(data: ObjectiveData, g: np.ndarray) -> np.ndarray:
    return -2.0 * data.beta * np.array(data.arrival_rate) * (data.cycle_s - g)


def value(data: ObjectiveData, green: ArrayLike) -> np.ndarray:
    """J. Returns a scalar for one plan, or an array for plans of shape (..., 2)."""
    g = np.asarray(green, dtype=float)
    queue = predict_queue(data, g)
    return np.sum(np.array(data.queue_weight) * queue**2, axis=-1) + _red_time_term(data, g)


def gradient(data: ObjectiveData, green: ArrayLike) -> np.ndarray:
    """Gradient of J for one plan. Continuous everywhere."""
    g = np.asarray(green, dtype=float)
    w, mu = np.array(data.queue_weight), np.array(data.discharge_rate_vps)
    return -2.0 * w * mu * predict_queue(data, g) + _red_time_gradient(data, g)


def hessian(data: ObjectiveData, green: ArrayLike) -> np.ndarray:
    """Diagonal Hessian of J for one plan.

    It jumps where a queue reaches zero; at that point the inactive value
    ([a > 0] = 0) is used.
    """
    g = np.asarray(green, dtype=float)
    w, mu = np.array(data.queue_weight), np.array(data.discharge_rate_vps)
    active = raw_queue(data, g) > 0
    return np.diag(2.0 * w * mu**2 * active + 2.0 * data.beta * np.array(data.arrival_rate))


def ns_value(data: ObjectiveData, green: ArrayLike) -> np.ndarray:
    """J_ns, with the same shapes as `value`."""
    g = np.asarray(green, dtype=float)
    queue = predict_queue(data, g)
    return np.sum(np.array(data.queue_weight) * queue, axis=-1) + _red_time_term(data, g)


def subgradient(data: ObjectiveData, green: ArrayLike, theta_at_kink: ArrayLike = 0.0) -> np.ndarray:
    """One subgradient of J_ns for one plan.

    `theta_at_kink` in [0, 1] (a scalar or one value per phase) selects the
    element used where a raw queue is exactly zero.
    """
    theta_kink = np.broadcast_to(np.asarray(theta_at_kink, dtype=float), (2,))
    if not np.all((theta_kink >= 0) & (theta_kink <= 1)):
        raise ValueError(f"theta_at_kink must lie in [0, 1]; got {theta_at_kink}")
    g = np.asarray(green, dtype=float)
    a = raw_queue(data, g)
    theta = np.where(a > 0, 1.0, np.where(a < 0, 0.0, theta_kink))
    w, mu = np.array(data.queue_weight), np.array(data.discharge_rate_vps)
    return -w * mu * theta + _red_time_gradient(data, g)
