"""Collect traffic measurements through TraCI (PRD FR-02, Technical Design 4.3).

Call `observe()` after every simulation step so no arrival is missed, and
`read()` at each decision instant.

When a queue fills an approach, further vehicles wait outside the network and
never appear on the road, so counting road arrivals alone underestimates demand.
With `include_pending` (the default) a vehicle counts as arriving when it first
appears either on the incoming edge or in SUMO's waiting-to-enter list. A real
road sensor could not see the latter; it belongs to the study's assumption of
perfect detection. The number waiting is reported either way.

Queues are read at the decision instant, which is just before the NS green. The
EW phase has then only just been served, so its queue is systematically smaller
than the NS one. With `queue_sampling: own_green`, call `sample_green_start(1)`
as the EW green begins; the next `read()` reports that EW queue, so both queues
are measured at the same point of their own cycle. The EW value is then part of
a cycle old.
"""

from __future__ import annotations

import math

from optitraffic.modelling.critical import critical_approach
from optitraffic.modelling.demand import DemandEstimator
from optitraffic.simulation.signals import stage_states
from optitraffic.types import ApproachState, Config, TrafficState


class MappingError(ValueError):
    """The configured directions do not match the simulated network."""


class StateCollector:
    def __init__(self, api, config: Config, start_s: float = 0.0) -> None:
        """`api` is a TraCI connection (or a test double with the same methods)."""
        self.api = api
        self.config = config
        self._phases = [
            [origin for origin, _ in movements] for movements in config.network.phase_movements
        ]
        self.edges = [edge for phase in self._phases for edge in phase]
        self._lanes = self._check_mapping()
        self.estimator = DemandEstimator(
            len(self.edges), config.estimation.window_s, config.signal.cycle_s, start_s
        )
        self._seen: set[str] = set()
        self._origins: dict[str, str] = {}  # vehicle -> first edge of its route
        self._last_observed: float | None = None
        self._issues: list[str] = []  # problems found since the last read
        self._pending: dict[str, int] = {edge: 0 for edge in self.edges}
        self._held: dict[str, float] = {}  # queues sampled as a green began

    # ------------------------------------------------------------------ setup
    def _check_mapping(self) -> dict[str, list[str]]:
        """Verify edges and signal links; return the lanes of each incoming edge."""
        network = self.config.network
        known = set(self.api.edge.getIDList())
        missing = [edge for edge in self.edges if edge not in known]
        if missing:
            raise MappingError(f"incoming edges not in the network: {missing}")
        if network.tls_id not in self.api.trafficlight.getIDList():
            raise MappingError(f"traffic light {network.tls_id!r} not in the network")
        lane_api = self.api.lane
        links = [
            (lane_api.getEdgeID(connection[0]), lane_api.getEdgeID(connection[1]), index)
            for index, connections in enumerate(
                self.api.trafficlight.getControlledLinks(network.tls_id)
            )
            for connection in connections
        ]
        try:
            stage_states(links, network)
        except ValueError as error:
            raise MappingError(str(error)) from error
        return {
            edge: [f"{edge}_{i}" for i in range(self.api.edge.getLaneNumber(edge))]
            for edge in self.edges
        }

    # ------------------------------------------------------------ every step
    def observe(self) -> None:
        """Record new arrivals. Safe to call twice at the same simulation time."""
        now = self.api.simulation.getTime()
        if now == self._last_observed:
            return
        step = self.config.simulation.step_length_s
        if self._last_observed is not None and now - self._last_observed > 1.5 * step:
            # Vehicles may have come and gone unseen, so the history is unusable.
            self._issues.append(f"observation gap before t={now:g}")
            self.estimator.reset(now)
            self._held.clear()
        self._last_observed = now
        try:
            arrivals = self._new_arrivals()
        except _traci_errors() as error:
            self._issues.append(f"arrival measurement failed: {error}")
            self.estimator.reset(now)
            return
        self.estimator.record(now, arrivals)

    def _new_arrivals(self) -> list[int]:
        pending: dict[str, list[str]] = {edge: [] for edge in self.edges}
        for vehicle in self.api.simulation.getPendingVehicles():
            origin = self._origins.get(vehicle)
            if origin is None:  # routes never change, so ask only once
                origin = self._origins[vehicle] = self.api.vehicle.getRoute(vehicle)[0]
            if origin in pending:
                pending[origin].append(vehicle)
        self._pending = {edge: len(vehicles) for edge, vehicles in pending.items()}

        counts = []
        for edge in self.edges:
            present = set(self.api.edge.getLastStepVehicleIDs(edge))
            if self.config.estimation.include_pending:
                present.update(pending[edge])
            new = present - self._seen
            self._seen |= new
            counts.append(len(new))
        return counts

    # ------------------------------------------------------------ green start
    def sample_green_start(self, phase: int) -> None:
        """Hold the queues of `phase` as its green begins (`own_green` only).

        The NS green starts at the decision instant, where `read()` measures it
        directly, so only the EW queues are ever held.
        """
        if self.config.estimation.queue_sampling != "own_green" or phase == 0:
            return
        self.observe()
        for edge in self._phases[phase]:
            issues: list[str] = []
            queue = self._queue(edge, issues)
            if issues:
                self._issues += issues
                self._held.pop(edge, None)
            else:
                self._held[edge] = queue

    def _queue(self, edge: str, issues: list[str]) -> float:
        queue = self._measure(
            self.api.lane.getLastStepHaltingNumber, self._lanes[edge], "queue", issues
        )
        if self.config.estimation.pending_in_queue:
            queue += self._pending[edge]
        return queue

    # ------------------------------------------------------ decision instant
    def read(self) -> TrafficState:
        """The current state. `valid` is False, with reasons, if it must not be used."""
        self.observe()
        now = self.api.simulation.getTime()
        issues, self._issues = self._issues, []
        rates = self.estimator.rates(now)
        if rates is None:
            issues.append("arrival rate not ready")
            rates = (0.0,) * len(self.edges)

        approaches = []
        for edge, rate in zip(self.edges, rates):
            lanes = self._lanes[edge]
            if (
                self.config.estimation.queue_sampling == "own_green"
                and edge in self._phases[1]
            ):
                queue = self._held.get(edge)
                if queue is None:
                    issues.append(f"queue of {edge} not yet sampled before its green")
                    queue = 0.0
            else:
                queue = self._queue(edge, issues)
            count = self._measure(self.api.lane.getLastStepVehicleNumber, lanes, "vehicle count", issues)
            waiting = self._measure(self.api.lane.getWaitingTime, lanes, "waiting time", issues)
            approaches.append(ApproachState(
                edge=edge,
                queue=queue,
                arrival_rate=rate,
                vehicle_count=int(count),
                waiting_time=waiting,
                pending=self._pending[edge],
            ))
        self._held.clear()  # a held queue is used by one decision only
        try:
            signal_state = self.api.trafficlight.getRedYellowGreenState(self.config.network.tls_id)
        except _traci_errors() as error:
            signal_state = ""
            issues.append(f"signal state unavailable: {error}")

        phases, start = [], 0
        for edges in self._phases:
            phases.append(approaches[start:start + len(edges)])
            start += len(edges)
        critical = [
            critical_approach(
                [a.queue for a in phase], [a.arrival_rate for a in phase], self.config.signal.cycle_s
            )
            for phase in phases
        ]
        return TrafficState(
            sim_time=now,
            queue=(critical[0][0], critical[1][0]),
            arrival_rate=(critical[0][1], critical[1][1]),
            vehicle_count=tuple(sum(a.vehicle_count for a in p) for p in phases),
            waiting_time=tuple(sum(a.waiting_time for a in p) for p in phases),
            pending=tuple(sum(a.pending for a in p) for p in phases),
            signal_state=signal_state,
            approaches=tuple(approaches),
            valid=not issues,
            issues=tuple(dict.fromkeys(issues)),
        )

    @staticmethod
    def _measure(read, lanes: list[str], what: str, issues: list[str]) -> float:
        """Sum a non-negative lane quantity; report bad data and return 0."""
        try:
            values = [float(read(lane)) for lane in lanes]
        except (*_traci_errors(), TypeError, ValueError) as error:
            issues.append(f"{what} unavailable for {lanes[0]}: {error}")
            return 0.0
        if not all(math.isfinite(v) and v >= 0 for v in values):
            issues.append(f"invalid {what} for {lanes[0]}: {values}")
            return 0.0
        return sum(values)


def _traci_errors() -> tuple[type[Exception], ...]:
    """Errors meaning one measurement is missing. A lost connection is not caught."""
    from traci.exceptions import TraCIException

    return (TraCIException, KeyError)
