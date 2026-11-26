"""Shared test data: the worked examples of Technical Design section 5.5."""

import pytest

from optitraffic.types import ObjectiveData

CASE_QUEUES = {"A": (40.0, 10.0), "B": (20.0, 15.0), "C": (20.0, 1.0)}


def make_data(queue, arrival_rate=(0.2, 0.1), beta=0.1, discharge_rate=(0.5, 0.5), weight=(1.0, 1.0)):
    return ObjectiveData(
        queue=tuple(queue),
        arrival_rate=tuple(arrival_rate),
        discharge_rate_vps=tuple(discharge_rate),
        queue_weight=tuple(weight),
        beta=beta,
        cycle_s=90.0,
    )


def random_data(rng):
    return make_data(
        queue=rng.uniform(0, 50, 2),
        arrival_rate=rng.uniform(0.0, 0.4, 2),
        beta=float(rng.uniform(0.0, 1.0)),
        discharge_rate=rng.uniform(0.3, 1.0, 2),
        weight=rng.uniform(0.2, 3.0, 2),
    )


@pytest.fixture
def case():
    return lambda name: make_data(CASE_QUEUES[name])
