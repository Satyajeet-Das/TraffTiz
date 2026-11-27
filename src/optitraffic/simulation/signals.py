"""Signal state strings and fixed-time programs (Technical Design section 7.3)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from optitraffic.types import NetworkParams, SignalParams

# One cycle, in order.
STAGES = ("ns_green", "ns_yellow", "all_red_1", "ew_green", "ew_yellow", "all_red_2")


def stage_states(
    links: Sequence[tuple[str, str, int]], network: NetworkParams
) -> dict[str, str]:
    """State string for every stage, derived from the network's link order.

    Raises ValueError unless the network's connections are exactly the configured
    movements and the link indices run from 0 without gaps.
    """
    phase_of = {m: phase for phase in (0, 1) for m in network.phase_movements[phase]}
    found = {(origin, destination) for origin, destination, _ in links}
    if found != set(phase_of):
        raise ValueError(
            f"network connections {sorted(found)} differ from configured movements {sorted(phase_of)}"
        )
    if sorted(index for _, _, index in links) != list(range(len(links))):
        raise ValueError("signal link indices must be 0..n-1 without gaps or repeats")
    phases = [phase_of[(o, d)] for o, d, _ in sorted(links, key=lambda link: link[2])]

    def state(active: int | None, colour: str) -> str:
        return "".join(colour if phase == active else "r" for phase in phases)

    all_red = state(None, "r")
    return {
        "ns_green": state(0, "G"),
        "ns_yellow": state(0, "y"),
        "all_red_1": all_red,
        "ew_green": state(1, "G"),
        "ew_yellow": state(1, "y"),
        "all_red_2": all_red,
    }


def cycle_stages(signal: SignalParams, green: tuple[int, int]) -> list[tuple[str, int]]:
    """(stage, duration in s) for one cycle; stages of zero length are omitted."""
    if sum(green) != signal.green_budget_s or not all(
        isinstance(g, int) and signal.g_min_s <= g <= signal.g_max_s for g in green
    ):
        raise ValueError(f"green times {green} are not a feasible whole-second plan")
    durations = (
        green[0], signal.yellow_s, signal.all_red_s,
        green[1], signal.yellow_s, signal.all_red_s,
    )
    return [(stage, d) for stage, d in zip(STAGES, durations) if d > 0]


def write_fixed_program(
    path: str | Path,
    tls_id: str,
    states: dict[str, str],
    signal: SignalParams,
    green: tuple[int, int],
) -> None:
    """Write a static program as a SUMO additional file."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<additional>",
        f'    <tlLogic id="{tls_id}" type="static" programID="fixed" offset="0">',
    ]
    lines += [
        f'        <phase duration="{duration}" state="{states[stage]}" name="{stage}"/>'
        for stage, duration in cycle_stages(signal, green)
    ]
    lines += ["    </tlLogic>", "</additional>"]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
