"""Run one scenario under a fixed-time signal program.

Used to validate the intersection (M3). Controllers and metrics come later.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from optitraffic.integration.client import TraciClient
from optitraffic.simulation.network import build_network, signal_links
from optitraffic.simulation.routes import generate_trips, write_route_file
from optitraffic.simulation.signals import stage_states, write_fixed_program
from optitraffic.simulation.sumo_env import find_binary
from optitraffic.types import Config


@dataclass(frozen=True)
class RunFiles:
    network: Path
    routes: Path
    program: Path
    trips: int
    states: dict[str, str]


@dataclass(frozen=True)
class RunSummary:
    scenario: str
    seed: int
    end_time_s: float
    scheduled: int  # vehicles in the route file
    departed: int  # entered the network
    arrived: int  # left the network
    still_waiting_to_enter: int
    max_halting: tuple[int, int]  # largest queue on one approach, (NS, EW)
    collisions: int
    teleports: int

    @property
    def valid(self) -> bool:
        return self.collisions == 0 and self.teleports == 0


def prepare_files(config: Config, seed: int, folder: str | Path, green: tuple[int, int]) -> RunFiles:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    network = build_network(folder / "intersection.net.xml")
    states = stage_states(signal_links(network, config.network.tls_id), config.network)
    program = folder / "fixed.add.xml"
    write_fixed_program(program, config.network.tls_id, states, config.signal, green)
    trips = generate_trips(config.scenario, config.network, config.simulation, seed)
    routes = folder / f"{config.scenario.name}_seed{seed}.rou.xml"
    write_route_file(routes, trips)
    return RunFiles(network, routes, program, len(trips), states)


def sumo_command(config: Config, files: RunFiles, seed: int, gui: bool = False) -> list[str]:
    command = [
        find_binary("sumo-gui" if gui else "sumo"),
        "--net-file", str(files.network),
        "--route-files", str(files.routes),
        "--additional-files", str(files.program),
        "--seed", str(seed),
        "--step-length", str(config.simulation.step_length_s),
        "--time-to-teleport", "-1",
        "--collision.action", "warn",  # count collisions instead of teleporting
        "--collision.check-junctions", "true",
        "--no-step-log", "true",
    ]
    if gui:
        command += ["--start", "true", "--delay", "50", "--quit-on-end", "true"]
    return command


def run_fixed(
    config: Config,
    seed: int,
    folder: str | Path,
    green: tuple[int, int] | None = None,
    gui: bool = False,
    on_step: Callable[[TraciClient], None] | None = None,
) -> RunSummary:
    """Simulate until warm-up + duration. Default plan: equal split."""
    if green is None:
        half = config.signal.green_budget_s // 2
        green = (half, config.signal.green_budget_s - half)
    files = prepare_files(config, seed, folder, green)
    incoming = [[origin for origin, _ in phase] for phase in config.network.phase_movements]
    departed = arrived = collisions = teleports = 0
    worst = [0, 0]
    with TraciClient(sumo_command(config, files, seed, gui)) as sim:
        simulation = sim.api.simulation
        while sim.time < config.simulation.end_s:
            sim.step()
            departed += simulation.getDepartedNumber()
            arrived += simulation.getArrivedNumber()
            collisions += simulation.getCollidingVehiclesNumber()
            teleports += simulation.getStartingTeleportNumber()
            for phase, edges in enumerate(incoming):
                halting = max(sim.api.edge.getLastStepHaltingNumber(e) for e in edges)
                worst[phase] = max(worst[phase], halting)
            if on_step is not None:
                on_step(sim)
        end_time = sim.time
    return RunSummary(
        scenario=config.scenario.name,
        seed=seed,
        end_time_s=end_time,
        scheduled=files.trips,
        departed=departed,
        arrived=arrived,
        still_waiting_to_enter=files.trips - departed,
        max_halting=(worst[0], worst[1]),
        collisions=collisions,
        teleports=teleports,
    )
