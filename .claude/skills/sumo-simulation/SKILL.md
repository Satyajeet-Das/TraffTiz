---
name: sumo-simulation
description: Use when installing SUMO or changing OptiTraffic's network files, route generation, TraCI state collection, signal state machine, validator, fallback or controllers.
---

# SUMO and TraCI

Design: `docs/TECHNICAL_DESIGN.md` §4 and §7.

## Setup

- Check availability with `sumo --version` and `python -c "import traci, sumolib"`.
- Ask before installing anything. Preferred: pinned `eclipse-sumo`, `traci`, `sumolib` in the project venv.

## Network and demand

- Edit the `.nod/.edg/.con` sources and rebuild with `netconvert`; never hand-edit `net.xml`.
- After a network change, recheck the link order used to build signal state strings.
- Routes come from `(scenario, seed)` with explicit departure times, sorted by time.

## TraCI

- One client wrapper owns start, step and close; close in `finally`.
- Use headless `sumo` for tests and experiments, `sumo-gui` for demos only.
- Count arrivals every step; sample queues at the decision instant.
- Unit tests use a fake client; real-SUMO tests carry `@pytest.mark.sumo`.

## Signal safety (must always hold)

1. Sequence: NS green → yellow → all-red → EW green → yellow → all-red.
2. No state shows green or yellow to both phases.
3. Plans change only after the final all-red.
4. Observed durations equal the plan and the configured clearances.
5. Invalid plan, invalid state, solver failure or timeout → fallback, with a logged reason.

Verify these from the recorded signal state of a real run, not only from controller internals.

## Run validity

Teleporting disabled. A collision, teleport or TraCI disconnect marks the run invalid; report it, do not drop it silently.
