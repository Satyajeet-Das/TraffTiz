import itertools

import pytest

from optitraffic.simulation.signals import STAGES, cycle_stages, stage_states, write_fixed_program
from optitraffic.types import NetworkParams, SignalParams

NETWORK = NetworkParams(
    "C",
    ((("N_in", "S_out"), ("S_in", "N_out")), (("E_in", "W_out"), ("W_in", "E_out"))),
)
LINKS = [("N_in", "S_out", 0), ("E_in", "W_out", 1), ("S_in", "N_out", 2), ("W_in", "E_out", 3)]
SIGNAL = SignalParams(cycle_s=90, yellow_s=3, all_red_s=2, g_min_s=10, g_max_s=70)


def test_states_follow_link_order():
    states = stage_states(LINKS, NETWORK)
    assert states == {
        "ns_green": "GrGr", "ns_yellow": "yryr", "all_red_1": "rrrr",
        "ew_green": "rGrG", "ew_yellow": "ryry", "all_red_2": "rrrr",
    }


@pytest.mark.parametrize("order", list(itertools.permutations(range(4))))
def test_no_state_serves_both_phases_for_any_link_order(order):
    links = [(o, d, order[i]) for i, (o, d, _) in enumerate(LINKS)]
    ns = {i for o, _, i in links if o[0] in "NS"}
    for state in stage_states(links, NETWORK).values():
        served = {i for i, colour in enumerate(state) if colour != "r"}
        assert not (served & ns and served - ns)


@pytest.mark.parametrize(
    "links",
    [
        LINKS[:3],  # missing movement
        LINKS + [("N_in", "E_out", 4)],  # turning movement not configured
        [(o, d, 0) for o, d, _ in LINKS],  # repeated index
        [(o, d, i + 1) for o, d, i in LINKS],  # gap at zero
    ],
)
def test_mismatched_network_rejected(links):
    with pytest.raises(ValueError):
        stage_states(links, NETWORK)


def test_cycle_order_and_length():
    stages = cycle_stages(SIGNAL, (50, 30))
    assert [s for s, _ in stages] == list(STAGES)
    assert [d for _, d in stages] == [50, 3, 2, 30, 3, 2]
    assert sum(d for _, d in stages) == SIGNAL.cycle_s


def test_zero_all_red_is_omitted():
    signal = SignalParams(cycle_s=86, yellow_s=3, all_red_s=0, g_min_s=10, g_max_s=70)
    assert [s for s, _ in cycle_stages(signal, (40, 40))] == [
        "ns_green", "ns_yellow", "ew_green", "ew_yellow"
    ]


@pytest.mark.parametrize("green", [(40, 41), (75, 5), (40.0, 40.0), (39.5, 40.5)])
def test_infeasible_plan_rejected(green):
    with pytest.raises(ValueError):
        cycle_stages(SIGNAL, green)


def test_lost_green_lengthens_displayed_green_only():
    signal = SignalParams(90, 3, 2, 10, 70, green_lost_s=1)
    assert signal.green_budget_s == 78
    stages = cycle_stages(signal, (49, 29))
    assert [d for _, d in stages] == [50, 3, 2, 30, 3, 2]
    assert sum(d for _, d in stages) == signal.cycle_s
    with pytest.raises(ValueError):
        cycle_stages(signal, (50, 30))  # displayed values are not a feasible effective plan


def test_program_file(tmp_path):
    path = tmp_path / "program.add.xml"
    write_fixed_program(path, "C", stage_states(LINKS, NETWORK), SIGNAL, (40, 40))
    text = path.read_text(encoding="utf-8")
    assert text.count("<phase ") == 6
    assert '<phase duration="40" state="GrGr" name="ns_green"/>' in text
