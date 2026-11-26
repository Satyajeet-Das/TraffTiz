from __future__ import annotations

import numpy as np

from optitraffic.optimization.solvers.base import Solver, blocked_components
from optitraffic.optimization.solvers.linesearch import armijo_search


class Newton(Solver):
    """Damped projected (semismooth) Newton method.

    Solves H d = -g on the components not blocked by a bound, then backtracks
    along the projection arc from step 1. Falls back to the negative gradient
    when the reduced Hessian is not positive definite or the Newton direction
    fails. Needs `problem.hessian`. Where the Hessian jumps (queue kinks) the
    problem supplies one side; the line search guards against cycling. Quadratic
    local convergence for smooth problems; finite on a single quadratic piece.
    """

    name = "newton"
    min_eigenvalue = 1e-12

    def _step(self, problem, x, f, g, k, state):
        free = ~blocked_components(problem, x, g)
        direction = np.zeros_like(x)
        if free.any():
            hessian = problem.hessian(x)[np.ix_(free, free)]
            if np.linalg.eigvalsh(hessian)[0] > self.min_eigenvalue:
                direction[free] = -np.linalg.solve(hessian, g[free])
        if g @ direction < 0:
            found = armijo_search(problem, x, f, g, direction)
            if found is not None:
                return found[0]
        found = armijo_search(problem, x, f, g, -g)
        return None if found is None else found[0]
