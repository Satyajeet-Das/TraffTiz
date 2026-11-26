from pathlib import Path

import pytest
import yaml

from optitraffic.config import ConfigError, build_config, config_to_dict, load_config

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "configs" / "default.yaml"
SCENARIOS = {
    "low": [(0.05, 0.05)],
    "medium": [(0.12, 0.12)],
    "high": [(0.20, 0.20)],
    "ns_dominant": [(0.28, 0.10)],
    "ew_dominant": [(0.10, 0.28)],
    "changing": [(0.28, 0.10), (0.10, 0.28)],
}


def load(name):
    return load_config(DEFAULT, ROOT / "configs" / "scenarios" / f"{name}.yaml")


def test_exactly_the_six_scenarios_exist():
    assert {p.stem for p in (ROOT / "configs" / "scenarios").glob("*.yaml")} == set(SCENARIOS)


@pytest.mark.parametrize("name", SCENARIOS)
def test_scenario_matches_design(name):
    config = load(name)
    assert config.scenario.name == name
    assert [s.arrival_rate for s in config.scenario.segments] == SCENARIOS[name]


@pytest.mark.parametrize("name", SCENARIOS)
def test_demand_is_below_capacity_on_average(name):
    config = load(name)
    capacity_share = config.signal.green_budget_s / config.signal.cycle_s
    for segment in config.scenario.segments:
        flow_ratio = sum(
            rate / mu for rate, mu in zip(segment.arrival_rate, config.model.discharge_rate_vps)
        )
        assert flow_ratio < capacity_share


def test_saved_config_round_trips_through_yaml():
    config = load("changing")
    assert build_config(yaml.safe_load(yaml.safe_dump(config_to_dict(config)))) == config


@pytest.mark.parametrize(
    "segments",
    [
        [],
        [{"start_fraction": 0.2, "arrival_rate": [0.1, 0.1]}],
        [{"start_fraction": 0.0, "arrival_rate": [0.1, 0.1]},
         {"start_fraction": 0.0, "arrival_rate": [0.1, 0.1]}],
        [{"start_fraction": 0.0, "arrival_rate": [0.1, 0.1]},
         {"start_fraction": 1.0, "arrival_rate": [0.1, 0.1]}],
        [{"start_fraction": 0.0, "arrival_rate": [-0.1, 0.1]}],
        [{"start_fraction": 0.0, "arrival_rate": [0.1]}],
        [{"start_fraction": 0.0}],
        [{"start_fraction": 0.0, "arrival_rate": [0.1, 0.1], "extra": 1}],
        ["medium"],
    ],
)
def test_invalid_segments_rejected(segments):
    data = config_to_dict(load("medium"))
    data["scenario"]["segments"] = segments
    with pytest.raises(ConfigError):
        build_config(data)


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("scenario", "name", ""),
        ("scenario", "name", "two words"),
        ("network", "tls_id", 'a"b'),
        ("network", "phase_movements", [[["N_in", "S_out"]]]),
        ("network", "phase_movements", [[], [["E_in", "W_out"]]]),
        ("network", "phase_movements", [[["N_in"]], [["E_in", "W_out"]]]),
        ("network", "phase_movements", [[["N_in", "S_out"]], [["N_in", "W_out"]]]),
        ("simulation", "warmup_s", -1),
        ("simulation", "duration_s", 0),
    ],
)
def test_invalid_network_and_run_settings_rejected(section, key, value):
    data = config_to_dict(load("medium"))
    data[section][key] = value
    with pytest.raises(ConfigError):
        build_config(data)
