# OptiTraffic

Numerical optimization for adaptive traffic signal timing, studied in simulation.

> **Status:** the system, both experiments and the [final report](docs/REPORT.md) are complete. The mathematics has been [checked numerically](docs/M1_VERIFICATION.md); [supervisor approval](docs/M1_SUPERVISOR_REVIEW.md) is pending.

Try after setup: `python examples/reference_cases.py` and `python examples/compare_solvers.py`

Watch the intersection with a fixed-time signal: `python scripts/run_scenarios.py --scenario medium --seed 1 --gui`

Watch the optimization-based controller: `python -m optitraffic.run --scenario changing --controller adaptive --gui` (add `--solver newton` to choose the algorithm). The baselines are `fixed_equal`, `fixed_calibrated`, `queue_proportional` and `actuated`.

## Goal

Decide how long each traffic light should stay green using numerical optimization, then test whether this improves traffic flow compared with fixed-time and queue-proportional signals.

## How it works

Once per signal cycle, at a single four-way intersection simulated in SUMO:

1. **Observe** queues and arrivals through TraCI.
2. **Predict** the queues left after the next cycle.
3. **Optimize** the North–South and East–West green times.
4. **Validate** the plan, falling back to a safe fixed plan if it fails.
5. **Apply** it at the next cycle boundary.
6. **Measure** waiting time, queue length, throughput and other metrics.

## The optimization problem

$$\min_{g_1,g_2}\; \sum_{i=1}^{2} w_iQ_i^2 + \beta\sum_{i=1}^{2}\lambda_i(C-g_i)^2$$

$$\text{subject to}\quad g_1+g_2=C-L, \qquad g_{min}\le g_i\le g_{max}$$

where $Q_i=\max\left(0,\; q_i+\lambda_iC-\dfrac{s_ig_i}{3600}\right)$ is the predicted queue, $g_i$ the green time, $q_i$ the current queue, $\lambda_i$ the arrival rate, $s_i$ the saturation flow, $C$ the cycle length and $L$ the lost time.

## Algorithms

Gradient descent, projected gradient descent, momentum, stochastic gradient descent, Newton's method, BFGS, conjugate gradient and the subgradient method (on a linear-queue variant of the objective). See the [solver notes](docs/SOLVERS.md).

## Technology

Python 3.12, SUMO with TraCI, NumPy, Pandas, Matplotlib, PyYAML and pytest. SciPy is used only for statistics and test cross-checks.

## Documentation

| Document | Contents |
|---|---|
| [**Final report**](docs/REPORT.md) | Formulation, algorithms, experiments, results, limitations |
| [Product requirements](docs/PRD.md) | What the project must do |
| [Technical design](docs/TECHNICAL_DESIGN.md) | Architecture, solver variants, signal safety, experiments |
| [Mathematics](docs/MATHEMATICS.md) | Derivations, convexity, KKT conditions and worked examples |
| [Work plan](docs/WORK_PLAN.md) | Milestones, tasks and acceptance checklist |
| [First results](docs/M9_RESULTS.md), [second results](docs/M9B_RESULTS.md) | All tables, including the algorithm comparison |
| [Demonstration guide](docs/DEMO.md) | A five-minute walk-through |
| [Presentation guide](docs/PRESENTATION.md) | What to explain, how, and likely questions |

## Roadmap

| Milestone | Description |
|---|---|
| M1 | Validate the mathematical formulation |
| M2 | Set up Python and SUMO |
| M3 | Build the intersection |
| M4 | Collect traffic state |
| M5 | Implement the queue model and objective |
| M6 | Implement and test the algorithms |
| M7 | Baseline controllers and signal control |
| M8 | Integrate adaptive control |
| M9 | Run experiments |
| M10 | Report and demonstration |

Progress is tracked in the [work plan](docs/WORK_PLAN.md).

## Setup

Requires Python 3.12. The commands are for Windows PowerShell; SUMO is installed into the virtual environment.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,sim,eval]"
```

## Check the installation

```powershell
pytest                            # unit tests
pytest -m sumo                    # tests that start SUMO
python scripts/check_sumo.py      # start and stop SUMO through TraCI
python verification/m1_checks.py  # check the mathematics
```

## Main result

On unseen traffic, after correcting when queues are measured, the optimization-based controller waited less than queue-proportional control in all 6 scenarios, was not clearly different from a fixed signal tuned to the true demand in 5, and was far better than it when demand changed. SUMO's actuated signal was better in all 6. The [first version](docs/M9_RESULTS.md) had lost to the tuned fixed signal in 4 scenarios. See the [report](docs/REPORT.md).

## Reproduce the results

After [setup](#setup), reproduce one headline result (40 runs, a few minutes): in high demand the measurement correction lowers mean waiting from 35.6 s to 24.6 s.

```powershell
python scripts/reproduce_headline.py
```

The full second experiment (about 3 hours with six parallel runs):

```powershell
python -m optitraffic.experiments --stage all
```

It writes to `results/m9b/`. Finished runs are skipped, and results made with different code or settings are refused rather than mixed. The tuning stage rewrites the `configs/frozen_m9b_*.yaml` files.

The first experiment, including the algorithm comparison, was produced at commit `c2f0f1f`. Its plan also runs on the current code with `--config configs/experiments.yaml` (about 90 minutes).

A controller decision has 0.1 s of wall-clock time. On a busy computer a decision can overrun, which changes that run; close other programs for exact reproduction.

## Dashboard

```powershell
python dashboard/build.py --open   # writes results/dashboard.html
```

One self-contained page built from the result tables: comparisons per scenario, paired differences, the queues and green times of any run, and run accounting.

## Demonstration

```powershell
python scripts/demo.py             # two controllers on the same traffic in sumo-gui
```

See the [demonstration guide](docs/DEMO.md).

## Scope and limitations

This is an academic, simulation-based study. It does not control real traffic signals, covers one intersection with through movements only, and uses a simplified queue and delay model. Results from the simulation do not show real-world improvement.
