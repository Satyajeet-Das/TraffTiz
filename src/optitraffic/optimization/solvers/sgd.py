from __future__ import annotations

import numpy as np

from optitraffic.optimization.solvers.base import Solver, require_positive


class SGD(Solver):
    """Mini-batch projected stochastic gradient descent with tail averaging.

        x+ = P(x - step_k * sampled_gradient),   step_k = initial_step / (1+k)^decay

    Needs `problem.sample_gradient`. decay in (0.5, 1] gives sum(step) infinite
    and sum(step^2) finite. The solution is the average of the second half of the
    iterates. Runs for `max_iterations` ("max_iter"); it does not stop on the
    exact residual, which a sampling method would not know. Reported objective,
    gradient and history use the problem's expected value, for evaluation only.
    The same seed gives the same result. Default initial_step 1/L.
    """

    name = "sgd"

    def __init__(
        self,
        initial_step: float | None = None,
        decay: float = 0.75,
        batch_size: int = 16,
        seed: int = 0,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.initial_step = (
            None if initial_step is None else require_positive(initial_step, "initial_step")
        )
        if not 0.5 < decay <= 1:
            raise ValueError(f"decay must lie in (0.5, 1]; got {decay}")
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self.decay, self.batch_size, self.seed = decay, batch_size, seed

    def _start(self, problem, x):
        if not hasattr(problem, "sample_gradient"):
            raise TypeError("sgd needs a problem with sample_gradient")
        return {"rng": np.random.default_rng(self.seed), "iterates": [x]}

    def _step(self, problem, x, f, g, k, state):
        step = self._fixed_step(problem, self.initial_step) / (1 + k) ** self.decay
        sample = problem.sample_gradient(x, state["rng"], self.batch_size)
        return problem.project(x - step * sample)

    def _update(self, problem, state, x, g, x_new, f_new, g_new):
        state["iterates"].append(x_new)

    def _is_converged(self, problem, x, g):
        return False

    def _output(self, state, x):
        iterates = state["iterates"]
        return np.mean(iterates[len(iterates) // 2 :], axis=0)
