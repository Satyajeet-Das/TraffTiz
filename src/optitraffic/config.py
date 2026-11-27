"""Load, merge and validate YAML configuration.

Files are merged in order (default first, then scenario files), followed by an
optional override mapping. Unknown keys, missing keys and invalid values are
errors.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

import yaml

from optitraffic.types import (
    SOLVER_NAMES,
    Config,
    EstimationParams,
    ModelParams,
    SignalParams,
    SimulationParams,
    SolverParams,
)

_SECTIONS = {
    "signal": SignalParams,
    "model": ModelParams,
    "estimation": EstimationParams,
    "solver": SolverParams,
    "simulation": SimulationParams,
}


class ConfigError(ValueError):
    """The configuration is missing, malformed or inconsistent."""


def load_config(*paths: str | Path, overrides: Mapping[str, Any] | None = None) -> Config:
    if not paths:
        raise ConfigError("at least one configuration file is required")
    merged: dict[str, Any] = {}
    for path in paths:
        merged = _merge(merged, _read_yaml(Path(path)))
    if overrides:
        merged = _merge(merged, overrides)
    return build_config(merged)


def build_config(data: Mapping[str, Any]) -> Config:
    _check_keys(data, set(_SECTIONS), "configuration")
    for name, cls in _SECTIONS.items():
        if not isinstance(data[name], Mapping):
            raise ConfigError(f"section '{name}' must be a mapping")
        _check_keys(data[name], {f.name for f in fields(cls)}, name)

    s = data["signal"]
    signal = SignalParams(
        cycle_s=_integer(s["cycle_s"], "signal.cycle_s", minimum=1),
        yellow_s=_integer(s["yellow_s"], "signal.yellow_s", minimum=1),
        all_red_s=_integer(s["all_red_s"], "signal.all_red_s", minimum=0),
        g_min_s=_integer(s["g_min_s"], "signal.g_min_s", minimum=1),
        g_max_s=_integer(s["g_max_s"], "signal.g_max_s", minimum=1),
    )
    _check_feasible(signal)

    m = data["model"]
    model = ModelParams(
        saturation_flow_vph=_pair(m["saturation_flow_vph"], "model.saturation_flow_vph", positive=True),
        queue_weight=_pair(m["queue_weight"], "model.queue_weight", positive=True),
        beta=_number(m["beta"], "model.beta", positive=False),
    )

    estimation = EstimationParams(
        window_s=_number(data["estimation"]["window_s"], "estimation.window_s", positive=True),
    )

    v = data["solver"]
    if v["name"] not in SOLVER_NAMES:
        raise ConfigError(f"solver.name must be one of {', '.join(SOLVER_NAMES)}; got {v['name']!r}")
    solver = SolverParams(
        name=v["name"],
        tolerance=_number(v["tolerance"], "solver.tolerance", positive=True),
        max_iterations=_integer(v["max_iterations"], "solver.max_iterations", minimum=1),
        time_budget_s=_number(v["time_budget_s"], "solver.time_budget_s", positive=True),
    )

    simulation = SimulationParams(
        step_length_s=_number(data["simulation"]["step_length_s"], "simulation.step_length_s", positive=True),
    )
    return Config(signal, model, estimation, solver, simulation)


def config_to_dict(config: Config) -> dict[str, Any]:
    """Plain dictionary that `build_config` accepts, for saving with a run."""
    return {
        section: {k: list(v) if isinstance(v, tuple) else v for k, v in values.items()}
        for section, values in asdict(config).items()
    }


def _read_yaml(path: Path) -> Mapping[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfigError(f"cannot read {path}: {error}") from error
    except yaml.YAMLError as error:
        raise ConfigError(f"invalid YAML in {path}: {error}") from error
    if not isinstance(data, Mapping):
        raise ConfigError(f"{path} must contain a mapping")
    return data


def _merge(base: Mapping[str, Any], update: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in update.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _check_keys(data: Mapping[str, Any], expected: set[str], where: str) -> None:
    unknown = sorted(str(k) for k in set(data) - expected)
    missing = sorted(expected - set(data))
    if unknown:
        raise ConfigError(f"unknown key(s) in {where}: {', '.join(unknown)}")
    if missing:
        raise ConfigError(f"missing key(s) in {where}: {', '.join(missing)}")


def _integer(value: Any, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ConfigError(f"{name} must be an integer >= {minimum}; got {value!r}")
    return value


def _number(value: Any, name: str, *, positive: bool) -> float:
    """A finite number, strictly positive or non-negative."""
    valid = (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and (value > 0 if positive else value >= 0)
    )
    if not valid:
        kind = "positive" if positive else "non-negative"
        raise ConfigError(f"{name} must be a finite {kind} number; got {value!r}")
    return float(value)


def _pair(value: Any, name: str, *, positive: bool) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ConfigError(f"{name} must list two values in (NS, EW) order; got {value!r}")
    ns, ew = (_number(v, name, positive=positive) for v in value)
    return (ns, ew)


def _check_feasible(signal: SignalParams) -> None:
    budget = signal.green_budget_s
    if signal.g_min_s > signal.g_max_s:
        raise ConfigError("signal.g_min_s must not exceed signal.g_max_s")
    if not 2 * signal.g_min_s <= budget <= 2 * signal.g_max_s:
        raise ConfigError(
            f"no feasible timing: green budget {budget} s must lie between "
            f"{2 * signal.g_min_s} s and {2 * signal.g_max_s} s"
        )
