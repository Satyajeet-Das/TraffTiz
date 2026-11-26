"""Traffic optimization problems (Technical Design sections 5.3, 6.3 and 6.5).

Variables are 1-D arrays so that solvers work in any dimension. Standard test
functions are in `test_functions.py`.
"""

from __future__ import annotations

import math

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


class StochasticProblem(ReducedProblem):
    """Expected J when arrivals per cycle are Poisson with mean lambda*C.

        F(g) = E[sum w max(0, q + A - mu g)^2] + beta sum lambda (C - g)^2

    The expectation is computed exactly from the Poisson probabilities (the far
    tail is dropped), so `value` and `gradient` give a reference for SGD.
    """

    def __init__(self, data: ObjectiveData, g_min: float, g_max: float, budget: float) -> None:
        super().__init__(data, g_min, g_max, budget)
        self._means = np.array(data.arrival_rate) * data.cycle_s
        top = self._means.max()
        self._counts = np.arange(int(top + 12.0 * math.sqrt(top) + 20))
        self._probabilities = np.stack([_poisson(mean, self._counts) for mean in self._means])

    def deterministic(self) -> ReducedProblem:
        """The problem with each arrival count replaced by its mean."""
        return ReducedProblem(self.data, self.lower, self.upper, self.budget)

    def gradient(self, x: ArrayLike) -> np.ndarray:
        green = self.green(x)
        leftover = self._leftover(green)  # (2, counts)
        expected = np.sum(self._probabilities * leftover, axis=-1)
        return self._reduced_gradient(green, expected)

    def sample_gradient(self, x: ArrayLike, rng: np.random.Generator, batch: int) -> np.ndarray:
        """Unbiased estimate of the gradient from `batch` sampled cycles."""
        green = self.green(x)
        d = self.data
        arrivals = rng.poisson(self._means, size=(batch, 2))
        leftover = np.maximum(
            0.0, np.array(d.queue) + arrivals - np.array(d.discharge_rate_vps) * green
        )
        return self._reduced_gradient(green, leftover.mean(axis=0))

    def hessian(self, x: ArrayLike) -> np.ndarray:
        raise NotImplementedError("not needed by any solver of the stochastic problem")

    def _leftover(self, green: np.ndarray) -> np.ndarray:
        """Residual queue for every arrival count, shape (..., 2, counts)."""
        d = self.data
        base = np.array(d.queue) - np.array(d.discharge_rate_vps) * green
        return np.maximum(0.0, base[..., None] + self._counts)

    def _reduced_gradient(self, green: np.ndarray, mean_queue: np.ndarray) -> np.ndarray:
        d = self.data
        w, mu, lam = (np.array(v) for v in (d.queue_weight, d.discharge_rate_vps, d.arrival_rate))
        full = -2.0 * w * mu * mean_queue - 2.0 * d.beta * lam * (d.cycle_s - green)
        return np.array([full[0] - full[1]])

    def _objective(self, green: np.ndarray) -> np.ndarray:
        d = self.data
        squares = np.sum(self._probabilities * self._leftover(green) ** 2, axis=-1)
        red = d.beta * np.sum(np.array(d.arrival_rate) * (d.cycle_s - green) ** 2, axis=-1)
        return np.sum(np.array(d.queue_weight) * squares, axis=-1) + red


def _poisson(mean: float, counts: np.ndarray) -> np.ndarray:
    if mean == 0:
        return (counts == 0).astype(float)
    log_factorial = np.array([math.lgamma(k + 1.0) for k in counts])
    return np.exp(counts * math.log(mean) - mean - log_factorial)


class PenaltyProblem:
    """Two-variable form J(g) + rho/2 (g_NS + g_EW - G)^2 with green bounds.

    The cycle constraint holds only approximately, so these solutions are for the
    algorithm study and must never be applied to the signals.
    """

    def __init__(
        self, data: ObjectiveData, g_min: float, g_max: float, budget: float, rho: float
    ) -> None:
        if not (math.isfinite(rho) and rho >= 0):
            raise ValueError(f"rho must be finite and non-negative; got {rho}")
        if not g_min <= g_max:
            raise ValueError("g_min must not exceed g_max")
        self.data, self.rho, self.budget = data, float(rho), float(budget)
        self.g_min, self.g_max = float(g_min), float(g_max)

    def violation(self, x: np.ndarray) -> float:
        """g_NS + g_EW - G, in seconds."""
        return float(np.sum(x) - self.budget)

    def value(self, x: np.ndarray) -> float:
        return float(objective.value(self.data, x) + 0.5 * self.rho * self.violation(x) ** 2)

    def gradient(self, x: np.ndarray) -> np.ndarray:
        return objective.gradient(self.data, x) + self.rho * self.violation(x)

    def hessian(self, x: np.ndarray) -> np.ndarray:
        return objective.hessian(self.data, x) + self.rho

    def project(self, x: np.ndarray) -> np.ndarray:
        return np.clip(x, self.g_min, self.g_max)

    def lipschitz_constant(self) -> float:
        d = self.data
        w, mu, lam = (np.array(v) for v in (d.queue_weight, d.discharge_rate_vps, d.arrival_rate))
        return float(np.max(2.0 * w * mu**2 + 2.0 * d.beta * lam) + 2.0 * self.rho)
