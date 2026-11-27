"""Run batches of simulations, resumably (Technical Design section 8.2).

Each run has its own folder holding `metrics.json`, the cycle log and SUMO's
trip output. A run is skipped if its record matches the current configuration
and source code; a mismatch stops the batch, so results from different versions
can never be mixed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import traceback
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from optitraffic.config import config_to_dict, load_config
from optitraffic.control.controllers import make_controller
from optitraffic.evaluation.metrics import control_metrics, read_tripinfo, traffic_metrics
from optitraffic.integration.queue_monitor import QueueMonitor
from optitraffic.run import simulate, write_cycles
from optitraffic.simulation.routes import generate_trips
from optitraffic.types import Config

ROOT = Path(__file__).resolve().parents[3]
RECORD = "metrics.json"


class StaleResultsError(RuntimeError):
    """Existing results were produced by a different configuration or code."""


@dataclass(frozen=True)
class RunSpec:
    scenario: str
    controller: str
    seed: int
    label: str = ""  # distinguishes parameter settings
    overrides: tuple[tuple[str, str, object], ...] = ()  # (section, key, value)

    @property
    def run_id(self) -> str:
        parts = (self.scenario, self.controller, f"seed{self.seed}", self.label)
        return "__".join(p for p in parts if p)


def source_hash(root: Path = ROOT) -> str:
    """Fingerprint of the code and network that determine a run's outcome."""
    files = sorted(
        [*(root / "src" / "optitraffic").rglob("*.py"), *(root / "sumo").glob("*.xml")]
    )
    digest = hashlib.sha256()
    for path in files:
        if path.name.endswith(".net.xml"):
            continue  # generated
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()[:16]


def run_config(config_paths: Sequence[Path], spec: RunSpec) -> Config:
    overrides: dict[str, dict[str, object]] = {}
    for section, key, value in spec.overrides:
        overrides.setdefault(section, {})[key] = value
    scenario = ROOT / "configs" / "scenarios" / f"{spec.scenario}.yaml"
    return load_config(*config_paths, scenario, overrides=overrides or None)


def run_hash(config: Config, spec: RunSpec, source: str) -> str:
    content = json.dumps(
        [config_to_dict(config), spec.controller, spec.seed, source], sort_keys=True
    )
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def execute_run(
    config_paths: Sequence[Path], spec: RunSpec, folder: Path, source: str
) -> dict[str, object]:
    """Simulate once and write its record. Never raises for a failed simulation."""
    logging.getLogger("optitraffic.run").setLevel(logging.ERROR)
    config = run_config(config_paths, spec)
    record: dict[str, object] = {
        "run_id": spec.run_id,
        "scenario": spec.scenario,
        "controller": spec.controller,
        "seed": spec.seed,
        "label": spec.label,
        "beta": config.model.beta,
        "window_s": config.estimation.window_s,
        "hash": run_hash(config, spec, source),
        "status": "failed",
        "error": "",
    }
    folder.mkdir(parents=True, exist_ok=True)
    (folder / RECORD).unlink(missing_ok=True)
    started = time.perf_counter()
    try:
        record.update(_simulate(config, spec, folder))
    except Exception as error:  # recorded, so that every run is accounted for
        record["error"] = f"{type(error).__name__}: {error}"
        (folder / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
    record["wall_s"] = round(time.perf_counter() - started, 2)
    temporary = folder / (RECORD + ".tmp")
    temporary.write_text(json.dumps(record, indent=1), encoding="utf-8")
    temporary.replace(folder / RECORD)
    return record


def _simulate(config: Config, spec: RunSpec, folder: Path) -> dict[str, object]:
    warmup, end = config.simulation.warmup_s, config.simulation.end_s
    edges = [origin for phase in config.network.phase_movements for origin, _ in phase]
    monitor = QueueMonitor(edges, warmup, end)
    trips_file = folder / "tripinfo.xml.gz"
    result = simulate(
        config,
        make_controller(spec.controller, config, spec.seed),
        spec.seed,
        folder,
        on_step=lambda sim, stage: monitor.observe(sim.api, sim.time),
        sumo_options=(
            "--tripinfo-output", str(trips_file),
            "--tripinfo-output.write-unfinished", "true",
            "--tripinfo-output.write-undeparted", "true",
        ),
    )
    write_cycles(folder / "cycles.csv", result.cycles)
    record: dict[str, object] = {
        "collisions": result.collisions,
        "teleports": result.teleports,
        "error": result.failure,
    }
    if result.failure:
        return {**record, "status": "failed"}
    schedule = generate_trips(config.scenario, config.network, config.simulation, spec.seed)
    record.update(traffic_metrics(read_tripinfo(trips_file), schedule, warmup, end))
    record.update(monitor.summary())
    record.update(control_metrics(result.cycles, config.signal, warmup))
    record["status"] = "done" if result.valid else "invalid"
    # Large files that the seed regenerates exactly.
    for name in ("intersection.net.xml", f"{spec.scenario}_seed{spec.seed}.rou.xml"):
        (folder / name).unlink(missing_ok=True)
    return record


def read_record(folder: Path) -> dict[str, object] | None:
    try:
        return json.loads((folder / RECORD).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def run_batch(
    config_paths: Sequence[Path],
    specs: Sequence[RunSpec],
    folder: Path,
    workers: int = 1,
    progress: Callable[[str], None] = print,
) -> list[dict[str, object]]:
    """Records for all specs, in order. Failed runs are tried again."""
    ids = [s.run_id for s in specs]
    if len(ids) != len(set(ids)):
        raise ValueError("two runs have the same id")
    source = source_hash()
    records: dict[str, dict[str, object]] = {}
    pending, stale = [], []
    for spec in specs:
        record = read_record(folder / spec.run_id)
        if record is None or record["status"] == "failed":
            pending.append(spec)
        elif record["hash"] != run_hash(run_config(config_paths, spec), spec, source):
            stale.append(spec.run_id)
        else:
            records[spec.run_id] = record
    if stale:
        raise StaleResultsError(
            f"{len(stale)} existing runs in {folder} were made with a different configuration "
            f"or code (e.g. {stale[0]}). Use a new experiment_id, or delete that folder."
        )

    progress(f"{len(specs)} runs: {len(records)} already done, {len(pending)} to run, "
             f"{workers} at a time")
    started = time.perf_counter()
    arguments = [(list(config_paths), s, folder / s.run_id, source) for s in pending]
    if workers == 1:
        finished = (execute_run(*a) for a in arguments)
        _collect(finished, records, len(pending), started, progress)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(execute_run, *a) for a in arguments]
            finished = (f.result() for f in as_completed(futures))
            _collect(finished, records, len(pending), started, progress)
    return [records[run_id] for run_id in ids]


def _collect(finished, records, total, started, progress) -> None:
    for count, record in enumerate(finished, 1):
        records[record["run_id"]] = record
        if record["status"] != "done":
            progress(f"  {record['status'].upper()}: {record['run_id']} {record['error']}")
        if count % 50 == 0 or count == total:
            progress(f"  {count}/{total} runs, {time.perf_counter() - started:.0f} s")
