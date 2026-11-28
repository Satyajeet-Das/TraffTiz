# Demonstration Guide

For what to say, see the [presentation guide](PRESENTATION.md).

About five minutes. Complete the [setup](../README.md#setup) first.

## Before presenting

```powershell
.\.venv\Scripts\Activate.ps1
python dashboard/build.py            # needs finished experiment results
python scripts/demo.py --headless    # quick check that the simulation runs
```

## 1. The problem (1 minute)

Show the objective in the [README](../README.md#the-optimization-problem): two green times that share a fixed budget, chosen once per signal cycle.

## 2. The mathematics (1 minute)

```powershell
python examples/reference_cases.py   # worked examples, including an optimum on a bound
python examples/compare_solvers.py   # all algorithms on the same problems
```

## 3. The simulation (2 minutes)

```powershell
python scripts/demo.py --scenario changing --controllers fixed_equal adaptive_own_green
```

Two `sumo-gui` windows open one after the other with identical traffic. In `sumo-gui`, raise the delay value to slow the vehicles down. Demand moves from North–South to East–West halfway through the measured period: watch the fixed signal build a queue while the adaptive one moves green time across.

Other controllers: `fixed_calibrated`, `queue_proportional`, `actuated`, `adaptive` (the original version). Close a window to move to the next run.

## 4. The results (1 minute)

```powershell
python dashboard/build.py --open
```

- **All scenarios** gives the comparison in one table. Point out where the proposed controller loses as well as where it wins.
- **Inside one run** shows the queues measured and the green times chosen, cycle by cycle.
- **Run accounting** shows that no run was dropped.
- Switch **Experiment** between `m9` and `m9b` to show the controller before and after the queue-measurement correction.

## If something fails

| Problem | Fix |
|---|---|
| `sumo-gui` does not open | add `--headless` and show the dashboard instead |
| No experiment results | show the tables and figures in [M9B_RESULTS.md](M9B_RESULTS.md) |
| Import errors | activate the virtual environment |

A single demonstration run is one random traffic sample. Quote numbers from the experiments, not from the demo.
