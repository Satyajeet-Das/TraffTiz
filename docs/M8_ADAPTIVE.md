# M8 Results: Adaptive Control

**Date:** 26 November 2026  
**Environment:** SUMO 1.28.0, Python 3.12.1, step 1 s

## What exists

- [AdaptiveController](../src/optitraffic/control/adaptive.py): once per cycle it builds the one-variable problem from the measured queues and arrival rates, solves it with the configured solver from an equal split, and rounds to whole seconds (Technical Design §5.6).
- The same validator, fallback and signal controller as the baselines. A solver result is now rejected if it is infeasible, even when reported as converged.
- Settings in `configs/default.yaml`: decision budget 0.1 s, of which the solver may use 80 % (`solver_budget_fraction`), and `accept_unconverged`.
- The cycle log records the solver, status, iterations, continuous solution, objective, residual and run time. The resolved configuration is saved with each run.

```powershell
python -m optitraffic.run --scenario changing --controller adaptive --seed 1 [--solver newton] [--gui]
```

All solvers minimise J. SGD minimises the expected value of J with random arrivals (§6.3), so it may choose a different plan. J_ns is used only in the solver study.

## Full runs

`python scripts/check_adaptive.py`, seed 1 (a tuning seed). Decision times depend on the machine.

All six scenarios with projected gradient: every run valid (47 cycles, no collisions or teleports), all 46 solver calls converged, and one fallback each, at t = 0 s before an arrival rate can be estimated. Slowest decision 6 ms.

All eight solvers on the `changing` scenario:

| Solver | Status over 46 decisions | Median decision (ms) | Slowest (ms) |
|---|---|---|---|
| Gradient descent | converged | 1.0 | 11 |
| Projected gradient | converged | 3.4 | 4.5 |
| Momentum | converged | 1.2 | 64 |
| SGD | **time budget** | 82 | 83 |
| Newton | converged | 1.6 | 14 |
| BFGS | converged | 1.3 | 2.0 |
| Conjugate gradient | converged | 1.1 | 3.3 |
| Subgradient | converged | 11 | 12 |

Each run had only the t = 0 fallback. These runs check safety and timing, not traffic performance.

## Safety checks

SUMO tests compare the observed signal states with the applied plans, for every scenario, every solver and a run with injected faults:

| Injected fault | Outcome |
|---|---|
| Solver raises an error | equal split, reason logged |
| Solver exceeds the time budget | equal split, reason logged |
| Numerical error | equal split, reason logged |
| Infeasible result | equal split, reason logged |
| Invalid traffic state | equal split, reason logged |

## Found and fixed

On the `low` scenario one decision ran out of time. When both queues can be cleared, only the small red-time term remains and the objective is very flat; projected gradient then zig-zagged with steps of almost 2/L. Its Armijo constant is now 0.25 instead of 1e-4, and that state needs 7 iterations instead of 569 ([solver notes](SOLVERS.md)). The plan chosen had been correct.

## Limitations and open points for M9

- **SGD is not reproducible online.** It always stops on wall-clock time, so the number of iterations depends on the machine. Before M9, either lower its iteration limit until the limit binds first, or study it only offline.
- Momentum's slowest decision (64 ms) is close to the solver's 80 ms share.
- The time budget is checked between solver iterations and after the decision; a single step that never returned would not be interrupted.
- Parameters (β, weights, window, solver settings) have not been tuned.
