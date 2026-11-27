# OptiTraffic

Numerical optimization for adaptive traffic signal timing, studied in simulation.

> **Status:** project setup (M2) and the queue model, objective functions (M5), all eight optimization algorithms (M6), the simulated intersection (M3), traffic data collection (M4), signal control with three baseline controllers (M7), the optimization-based controller (M8) and the experiments (M9) are complete. The mathematics has been [checked numerically](docs/M1_VERIFICATION.md) and [supervisor approval](docs/M1_SUPERVISOR_REVIEW.md) is pending. The final report (M10) is not written yet.

Try after setup: `python examples/reference_cases.py` and `python examples/compare_solvers.py`

Watch the intersection with a fixed-time signal: `python scripts/run_scenarios.py --scenario medium --seed 1 --gui`

Watch the optimization-based controller: `python -m optitraffic.run --scenario changing --controller adaptive --gui` (add `--solver newton` to choose the algorithm). The baselines are `fixed_equal`, `fixed_calibrated` and `queue_proportional`.

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

## Planned technology

Python 3.12, SUMO with TraCI, NumPy, Pandas, Matplotlib, PyYAML and pytest. SciPy is used only for statistics and test cross-checks.

## Documentation

| Document | Contents |
|---|---|
| [Product requirements](docs/PRD.md) | What the project must do |
| [Technical design](docs/TECHNICAL_DESIGN.md) | Architecture, solver variants, signal safety, experiments |
| [Mathematics](docs/MATHEMATICS.md) | Derivations, convexity, KKT conditions and worked examples |
| [Work plan](docs/WORK_PLAN.md) | Milestones, tasks and acceptance checklist |

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

## Experiments

```powershell
python -m optitraffic.experiments --stage all   # about 90 minutes
```

On unseen traffic the optimization-based controller waited less than the queue-proportional controller in 5 of 6 scenarios, but less than the demand-calibrated fixed signal in only 2 of 6. See the [results](docs/M9_RESULTS.md).

## Scope and limitations

This is an academic, simulation-based study. It does not control real traffic signals, covers one intersection with through movements only, and uses a simplified queue and delay model. Results from the simulation do not show real-world improvement.
