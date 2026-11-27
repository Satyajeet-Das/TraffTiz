"""SUMO starts headless, advances through TraCI and closes."""

import importlib.util
from pathlib import Path

import pytest

from optitraffic.simulation.sumo_env import SumoNotFoundError, find_binary

pytestmark = pytest.mark.sumo

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_sumo.py"


def test_headless_run_through_traci():
    pytest.importorskip("traci")
    try:
        find_binary("sumo")
    except SumoNotFoundError as error:
        pytest.skip(str(error))
    spec = importlib.util.spec_from_file_location("check_sumo", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    version, sim_time = module.run_check(steps=5)

    assert version.startswith("SUMO")
    assert sim_time == 5.0
