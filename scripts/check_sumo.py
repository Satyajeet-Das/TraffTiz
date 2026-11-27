"""Check that SUMO can be started headless and controlled through TraCI.

Builds a throwaway network in a temporary folder, runs a few steps and closes.

Run:  python scripts/check_sumo.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import traci

from optitraffic.simulation.sumo_env import find_binary, sumo_environment

STEPS = 10


def run_check(steps: int = STEPS) -> tuple[str, float]:
    """Return the SUMO version string and the simulation time after `steps` steps."""
    netgenerate = find_binary("netgenerate")
    sumo = find_binary("sumo")
    with tempfile.TemporaryDirectory() as folder:
        network = Path(folder) / "check.net.xml"
        subprocess.run(
            [netgenerate, "--grid", "--grid.number", "2", "--grid.length", "100",
             "--output-file", str(network)],
            check=True, capture_output=True, env=sumo_environment(netgenerate),
        )
        traci.start([sumo, "--net-file", str(network), "--step-length", "1",
                     "--no-step-log", "true"])
        try:
            version = traci.getVersion()[1]
            for _ in range(steps):
                traci.simulationStep()
            sim_time = traci.simulation.getTime()
        finally:
            traci.close()
    return version, sim_time


def main() -> int:
    version, sim_time = run_check()
    print(f"{version}: ran to t={sim_time:.0f} s and closed cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
