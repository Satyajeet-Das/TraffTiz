from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from optitraffic.config import load_config
from optitraffic.simulation.routes import generate_trips, write_route_file
from optitraffic.types import DemandSegment, ScenarioParams

ROOT = Path(__file__).resolve().parents[1]


def load(name="medium"):
    return load_config(ROOT / "configs" / "default.yaml",
                       ROOT / "configs" / "scenarios" / f"{name}.yaml")


def trips_for(config, seed):
    return generate_trips(config.scenario, config.network, config.simulation, seed)


def test_same_seed_gives_identical_file(tmp_path):
    config = load("changing")
    for name in ("a", "b"):
        write_route_file(tmp_path / name, trips_for(config, 7))
    assert (tmp_path / "a").read_bytes() == (tmp_path / "b").read_bytes()
    write_route_file(tmp_path / "c", trips_for(config, 8))
    assert (tmp_path / "a").read_bytes() != (tmp_path / "c").read_bytes()


def test_trips_are_sorted_unique_and_in_range():
    config = load("high")
    trips = trips_for(config, 1)
    departures = [t.depart_s for t in trips]
    assert departures == sorted(departures)
    assert len({t.vehicle_id for t in trips}) == len(trips)
    assert 0 <= departures[0] and departures[-1] < config.simulation.end_s
    allowed = {m for phase in config.network.phase_movements for m in phase}
    assert {(t.origin, t.destination) for t in trips} == allowed


@pytest.mark.parametrize("name", ["low", "ns_dominant"])
def test_mean_rate_matches_scenario(name):
    config = load(name)
    horizon, seeds = config.simulation.end_s, 40
    counts = {}
    for seed in range(seeds):
        for trip in trips_for(config, seed):
            counts[trip.origin] = counts.get(trip.origin, 0) + 1
    rates = config.scenario.segments[0].arrival_rate
    for phase, movements in enumerate(config.network.phase_movements):
        expected = rates[phase] * horizon
        for origin, _ in movements:
            # Poisson: the mean over seeds has variance expected / seeds.
            assert abs(counts[origin] / seeds - expected) < 4 * np.sqrt(expected / seeds)


def test_gaps_are_exponential():
    config = load("high")
    trips = [t for seed in range(20) for t in [trips_for(config, seed)]]
    gaps = np.concatenate([np.diff([t.depart_s for t in run if t.origin == "N_in"]) for run in trips])
    assert gaps.mean() == pytest.approx(5.0, rel=0.05)
    assert gaps.std() == pytest.approx(5.0, rel=0.07)  # equal to the mean if exponential


def test_changing_scenario_switches_at_half_of_measured_period():
    config = load("changing")
    switch = config.simulation.warmup_s + 0.5 * config.simulation.duration_s
    counts = np.zeros((2, 2))  # (before/after, NS/EW)
    for seed in range(10):
        for trip in trips_for(config, seed):
            counts[int(trip.depart_s >= switch), int(trip.origin[0] in "EW")] += 1
    assert counts[0, 0] > 2 * counts[0, 1]
    assert counts[1, 1] > 2 * counts[1, 0]


def test_zero_rate_gives_no_vehicles():
    config = load()
    scenario = ScenarioParams("ns_only", (DemandSegment(0.0, (0.2, 0.0)),))
    trips = trips_for(replace(config, scenario=scenario), 1)
    assert trips and all(t.origin in ("N_in", "S_in") for t in trips)


def test_approaches_have_independent_streams():
    trips = trips_for(load("high"), 1)
    north = [t.depart_s for t in trips if t.origin == "N_in"]
    south = [t.depart_s for t in trips if t.origin == "S_in"]
    assert north != south
