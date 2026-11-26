"""The collector against a stand-in for TraCI; no SUMO run needed."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from optitraffic.config import load_config
from optitraffic.integration.state_collector import MappingError, StateCollector

pytest.importorskip("traci")

CONFIG = load_config(Path(__file__).resolve().parents[1] / "configs" / "default.yaml")
EDGES = ("N_in", "S_in", "E_in", "W_in")
LINKS = [("N_in", "S_out"), ("E_in", "W_out"), ("S_in", "N_out"), ("W_in", "E_out")]


class FakeTraci:
    def __init__(self):
        self.time = 0.0
        self.on_road = {e: [] for e in EDGES}
        self.waiting = {}  # vehicle -> origin edge
        self.halting = dict.fromkeys(EDGES, 0)
        self.wait_time = dict.fromkeys(EDGES, 0.0)
        self.broken: set[str] = set()
        self.links = list(LINKS)
        self.edges = list(EDGES) + [d for _, d in LINKS]
        self.tls = ["C"]
        lane_value = lambda table: lambda lane: self._lane(table, lane)
        self.simulation = SimpleNamespace(
            getTime=lambda: self.time, getPendingVehicles=lambda: list(self.waiting)
        )
        self.vehicle = SimpleNamespace(getRoute=lambda v: (self.waiting[v], "out"))
        self.edge = SimpleNamespace(
            getIDList=lambda: self.edges,
            getLaneNumber=lambda e: 1,
            getLastStepVehicleIDs=lambda e: list(self.on_road[e]),
        )
        self.lane = SimpleNamespace(
            getEdgeID=lambda lane: lane.rsplit("_", 1)[0],
            getLastStepHaltingNumber=lane_value(self.halting),
            getLastStepVehicleNumber=lambda lane: len(self.on_road[lane.rsplit("_", 1)[0]]),
            getWaitingTime=lane_value(self.wait_time),
        )
        self.trafficlight = SimpleNamespace(
            getIDList=lambda: self.tls,
            getControlledLinks=lambda t: [[(f"{a}_0", f"{b}_0", "via")] for a, b in self.links],
            getRedYellowGreenState=lambda t: "GrGr",
        )

    def _lane(self, table, lane):
        if lane in self.broken:
            raise KeyError(lane)
        return table[lane.rsplit("_", 1)[0]]


def run(collector, api, until, arrive=None):
    """Step the fake to `until`; `arrive(t)` may add vehicles before observing."""
    for t in range(int(api.time) + 1, until + 1):
        api.time = float(t)
        if arrive:
            arrive(t)
        collector.observe()


def north_every(api, period):
    def arrive(t):
        if t % period == 0:
            api.on_road["N_in"].append(f"n{t}")
    return arrive


def test_measurements_are_assigned_to_the_right_direction():
    api = FakeTraci()
    api.halting.update(N_in=3, S_in=9, E_in=4, W_in=1)
    api.wait_time.update(N_in=10.0, S_in=20.0, E_in=5.0, W_in=1.0)
    collector = StateCollector(api, CONFIG)
    run(collector, api, 90, north_every(api, 10))
    state = collector.read()
    assert state.valid and state.issues == ()
    assert state.sim_time == 90 and state.signal_state == "GrGr"
    assert [a.edge for a in state.approaches] == list(EDGES)
    # N: 3 + 0.1*90 = 12 expected; S: 9 + 0 = 9. N is critical.
    assert state.queue == (3, 4)
    assert state.arrival_rate == pytest.approx((0.1, 0.0))
    assert state.vehicle_count == (9, 0)
    assert state.waiting_time == (30.0, 6.0)
    assert state.pending == (0, 0)


def test_first_cycle_is_invalid_until_rates_are_ready():
    api = FakeTraci()
    collector = StateCollector(api, CONFIG)
    run(collector, api, 30)
    state = collector.read()
    assert not state.valid
    assert state.issues == ("arrival rate not ready",)
    assert state.arrival_rate == (0.0, 0.0)


def test_each_vehicle_counts_once():
    api = FakeTraci()
    collector = StateCollector(api, CONFIG)
    api.on_road["E_in"] = ["e1", "e2"]
    run(collector, api, 90)  # the same two vehicles stay for 90 steps
    assert collector.read().arrival_rate == pytest.approx((0.0, 2 / 90))
    collector.observe()  # same time again changes nothing
    assert collector.read().arrival_rate == pytest.approx((0.0, 2 / 90))


@pytest.mark.parametrize(("include", "expected"), [(True, 3 / 90), (False, 1 / 90)])
def test_waiting_vehicles(include, expected):
    config = replace(CONFIG, estimation=replace(CONFIG.estimation, include_pending=include))
    api = FakeTraci()
    collector = StateCollector(api, config)
    api.waiting = {"a": "N_in", "b": "N_in", "x": "N_in"}
    run(collector, api, 10)
    del api.waiting["x"]  # x gets onto the road: still one arrival
    api.on_road["N_in"] = ["x"]
    run(collector, api, 90)
    state = collector.read()
    assert state.arrival_rate[0] == pytest.approx(expected)
    assert state.pending == (2, 0)
    assert state.valid  # a full road is reported, not treated as bad data


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf"), None])
def test_invalid_measurement_is_flagged_and_never_propagated(bad):
    api = FakeTraci()
    collector = StateCollector(api, CONFIG)
    run(collector, api, 90)
    api.halting["E_in"] = bad
    state = collector.read()
    assert not state.valid
    assert any("queue" in issue and "E_in" in issue for issue in state.issues)
    assert state.queue == (0, 0)


def test_missing_measurement_is_flagged_then_recovers():
    api = FakeTraci()
    collector = StateCollector(api, CONFIG)
    run(collector, api, 90)
    api.broken = {"W_in_0"}
    assert not collector.read().valid
    api.broken = set()
    run(collector, api, 91)
    assert collector.read().valid


def test_observation_gap_invalidates_and_restarts_the_window():
    api = FakeTraci()
    collector = StateCollector(api, CONFIG)
    run(collector, api, 100)
    api.time = 150.0  # 50 steps were not observed
    state = collector.read()
    assert not state.valid
    assert any("gap" in issue for issue in state.issues)
    run(collector, api, 240)
    assert collector.read().valid


def test_failed_arrival_measurement_is_flagged():
    api = FakeTraci()
    collector = StateCollector(api, CONFIG)
    run(collector, api, 90)

    def fail(edge):
        raise KeyError(edge)

    working, api.edge.getLastStepVehicleIDs = api.edge.getLastStepVehicleIDs, fail
    api.time = 91.0
    state = collector.read()
    api.edge.getLastStepVehicleIDs = working
    assert not state.valid
    assert any("arrival measurement failed" in issue for issue in state.issues)


def test_lost_connection_is_not_swallowed():
    api = FakeTraci()
    collector = StateCollector(api, CONFIG)

    def lost():
        raise ConnectionError("closed")

    api.simulation.getTime = lost
    with pytest.raises(ConnectionError):
        collector.read()


@pytest.mark.parametrize(
    "break_mapping",
    [
        lambda api: api.edges.remove("W_in"),
        lambda api: api.tls.clear(),
        lambda api: api.links.pop(),
        lambda api: api.links.__setitem__(0, ("N_in", "E_out")),
    ],
)
def test_wrong_direction_mapping_stops_at_startup(break_mapping):
    api = FakeTraci()
    break_mapping(api)
    with pytest.raises(MappingError):
        StateCollector(api, CONFIG)
