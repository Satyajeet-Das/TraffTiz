"""Shared immutable types. Pairs are always in phase order (NS, EW)."""

from __future__ import annotations

from dataclasses import dataclass

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

    @property
    def lost_time_s(self) -> int:
        """Yellow and all-red for both phases (design decision D4)."""
        return 2 * (self.yellow_s + self.all_red_s)

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
class EstimationParams:
    window_s: float


@dataclass(frozen=True)
class SolverParams:
    name: str
    tolerance: float
    max_iterations: int
    time_budget_s: float


@dataclass(frozen=True)
class SimulationParams:
    step_length_s: float


@dataclass(frozen=True)
class Config:
    signal: SignalParams
    model: ModelParams
    estimation: EstimationParams
    solver: SolverParams
    simulation: SimulationParams
