# M3 Results: Intersection

**Date:** 26 November 2026  
**Environment:** SUMO 1.28.0, Python 3.12.1, default Krauss car-following, step 1 s

## What exists

- One signalized junction, four approaches of 300 m nominal length (less inside the junction), one lane each, 50 km/h, through movements only. Sources in [sumo/](../sumo/).
- Signal state strings derived from the network's link order, with yellow and all-red.
- Seeded Poisson demand with explicit departure times for the six [scenarios](../configs/scenarios/).
- A fixed-time runner: `python scripts/run_scenarios.py` (add `--scenario medium --gui` to watch).

## Scenario validation

Equal split (40 s / 40 s), 4200 s per run, seeds 1–3, from `python scripts/run_scenarios.py`. "Waiting" is vehicles that could not enter by the end; "max queue" is the most halted vehicles on one approach.

| Scenario | Scheduled | Waiting | Max queue NS | Max queue EW | Collisions, teleports |
|---|---|---|---|---|---|
| low | 808–864 | 0–1 | 5–8 | 5–8 | 0 |
| medium | 1992–2022 | 0–1 | 13–16 | 13–18 | 0 |
| high | 3320–3354 | 0 | 23–26 | 24–31 | 0 |
| ns_dominant | 3129–3201 | 380–434 | 32–33 | 11–16 | 0 |
| ew_dominant | 3106–3227 | 342–479 | 9–12 | 32–33 | 0 |
| changing | 3150–3195 | 85–192 | 31–33 | 32 | 0 |

All 18 runs were valid. Identical route files for the same seed, and the observed signal sequence and durations over three cycles, are covered by tests.

**These are not controller results.** The equal split is deliberately simple and these runs only validate the intersection.

## Saturation flow (decision D6)

`python scripts/measure_saturation.py`: NS approach flooded with traffic, vehicles crossing the stop line counted per cycle (cycle 150 s, 5 seeds, 60 fully queued cycles per green duration).

| Displayed green (s) | 15 | 25 | 35 | 45 | 55 |
|---|---|---|---|---|---|
| Mean vehicles per cycle | 7.10 | 12.53 | 17.75 | 22.73 | 27.87 |

Fit: `vehicles = 0.5173 · green − 0.510`, residual standard deviation 0.56 vehicles.

- **Saturation flow: 1862 veh/h per lane.** The config now uses 1860. The worked examples in the documents keep 1800.
- Only the N approach was measured; the others have the same geometry and vehicle type.
- Departures are detected once per 1 s step.

## Lost time (decision D4)

The fit gives effective green about **0.99 s shorter** than displayed green. D4 assumes they are equal, so the model overestimates discharge by about half a vehicle per phase per cycle.

**Decided and applied in M7:** the signal shows 1 s more than the effective green (`signal.green_lost_s: 1`), so lost time is 12 s and the green budget 78 s. The equal split is still displayed as 40 s / 40 s, so the runs above are unchanged.

## Demand levels

Flow ratio `Y = Σλᵢ/μᵢ` with μ = 1860/3600: low 0.19, medium 0.46, high 0.77, dominant and changing 0.74. All are below `G/C = 0.87` (G = 78 after the M7 change), so the scenarios are unchanged.

The dominant scenarios exceed the dominant approach's capacity under an equal split (it needs about 50 s of green), which is why queues fill the approach. A better split should avoid this, so they can separate controllers.

## Risk for M4

When a queue fills the approach, new vehicles cannot enter, so counting arrivals on the incoming edge **underestimates demand** exactly when it is highest. M4 must either detect this condition, use longer approaches, or both, and results must report waiting-to-enter vehicles.
