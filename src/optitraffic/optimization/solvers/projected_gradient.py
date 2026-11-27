from __future__ import annotations

from optitraffic.optimization.solvers.base import Solver, require_positive
from optitraffic.optimization.solvers.linesearch import armijo_search


class ProjectedGradient(Solver):
    """Projected gradient with Armijo backtracking along the projection arc.

    x+ = P(x - t * grad f(x)). Needs no Lipschitz constant. The first trial step
    is `initial_step`; later searches start at twice the last accepted step.
    Monotone. This is the default online solver.
    """

    name = "projected_gradient"

    def __init__(self, initial_step: float = 1.0, **kwargs) -> None:
        super().__init__(**kwargs)
        self.initial_step = require_positive(initial_step, "initial_step")

    def _step(self, problem, x, f, g, k, state):
        found = armijo_search(problem, x, f, g, -g, state.get("step", self.initial_step))
        if found is None:
            return None
        x_new, accepted = found
        state["step"] = 2.0 * accepted
        return x_new
