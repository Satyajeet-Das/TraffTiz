"""Load and check an experiment plan (configs/experiments*.yaml).

A plan compares *variants*: a controller together with the settings it uses.
A variant may list a tuning grid; the tuning stage then writes the chosen values
to the variant's `settings` file, which later stages merge into its config.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from optitraffic.config import ConfigError, load_config
from optitraffic.control.controllers import CONTROLLERS

_REQUIRED = {"experiment_id", "base_configs", "workers", "scenarios", "variants",
             "tuning", "evaluation", "verify"}
_OPTIONAL = {"solver_study"}
_KEYS = {
    "tuning": {"seeds"},
    "evaluation": {"seeds", "proposed", "baselines", "primary_metric", "metrics", "confidence"},
    "verify": {"runs", "seed"},
    "solver_study": {
        "variant", "seed", "max_iterations", "sgd_states", "curve_states", "penalty_rho",
        "penalty_states", "penalty_max_iterations", "penalty_grid_checks",
        "quadratic_dimensions", "quadratic_conditions", "quadratic_problems",
        "rosenbrock_max_iterations",
    },
}
_VARIANT_KEYS = {"controller", "label", "settings", "overrides", "tune"}


@dataclass(frozen=True)
class Variant:
    name: str
    controller: str
    label: str
    settings: Path | None  # config overlay; written by tuning if `tune` is given
    overrides: tuple[tuple[str, str, object], ...]  # (section, key, value)
    tune: tuple[tuple[str, str, tuple[float, ...]], ...]  # (section, key, grid)


@dataclass(frozen=True)
class ExperimentPlan:
    experiment_id: str
    base_configs: tuple[Path, ...]
    workers: int
    scenarios: tuple[str, ...]
    variants: Mapping[str, Variant]
    tuning: Mapping
    evaluation: Mapping
    verify: Mapping
    solver_study: Mapping | None
    source: Path

    @property
    def controllers(self) -> tuple[str, ...]:
        """Names of the variants in the evaluation, proposed last."""
        return (*self.evaluation["baselines"], self.evaluation["proposed"])

    @property
    def labels(self) -> dict[str, str]:
        """Display names in the order the plan lists the variants."""
        return {name: v.label for name, v in self.variants.items() if name in self.controllers}


def load_plan(path: str | Path, root: Path) -> ExperimentPlan:
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ConfigError(f"cannot read {path}: {error}") from error
    if not isinstance(data, Mapping) or not _REQUIRED <= set(data) <= _REQUIRED | _OPTIONAL:
        found = sorted(data) if isinstance(data, Mapping) else data
        raise ConfigError(
            f"{path.name} needs the keys {sorted(_REQUIRED)} (optionally {sorted(_OPTIONAL)}); "
            f"got {found}"
        )
    for section, expected in _KEYS.items():
        if section in _OPTIONAL and section not in data:
            continue
        part = data[section]
        if not isinstance(part, Mapping) or set(part) != expected:
            found = sorted(part) if isinstance(part, Mapping) else part
            raise ConfigError(f"{section} needs exactly the keys {sorted(expected)}; got {found}")
    if not isinstance(data["variants"], Mapping) or not data["variants"]:
        raise ConfigError("variants must be a non-empty mapping")
    plan = ExperimentPlan(
        experiment_id=str(data["experiment_id"]),
        base_configs=tuple(root / p for p in data["base_configs"]),
        workers=int(data["workers"]),
        scenarios=tuple(data["scenarios"]),
        variants={name: _variant(name, item, root) for name, item in data["variants"].items()},
        tuning=data["tuning"],
        evaluation=data["evaluation"],
        verify=data["verify"],
        solver_study=data.get("solver_study"),
        source=path,
    )
    _check(plan, root)
    return plan


def _variant(name: str, data: object, root: Path) -> Variant:
    if not isinstance(data, Mapping) or "controller" not in data or set(data) - _VARIANT_KEYS:
        raise ConfigError(
            f"variant {name!r} needs 'controller' and may only use {sorted(_VARIANT_KEYS)}"
        )
    if data["controller"] not in CONTROLLERS:
        raise ConfigError(f"unknown controller(s): {data['controller']}")
    overrides = tuple(
        (section, key, value)
        for section, values in data.get("overrides", {}).items()
        for key, value in values.items()
    )
    tune = []
    for dotted, grid in data.get("tune", {}).items():
        section, _, key = str(dotted).partition(".")
        if not key or not isinstance(grid, list) or not grid:
            raise ConfigError(f"variant {name!r}: tune needs 'section.key: [values]'; got {dotted!r}")
        tune.append((section, key, tuple(float(v) for v in grid)))
    settings = root / data["settings"] if "settings" in data else None
    if tune and settings is None:
        raise ConfigError(f"variant {name!r} is tuned, so it needs a settings file to write")
    return Variant(
        name=str(name),
        controller=data["controller"],
        label=str(data.get("label", name)),
        settings=settings,
        overrides=overrides,
        tune=tuple(tune),
    )


def _check(plan: ExperimentPlan, root: Path) -> None:
    if plan.workers < 1:
        raise ConfigError("workers must be at least 1")
    for name in plan.scenarios:
        if not (root / "configs" / "scenarios" / f"{name}.yaml").is_file():
            raise ConfigError(f"unknown scenario {name!r}")
    unknown = [c for c in plan.controllers if c not in plan.variants]
    if unknown:
        raise ConfigError(f"unknown variant(s) in the evaluation: {', '.join(unknown)}")
    if len(set(plan.controllers)) != len(plan.controllers):
        raise ConfigError("each variant may appear only once in the evaluation")
    # Every override and tuned key must exist in the configuration.
    scenario = root / "configs" / "scenarios" / f"{plan.scenarios[0]}.yaml"
    for variant in plan.variants.values():
        overrides: dict[str, dict[str, object]] = {}
        tuned = tuple((section, key, grid[0]) for section, key, grid in variant.tune)
        for section, key, value in (*variant.overrides, *tuned):
            overrides.setdefault(section, {})[key] = value
        load_config(*plan.base_configs, scenario, overrides=overrides or None)
    tuning, evaluation = plan.tuning["seeds"], plan.evaluation["seeds"]
    for seeds, name in ((tuning, "tuning"), (evaluation, "evaluation")):
        if not seeds or len(set(seeds)) != len(seeds):
            raise ConfigError(f"{name} seeds must be non-empty and different")
    shared = sorted(set(tuning) & set(evaluation))
    if shared:
        raise ConfigError(f"tuning and evaluation must not share seeds: {shared}")
    if plan.evaluation["primary_metric"] not in plan.evaluation["metrics"]:
        raise ConfigError("the primary metric must be one of the compared metrics")
    if plan.solver_study and plan.solver_study["variant"] not in plan.variants:
        raise ConfigError("solver_study.variant must name a variant")
