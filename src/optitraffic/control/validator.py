"""Check a proposed plan before it reaches the signals (PRD FR-07, Design 7.2).

`decide` is the only way a controller's plan is accepted: anything that fails is
replaced by the fallback equal split, with the reason recorded.
"""

from __future__ import annotations

import time

from optitraffic.control.controllers import Controller, proportional_plan
from optitraffic.types import SignalParams, TimingPlan, TrafficState

FALLBACK = "fallback"
USABLE_STATUSES = ("converged", "max_iter", "stalled", "time_budget")


class Validator:
    def __init__(
        self, signal: SignalParams, time_budget_s: float, accept_unconverged: bool = True
    ) -> None:
        """With `accept_unconverged`, an unconverged solver result is still usable
        if it is feasible and no worse than its starting point."""
        self.signal = signal
        self.time_budget_s = time_budget_s
        self.accept_unconverged = accept_unconverged
        self.fallback_green = proportional_plan(1.0, 1.0, signal)
        problems = self.plan_problems(self.fallback_green)
        if problems:
            raise ValueError(f"the fallback plan is not feasible: {problems}")

    def plan_problems(self, green: object) -> list[str]:
        """Why these green times are infeasible; empty if they are acceptable."""
        if not (isinstance(green, tuple) and len(green) == 2):
            return [f"plan needs two green times; got {green!r}"]
        if not all(type(g) is int for g in green):  # rejects floats, NaN and bool
            return [f"green times must be whole seconds (int); got {green!r}"]
        s, problems = self.signal, []
        if not all(s.g_min_s <= g <= s.g_max_s for g in green):
            problems.append(f"green {green} outside [{s.g_min_s}, {s.g_max_s}] s")
        if sum(green) != s.green_budget_s:
            problems.append(f"green {green} does not sum to {s.green_budget_s} s")
        return problems

    def solver_problems(self, plan: TimingPlan) -> list[str]:
        result = plan.solver
        if result is None or result.converged:
            return []
        if result.status not in USABLE_STATUSES:
            return [f"solver failed with status {result.status}"]
        improved = bool(result.history) and result.objective <= result.history[0]
        if self.accept_unconverged and result.feasible and improved:
            return []
        return [f"solver did not converge (status {result.status})"]

    def fallback(self, reason: str, rejected: TimingPlan | None = None) -> TimingPlan:
        solver = rejected.solver if rejected else None
        return TimingPlan(self.fallback_green, FALLBACK, reason, solver)

    def decide(self, controller: Controller, state: TrafficState) -> tuple[TimingPlan, float]:
        """(plan to apply, controller wall-clock time in s)."""
        if controller.needs_state and not state.valid:
            return self.fallback("invalid state: " + "; ".join(state.issues)), 0.0
        started = time.perf_counter()
        try:
            plan = controller.plan(state)
        except Exception as error:  # any controller fault must leave the signals safe
            elapsed = time.perf_counter() - started
            return self.fallback(f"controller error: {type(error).__name__}: {error}"), elapsed
        elapsed = time.perf_counter() - started
        if not isinstance(plan, TimingPlan):
            return self.fallback(f"controller returned {type(plan).__name__}, not a plan"), elapsed
        problems = self.plan_problems(plan.green) + self.solver_problems(plan)
        if elapsed > self.time_budget_s:
            problems.append(f"decision took {elapsed:.3f} s, over the {self.time_budget_s} s budget")
        if problems:
            return self.fallback("; ".join(problems), plan), elapsed
        return plan, elapsed
