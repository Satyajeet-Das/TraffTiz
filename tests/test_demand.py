import numpy as np
import pytest

from optitraffic.modelling.critical import critical_approach
from optitraffic.modelling.demand import DemandEstimator


def estimator(window=180.0, minimum=90.0, approaches=2, start=0.0):
    return DemandEstimator(approaches, window, minimum, start)


def feed(e, until, per_step=(1, 0), every=1):
    for t in range(1, until + 1):
        e.record(float(t), per_step if t % every == 0 else (0,) * e.approaches)


def test_not_ready_during_first_cycle():
    e = estimator()
    feed(e, 89)
    assert e.rates(89.0) is None
    e.record(90.0, (1, 0))
    assert e.rates(90.0) == (1.0, 0.0)


def test_uses_elapsed_time_until_window_is_full():
    e = estimator()
    feed(e, 120, every=4)  # one arrival every 4 s on the first approach
    assert e.rates(120.0) == pytest.approx((0.25, 0.0))


def test_old_arrivals_leave_the_window():
    e = estimator(window=100.0, minimum=10.0)
    for t in range(1, 101):
        e.record(float(t), (1, 0))
    for t in range(101, 151):
        e.record(float(t), (0, 2))
    # Window (50, 150]: 50 arrivals on the first, 100 on the second approach.
    assert e.rates(150.0) == pytest.approx((0.5, 1.0))
    assert e.rates(400.0) == (0.0, 0.0)


def test_boundary_event_is_excluded():
    e = estimator(window=10.0, minimum=1.0, approaches=1)
    e.record(5.0, (3,))
    assert e.rates(14.9) == (0.3,)
    assert e.rates(15.0) == (0.0,)


def test_window_shorter_than_cycle_is_ready_after_one_window():
    e = estimator(window=30.0, minimum=90.0)
    feed(e, 30)
    assert e.rates(30.0) == (1.0, 0.0)


def test_reset_and_start_time():
    e = estimator(start=1000.0)
    assert e.rates(1089.0) is None
    assert e.rates(1090.0) == (0.0, 0.0)
    e.reset(2000.0)
    assert e.rates(2010.0) is None


def test_rates_are_nonnegative_and_finite():
    rng = np.random.default_rng(12)
    e = estimator()
    for t in range(1, 2000):
        e.record(float(t), tuple(int(n) for n in rng.poisson((0.2, 0.05))))
        rates = e.rates(float(t))
        assert rates is None or all(np.isfinite(r) and r >= 0 for r in rates)


def test_unbiased_for_poisson_arrivals():
    rng = np.random.default_rng(13)
    estimates = []
    for _ in range(300):
        e = estimator(approaches=1)
        for t in range(1, 361):
            e.record(float(t), (int(rng.poisson(0.2)),))
        estimates.append(e.rates(360.0)[0])
    assert np.mean(estimates) == pytest.approx(0.2, rel=0.03)
    assert np.var(estimates) == pytest.approx(0.2 / 180, rel=0.25)  # lambda / window


@pytest.mark.parametrize("counts", [(-1, 0), (1,), (1, 2, 3), (0.5, 0), (float("nan"), 0)])
def test_invalid_counts_rejected(counts):
    with pytest.raises(ValueError):
        estimator().record(1.0, counts)


@pytest.mark.parametrize("time", [float("nan"), float("inf"), 4.0])
def test_invalid_or_backward_time_rejected(time):
    e = estimator()
    e.record(5.0, (0, 0))
    with pytest.raises(ValueError):
        e.record(time, (0, 0))
    with pytest.raises(ValueError):
        e.rates(time)


@pytest.mark.parametrize(
    "arguments", [(0, 180, 90), (2, 0, 90), (2, 180, -1), (2, float("nan"), 90)]
)
def test_invalid_settings_rejected(arguments):
    with pytest.raises(ValueError):
        DemandEstimator(*arguments)


def test_critical_approach_uses_expected_queue():
    # Second approach has the shorter queue but far more arrivals.
    assert critical_approach([10, 5], [0.0, 0.2], 90) == (5, 0.2)
    assert critical_approach([10, 5], [0.0, 0.0], 90) == (10, 0.0)
    assert critical_approach([7, 7], [0.1, 0.1], 90) == (7, 0.1)


@pytest.mark.parametrize(("queues", "rates"), [([], []), ([1], [0.1, 0.2])])
def test_critical_approach_rejects_bad_input(queues, rates):
    with pytest.raises(ValueError):
        critical_approach(queues, rates, 90)
