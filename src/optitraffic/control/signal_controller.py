"""Execute timing plans safely (PRD FR-08, NFR-02, Technical Design 7.3).

The controller walks through one fixed sequence,

    NS green, NS yellow, all-red, EW green, EW yellow, all-red,

one simulation step at a time. A plan can be loaded only at a cycle boundary and
cannot change until that cycle has finished.
"""

from __future__ import annotations

from optitraffic.simulation.signals import STAGES, cycle_stages
from optitraffic.types import SignalParams, TimingPlan


class PhaseError(RuntimeError):
    """An operation that would break the signal sequence."""


class SignalController:
    def __init__(self, states: dict[str, str], signal: SignalParams, step_s: float = 1.0) -> None:
        _check_states(states)
        self.states = dict(states)
        self.signal = signal
        self.step_s = step_s
        for duration in (signal.yellow_s, signal.all_red_s, 1):
            _steps(duration, step_s)
        self._schedule: list[tuple[str, str]] = []  # (stage, state) for each step left
        self._plan: TimingPlan | None = None

    @property
    def at_boundary(self) -> bool:
        """True before the first cycle and once the current cycle has finished."""
        return not self._schedule

    @property
    def plan(self) -> TimingPlan | None:
        return self._plan

    def load(self, plan: TimingPlan) -> None:
        """Start a new cycle. Raises if a cycle is running or the plan is infeasible."""
        if not self.at_boundary:
            raise PhaseError("a plan can only be loaded at a cycle boundary")
        schedule = [
            (stage, self.states[stage])
            for stage, duration in cycle_stages(self.signal, plan.green)
            for _ in range(_steps(duration, self.step_s))
        ]
        self._schedule = schedule[::-1]
        self._plan = plan

    def next_state(self) -> tuple[str, str]:
        """(stage, state string) for the next step, advancing the cycle."""
        if self.at_boundary:
            raise PhaseError("no cycle is running; load a plan first")
        return self._schedule.pop()

    def apply(self, api, tls_id: str) -> str:
        """Show the next step's state on the SUMO traffic light; returns the stage."""
        stage, state = self.next_state()
        api.trafficlight.setRedYellowGreenState(tls_id, state)
        return stage


def _steps(duration_s: int, step_s: float) -> int:
    count = duration_s / step_s
    if abs(count - round(count)) > 1e-9:
        raise ValueError(f"{duration_s} s is not a whole number of {step_s} s steps")
    return round(count)


def _check_states(states: dict[str, str]) -> None:
    """Refuse state strings that could show conflicting movements."""
    if set(states) != set(STAGES) or len({len(s) for s in states.values()}) != 1:
        raise ValueError("states must define every stage with equal length")

    def served(stage: str) -> set[int]:
        return {i for i, colour in enumerate(states[stage]) if colour != "r"}

    ns, ew = served("ns_green"), served("ew_green")
    expected = {
        "ns_green": ("G", ns), "ns_yellow": ("y", ns), "all_red_1": ("r", set()),
        "ew_green": ("G", ew), "ew_yellow": ("y", ew), "all_red_2": ("r", set()),
    }
    if not ns or not ew or ns & ew:
        raise ValueError("the two phases must serve separate, non-empty sets of links")
    for stage, (colour, links) in expected.items():
        wanted = "".join(colour if i in links else "r" for i in range(len(states[stage])))
        if states[stage] != wanted:
            raise ValueError(f"unsafe or inconsistent state for {stage}: {states[stage]!r}")
