"""The optimization-based controller (PRD FR-09, Technical Design 5 and 7).

Once per cycle: build the reduced problem from the measured queues and arrival
rates, minimise it with the configured solver starting from an equal split, and
round the result to whole seconds. The plan still has to pass the validator.

All solvers minimise J (the subgradient of a differentiable J is its gradient),
except SGD, which minimises the expected value of J over Poisson arrivals
(Technical Design 6.3) and so can choose a different plan.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import replace

from numpy.typing import ArrayLike

from optitraffic.optimization.problems import ReducedProblem, StochasticProblem
from optitraffic.optimization.solvers import Solver, create_solver
from optitraffic.types import Config, ObjectiveData, TimingPlan, TrafficState


def round_green(problem: ReducedProblem, x: ArrayLike) -> tuple[int, int]:
    """Whole-second plan (NS, EW) from a continuous solution (Design 5.6).

    Takes whichever of the floor and ceiling of g_NS, kept inside the feasible
    interval, has the lower objective; ties go to the one nearer the solution,
    then nearer an equal split.
    """
    (g_ns,) = (float(v) for v in x)
    if not math.isfinite(g_ns):
        raise ValueError(f"cannot round a non-finite green time: {g_ns}")
    low, high = math.ceil(problem.lower), math.floor(problem.upper)
    if low > high:
        raise ValueError(f"no whole-second plan in [{problem.lower}, {problem.upper}]")
    candidates = {min(high, max(low, c)) for c in (math.floor(g_ns), math.ceil(g_ns))}
    best = min(
        candidates,
        key=lambda c: (problem.value([c]), abs(c - g_ns), abs(c - problem.budget / 2), c),
    )
    return (best, round(problem.budget) - best)


class AdaptiveController:
    """`solver_factory` replaces `create_solver`, for failure-injection tests."""

    name = "adaptive"
    needs_state = True

    def __init__(
        self,
        config: Config,
        seed: int = 0,
        solver_factory: Callable[..., Solver] = create_solver,
    ) -> None:
        self.signal = config.signal
        self.model = config.model
        self.solver_name = config.solver.name
        self.seed = seed
        self._factory = solver_factory
        # The rest of the decision budget covers rounding and checks.
        limit = (
            config.solver.sgd_max_iterations
            if self.solver_name == "sgd"
            else config.solver.max_iterations
        )
        self._params = replace(
            config.solver,
            max_iterations=limit,
            time_budget_s=config.solver.time_budget_s * config.solver.solver_budget_fraction,
        )

    def problem(self, state: TrafficState) -> ReducedProblem:
        data = ObjectiveData.from_params(
            state.queue, state.arrival_rate, self.model, self.signal
        )
        if self.solver_name == "sgd":
            return StochasticProblem(
                data, self.signal.g_min_s, self.signal.g_max_s, self.signal.green_budget_s
            )
        return ReducedProblem.from_signal(data, self.signal)

    def plan(self, state: TrafficState) -> TimingPlan:
        problem = self.problem(state)
        options = {}
        if self.solver_name == "sgd":
            # A different but reproducible random stream at every decision.
            options["seed"] = (self.seed, round(state.sim_time * 1000))
        result = self._factory(self._params, **options).solve(problem, [problem.budget / 2])
        return TimingPlan(
            round_green(problem, result.x), self.name, solver=result, solver_name=self.solver_name
        )
