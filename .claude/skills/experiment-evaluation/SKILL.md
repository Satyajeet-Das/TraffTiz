---
name: experiment-evaluation
description: Use when computing OptiTraffic metrics, running experiment batches, comparing controllers or solvers, producing result figures or writing results into the report.
---

# Experiment evaluation

Metrics and protocol: `docs/TECHNICAL_DESIGN.md` §8; solver tracks §6.5.

## Before a batch

- Tests pass; config is frozen and saved with software versions.
- Tuning used seeds 1–5 only; evaluation uses 101–120.
- Every controller gets the same route file for a given scenario and seed.
- Smoke-run one seed per scenario and controller first, and state the expected total run time.

## Analysis

- Pair by `(scenario, seed)`. Report mean difference, 95% CI, Wilcoxon signed-rank, Holm correction.
- Report each scenario separately before any aggregate.
- Show insertion delay, unfinished vehicles and worst-approach delay beside average waiting time.
- Count failed, invalid and fallback runs and cycles.
- Report J_ns and penalty-form results separately from the primary objective.
- Load the `dataviz` skill before plotting.

## Integrity

- Never edit result files, drop seeds after seeing results, or retune on evaluation seeds. If the config changes, rerun the whole matrix.
- A lower objective value is not evidence of better traffic; use SUMO metrics.
- State losses and ties plainly. All claims apply to this simulation only.
- Every number in the report traces to a file in `results/<experiment_id>/`.
