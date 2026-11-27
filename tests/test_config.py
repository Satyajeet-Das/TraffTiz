from pathlib import Path

import pytest
import yaml

from optitraffic.config import ConfigError, build_config, config_to_dict, load_config

DEFAULT = Path(__file__).resolve().parents[1] / "configs" / "default.yaml"


def default_data():
    return yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))


def test_defaults_match_design():
    config = load_config(DEFAULT)
    assert config.signal.lost_time_s == 12
    assert config.signal.green_budget_s == 78
    assert config.signal.displayed_green_s(39) == 40
    assert config.model.discharge_rate_vps == pytest.approx((1860 / 3600, 1860 / 3600))
    assert config.model.beta == 0.1
    assert config.solver.name == "projected_gradient"


def test_round_trip():
    config = load_config(DEFAULT)
    assert build_config(config_to_dict(config)) == config


def test_later_file_and_overrides_take_priority(tmp_path):
    scenario = tmp_path / "scenario.yaml"
    scenario.write_text("model:\n  beta: 0.5\nsolver:\n  name: newton\n", encoding="utf-8")
    config = load_config(DEFAULT, scenario, overrides={"model": {"beta": 0.7}})
    assert config.model.beta == 0.7
    assert config.solver.name == "newton"
    assert config.model.queue_weight == (1.0, 1.0)  # untouched keys survive the merge


def test_config_is_immutable():
    config = load_config(DEFAULT)
    with pytest.raises(AttributeError):
        config.signal.cycle_s = 100


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("signal", "cycle_s", 0),
        ("signal", "cycle_s", 90.5),
        ("signal", "yellow_s", 0),
        ("signal", "all_red_s", -1),
        ("signal", "g_min_s", True),
        ("signal", "g_min_s", 40),  # 2 * g_min exceeds the budget
        ("signal", "g_max_s", 38),  # 2 * g_max is below the budget
        ("signal", "green_lost_s", -1),
        ("signal", "green_lost_s", 0.5),
        ("estimation", "pending_in_queue", 0),
        ("signal", "g_min_s", 71),  # above g_max
        ("model", "saturation_flow_vph", [1800]),
        ("model", "saturation_flow_vph", [1800, 0]),
        ("model", "queue_weight", [1.0, float("nan")]),
        ("model", "queue_weight", "11"),
        ("model", "beta", -0.1),
        ("model", "beta", float("inf")),
        ("estimation", "window_s", 0),
        ("estimation", "include_pending", "yes"),
        ("estimation", "include_pending", 1),
        ("solver", "name", "simplex"),
        ("solver", "tolerance", "small"),
        ("solver", "max_iterations", 0),
        ("solver", "time_budget_s", -1),
        ("simulation", "step_length_s", 0),
    ],
)
def test_invalid_values_rejected(section, key, value):
    data = default_data()
    data[section][key] = value
    with pytest.raises(ConfigError):
        build_config(data)


@pytest.mark.parametrize(("g_min", "g_max"), [(39, 70), (10, 39)])
def test_feasibility_limits_are_inclusive(g_min, g_max):
    data = default_data()
    data["signal"].update(g_min_s=g_min, g_max_s=g_max)
    assert build_config(data).signal.green_budget_s == 78


def test_beta_may_be_zero():
    data = default_data()
    data["model"]["beta"] = 0
    assert build_config(data).model.beta == 0.0


def test_unknown_and_missing_keys_rejected():
    data = default_data()
    data["model"]["betta"] = 0.1
    with pytest.raises(ConfigError, match="unknown key"):
        build_config(data)

    data = default_data()
    del data["signal"]["cycle_s"]
    with pytest.raises(ConfigError, match="missing key"):
        build_config(data)

    data = default_data()
    data["extra"] = {}
    with pytest.raises(ConfigError, match="unknown key"):
        build_config(data)


def test_section_must_be_mapping():
    data = default_data()
    data["signal"] = 5
    with pytest.raises(ConfigError, match="must be a mapping"):
        build_config(data)


@pytest.mark.parametrize("content", ["", "- 1\n", "signal: [\n"])
def test_bad_files_rejected(tmp_path, content):
    path = tmp_path / "bad.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_missing_file_and_no_file_rejected(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "absent.yaml")
    with pytest.raises(ConfigError):
        load_config()
