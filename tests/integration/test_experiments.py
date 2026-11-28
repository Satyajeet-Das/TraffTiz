"""The batch runner with real SUMO runs."""

from pathlib import Path

import pytest

pytest.importorskip("pandas")

from optitraffic.evaluation.runner import RunSpec, StaleResultsError, run_batch  # noqa: E402

pytestmark = pytest.mark.sumo

ROOT = Path(__file__).resolve().parents[2]
SHORT = (("simulation", "warmup_s", 180.0), ("simulation", "duration_s", 360.0))


@pytest.fixture
def configs():
    return [ROOT / "configs" / "default.yaml"]


def specs(controllers=("fixed_equal", "adaptive"), overrides=SHORT):
    return [RunSpec("ns_dominant", c, 2, overrides=overrides) for c in controllers]


def test_batch_records_resume_and_reproduction(configs, tmp_path):
    messages = []
    first = run_batch(configs, specs(), tmp_path / "a", progress=messages.append)
    assert [r["status"] for r in first] == ["done", "done"]
    for record in first:
        assert record["vehicles"] == (
            record["finished"] + record["unfinished_on_road"] + record["never_entered"])
        assert record["avg_total_wait_s"] > 0 and record["throughput_veh"] > 0
        assert record["max_queue_veh"] > 0 and record["infeasible_applied"] == 0
    # Both controllers received exactly the same measured vehicles.
    assert first[0]["vehicles"] == first[1]["vehicles"]
    assert first[1]["solver_calls"] == first[1]["cycles"] > 0
    assert (tmp_path / "a" / specs()[0].run_id / "tripinfo.xml.gz").is_file()

    messages.clear()
    assert run_batch(configs, specs(), tmp_path / "a", progress=messages.append) == first
    assert "2 already done, 0 to run" in messages[0]

    repeated = run_batch(configs, specs(), tmp_path / "b", workers=2, progress=messages.append)
    ignored = {"wall_s", "solver_mean_ms", "solver_max_ms", "decision_max_ms"}
    for a, b in zip(first, repeated):
        assert {k: v for k, v in a.items() if k not in ignored} == {
            k: v for k, v in b.items() if k not in ignored}


def test_changed_configuration_is_refused(configs, tmp_path):
    run_batch(configs, specs(("fixed_equal",)), tmp_path, progress=lambda _: None)
    changed = specs(("fixed_equal",), (*SHORT, ("model", "beta", 0.3)))
    with pytest.raises(StaleResultsError):
        run_batch(configs, changed, tmp_path, progress=lambda _: None)


def test_failed_run_is_recorded_and_retried(configs, tmp_path):
    broken = [RunSpec("ns_dominant", "no_such_controller", 1, overrides=SHORT)]
    messages = []
    for _ in range(2):
        records = run_batch(configs, broken, tmp_path, progress=messages.append)
        assert records[0]["status"] == "failed" and "no_such_controller" in records[0]["error"]
    assert sum("0 already done, 1 to run" in m for m in messages) == 2
    assert (tmp_path / broken[0].run_id / "error.txt").is_file()


def test_variants_including_actuated(configs, tmp_path):
    runs = [
        RunSpec("ns_dominant", "actuated", 2, overrides=SHORT),
        RunSpec("ns_dominant", "queue_proportional", 2, variant="qp_own",
                overrides=(*SHORT, ("estimation", "queue_sampling", "own_green"))),
    ]
    records = run_batch(configs, runs, tmp_path, progress=lambda _: None)
    assert [r["status"] for r in records] == ["done", "done"], records
    assert [r["controller"] for r in records] == ["actuated", "qp_own"]
    actuated = records[0]
    assert actuated["cycles"] > 0 and actuated["infeasible_applied"] == 0
    assert actuated["signal_errors"] == 0 and actuated["solver_calls"] == 0
    assert (tmp_path / runs[0].run_id / "greens.csv").is_file()
