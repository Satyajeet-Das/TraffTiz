"""Traffic and controller metrics for one run (Technical Design section 8.1).

Traffic metrics cover the *measured vehicles*: those scheduled to depart in
[warm-up, end). The set comes from the demand, so it is identical for every
controller with the same scenario and seed. Vehicles still in the network, or
still waiting to enter it, when the run ends are included with the delay they
had accumulated by then.
"""

from __future__ import annotations

import gzip
import statistics
import xml.etree.ElementTree as ElementTree
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from optitraffic.control.validator import FALLBACK, Validator
from optitraffic.simulation.routes import Trip
from optitraffic.types import CycleRecord, ObservedGreen, SignalParams

# Metrics that depend on wall-clock time and so differ between identical runs.
TIMING_METRICS = ("solver_mean_ms", "solver_max_ms", "decision_max_ms")


@dataclass(frozen=True)
class TripResult:
    departed: bool
    arrival_s: float | None
    depart_delay_s: float  # for a vehicle that never entered: time spent waiting
    duration_s: float
    waiting_s: float  # time halted on the road
    stops: int
    time_loss_s: float


def read_tripinfo(path: str | Path) -> dict[str, TripResult]:
    """SUMO trip output, written with unfinished and undeparted vehicles."""
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rb") as handle:
        root = ElementTree.parse(handle).getroot()
    results: dict[str, TripResult] = {}
    for item in root.iter("tripinfo"):
        vehicle = item.get("id")
        if vehicle in results:
            raise ValueError(f"vehicle {vehicle} appears twice in {path}")
        arrival = float(item.get("arrival"))
        results[vehicle] = TripResult(
            departed=float(item.get("depart")) >= 0,
            arrival_s=arrival if arrival >= 0 else None,
            depart_delay_s=float(item.get("departDelay")),
            duration_s=float(item.get("duration")),
            waiting_s=float(item.get("waitingTime")),
            stops=int(item.get("waitingCount")),
            time_loss_s=float(item.get("timeLoss")),
        )
    return results


def traffic_metrics(
    results: dict[str, TripResult], schedule: Sequence[Trip], warmup_s: float, end_s: float
) -> dict[str, float]:
    measured = [t for t in schedule if warmup_s <= t.depart_s < end_s]
    if not measured:
        raise ValueError("no vehicle is scheduled in the measured period")
    missing = [t.vehicle_id for t in measured if t.vehicle_id not in results]
    if missing:
        raise ValueError(f"{len(missing)} vehicles have no trip record, e.g. {missing[0]}")

    all_trips = [results[t.vehicle_id] for t in measured]
    departed = [r for r in all_trips if r.departed]
    finished = [r for r in departed if r.arrival_s is not None]
    unfinished = [r for r in departed if r.arrival_s is None]

    by_approach: dict[str, list[float]] = {}
    for trip in measured:
        r = results[trip.vehicle_id]
        by_approach.setdefault(trip.origin, []).append(r.time_loss_s + r.depart_delay_s)

    return {
        "vehicles": len(measured),
        "finished": len(finished),
        "unfinished_on_road": len(unfinished),
        "never_entered": len(all_trips) - len(departed),
        # Primary metric: halted on the road plus waiting to get onto it.
        "avg_total_wait_s": _mean([r.waiting_s + r.depart_delay_s for r in all_trips]),
        "avg_waiting_s": _mean([r.waiting_s for r in departed]),
        "avg_waiting_finished_s": _mean([r.waiting_s for r in finished]),
        "avg_waiting_unfinished_s": _mean([r.waiting_s for r in unfinished]),
        "avg_insertion_delay_s": _mean([r.depart_delay_s for r in all_trips]),
        "avg_travel_time_s": _mean([r.duration_s for r in finished]),
        "avg_travel_time_unfinished_s": _mean([r.duration_s for r in unfinished]),
        "avg_delay_s": _mean([r.time_loss_s + r.depart_delay_s for r in all_trips]),
        "worst_approach_delay_s": max(_mean(v) for v in by_approach.values()),
        "stops_per_vehicle": _mean([r.stops for r in departed]),
        # Every vehicle that left the network during the measured period.
        "throughput_veh": sum(
            r.arrival_s is not None and warmup_s <= r.arrival_s <= end_s for r in results.values()
        ),
    }


def control_metrics(
    cycles: Sequence[CycleRecord], signal: SignalParams, warmup_s: float
) -> dict[str, object]:
    """Decisions made in the measured period, plus fallbacks over the whole run."""
    measured = [c for c in cycles if c.start_s >= warmup_s]
    checker = Validator(signal, 1.0)
    solved = [c for c in measured if c.plan.solver is not None]
    results = [c.plan.solver for c in solved]
    rejected = [
        c for c in measured
        if c.plan.source == FALLBACK and not c.plan.reason.startswith("invalid state")
    ]
    statuses = Counter(r.status for r in results)
    return {
        "cycles": len(measured),
        "fallbacks": sum(c.plan.source == FALLBACK for c in measured),
        "fallbacks_whole_run": sum(c.plan.source == FALLBACK for c in cycles),
        "rejected_plans": len(rejected),
        "infeasible_applied": sum(bool(checker.plan_problems(c.plan.green)) for c in cycles),
        "mean_green_ns_s": _mean([c.plan.green[0] for c in measured]),
        "solver_calls": len(solved),
        "solver_converged": statuses.get("converged", 0),
        "solver_statuses": ";".join(f"{k}:{v}" for k, v in sorted(statuses.items())),
        "mean_iterations": _mean([r.iterations for r in results]),
        "solver_mean_ms": _mean([1000 * r.runtime_s for r in results]),
        "solver_max_ms": max((1000 * r.runtime_s for r in results), default=None),
        "decision_max_ms": max((1000 * c.decision_s for c in measured), default=None),
    }


def observed_metrics(
    greens: Sequence[ObservedGreen], signal: SignalParams, warmup_s: float
) -> dict[str, object]:
    """The same keys as `control_metrics` for a signal that SUMO runs itself.

    A cycle is counted at each NS green; there are no plans, fallbacks or solver.
    A green outside the displayed limits counts as infeasible.
    """
    shortest = signal.displayed_green_s(signal.g_min_s)
    longest = signal.displayed_green_s(signal.g_max_s)
    ns = [g for g in greens if g.phase == 0 and g.start_s >= warmup_s]
    return {
        "cycles": len(ns),
        "fallbacks": 0,
        "fallbacks_whole_run": 0,
        "rejected_plans": 0,
        "infeasible_applied": sum(not shortest <= g.displayed_s <= longest for g in greens),
        "mean_green_ns_s": _mean([g.displayed_s - signal.green_lost_s for g in ns]),
        "solver_calls": 0,
        "solver_converged": 0,
        "solver_statuses": "",
        "mean_iterations": None,
        "solver_mean_ms": None,
        "solver_max_ms": None,
        "decision_max_ms": None,
    }


def _mean(values: Sequence[float]) -> float | None:
    """None, not NaN, when there is nothing to average."""
    return statistics.fmean(values) if values else None
