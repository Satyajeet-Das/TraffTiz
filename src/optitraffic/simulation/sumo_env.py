"""Locate a SUMO installation (pip package, SUMO_HOME or PATH)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


class SumoNotFoundError(RuntimeError):
    """No usable SUMO executable was found."""


def find_binary(name: str = "sumo") -> str:
    """Return the full path of a SUMO executable such as `sumo` or `netconvert`.

    The pinned pip package is preferred so that runs use a known version.
    """
    exe = f"{name}.exe" if os.name == "nt" else name
    homes: list[str] = []
    try:
        import sumo  # provided by the eclipse-sumo package

        homes.append(sumo.SUMO_HOME)
    except ImportError:
        pass
    if os.environ.get("SUMO_HOME"):
        homes.append(os.environ["SUMO_HOME"])

    for home in homes:
        candidate = Path(home) / "bin" / exe
        if candidate.is_file():
            return str(candidate)
    on_path = shutil.which(name)
    if on_path:
        return on_path
    raise SumoNotFoundError(f"'{name}' not found; install the project's 'sim' extra")


def sumo_environment(binary: str) -> dict[str, str]:
    """Environment for a SUMO subprocess, with SUMO_HOME matching the binary."""
    return {**os.environ, "SUMO_HOME": str(Path(binary).parent.parent)}
