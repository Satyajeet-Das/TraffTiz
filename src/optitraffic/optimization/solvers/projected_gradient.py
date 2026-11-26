from __future__ import annotations

from optitraffic.optimization.solvers.base import Solver, require_positive
from optitraffic.optimization.solvers.linesearch import armijo_search


class ProjectedGradient(Solver):
    """Projected gradient with Armijo backtracking along the projection arc.

    x+ = P(x - t * grad f(x)). Needs no Lipschitz constant. The first trial step
    is `initial_step`; later searches start at twice the last accepted step.
    Monotone. This is the default online solver.

    `armijo_c` in (0, 0.5] is the sufficient-decrease constant. On a quadratic
    with curvature L it accepts t <= 2(1 - c)/L, so a very small c lets the
    iterates zig-zag with steps of almost 2/L; c = 0.25 at least halves the
    error of a one-variable quadratic in every iteration.
    """

    name = "projected_gradient"

    def __init__(self, initial_step: float = 1.0, armijo_c: float = 0.25, **kwargs) -> None:
        super().__init__(**kwargs)
        self.initial_step = require_positive(initial_step, "initial_step")
        if not 0 < armijo_c <= 0.5:  # also rejects NaN
            raise ValueError(f"armijo_c must lie in (0, 0.5]; got {armijo_c}")
        self.armijo_c = armijo_c

    def _step(self, problem, x, f, g, k, state):
        step = state.get("step", self.initial_step)
        found = armijo_search(problem, x, f, g, -g, step, c=self.armijo_c)
        if found is None:
            return None
        x_new, accepted = found
        state["step"] = 2.0 * accepted
        return x_new
