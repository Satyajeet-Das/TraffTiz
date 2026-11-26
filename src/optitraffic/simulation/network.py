"""Build the SUMO network from the sources in sumo/ and read its signal links."""

from __future__ import annotations

import subprocess
from pathlib import Path

from optitraffic.simulation.sumo_env import find_binary, sumo_environment

SOURCE_DIR = Path(__file__).resolve().parents[3] / "sumo"


def build_network(output: str | Path, source_dir: str | Path = SOURCE_DIR) -> Path:
    """Run netconvert on the node, edge and connection files."""
    source, output = Path(source_dir), Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    netconvert = find_binary("netconvert")
    result = subprocess.run(
        [
            netconvert,
            "--node-files", str(source / "intersection.nod.xml"),
            "--edge-files", str(source / "intersection.edg.xml"),
            "--connection-files", str(source / "intersection.con.xml"),
            "--no-turnarounds", "true",
            "--output-file", str(output),
        ],
        capture_output=True,
        text=True,
        env=sumo_environment(netconvert),
    )
    if result.returncode != 0:
        raise RuntimeError(f"netconvert failed:\n{result.stderr}")
    return output


def signal_links(network_file: str | Path, tls_id: str) -> list[tuple[str, str, int]]:
    """(incoming edge, outgoing edge, link index) for every controlled connection."""
    import sumolib

    net = sumolib.net.readNet(str(network_file))
    tls = {t.getID(): t for t in net.getTrafficLights()}
    if tls_id not in tls:
        raise ValueError(f"traffic light {tls_id!r} not found; network has {sorted(tls)}")
    return [
        (incoming.getEdge().getID(), outgoing.getEdge().getID(), index)
        for incoming, outgoing, index in tls[tls_id].getConnections()
    ]
