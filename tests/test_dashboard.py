"""The dashboard builder on a small made-up results folder."""

import importlib.util
import json
import re
from pathlib import Path

import pytest
import yaml

pd = pytest.importorskip("pandas")

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dashboard_build", ROOT / "dashboard" / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

CONTROLLERS = ("actuated", "adaptive")


def write_experiment(folder: Path, label: str = "Adaptive") -> Path:
    folder.mkdir(parents=True)
    config = {"signal": {"green_lost_s": 1}, "simulation": {"warmup_s": 600.0}}
    (folder / "config.yaml").write_text(yaml.safe_dump({
        "experiment": {
            "experiment_id": folder.name,
            "variants": {"adaptive": {"label": label}, "actuated": {"label": "Actuated"}},
            "evaluation": {"seeds": [7], "proposed": "adaptive", "baselines": ["actuated"],
                           "primary_metric": "avg_total_wait_s",
                           "metrics": ["avg_total_wait_s"]},
        },
        "resolved": {name: {"low": config} for name in CONTROLLERS},
    }), encoding="utf-8")
    keys = [{"scenario": "low", "controller": c} for c in CONTROLLERS]
    pd.DataFrame([{**k, "metric": "avg_total_wait_s", "n": 1, "mean": 5.0,
                   "ci_low": 4.0, "ci_high": 6.0} for k in keys]
                 ).to_csv(folder / "means.csv", index=False)
    pd.DataFrame([{"scenario": "low", "baseline": "actuated", "metric": "avg_total_wait_s",
                   "mean_difference": -1.0, "ci_low": -2.0, "ci_high": 0.0,
                   "p_holm": float("nan"), "verdict": "no clear difference", "n_pairs": 1}]
                 ).to_csv(folder / "summary.csv", index=False)
    pd.DataFrame([{**k, **dict.fromkeys(
        ("runs", "done", "invalid", "failed", "collisions", "teleports", "fallbacks",
         "infeasible_applied"), 0)} for k in keys]).to_csv(folder / "counts.csv", index=False)
    row = {"scenario": "low", "controller": "adaptive", "seed": 7, "green_ns": 40,
           "green_ew": 38, "queue_ns": 3.0, "queue_ew": 2.0}
    pd.DataFrame([
        {**row, "start_s": 0.0, "valid": False, "source": "fallback"},
        {**row, "start_s": 90.0, "valid": True, "source": "adaptive"},
    ]).to_csv(folder / "cycles.csv", index=False)
    pd.DataFrame([{"run_id": f"low__{c}__seed7", **k, "seed": 7}
                  for c, k in zip(CONTROLLERS, keys)]).to_csv(folder / "runs.csv", index=False)
    greens = folder / "evaluation" / "low__actuated__seed7"
    greens.mkdir(parents=True)
    pd.DataFrame({"start_s": [0.0, 26.0, 60.0], "phase": ["NS", "EW", "NS"],
                  "displayed_s": [21.0, 29.0, 31.0]}).to_csv(greens / "greens.csv", index=False)
    return folder


def embedded(page: str) -> list:
    match = re.search(r"^const DATA = (.*);$", page, re.MULTILINE)
    return json.loads(match.group(1))


def test_experiment_data(tmp_path):
    data = build.load_experiment(write_experiment(tmp_path / "x1"))
    assert data["controllers"] == ["actuated", "adaptive"] and data["proposed"] == "adaptive"
    assert data["warmup_s"] == 600.0 and data["verify"] is None
    assert data["paired"][0]["p_holm"] is None  # missing stays missing, not NaN
    planned = data["runs"]["low|adaptive|7"]
    assert planned["rows"] == [[0.0, None, None, 40, 38, 1], [90.0, 3.0, 2.0, 40, 38, 0]]
    # Effective greens; the unfinished last cycle has no EW green.
    assert data["runs"]["low|actuated|7"]["rows"] == [
        [0.0, None, None, 20.0, 28.0, 0], [60.0, None, None, 30.0, None, 0]]


def test_build_writes_one_self_contained_page(tmp_path, capsys):
    write_experiment(tmp_path / "x1")
    write_experiment(tmp_path / "x2", label="</script><b>name")
    (tmp_path / "unfinished").mkdir()
    assert build.main(["--results", str(tmp_path)]) == 0
    page = (tmp_path / "dashboard.html").read_text(encoding="utf-8")
    assert [d["id"] for d in embedded(page)] == ["x1", "x2"]
    assert embedded(page)[1]["labels"]["adaptive"] == "</script><b>name"
    assert page.count("</script>") == 1  # data cannot close the script
    assert "http://" not in page.replace("http://www.w3.org/2000/svg", "")
    assert "https://" not in page and "innerHTML" not in page


def test_missing_results_are_reported(tmp_path, capsys):
    assert build.main(["--results", str(tmp_path)]) == 1
    assert "no finished experiment" in capsys.readouterr().err
    (tmp_path / "half").mkdir()
    assert build.main(["half", "--results", str(tmp_path)]) == 1
    assert "means.csv" in capsys.readouterr().err
