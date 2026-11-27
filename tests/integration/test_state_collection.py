"""State collection from a real SUMO run (FR-02, FR-03)."""

import importlib.util
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from optitraffic.config import load_config

pytestmark = pytest.mark.sumo

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location(
        "check_estimates", ROOT / "scripts" / "check_estimates.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load(name, duration=900.0, include_pending=True):
    config = load_config(ROOT / "configs" / "default.yaml",
                         ROOT / "configs" / "scenarios" / f"{name}.yaml")
    return replace(
        config,
        simulation=replace(config.simulation, warmup_s=0.0, duration_s=duration),
        estimation=replace(config.estimation, include_pending=include_pending),
    )


def test_states_are_valid_after_the_first_cycle(tool):
    states = tool.collect(load("medium"), seed=1)
    assert [s.sim_time for s in states] == [90.0 * k for k in range(1, 11)]
    assert all(s.valid for s in states), [s.issues for s in states]
    for state in states:
        # Decision instants fall at the end of the final all-red.
        assert state.signal_state == "rrrr"
        for a in state.approaches:
            assert 0 <= a.queue <= a.vehicle_count
            assert np.isfinite(a.arrival_rate) and a.arrival_rate >= 0
            assert a.waiting_time >= 0
    assert any(s.queue[0] > 0 for s in states)


@pytest.mark.parametrize("name", ["medium", "ns_dominant", "changing"])
def test_estimates_match_generated_demand(tool, name):
    config = load(name, duration=1800.0)
    against_demand, against_rate = tool.errors(config, seed=2)
    # Every scheduled vehicle is counted exactly once, in the window where it appears.
    assert np.abs(against_demand).max() < 1e-12
    # Poisson sampling error around the true rate: sd = sqrt(rate / window) < 0.04.
    assert abs(against_rate.mean()) < 0.015
    assert np.sqrt(np.mean(against_rate**2)) < 0.06


def test_ignoring_waiting_vehicles_underestimates_a_full_road(tool):
    config = load("ns_dominant", duration=1800.0, include_pending=False)
    full = tool.collect(config, seed=2)
    assert any(s.pending[0] > 20 for s in full)
    against_demand, _ = tool.errors(config, seed=2)
    assert against_demand.min() < -0.04
