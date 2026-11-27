"""Optimization problems (Technical Design sections 5.3 and 6.5).

Variables are 1-D arrays so that solvers work in any dimension. Only the
reduced one-variable problem exists so far; the penalty form, stochastic
problem and test functions belong to milestone M6.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike

from optitraffic.optimization import objective
from optitraffic.optimization.constraints import feasible_interval, project_interval, split_green
from optitraffic.types import ObjectiveData, SignalParams


class ReducedProblem:
    """phi(g) = J(g, G - g) for g = g_NS in [lower, upper].

    With `nonsmooth=True` the objective is J_ns and `gradient` returns a
    subgradient.
    """

    def __init__(
        self,
        data: ObjectiveData,
        g_min: float,
        g_max: float,
        budget: float,
        nonsmooth: bool = False,
    ) -> None:
        self.data = data
        self.budget = float(budget)
        self.nonsmooth = nonsmooth
        self.lower, self.upper = feasible_interval(g_min, g_max, budget)

    @classmethod
    def from_signal(
        cls, data: ObjectiveData, signal: SignalParams, nonsmooth: bool = False
    ) -> ReducedProblem:
        return cls(data, signal.g_min_s, signal.g_max_s, signal.green_budget_s, nonsmooth)

    def green(self, x: ArrayLike) -> np.ndarray:
        """Full plan (NS, EW) for the variable x = [g_NS]."""
        return split_green(self._scalar(x), self.budget)

    def value(self, x: ArrayLike) -> float:
        return float(self._objective(self.green(x)))

    def values(self, points: ArrayLike) -> np.ndarray:
        """Objective at many values of g_NS (a 1-D array)."""
        g = np.asarray(points, dtype=float)
        return self._objective(np.stack([g, self.budget - g], axis=-1))

    def gradient(self, x: ArrayLike) -> np.ndarray:
        derivative = objective.subgradient if self.nonsmooth else objective.gradient
        d = derivative(self.data, self.green(x))
        return np.array([d[0] - d[1]])  # minus because g_EW = G - g_NS

    def one_sided_derivatives(self, g_ns: float) -> tuple[float, float]:
        """Left and right derivatives of phi. They differ only at J_ns kinks."""
        if not self.nonsmooth:
            d = float(self.gradient([g_ns])[0])
            return (d, d)
        green = split_green(g_ns, self.budget)
        # Increasing g_NS empties the NS queue and lengthens the EW queue.
        left = objective.subgradient(self.data, green, theta_at_kink=(1.0, 0.0))
        right = objective.subgradient(self.data, green, theta_at_kink=(0.0, 1.0))
        return (float(left[0] - left[1]), float(right[0] - right[1]))

    def hessian(self, x: ArrayLike) -> np.ndarray:
        if self.nonsmooth:
            raise NotImplementedError("J_ns is not twice differentiable")
        diagonal = np.diag(objective.hessian(self.data, self.green(x)))
        return np.array([[diagonal.sum()]])

    def project(self, x: ArrayLike) -> np.ndarray:
        return np.array([project_interval(self._scalar(x), self.lower, self.upper)])

    def residual(self, x: ArrayLike) -> float:
        """Projected-gradient residual |x - P(x - phi'(x))|.

        Zero at a minimiser of J. Not a valid stopping test for J_ns, whose
        chosen subgradient need not vanish at a minimiser.
        """
        point = np.asarray(x, dtype=float)
        return float(np.linalg.norm(point - self.project(point - self.gradient(point))))

    def lipschitz_constant(self) -> float:
        """Lipschitz constant of phi' (smooth objective only)."""
        if self.nonsmooth:
            raise NotImplementedError("J_ns has a discontinuous derivative")
        d = self.data
        w, mu, lam = (np.array(v) for v in (d.queue_weight, d.discharge_rate_vps, d.arrival_rate))
        return float(np.sum(2.0 * w * mu**2 + 2.0 * d.beta * lam))

    def kinks(self) -> list[float]:
        """Values of g_NS in [lower, upper] where a predicted queue reaches zero."""
        d = self.data
        empty = [
            (q + lam * d.cycle_s) / mu
            for q, lam, mu in zip(d.queue, d.arrival_rate, d.discharge_rate_vps)
        ]
        candidates = (empty[0], self.budget - empty[1])
        return sorted(k for k in candidates if self.lower <= k <= self.upper)

    def _objective(self, green: np.ndarray) -> np.ndarray:
        function = objective.ns_value if self.nonsmooth else objective.value
        return function(self.data, green)

    @staticmethod
    def _scalar(x: ArrayLike) -> float:
        point = np.asarray(x, dtype=float)
        if point.shape != (1,) or not np.isfinite(point[0]):
            raise ValueError(f"x must be a finite array of shape (1,); got {point}")
        return float(point[0])
