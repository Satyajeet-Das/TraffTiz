from __future__ import annotations

import numpy as np

from optitraffic.optimization.solvers.base import Solver, blocked_components
from optitraffic.optimization.solvers.linesearch import armijo_search, exact_search


class BFGS(Solver):
    """Projected BFGS with an inverse-Hessian approximation H.

    Direction -H g on the components not blocked by a bound. With the default
    exact line search it finishes in at most n steps on an unconstrained convex
    quadratic. If that step leaves the bounds, or `line_search="armijo"`,
    backtracking along the projection arc is used. H starts as the identity,
    is rescaled by y.s / y.y before the first update, and the update is skipped
    when y.s is not safely positive. In one dimension this is the secant method.
    """

    name = "bfgs"

    def __init__(self, line_search: str = "exact", **kwargs) -> None:
        super().__init__(**kwargs)
        if line_search not in ("exact", "armijo"):
            raise ValueError(f"line_search must be 'exact' or 'armijo'; got {line_search!r}")
        self.line_search = line_search

    def _step(self, problem, x, f, g, k, state):
        inverse = state.setdefault("inverse", np.eye(len(x)))
        free = ~blocked_components(problem, x, g)
        direction = np.zeros_like(x)
        direction[free] = -(inverse[np.ix_(free, free)] @ g[free])
        if not g @ direction < 0:
            direction = np.where(free, -g, 0.0)

        if self.line_search == "exact":
            x_new = exact_search(problem, x, f, g, direction)
            if x_new is not None and np.array_equal(x_new, problem.project(x_new)):
                return x_new
        for candidate in (direction, -g):
            found = armijo_search(problem, x, f, g, candidate)
            if found is not None:
                return found[0]
        return None

    def _update(self, problem, state, x, g, x_new, f_new, g_new):
        s, y = x_new - x, g_new - g
        curvature = float(y @ s)
        if curvature <= 1e-12 * np.linalg.norm(s) * np.linalg.norm(y):
            return
        inverse = state["inverse"]
        if not state.get("scaled"):
            inverse = np.eye(len(x)) * (curvature / float(y @ y))
            state["scaled"] = True
        rho = 1.0 / curvature
        left = np.eye(len(x)) - rho * np.outer(s, y)
        state["inverse"] = left @ inverse @ left.T + rho * np.outer(s, s)
