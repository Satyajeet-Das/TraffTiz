"""Load and check the experiment plan (configs/experiments.yaml)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from optitraffic.config import ConfigError
from optitraffic.control.controllers import CONTROLLERS

_KEYS = {
    None: {"experiment_id", "base_configs", "frozen_config", "workers", "scenarios",
           "tuning", "evaluation", "verify", "solver_study"},
    "tuning": {"seeds", "beta", "window_s"},
    "evaluation": {"seeds", "proposed", "baselines", "primary_metric", "metrics", "confidence"},
    "verify": {"runs", "seed"},
    "solver_study": {
        "seed", "max_iterations", "sgd_states", "curve_states", "penalty_rho",
        "penalty_states", "penalty_max_iterations", "penalty_grid_checks",
        "quadratic_dimensions", "quadratic_conditions", "quadratic_problems",
        "rosenbrock_max_iterations",
    },
}


@dataclass(frozen=True)
class ExperimentPlan:
    experiment_id: str
    base_configs: tuple[Path, ...]
    frozen_config: Path
    workers: int
    scenarios: tuple[str, ...]
    tuning: Mapping
    evaluation: Mapping
    verify: Mapping
    solver_study: Mapping
    source: Path

    @property
    def controllers(self) -> tuple[str, ...]:
        return (*self.evaluation["baselines"], self.evaluation["proposed"])


def load_plan(path: str | Path, root: Path) -> ExperimentPlan:
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ConfigError(f"cannot read {path}: {error}") from error
    for section, expected in _KEYS.items():
        part = data if section is None else data.get(section)
        if not isinstance(part, Mapping) or set(part) != expected:
            found = sorted(part) if isinstance(part, Mapping) else part
            raise ConfigError(
                f"{section or path.name} needs exactly the keys {sorted(expected)}; got {found}"
            )
    plan = ExperimentPlan(
        experiment_id=str(data["experiment_id"]),
        base_configs=tuple(root / p for p in data["base_configs"]),
        frozen_config=root / data["frozen_config"],
        workers=int(data["workers"]),
        scenarios=tuple(data["scenarios"]),
        tuning=data["tuning"],
        evaluation=data["evaluation"],
        verify=data["verify"],
        solver_study=data["solver_study"],
        source=path,
    )
    _check(plan, root)
    return plan


def _check(plan: ExperimentPlan, root: Path) -> None:
    if plan.workers < 1:
        raise ConfigError("workers must be at least 1")
    for name in plan.scenarios:
        if not (root / "configs" / "scenarios" / f"{name}.yaml").is_file():
            raise ConfigError(f"unknown scenario {name!r}")
    unknown = [c for c in plan.controllers if c not in CONTROLLERS]
    if unknown:
        raise ConfigError(f"unknown controller(s): {', '.join(unknown)}")
    tuning, evaluation = plan.tuning["seeds"], plan.evaluation["seeds"]
    for seeds, name in ((tuning, "tuning"), (evaluation, "evaluation")):
        if not seeds or len(set(seeds)) != len(seeds):
            raise ConfigError(f"{name} seeds must be non-empty and different")
    shared = sorted(set(tuning) & set(evaluation))
    if shared:
        raise ConfigError(f"tuning and evaluation must not share seeds: {shared}")
    if plan.evaluation["primary_metric"] not in plan.evaluation["metrics"]:
        raise ConfigError("the primary metric must be one of the compared metrics")
