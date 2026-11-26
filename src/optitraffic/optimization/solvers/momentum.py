from __future__ import annotations

import numpy as np

from optitraffic.optimization.solvers.base import Solver, require_positive


class Momentum(Solver):
    """Projected heavy-ball method.

        v <- momentum * v - step * grad f(x),   x+ = P(x + v)

    The stored velocity is the step actually taken, so it does not build up
    against a bound. Velocity is dropped if the move would be zero or would raise
    the objective by more than `restart_rise` (relative). Default step 1/L.
    Not monotone; no general convergence guarantee for piecewise quadratics.
    """

    name = "momentum"

    def __init__(
        self,
        step: float | None = None,
        momentum: float = 0.9,
        restart_rise: float = 0.1,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.step = None if step is None else require_positive(step, "step")
        if not 0 <= momentum < 1:
            raise ValueError(f"momentum must lie in [0, 1); got {momentum}")
        self.momentum = momentum
        self.restart_rise = require_positive(restart_rise, "restart_rise")

    def _step(self, problem, x, f, g, k, state):
        step = self._fixed_step(problem, self.step)
        velocity = state.get("velocity", np.zeros_like(x))
        x_new = problem.project(x + self.momentum * velocity - step * g)
        too_high = problem.value(x_new) > f + self.restart_rise * max(1.0, abs(f))
        if too_high or np.array_equal(x_new, x):
            x_new = problem.project(x - step * g)  # restart from a plain gradient step
        if np.array_equal(x_new, x):
            return None
        state["velocity"] = x_new - x
        return x_new
