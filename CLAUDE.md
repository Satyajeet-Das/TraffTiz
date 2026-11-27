# CLAUDE.md — OptiTraffic

Simulation-based academic study: numerical optimization of green times at one four-way intersection (SUMO + TraCI + Python).

## Source of truth

1. [docs/PRD.md](docs/PRD.md) — requirements (what)
2. [docs/TECHNICAL_DESIGN.md](docs/TECHNICAL_DESIGN.md) — design (how)
3. [docs/WORK_PLAN.md](docs/WORK_PLAN.md) — order of work and status

If they disagree, say so and ask. Do not silently pick one. Open decisions are listed in Technical Design §2.

## Current status

M1: maths verified (`python verification/m1_checks.py`, see [report](docs/M1_VERIFICATION.md)); supervisor approval pending ([review sheet](docs/M1_SUPERVISOR_REVIEW.md)). M2 complete: package skeleton, config loader, SUMO 1.28.0 check. M5 complete: queue model, objectives, reduced problem, oracle. M6 complete: all eight solvers ([notes](docs/SOLVERS.md)). M3 complete: intersection, seeded demand, saturation flow 1860 veh/h ([results](docs/M3_INTERSECTION.md)). M4 complete: state collection and demand estimation ([results](docs/M4_STATE_COLLECTION.md)). M7 complete: signal controller, validator with fallback, three baselines, `optitraffic.run`. Green times in plans are effective green (signal shows +1 s). M8 complete: adaptive controller with any of the eight solvers ([results](docs/M8_ADAPTIVE.md)). Next: M9 (experiments); first settle SGD's time-budget dependence. Update this section and the work plan checkboxes as milestones land.

## Commands

```powershell
py -3.12 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev,sim]"
pytest                      # unit tests, no SUMO needed
pytest -m sumo              # integration tests, SUMO needed
python scripts/check_sumo.py
python examples/reference_cases.py
python examples/compare_solvers.py
python scripts/run_scenarios.py          # all scenarios, fixed equal split
python scripts/measure_saturation.py     # slow: about 10 minutes
python scripts/check_estimates.py        # slow: several minutes
python scripts/check_adaptive.py         # slow: several minutes
```

```powershell
python -m optitraffic.run --scenario medium --controller adaptive --seed 1 [--solver newton] [--gui]
```

Planned, not yet implemented (experiments in M9):

```powershell
python -m optitraffic.experiments --config configs/experiments.yaml
```

## Architecture rules

- `modelling/` and `optimization/` are pure Python + NumPy. They never import `traci`, `sumolib`, `simulation/`, `integration/` or `control/`.
- Only `integration/` and `control/signal_controller.py` talk to TraCI.
- The optimizer proposes; the validator checks; the signal controller executes. No solver touches signal state.
- Solvers are hand-written. `scipy.optimize` may appear only in tests, as a cross-check.
- All solvers implement the common interface and return `SolverResult`.

## Conventions

- Units: queue = veh, arrival rate = veh/s, saturation flow = veh/h in config and converted once to veh/s, time = s. Put the unit in the name when ambiguous (`saturation_flow_vph`).
- Phase order is always `(NS, EW)`.
- All tunables live in YAML under `configs/`; no magic numbers in code.
- All randomness takes an explicit seed.
- Type hints on public functions; frozen dataclasses for state and results.
- Never use NaN or inf as a "missing" value in control logic; return an explicit status.

## Safety and integrity

- Never apply a plan mid-phase. Never skip yellow or all-red. Invalid plan → fallback, logged and counted.
- Do not edit files in `results/` by hand. Do not tune on evaluation seeds.
- Report unfavourable results as they are. Claims are about the simulation only.

## Project skills

| Skill | Use when |
|---|---|
| `optimizer-verification` | changing the model, objective, derivatives, projection or a solver |
| `sumo-simulation` | changing the network, routes, TraCI code or signal control |
| `experiment-evaluation` | running experiments, computing metrics, writing results |

General skills worth using: `dataviz` (before any plot), `code-review` (end of each milestone).
