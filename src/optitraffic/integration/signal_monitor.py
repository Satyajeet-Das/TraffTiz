"""Record a signal that SUMO runs itself, such as the actuated baseline.

Our signal controller does not set these states, so the sequence is checked from
what the simulation shows: green, yellow, all-red for NS, then the same for EW.
"""

from __future__ import annotations

from optitraffic.simulation.signals import STAGES, cycle_stages
from optitraffic.types import ObservedGreen, SignalParams


class SignalMonitor:
    """Feed it the state shown during every step, in order."""

    def __init__(self, states: dict[str, str], signal: SignalParams, step_s: float = 1.0) -> None:
        green = signal.green_budget_s // 2
        present = [s for s, _ in cycle_stages(signal, (green, signal.green_budget_s - green))]
        self._stages = [s for s in STAGES if s in present]
        self._states = [states[s] for s in self._stages]
        if any(a == b for a, b in zip(self._states, self._states[1:])):
            raise ValueError("consecutive stages must show different states")
        self._clearance = {
            "ns_yellow": signal.yellow_s, "ew_yellow": signal.yellow_s,
            "all_red_1": signal.all_red_s, "all_red_2": signal.all_red_s,
        }
        self.step_s = step_s
        self._index = 0  # position in the cycle
        self._length = 0  # steps shown in the current stage
        self._start_s = 0.0
        self.greens: list[ObservedGreen] = []
        self.errors: list[str] = []

    @property
    def stage(self) -> str:
        return self._stages[self._index]

    def observe(self, state: str, start_s: float) -> str:
        """`state` was shown in the step beginning at `start_s`; returns the stage."""
        if state == self._states[self._index]:
            if self._length == 0:
                self._start_s = start_s
            self._length += 1
            return self.stage
        following = (self._index + 1) % len(self._stages)
        if self._length == 0 or state != self._states[following]:
            self.errors.append(f"t={start_s:g}: unexpected state {state!r} during {self.stage}")
            return self.stage
        self._finish()
        self._index, self._length, self._start_s = following, 1, start_s
        return self.stage

    def _finish(self) -> None:
        shown = self._length * self.step_s
        if self.stage.endswith("green"):
            phase = 0 if self.stage == "ns_green" else 1
            self.greens.append(ObservedGreen(phase, self._start_s, shown))
        elif abs(shown - self._clearance[self.stage]) > 1e-9:
            self.errors.append(
                f"t={self._start_s:g}: {self.stage} lasted {shown:g} s, "
                f"not {self._clearance[self.stage]} s"
            )
