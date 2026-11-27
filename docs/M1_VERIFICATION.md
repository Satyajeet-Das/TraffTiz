# M1 Verification Report

**Date:** 26 November 2026  
**Script:** [m1_checks.py](../verification/m1_checks.py)  
**Environment:** Python 3.12.1, NumPy 2.2.6, random seed 2026  
**Result:** 135 of 135 checks passed on the first run

```powershell
python verification/m1_checks.py
```

## Method

`J` and `J_ns` are written in the script directly from PRD §5–§6. Derived formulas are compared with finite differences, dense grid search or randomized inequality tests on those definitions. Numbers quoted in the documents must match to half a unit of their last printed digit.

## Results

| Area | Checks | What was confirmed | Tolerance |
|---|---|---|---|
| Derivatives | 5 | gradient, Hessian, reduced first and second derivatives, `J_ns` gradient away from kinks (500 random states) | relative error below 1e-6; worst 2.7e-8 |
| Smoothness (D1) | 3 | `J` slopes agree at queue kinks; `J_ns` slopes jump by `w·μ`; second derivative of `J` jumps | slope gap below 1e-5 |
| Subgradient and convexity | 6 | subgradient inequality including kinks, convexity of `J` and `J_ns`, Lipschitz and strong convexity bounds (4000 random states) | violation below 1e-8 |
| Projection | 4 | feasible, idempotent, nearest point in 1-D and 2-D (500 random problems) | grid spacing |
| Reference cases A–C | 19 | every value in Technical Design §5.5 and the related values | quoted precision |
| KKT and β | 14 | multipliers for A and B, shadow price, formula `g*(β)` | quoted precision |
| Worked iterations | 51 | tables and values for gradient descent, projected GD, momentum, Newton, BFGS, subgradient | quoted precision |
| Penalty form (D2) | 26 | solutions, violation, condition numbers, behaviour of Newton, CG, BFGS, gradient descent | quoted precision; solver error below 1e-6 |
| Numerics and stochastic | 5 | rounding loss, error order across a kink, unbiased gradient, `F ≥ J` | see script |
| Multi-cycle extension | 2 | convex; not differentiable everywhere | see script |

## Observations relevant to D1 and D2

**Penalty form, case B, from (40, 40)**

| ρ | condition number | gradient descent iterations | CG, BFGS (exact line search) | Newton |
|---|---|---|---|---|
| 1 | 4.8 | 72 | 2 | 1 |
| 10 | 38.7 | 643 | 2 | 1 |
| 100 | 378 | 6353 | 2 | 1 |

The 2-D form separates gradient descent clearly from the second-order and conjugate methods. It does **not** separate CG from BFGS, and these runs use one quadratic piece without active bounds. Momentum was not run on it.

**`J_ns` behaviour.** When both predicted queues are positive and `w·μ` is equal for both phases, the two queue terms cancel in the reduced derivative. The split then depends only on the β term, not on the queue sizes. This follows from the formula (compare the case C derivative, which contains no queue value). It makes `J_ns` suitable for studying the subgradient method but a weak choice for signal control.

## Corrections

No formula or value needed correction. The note in Technical Design §5.5 that case C was unconfirmed has been updated.

## Not verified

- Convergence rates and complexity costs in Mathematics §9 and §13 are cited theory. Only the subgradient error bound was tested, on five iterates of case C.
- Random testing supports the convexity and inequality claims but does not prove them. The proofs are in Mathematics §6.
- The queue model against real SUMO behaviour, including saturation flow (D6), needs M3.
- Default parameters, demand levels and the choice of queue per phase (D3) are design choices, not mathematical results.
- The solvers were exercised only as far as needed to check the documents. They are not the M6 implementations.
