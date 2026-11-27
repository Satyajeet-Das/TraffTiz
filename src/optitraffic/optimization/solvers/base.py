"""Common solver interface and iteration loop (Technical Design section 6.1).

A problem provides `value(x)`, `gradient(x)` and `project(x)`; some solvers also
need `hessian(x)`, `lipschitz_constant()` or `sample_gradient(x, rng, batch)`.
Every constraint set used here is a box, so projection works per component.
"""

from __future__ import annotations

import math
import time
from typing import Any, Protocol

import numpy as np
from numpy.typing import ArrayLike

from optitraffic.types import SolverResult


class Problem(Protocol):
    def value(self, x: np.ndarray) -> float: ...
    def gradient(self, x: np.ndarray) -> np.ndarray: ...
    def project(self, x: np.ndarray) -> np.ndarray: ...


def projected_residual(problem: Problem, x: np.ndarray, gradient: np.ndarray) -> float:
    """|x - P(x - gradient)|; zero exactly at a minimiser of a convex problem."""
    return float(np.linalg.norm(x - problem.project(x - gradient)))


def blocked_components(problem: Problem, x: np.ndarray, gradient: np.ndarray) -> np.ndarray:
    """Components on a bound that the negative gradient pushes outwards."""
    return (problem.project(x - gradient) == x) & (gradient != 0)


def require_positive(value: float, name: str) -> float:
    if not (math.isfinite(value) and value > 0):
        raise ValueError(f"{name} must be finite and positive; got {value}")
    return value


class Solver:
    """Base class. Subclasses implement `_step` and may override the other hooks.

    Stops when the projected-gradient residual reaches `tolerance`
    ("converged"), after `max_iterations` ("max_iter"), when `time_budget_s` is
    used up ("time_budget"), when no further step can be taken ("stalled"), or on
    a non-finite number ("numerical_error", returning the last finite point).
    The starting point is projected onto the constraints first.
    """

    name = "solver"
    handles_nonsmooth = False

    def __init__(
        self,
        tolerance: float = 1e-6,
        max_iterations: int = 500,
        time_budget_s: float | None = None,
    ) -> None:
        self.tolerance = require_positive(tolerance, "tolerance")
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
        self.max_iterations = max_iterations
        self.time_budget_s = (
            None if time_budget_s is None else require_positive(time_budget_s, "time_budget_s")
        )

    def solve(self, problem: Problem, x0: ArrayLike) -> SolverResult:
        started = time.perf_counter()
        start = np.array(x0, dtype=float)
        if start.ndim != 1 or not np.all(np.isfinite(start)):
            raise ValueError(f"x0 must be a finite 1-D array; got {start}")
        if getattr(problem, "nonsmooth", False) and not self.handles_nonsmooth:
            raise ValueError(f"{self.name} needs a differentiable objective")

        # Overflow is detected explicitly below, so NumPy need not warn about it.
        with np.errstate(over="ignore", invalid="ignore"):
            x = problem.project(start)
            state = self._start(problem, x)
            f, g = problem.value(x), problem.gradient(x)
            history = [f]
            iterations = 0
            while True:
                if not (math.isfinite(f) and np.all(np.isfinite(g))):
                    status = "numerical_error"
                elif self._is_converged(problem, x, g):
                    status = "converged"
                elif iterations >= self.max_iterations:
                    status = "max_iter"
                elif (
                    self.time_budget_s is not None
                    and time.perf_counter() - started >= self.time_budget_s
                ):
                    status = "time_budget"
                elif self._has_stalled(state):
                    status = "stalled"
                else:
                    x_new = self._step(problem, x, f, g, iterations, state)
                    if x_new is None:
                        status = "stalled"
                    elif not np.all(np.isfinite(x_new)):
                        status = "numerical_error"
                    else:
                        f_new, g_new = problem.value(x_new), problem.gradient(x_new)
                        if not (math.isfinite(f_new) and np.all(np.isfinite(g_new))):
                            status = "numerical_error"
                        else:
                            self._update(problem, state, x, g, x_new, f_new, g_new)
                            x, f, g = x_new, f_new, g_new
                            history.append(f)
                            iterations += 1
                            continue
                break

            x_out = self._output(state, x)
            if x_out is not x:
                f, g = problem.value(x_out), problem.gradient(x_out)
            residual = projected_residual(problem, x_out, g)

        return SolverResult(
            x0=start,
            x=x_out,
            objective=f,
            gradient=g,
            residual=residual,
            iterations=iterations,
            converged=status == "converged",
            status=status,
            runtime_s=time.perf_counter() - started,
            feasible=bool(np.allclose(x_out, problem.project(x_out), rtol=0, atol=1e-9)),
            history=tuple(history),
        )

    # Hooks -----------------------------------------------------------------
    def _start(self, problem: Problem, x: np.ndarray) -> dict[str, Any]:
        """Per-run memory, so that a solver object can be reused."""
        return {}

    def _step(
        self, problem: Problem, x: np.ndarray, f: float, g: np.ndarray, k: int, state: dict
    ) -> np.ndarray | None:
        """Return the next iterate, or None if no step is possible."""
        raise NotImplementedError

    def _update(self, problem, state, x, g, x_new, f_new, g_new) -> None:
        """Update memory after an accepted step."""

    def _is_converged(self, problem: Problem, x: np.ndarray, g: np.ndarray) -> bool:
        return projected_residual(problem, x, g) <= self.tolerance

    def _has_stalled(self, state: dict) -> bool:
        return False

    def _output(self, state: dict, x: np.ndarray) -> np.ndarray:
        """The solution to report; the last iterate unless overridden."""
        return x

    def _fixed_step(self, problem: Problem, step: float | None) -> float:
        """The given step, or 1/L when the problem knows its Lipschitz constant."""
        if step is not None:
            return step
        if not hasattr(problem, "lipschitz_constant"):
            raise ValueError(f"{self.name} needs an explicit step for this problem")
        return 1.0 / problem.lipschitz_constant()
