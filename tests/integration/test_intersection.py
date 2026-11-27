"""The intersection in real SUMO (FR-01)."""

from dataclasses import replace
from pathlib import Path

import pytest

from optitraffic.config import load_config
from optitraffic.simulation.fixed_run import run_fixed
from optitraffic.simulation.network import build_network, signal_links
from optitraffic.simulation.signals import cycle_stages, stage_states

pytestmark = pytest.mark.sumo

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ("low", "medium", "high", "ns_dominant", "ew_dominant", "changing")


def load(name, duration=600.0):
    config = load_config(ROOT / "configs" / "default.yaml",
                         ROOT / "configs" / "scenarios" / f"{name}.yaml")
    return replace(
        config, simulation=replace(config.simulation, warmup_s=0.0, duration_s=duration)
    )


@pytest.fixture(scope="module")
def network(tmp_path_factory):
    return build_network(tmp_path_factory.mktemp("net") / "intersection.net.xml")


def test_geometry(network):
    import sumolib

    net = sumolib.net.readNet(str(network))
    for direction in "NSEW":
        for kind in ("in", "out"):
            edge = net.getEdge(f"{direction}_{kind}")
            assert edge.getLaneNumber() == 1
            assert 270 < edge.getLength() <= 300
    assert len(net.getEdges()) == 8  # no turnarounds or extra roads


def test_signal_links_match_configuration(network):
    config = load("medium")
    states = stage_states(signal_links(network, config.network.tls_id), config.network)
    assert all(len(state) == 4 for state in states.values())


def test_unknown_traffic_light_rejected(network):
    with pytest.raises(ValueError):
        signal_links(network, "nowhere")


@pytest.mark.parametrize("name", SCENARIOS)
def test_vehicles_enter_and_leave_without_incidents(name, tmp_path):
    summary = run_fixed(load(name), seed=1, folder=tmp_path)
    assert summary.valid, summary
    assert summary.end_time_s == 600
    assert 0 < summary.arrived <= summary.departed <= summary.scheduled


def test_observed_signal_sequence_and_durations(tmp_path):
    config = load("medium", duration=270.0)  # three cycles
    observed = []
    summary = run_fixed(
        config, seed=1, folder=tmp_path, green=(50, 30),
        on_step=lambda sim: observed.append(
            sim.api.trafficlight.getRedYellowGreenState(config.network.tls_id)
        ),
    )
    assert summary.valid
    states = stage_states(
        signal_links(tmp_path / "intersection.net.xml", config.network.tls_id), config.network
    )
    expected = [
        states[stage]
        for stage, duration in cycle_stages(config.signal, (50, 30))
        for _ in range(duration)
    ] * 3
    assert observed == expected


def test_same_seed_reproduces_the_run(tmp_path):
    config = load("high")
    first = run_fixed(config, seed=5, folder=tmp_path / "a")
    assert run_fixed(config, seed=5, folder=tmp_path / "b") == first
    assert run_fixed(config, seed=6, folder=tmp_path / "c") != first
