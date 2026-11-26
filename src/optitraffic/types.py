"""Shared immutable types. Pairs are always in phase order (NS, EW)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

SOLVER_NAMES = (
    "gradient_descent",
    "projected_gradient",
    "momentum",
    "sgd",
    "newton",
    "bfgs",
    "conjugate_gradient",
    "subgradient",
)


@dataclass(frozen=True)
class SignalParams:
    cycle_s: int
    yellow_s: int
    all_red_s: int
    g_min_s: int
    g_max_s: int
    green_lost_s: int = 0  # part of each displayed green that serves no vehicles

    @property
    def lost_time_s(self) -> int:
        """Yellow, all-red and lost green for both phases (design decision D4)."""
        return 2 * (self.yellow_s + self.all_red_s + self.green_lost_s)

    def displayed_green_s(self, effective_s: int) -> int:
        """Green shown on the signal for a given effective green."""
        return effective_s + self.green_lost_s

    @property
    def green_budget_s(self) -> int:
        return self.cycle_s - self.lost_time_s


@dataclass(frozen=True)
class ModelParams:
    saturation_flow_vph: tuple[float, float]
    queue_weight: tuple[float, float]
    beta: float

    @property
    def discharge_rate_vps(self) -> tuple[float, float]:
        ns, ew = self.saturation_flow_vph
        return (ns / 3600.0, ew / 3600.0)


@dataclass(frozen=True)
class ObjectiveData:
    """Everything needed to evaluate the objective for one signal cycle."""

    queue: tuple[float, float]  # veh
    arrival_rate: tuple[float, float]  # veh/s
    discharge_rate_vps: tuple[float, float]  # veh/s during green
    queue_weight: tuple[float, float]
    beta: float  # veh/s
    cycle_s: float

    def __post_init__(self) -> None:
        for name, positive in (
            ("queue", False),
            ("arrival_rate", False),
            ("discharge_rate_vps", True),
            ("queue_weight", True),
        ):
            values = tuple(float(v) for v in getattr(self, name))
            if len(values) != 2 or not all(_valid(v, positive) for v in values):
                kind = "positive" if positive else "non-negative"
                raise ValueError(f"{name} needs two finite {kind} values; got {values}")
            object.__setattr__(self, name, values)
        if not _valid(self.beta, positive=False):
            raise ValueError(f"beta must be finite and non-negative; got {self.beta}")
        if not _valid(self.cycle_s, positive=True):
            raise ValueError(f"cycle_s must be finite and positive; got {self.cycle_s}")

    @classmethod
    def from_params(
        cls,
        queue: Sequence[float],
        arrival_rate: Sequence[float],
        model: ModelParams,
        signal: SignalParams,
    ) -> ObjectiveData:
        return cls(
            queue=tuple(queue),
            arrival_rate=tuple(arrival_rate),
            discharge_rate_vps=model.discharge_rate_vps,
            queue_weight=model.queue_weight,
            beta=model.beta,
            cycle_s=float(signal.cycle_s),
        )


def _valid(value: float, positive: bool) -> bool:
    return math.isfinite(value) and (value > 0 if positive else value >= 0)


@dataclass(frozen=True)
class EstimationParams:
    window_s: float
    include_pending: bool  # count waiting vehicles as arrivals
    pending_in_queue: bool  # add waiting vehicles to the queue


@dataclass(frozen=True)
class SolverParams:
    name: str
    tolerance: float
    max_iterations: int
    time_budget_s: float  # for one whole decision
    solver_budget_fraction: float = 0.8  # share of the budget the solver may use
    accept_unconverged: bool = True  # use a feasible, improved but unconverged result


@dataclass(frozen=True)
class SolverResult:
    """What every algorithm reports (PRD FR-06)."""

    x0: np.ndarray  # as given, before projection
    x: np.ndarray  # final solution
    objective: float
    gradient: np.ndarray  # or a subgradient, at x
    residual: float  # |x - P(x - gradient)|
    iterations: int
    converged: bool
    status: str  # converged | max_iter | stalled | time_budget | numerical_error
    runtime_s: float
    feasible: bool
    history: tuple[float, ...]  # objective at each iterate, starting point first


@dataclass(frozen=True)
class SimulationParams:
    step_length_s: float
    warmup_s: float
    duration_s: float  # measured period after the warm-up

    @property
    def end_s(self) -> float:
        return self.warmup_s + self.duration_s


Movement = tuple[str, str]  # (incoming edge, outgoing edge)


@dataclass(frozen=True)
class NetworkParams:
    tls_id: str
    phase_movements: tuple[tuple[Movement, ...], tuple[Movement, ...]]  # (NS, EW)


@dataclass(frozen=True)
class DemandSegment:
    start_fraction: float  # of the measured period
    arrival_rate: tuple[float, float]  # veh/s per approach, (NS, EW)


@dataclass(frozen=True)
class ScenarioParams:
    name: str
    segments: tuple[DemandSegment, ...]


@dataclass(frozen=True)
class ApproachState:
    """Measurements for one incoming edge."""

    edge: str
    queue: float  # halting on the road, plus waiting to enter if configured
    arrival_rate: float  # veh/s
    vehicle_count: int
    waiting_time: float  # s, summed over vehicles on the road
    pending: int  # vehicles waiting to enter because the road is full


@dataclass(frozen=True)
class TrafficState:
    """Measurements at one decision instant. Pairs are in (NS, EW) order.

    `queue` and `arrival_rate` belong to each phase's critical approach (D3);
    counts, waiting time and pending vehicles are summed over the phase. If
    `valid` is False the numbers must not be used for control.
    """

    sim_time: float
    queue: tuple[float, float]
    arrival_rate: tuple[float, float]
    vehicle_count: tuple[int, int]
    waiting_time: tuple[float, float]
    pending: tuple[int, int]
    signal_state: str
    approaches: tuple[ApproachState, ...]
    valid: bool
    issues: tuple[str, ...]


@dataclass(frozen=True)
class TimingPlan:
    """Green times for one cycle."""

    green: tuple[int, int]  # effective green in whole seconds, (NS, EW)
    source: str  # controller name, or "fallback"
    reason: str = ""  # why the fallback was used
    solver: SolverResult | None = None
    solver_name: str = ""


@dataclass(frozen=True)
class CycleRecord:
    """What happened at one decision instant."""

    start_s: float
    state: TrafficState
    plan: TimingPlan  # the plan actually applied
    decision_s: float  # wall-clock time the controller took


@dataclass(frozen=True)
class Config:
    signal: SignalParams
    model: ModelParams
    estimation: EstimationParams
    solver: SolverParams
    simulation: SimulationParams
    network: NetworkParams
    scenario: ScenarioParams
