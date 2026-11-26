from __future__ import annotations

import numpy as np

from optitraffic.optimization.solvers.base import Solver, blocked_components
from optitraffic.optimization.solvers.linesearch import armijo_search, exact_search


class ConjugateGradient(Solver):
    """Nonlinear conjugate gradient, Polak-Ribiere+, with an exact line search.

    r = gradient with blocked components set to zero,
    beta = max(0, r_new.(r_new - r) / r.r),   d_new = -r_new + beta * d.

    Restarts with d = -r every n steps, when d is not a descent direction, when
    the set of blocked bounds changes, and after a step that had to be projected.
    At most n steps on an unconstrained convex quadratic (it then equals linear
    CG). In one dimension it is steepest descent with an exact line search.
    """

    name = "conjugate_gradient"

    def _step(self, problem, x, f, g, k, state):
        blocked = blocked_components(problem, x, g)
        residual = np.where(blocked, 0.0, g)
        direction = -residual
        previous = state.get("previous")
        if previous is not None and state["since_restart"] < len(x):
            old_residual, old_direction, old_blocked = previous
            if np.array_equal(blocked, old_blocked):
                beta = max(0.0, residual @ (residual - old_residual) / (old_residual @ old_residual))
                candidate = -residual + beta * old_direction
                if g @ candidate < 0:
                    direction = candidate
        restarted = np.array_equal(direction, -residual)
        since_restart = 1 if restarted else state["since_restart"] + 1

        x_new = exact_search(problem, x, f, g, direction)
        if x_new is not None and np.array_equal(x_new, problem.project(x_new)):
            state["previous"] = (residual, direction, blocked)
            state["since_restart"] = since_restart
            return x_new

        state["previous"] = None  # the step leaves the bounds or failed: restart
        for candidate in (direction, -g):
            found = armijo_search(problem, x, f, g, candidate)
            if found is not None:
                return found[0]
        return None
