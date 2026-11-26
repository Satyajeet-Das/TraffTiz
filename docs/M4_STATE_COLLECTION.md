# M4 Results: Traffic State Collection

**Date:** 26 November 2026  
**Environment:** SUMO 1.28.0, Python 3.12.1, step 1 s

## What exists

- [StateCollector](../src/optitraffic/integration/state_collector.py): checks the direction mapping against the network at startup, records arrivals every step, and returns a `TrafficState` at each decision instant.
- [DemandEstimator](../src/optitraffic/modelling/demand.py): sliding-window rate `N / Δt`, using elapsed time until the window is full, not ready during the first cycle.
- One value per phase from the critical approach (decision D3). All four approaches are also kept in the state.
- Bad, missing or non-finite readings, observation gaps and an unready estimator set `valid = False` with a reason. A lost TraCI connection is not caught.

## Accuracy

`python scripts/check_estimates.py`: error in veh/s at every cycle boundary, all approaches, seeds 1–3, 4200 s runs, 180 s window, fixed equal split.

- **vs demand:** against the vehicles actually scheduled in the same window.
- **vs rate:** against the scenario's underlying rate, so it includes Poisson sampling noise.

| Scenario | Waiting vehicles | vs demand: mean | vs demand: max | vs rate: mean | vs rate: rms |
|---|---|---|---|---|---|
| low | counted | 0.0000 | 0.0000 | 0.0001 | 0.0163 |
| low | ignored | 0.0000 | 0.0056 | 0.0001 | 0.0163 |
| medium | counted | 0.0000 | 0.0000 | −0.0003 | 0.0257 |
| medium | ignored | 0.0000 | 0.0111 | −0.0003 | 0.0257 |
| high | counted | 0.0000 | 0.0000 | −0.0011 | 0.0335 |
| high | ignored | 0.0000 | 0.0556 | −0.0012 | 0.0327 |
| ns_dominant | counted | 0.0000 | 0.0000 | −0.0014 | 0.0314 |
| ns_dominant | ignored | −0.0229 | 0.1389 | −0.0243 | 0.0419 |
| ew_dominant | counted | 0.0000 | 0.0000 | −0.0017 | 0.0324 |
| ew_dominant | ignored | −0.0257 | 0.1722 | −0.0273 | 0.0424 |
| changing | counted | 0.0000 | 0.0000 | −0.0010 | 0.0326 |
| changing | ignored | −0.0089 | 0.1778 | −0.0110 | 0.0550 |

- With waiting vehicles counted, every vehicle is counted once in the window where it appears.
- The remaining error against the underlying rate is sampling noise. For a Poisson process its standard deviation is `√(λ/Δt)`, which is 0.026 for λ = 0.12, matching the medium scenario.
- Ignoring waiting vehicles underestimates demand badly when roads fill: single windows are off by up to 0.18 veh/s, comparable to the rates themselves.

## Detection delay

A vehicle becomes visible 1–2 s after its scheduled departure (at `⌈depart/step⌉·step + step`): SUMO inserts it in the next step and reports it when that step ends. A check of 3579 vehicles across three scenarios found none missed and no other delay. The accuracy comparison accounts for it.

## Decision D7: counting vehicles outside the road

`estimation.include_pending` is **true** by default. A real road sensor could not see vehicles that have not entered the road, so this relies on the study's assumption of perfect detection. All controllers receive the same information. Setting it to false gives the sensor-like behaviour in the table above.

## Open for M7 and M8

The **queue** is still the number of halted vehicles on the road, which stops growing at roughly 33 when the road is full. The number waiting to enter is reported separately. Whether controllers add it to the queue needs deciding before M8.
