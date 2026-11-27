from __future__ import annotations

import numpy as np

from optitraffic.optimization.solvers.base import Solver, require_positive


class Subgradient(Solver):
    """Projected subgradient method with step initial_step / sqrt(k + 1).

    For convex, possibly nonsmooth objectives. Not a descent method, so the best
    iterate is returned (`history` holds every iterate's value). Stops after
    `patience` iterations without improving the best value by more than
    `improvement` ("stalled") or at the iteration limit. "converged" is reported
    only if the projected residual of the current subgradient is within
    tolerance, which is sufficient but not necessary for optimality; at a kink
    minimiser it usually never happens. Error decreases like log k / sqrt k.
    """

    name = "subgradient"
    handles_nonsmooth = True

    def __init__(
        self,
        initial_step: float = 10.0,
        patience: int = 500,
        improvement: float = 1e-9,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.initial_step = require_positive(initial_step, "initial_step")
        if patience < 1:
            raise ValueError("patience must be at least 1")
        self.patience = patience
        self.improvement = require_positive(improvement, "improvement")

    def _start(self, problem, x):
        # reference_value is the value at the last significant improvement.
        value = problem.value(x)
        return {"best_x": x, "best_value": value, "reference_value": value, "waiting": 0}

    def _step(self, problem, x, f, g, k, state):
        # A step stopped by a bound may not move; later subgradients can differ.
        return problem.project(x - self.initial_step / np.sqrt(k + 1) * g)

    def _update(self, problem, state, x, g, x_new, f_new, g_new):
        if f_new < state["best_value"]:
            state["best_x"], state["best_value"] = x_new, f_new
        if f_new < state["reference_value"] - self.improvement:
            state["reference_value"], state["waiting"] = f_new, 0
        else:
            state["waiting"] += 1

    def _has_stalled(self, state):
        return state["waiting"] >= self.patience

    def _output(self, state, x):
        return state["best_x"]
