import numpy as np
import pytest
from conftest import make_data, random_data

from optitraffic.modelling.queue import predict_queue, raw_queue
from optitraffic.types import ModelParams, ObjectiveData, SignalParams


def test_hand_calculation(case):
    data = case("A")
    np.testing.assert_allclose(raw_queue(data, (40, 40)), (38, -1))
    np.testing.assert_allclose(predict_queue(data, (40, 40)), (38, 0))


def test_queue_never_negative():
    rng = np.random.default_rng(1)
    for _ in range(500):
        assert np.all(predict_queue(random_data(rng), rng.uniform(0, 90, 2)) >= 0)


def test_broadcasts_over_many_plans(case):
    plans = np.array([[40.0, 40.0], [70.0, 10.0]])
    np.testing.assert_allclose(predict_queue(case("A"), plans), [[38, 0], [23, 14]])


def test_built_from_configuration_converts_units():
    signal = SignalParams(cycle_s=90, yellow_s=3, all_red_s=2, g_min_s=10, g_max_s=70)
    model = ModelParams(saturation_flow_vph=(1800, 3600), queue_weight=(1, 2), beta=0.1)
    data = ObjectiveData.from_params((40, 10), (0.2, 0.1), model, signal)
    assert data.discharge_rate_vps == (0.5, 1.0)
    assert data.cycle_s == 90
    assert data.queue == (40.0, 10.0)


@pytest.mark.parametrize(
    "changes",
    [
        {"queue": (-1, 0)},
        {"queue": (float("nan"), 0)},
        {"queue": (1, 2, 3)},
        {"arrival_rate": (0.1, -0.1)},
        {"arrival_rate": (float("inf"), 0.1)},
        {"discharge_rate": (0.0, 0.5)},
        {"weight": (1.0, 0.0)},
        {"beta": -0.1},
        {"beta": float("nan")},
    ],
)
def test_invalid_data_rejected(changes):
    arguments = {"queue": (1, 1), **changes}
    with pytest.raises(ValueError):
        make_data(**arguments)


@pytest.mark.parametrize("green", [(float("nan"), 40), (40, float("inf")), (40,), (1, 2, 3)])
def test_invalid_green_rejected(case, green):
    with pytest.raises(ValueError):
        predict_queue(case("A"), green)
