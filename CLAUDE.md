# CLAUDE.md — OptiTraffic

Simulation-based academic study: numerical optimization of green times at one four-way intersection (SUMO + TraCI + Python).

## Source of truth

1. [docs/PRD.md](docs/PRD.md) — requirements (what)
2. [docs/TECHNICAL_DESIGN.md](docs/TECHNICAL_DESIGN.md) — design (how)
3. [docs/WORK_PLAN.md](docs/WORK_PLAN.md) — order of work and status

If they disagree, say so and ask. Do not silently pick one. Open decisions are listed in Technical Design §2.

## Current status

M1: maths verified (`python verification/m1_checks.py`, see [report](docs/M1_VERIFICATION.md)); supervisor approval pending ([review sheet](docs/M1_SUPERVISOR_REVIEW.md)). No project code under `src/` yet. Update this section and the work plan checkboxes as milestones land.

## Commands (valid from M2 onwards)

```powershell
py -3.12 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest                      # unit tests, no SUMO needed
pytest -m sumo              # integration tests, SUMO needed
python -m optitraffic.run --config configs/default.yaml --scenario medium --controller adaptive --seed 1
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
