"""Observation of a signal that SUMO runs itself, and the actuated program file."""

import itertools
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import pytest

from optitraffic.config import ConfigError, load_config
from optitraffic.integration.signal_monitor import SignalMonitor
from optitraffic.simulation.signals import STAGES, write_actuated_program

CONFIG = load_config(Path(__file__).resolve().parents[1] / "configs" / "default.yaml")
STATES = {
    "ns_green": "GrGr", "ns_yellow": "yryr", "all_red_1": "rrrr",
    "ew_green": "rGrG", "ew_yellow": "ryry", "all_red_2": "rrrr",
}


def feed(durations):
    monitor = SignalMonitor(STATES, CONFIG.signal)
    time = itertools.count()
    for stage, seconds in durations:
        for _ in range(seconds):
            monitor.observe(STATES[stage], float(next(time)))
    return monitor


def cycle(ns, ew, yellow=3, red=2):
    return list(zip(STAGES, (ns, yellow, red, ew, yellow, red)))


def test_completed_greens_are_recorded():
    monitor = feed(cycle(20, 45) + cycle(11, 71) + [("ns_green", 5)])
    assert monitor.errors == []
    assert [(g.phase, g.start_s, g.displayed_s) for g in monitor.greens] == [
        (0, 0.0, 20.0), (1, 25.0, 45.0), (0, 75.0, 11.0), (1, 91.0, 71.0),
    ]  # the unfinished last green is not counted


@pytest.mark.parametrize("durations, text", [
    (cycle(20, 20, yellow=2), "lasted 2 s"),
    (cycle(20, 20, red=1) + [("ns_green", 1)], "lasted 1 s"),
    ([("ns_green", 20), ("ew_green", 20)], "unexpected state"),  # no clearance
    ([("ns_green", 20), ("all_red_1", 2)], "unexpected state"),  # no yellow
    ([("ew_green", 20)], "unexpected state"),  # wrong first stage
])
def test_unsafe_sequences_are_reported(durations, text):
    errors = feed(durations).errors
    assert errors and any(text in error for error in errors)


def test_actuated_program_uses_the_signal_limits(tmp_path):
    path = tmp_path / "a.add.xml"
    write_actuated_program(path, "C", STATES, CONFIG.signal, CONFIG.actuated)
    logic = ElementTree.parse(path).getroot().find("tlLogic")
    assert logic.get("type") == "actuated"
    assert {p.get("key"): float(p.get("value")) for p in logic.findall("param")} == {
        "max-gap": 3.0, "detector-gap": 2.0}
    phases = logic.findall("phase")
    assert [p.get("state") for p in phases] == [STATES[s] for s in STAGES]
    for stage, phase in zip(STAGES, phases):
        if stage.endswith("green"):  # displayed limits: effective 10..70 plus 1 s
            assert (phase.get("minDur"), phase.get("maxDur")) == ("11", "71")
        else:
            assert phase.get("minDur") is None
            assert phase.get("duration") == ("3" if "yellow" in stage else "2")


@pytest.mark.parametrize("override", [
    {"estimation": {"queue_sampling": "sometimes"}},
    {"actuated": {"max_gap_s": 0}},
    {"actuated": {"detector_gap_s": -1}},
])
def test_new_settings_are_validated(override):
    path = Path(__file__).resolve().parents[1] / "configs" / "default.yaml"
    with pytest.raises(ConfigError):
        load_config(path, overrides=override)
