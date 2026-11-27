"""Run one simulation with a signal controller.

    python -m optitraffic.run --scenario medium --controller adaptive --seed 1

Travel-time and waiting-time metrics are added in milestone M9.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from optitraffic.config import config_to_dict, load_config
from optitraffic.control.controllers import CONTROLLERS, Controller, make_controller
from optitraffic.control.signal_controller import SignalController
from optitraffic.control.validator import FALLBACK, Validator
from optitraffic.integration.client import TraciClient
from optitraffic.integration.state_collector import StateCollector
from optitraffic.simulation.fixed_run import StepCounter, prepare_files, sumo_command
from optitraffic.types import SOLVER_NAMES, Config, CycleRecord

ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunResult:
    scenario: str
    controller: str
    seed: int
    end_time_s: float
    scheduled: int
    departed: int
    arrived: int
    collisions: int
    teleports: int
    cycles: tuple[CycleRecord, ...]
    failure: str = ""  # set if the simulation connection was lost

    @property
    def fallbacks(self) -> int:
        return sum(c.plan.source == FALLBACK for c in self.cycles)

    @property
    def valid(self) -> bool:
        return not self.failure and self.collisions == 0 and self.teleports == 0


def simulate(
    config: Config,
    controller: Controller,
    seed: int,
    folder: str | Path,
    gui: bool = False,
    on_step: Callable[[TraciClient, str], None] | None = None,
) -> RunResult:
    """Run until warm-up + duration. `on_step` receives the client and stage name."""
    from traci.exceptions import FatalTraCIError

    validator = Validator(
        config.signal, config.solver.time_budget_s, config.solver.accept_unconverged
    )
    files = prepare_files(config, seed, folder, validator.fallback_green)
    signals = SignalController(files.states, config.signal, config.simulation.step_length_s)
    counter = StepCounter()
    cycles: list[CycleRecord] = []
    end_time, failure = 0.0, ""
    try:
        with TraciClient(sumo_command(config, files, seed, gui)) as sim:
            collector = StateCollector(sim.api, config, start_s=sim.time)
            while sim.time < config.simulation.end_s:
                if signals.at_boundary:
                    state = collector.read()
                    plan, elapsed = validator.decide(controller, state)
                    if plan.source == FALLBACK:
                        log.warning("t = %.0f s: fallback plan: %s", sim.time, plan.reason)
                    signals.load(plan)
                    cycles.append(CycleRecord(sim.time, state, plan, elapsed))
                stage = signals.apply(sim.api, config.network.tls_id)
                sim.step()
                collector.observe()
                counter.update(sim.api)
                end_time = sim.time
                if on_step is not None:
                    on_step(sim, stage)
    except FatalTraCIError as error:
        failure = f"simulation connection lost: {error}"
    return RunResult(
        scenario=config.scenario.name,
        controller=controller.name,
        seed=seed,
        end_time_s=end_time,
        scheduled=files.trips,
        departed=counter.departed,
        arrived=counter.arrived,
        collisions=counter.collisions,
        teleports=counter.teleports,
        cycles=tuple(cycles),
        failure=failure,
    )


def write_cycles(path: str | Path, cycles: tuple[CycleRecord, ...]) -> None:
    """One row per decision: measurements, applied plan, why, and the solver result.

    The solver columns are empty when no solver ran. They are kept when its plan
    was rejected, so `green_ns` then differs from the solver's solution.
    """
    columns = [
        "start_s", "valid", "queue_ns", "queue_ew", "rate_ns", "rate_ew", "pending_ns",
        "pending_ew", "green_ns", "green_ew", "source", "reason", "decision_s",
        "solver", "status", "iterations", "solution_ns", "objective", "residual", "solver_s",
    ]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for c in cycles:
            r = c.plan.solver
            solver = [""] * 6 if r is None else [
                r.status, r.iterations, float(r.x[0]), r.objective, r.residual,
                f"{r.runtime_s:.6f}",
            ]
            writer.writerow([
                c.start_s, c.state.valid, *c.state.queue, *c.state.arrival_rate,
                *c.state.pending, *c.plan.green, c.plan.source,
                c.plan.reason or "; ".join(c.state.issues), f"{c.decision_s:.6f}",
                c.plan.solver_name, *solver,
            ])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one simulation with a signal controller.")
    parser.add_argument("--config", default=ROOT / "configs" / "default.yaml")
    parser.add_argument("--scenario", default="medium",
                        help="a name in configs/scenarios/ (default: medium)")
    parser.add_argument("--controller", choices=sorted(CONTROLLERS), default="fixed_equal")
    parser.add_argument("--solver", choices=SOLVER_NAMES,
                        help="solver for the adaptive controller (default: from the config)")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--gui", action="store_true", help="show the run in sumo-gui")
    parser.add_argument("--out", help="output folder (default: results/<run name>)")
    args = parser.parse_args(argv)
    if args.solver and args.controller != "adaptive":
        parser.error("--solver applies only to --controller adaptive")

    config = load_config(
        args.config,
        ROOT / "configs" / "scenarios" / f"{args.scenario}.yaml",
        overrides={"solver": {"name": args.solver}} if args.solver else None,
    )
    run_name = "_".join(filter(None, (args.scenario, args.controller, args.solver)))
    folder = Path(args.out or ROOT / "results" / f"{run_name}_seed{args.seed}")
    controller = make_controller(args.controller, config, args.seed)
    result = simulate(config, controller, args.seed, folder, args.gui)
    write_cycles(folder / "cycles.csv", result.cycles)
    (folder / "config.yaml").write_text(
        yaml.safe_dump(config_to_dict(config), sort_keys=False), encoding="utf-8"
    )

    print(f"{result.controller} on {result.scenario}, seed {result.seed}: "
          f"t = {result.end_time_s:.0f} s, {len(result.cycles)} cycles")
    print(f"  vehicles: {result.scheduled} scheduled, {result.departed} entered, {result.arrived} left")
    print(f"  fallback cycles: {result.fallbacks}, collisions: {result.collisions}, "
          f"teleports: {result.teleports}")
    statuses = Counter(c.plan.solver.status for c in result.cycles if c.plan.solver)
    if statuses:
        slowest = max(c.decision_s for c in result.cycles)
        summary = ", ".join(f"{name} {count}" for name, count in sorted(statuses.items()))
        print(f"  solver {config.solver.name}: {summary}; slowest decision {1000 * slowest:.1f} ms")
    print(f"  cycle log: {folder / 'cycles.csv'}")
    if result.failure:
        print(f"  FAILED: {result.failure}", file=sys.stderr)
    return 0 if result.valid else 1


if __name__ == "__main__":
    sys.exit(main())
