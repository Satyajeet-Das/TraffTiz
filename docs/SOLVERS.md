# Optimization Solvers

All eight algorithms of PRD FR-06 are implemented by hand in [solvers/](../src/optitraffic/optimization/solvers/). Each class docstring gives its full description.

```python
from optitraffic.optimization.solvers import Newton
result = Newton().solve(problem, x0)     # returns a SolverResult
```

## Variants

| Solver | Update | Needs | Default parameters | Main limitation |
|---|---|---|---|---|
| Gradient descent | `P(x − α∇f)`, fixed α | Lipschitz gradient | α = 1/L | slow when ill-conditioned |
| Projected gradient | `P(x − t∇f)`, Armijo on the projection arc | gradient | first t = 1, then twice the last | slow when ill-conditioned |
| Momentum | heavy ball, velocity = step taken | gradient | α = 1/L, momentum 0.9, restart on a 10% rise | not monotone; no general guarantee here |
| SGD | `P(x − αₖ ĝ)`, tail average | sampled gradient | α₀ = 1/L, decay 0.75, batch 16, seed 0 | noisy; always runs to the iteration limit |
| Newton | damped, projected, free variables only | Hessian | gradient fallback if not positive definite | Hessian jumps at queue kinks |
| BFGS | inverse update on free variables | gradient | exact line search; Armijo optional | stores an n×n matrix |
| Conjugate gradient | nonlinear Polak–Ribière+ | gradient | exact line search, restart every n | restarts whenever a bound is hit |
| Subgradient | `P(x − α₀/√(k+1) v)`, best iterate | subgradient | α₀ = 10, patience 500 | slow; no reliable optimality test |

Shared settings: `tolerance` 1e-6, `max_iterations` 500, optional `time_budget_s`. The smooth solvers refuse a nonsmooth problem.

**Stopping.** `converged` means the projected residual `|x − P(x − ∇f)|` is within tolerance. Other statuses are `max_iter`, `time_budget`, `stalled` and `numerical_error`.

**Line search near the optimum.** When the predicted decrease is too small to measure in floating point, the decrease is estimated from the gradients at both ends of the step. Without this, projected gradient oscillated near the optimum without reaching the tolerance.

## Measured behaviour

Output of `python examples/compare_solvers.py` on 26 November 2026 (Python 3.12.1, NumPy 2.2.6). These are single problem instances, not the M9 experiment.

### One-variable problem, start g = 40

| Problem | Solver | Iterations | Error in g (s) |
|---|---|---|---|
| Case A | all six smooth solvers | 1 | 0 |
| Case B | gradient descent, momentum, Newton, BFGS, CG | 1 | 4.6e-11 |
| Case B | projected gradient | 6 | 6.6e-7 |
| Case C (`J_ns`) | subgradient | 500 (limit) | 2.9e-5 |
| Case B, random arrivals | SGD, seeds 0 and 1 | 500 (limit) | 0.058 and 0.0078 |

With one variable and a step of 1/L, most methods solve case B in a single step. **This problem cannot rank them** (decision D2).

### Two-variable penalty form, case B, iterations from (40, 40)

| Solver | ρ = 1 | ρ = 10 | ρ = 100 |
|---|---|---|---|
| Gradient descent | 70 | 619 | 6113 |
| Projected gradient | 33 | 285 | 2789 |
| Momentum | 268 | 293 | 359 |
| Newton | 1 | 1 | 1 |
| BFGS | 2 | 2 | 2 |
| Conjugate gradient | 2 | 2 | 2 |

- Gradient methods slow roughly in proportion to ρ.
- Momentum is worse at ρ = 1 and much better at ρ = 100 with the same untuned setting.
- Newton, BFGS and CG do not separate meaningfully in two variables.

### Rosenbrock function from (−1.2, 1)

| Solver | Iterations | Error |
|---|---|---|
| Projected gradient | 15110 | 1.7e-6 |
| Conjugate gradient | 38 | 8.2e-11 |
| BFGS | 22 | 3.2e-10 |
| Newton | 21 | 1.4e-10 |

Gradient descent, momentum, SGD and subgradient were not run on Rosenbrock.

## Run time

In this run the smooth solvers took under 3 ms on the one-variable problem. Subgradient took about 100 ms and SGD about 125–170 ms for 500 iterations, at or above the 100 ms online budget. SGD's time includes computing the exact expected value at every iteration for reporting. This matters only if one of them is chosen for online control; the default is projected gradient.

## How they are tested

Against the oracle on the reference cases, bound and empty-queue cases and random problems; against known optima for random quadratics up to 10 variables (including with bounds) and the penalty form. Newton and BFGS are also tested on 5-variable Rosenbrock. See [test_solvers.py](../tests/test_solvers.py).
