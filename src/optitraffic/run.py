"""Run one simulation with a signal controller.

    python -m optitraffic.run --scenario medium --controller queue_proportional --seed 1

Travel-time and waiting-time metrics are added in milestone M9.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from optitraffic.config import load_config
from optitraffic.control.controllers import CONTROLLERS, Controller, make_controller
from optitraffic.control.signal_controller import SignalController
from optitraffic.control.validator import FALLBACK, Validator
from optitraffic.integration.client import TraciClient
from optitraffic.integration.state_collector import StateCollector
from optitraffic.simulation.fixed_run import StepCounter, prepare_files, sumo_command
from optitraffic.types import Config, CycleRecord

ROOT = Path(__file__).resolve().parents[2]


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

    validator = Validator(config.signal, config.solver.time_budget_s)
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
    """One row per decision: measurements, applied plan and why."""
    columns = [
        "start_s", "valid", "queue_ns", "queue_ew", "rate_ns", "rate_ew", "pending_ns",
        "pending_ew", "green_ns", "green_ew", "source", "reason", "decision_s",
    ]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for c in cycles:
            writer.writerow([
                c.start_s, c.state.valid, *c.state.queue, *c.state.arrival_rate,
                *c.state.pending, *c.plan.green, c.plan.source,
                c.plan.reason or "; ".join(c.state.issues), f"{c.decision_s:.6f}",
            ])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one simulation with a signal controller.")
    parser.add_argument("--config", default=ROOT / "configs" / "default.yaml")
    parser.add_argument("--scenario", default="medium",
                        help="a name in configs/scenarios/ (default: medium)")
    parser.add_argument("--controller", choices=sorted(CONTROLLERS), default="fixed_equal")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--gui", action="store_true", help="show the run in sumo-gui")
    parser.add_argument("--out", help="output folder (default: results/<scenario>_<controller>_seed<n>)")
    args = parser.parse_args(argv)

    config = load_config(args.config, ROOT / "configs" / "scenarios" / f"{args.scenario}.yaml")
    folder = Path(args.out or ROOT / "results" / f"{args.scenario}_{args.controller}_seed{args.seed}")
    result = simulate(config, make_controller(args.controller, config), args.seed, folder, args.gui)
    write_cycles(folder / "cycles.csv", result.cycles)

    print(f"{result.controller} on {result.scenario}, seed {result.seed}: "
          f"t = {result.end_time_s:.0f} s, {len(result.cycles)} cycles")
    print(f"  vehicles: {result.scheduled} scheduled, {result.departed} entered, {result.arrived} left")
    print(f"  fallback cycles: {result.fallbacks}, collisions: {result.collisions}, "
          f"teleports: {result.teleports}")
    print(f"  cycle log: {folder / 'cycles.csv'}")
    if result.failure:
        print(f"  FAILED: {result.failure}", file=sys.stderr)
    return 0 if result.valid else 1


if __name__ == "__main__":
    sys.exit(main())
