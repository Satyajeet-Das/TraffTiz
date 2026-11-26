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
    DemandSegment,
    EstimationParams,
    ModelParams,
    NetworkParams,
    ScenarioParams,
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
    "network": NetworkParams,
    "scenario": ScenarioParams,
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

    t = data["simulation"]
    simulation = SimulationParams(
        step_length_s=_number(t["step_length_s"], "simulation.step_length_s", positive=True),
        warmup_s=_number(t["warmup_s"], "simulation.warmup_s", positive=False),
        duration_s=_number(t["duration_s"], "simulation.duration_s", positive=True),
    )
    return Config(
        signal, model, estimation, solver, simulation,
        _network(data["network"]), _scenario(data["scenario"]),
    )


def config_to_dict(config: Config) -> dict[str, Any]:
    """Plain dictionary that `build_config` accepts, for saving with a run."""
    return _plain(asdict(config))


def _plain(value: Any) -> Any:
    """Turn tuples into lists at every depth, so the result can be saved as YAML."""
    if isinstance(value, Mapping):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or any(c.isspace() or c in '<>&"' for c in value):
        raise ConfigError(f"{name} must be a name without spaces or XML characters; got {value!r}")
    return value


def _sequence(value: Any, name: str, length: int | None = None) -> list[Any] | tuple[Any, ...]:
    ok = isinstance(value, (list, tuple)) and value and (length is None or len(value) == length)
    if not ok:
        expected = "a non-empty list" if length is None else f"a list of {length}"
        raise ConfigError(f"{name} must be {expected}; got {value!r}")
    return value


def _network(data: Mapping[str, Any]) -> NetworkParams:
    name = "network.phase_movements"
    phases = []
    for phase in _sequence(data["phase_movements"], name, 2):
        movements = []
        for movement in _sequence(phase, name):
            origin, destination = _sequence(movement, name, 2)
            movements.append((_text(origin, name), _text(destination, name)))
        phases.append(tuple(movements))
    incoming = [origin for phase in phases for origin, _ in phase]
    if len(incoming) != len(set(incoming)):
        raise ConfigError(f"{name}: each incoming edge may appear only once")
    return NetworkParams(_text(data["tls_id"], "network.tls_id"), (phases[0], phases[1]))


def _scenario(data: Mapping[str, Any]) -> ScenarioParams:
    segments = []
    for item in _sequence(data["segments"], "scenario.segments"):
        if not isinstance(item, Mapping):
            raise ConfigError("each scenario segment must be a mapping")
        _check_keys(item, {f.name for f in fields(DemandSegment)}, "scenario segment")
        segments.append(DemandSegment(
            start_fraction=_number(item["start_fraction"], "scenario start_fraction", positive=False),
            arrival_rate=_pair(item["arrival_rate"], "scenario arrival_rate", positive=False),
        ))
    starts = [s.start_fraction for s in segments]
    if starts[0] != 0 or starts[-1] >= 1 or any(b <= a for a, b in zip(starts, starts[1:])):
        raise ConfigError("scenario segments must start at 0, increase strictly and stay below 1")
    return ScenarioParams(_text(data["name"], "scenario.name"), tuple(segments))


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
