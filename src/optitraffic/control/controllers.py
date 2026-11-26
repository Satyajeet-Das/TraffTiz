"""Baseline controllers (PRD FR-09, Technical Design section 7.1).

Every controller has a `name`, says whether it `needs_state`, and returns a
`TimingPlan` of whole-second effective greens. The optimization-based controller
is in `adaptive.py`.
"""

from __future__ import annotations

import math
from typing import Protocol

from optitraffic.control.adaptive import AdaptiveController
from optitraffic.types import Config, SignalParams, TimingPlan, TrafficState


class Controller(Protocol):
    name: str
    needs_state: bool

    def plan(self, state: TrafficState) -> TimingPlan: ...


def whole_second_plan(g_ns: float, signal: SignalParams) -> tuple[int, int]:
    """Nearest feasible whole-second plan for a desired NS green."""
    if not math.isfinite(g_ns):
        raise ValueError(f"green time must be finite; got {g_ns}")
    budget = signal.green_budget_s
    low = max(signal.g_min_s, budget - signal.g_max_s)
    high = min(signal.g_max_s, budget - signal.g_min_s)
    ns = min(high, max(low, math.floor(g_ns + 0.5)))
    return (ns, budget - ns)


def proportional_plan(ns: float, ew: float, signal: SignalParams) -> tuple[int, int]:
    """Split the green budget in proportion to two demands; equal if both are zero."""
    if not (ns >= 0 and ew >= 0 and math.isfinite(ns + ew)):
        raise ValueError(f"demands must be finite and non-negative; got {ns}, {ew}")
    share = 0.5 if ns + ew == 0 else ns / (ns + ew)
    return whole_second_plan(share * signal.green_budget_s, signal)


class FixedEqual:
    """The same effective green for both phases."""

    name = "fixed_equal"
    needs_state = False

    def __init__(self, config: Config) -> None:
        self._green = proportional_plan(1.0, 1.0, config.signal)

    def plan(self, state: TrafficState) -> TimingPlan:
        return TimingPlan(self._green, self.name)


class FixedCalibrated:
    """Fixed split in proportion to the flow ratios of the scenario's average demand.

    It knows the true long-run rates, which the adaptive controller does not. For
    a changing scenario it uses the average over the measured period.
    """

    name = "fixed_calibrated"
    needs_state = False

    def __init__(self, config: Config) -> None:
        segments = config.scenario.segments
        ends = [s.start_fraction for s in segments[1:]] + [1.0]
        average = [
            sum(s.arrival_rate[i] * (end - s.start_fraction) for s, end in zip(segments, ends))
            for i in (0, 1)
        ]
        ratios = [rate / mu for rate, mu in zip(average, config.model.discharge_rate_vps)]
        self._green = proportional_plan(ratios[0], ratios[1], config.signal)

    def plan(self, state: TrafficState) -> TimingPlan:
        return TimingPlan(self._green, self.name)


class QueueProportional:
    """Green in proportion to the current queue of each phase."""

    name = "queue_proportional"
    needs_state = True

    def __init__(self, config: Config) -> None:
        self._signal = config.signal

    def plan(self, state: TrafficState) -> TimingPlan:
        return TimingPlan(proportional_plan(*state.queue, self._signal), self.name)


CONTROLLERS = {
    cls.name: cls
    for cls in (FixedEqual, FixedCalibrated, QueueProportional, AdaptiveController)
}


def make_controller(name: str, config: Config, seed: int = 0) -> Controller:
    """`seed` is used only by controllers with random numbers (adaptive with SGD)."""
    if name not in CONTROLLERS:
        raise ValueError(f"unknown controller {name!r}; choose from {', '.join(CONTROLLERS)}")
    if name == AdaptiveController.name:
        return AdaptiveController(config, seed)
    return CONTROLLERS[name](config)
