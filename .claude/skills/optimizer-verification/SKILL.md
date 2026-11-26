---
name: optimizer-verification
description: Use when writing or changing OptiTraffic's queue model, objective, gradient, Hessian, subgradient, projection, line search or any optimization solver, or when a solver gives unexpected results.
---

# Optimizer verification

Formulas and variants: `docs/TECHNICAL_DESIGN.md` §5 and §6. Read the relevant part first.

## Order of work

1. Write the failing test.
2. Implement.
3. Run the checks below that apply.
4. Record the solver's variant, assumptions and parameters in its docstring.

## Checks

| Changed | Required checks |
|---|---|
| Queue or objective | Reference cases A–C (§5.5); non-negative queues; unit consistency |
| Derivatives | Central differences (h≈1e-5, relative error < 1e-6) away from kinks; at kinks check J's gradient is continuous and J_ns satisfies `f(y) ≥ f(x) + v·(y−x)` |
| Projection | Idempotent; output feasible; sum equals G; inside and outside bounds; ℓ = u |
| Solver | Matches oracle from interior, bound and infeasible starts; optimum on each bound; one queue zero; both zero; zero arrival rate; max-iteration and numerical-error statuses |
| Stochastic | Same seed gives same result; mean over seeds approaches the sample-average reference |

## Rules

- Convergence means `|x − P(x − ∇f(x))| ≤ tol`, never `|∇f| ≈ 0` alone.
- Only projected gradient and similar monotone methods are tested for monotone decrease.
- The objective is C¹; the nonsmooth study uses J_ns only.
- No `scipy.optimize` outside tests. No `traci` import in `modelling/` or `optimization/`.
- Never loosen a tolerance to make a test pass without explaining why in the test.

## Debugging non-convergence

Check in order: gradient by finite differences; sign of `∂J/∂g₂` in the reduced derivative; step size against `2/L_φ`; line search acting on the projected point; oscillation across `aᵢ = 0`.
