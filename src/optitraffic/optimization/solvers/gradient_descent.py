from __future__ import annotations

import numpy as np

from optitraffic.optimization.solvers.base import Solver, require_positive


class GradientDescent(Solver):
    """Fixed-step gradient descent, x <- P(x - step * grad f(x)).

    Assumes a Lipschitz continuous gradient. Converges for 0 < step < 2/L; the
    default is 1/L. On an unconstrained problem P is the identity, giving plain
    gradient descent. Linear convergence when strongly convex; slow when
    ill-conditioned.
    """

    name = "gradient_descent"

    def __init__(self, step: float | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.step = None if step is None else require_positive(step, "step")

    def _step(self, problem, x, f, g, k, state):
        x_new = problem.project(x - self._fixed_step(problem, self.step) * g)
        return None if np.array_equal(x_new, x) else x_new
