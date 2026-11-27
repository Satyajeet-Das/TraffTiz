# Work Plan — OptiTraffic

**Based on:** [PRD.md](PRD.md) §13 and [TECHNICAL_DESIGN.md](TECHNICAL_DESIGN.md)

Effort is in focused person-days and is an estimate. No team size or deadline is defined yet, so there are no calendar dates.

---

## 1. Overview

| ID | Milestone | Effort | Depends on | Skill |
|---|---|---|---|---|
| M1 | Validate idea and formulation | 2 | — | optimizer-verification |
| M2 | Environment setup | 1 | — | sumo-simulation |
| M3 | Four-way intersection | 3 | M2 | sumo-simulation |
| M4 | State collection | 3 | M3 | sumo-simulation |
| M5 | Queue model and objective | 2 | M1, M2 | optimizer-verification |
| M6 | Optimization algorithms | 8 | M5 | optimizer-verification |
| M7 | Baseline controllers and signal control | 4 | M4 | sumo-simulation |
| M8 | Adaptive integration | 3 | M6, M7 | sumo-simulation |
| M9 | Experiments and analysis | 5 | M8 | experiment-evaluation |
| M10 | Report and demonstration | 5 | M9 | experiment-evaluation |
| | **Total** | **36** | | |

```text
M1 ──────────┐
M2 ──┬───────┴─> M5 ──> M6 ───────┐
     └─> M3 ──> M4 ──> M7 ────────┴─> M8 ──> M9 ──> M10
```

Two parallel tracks after M2: **maths** (M5, M6) and **simulation** (M3, M4, M7). Critical path (estimate): M1 → M5 → M6 → M8 → M9 → M10 = 25 days.

M7 includes the signal state machine, because the baselines cannot run without it.

---

## 2. Milestones

Each milestone is done when its exit criteria pass and tests are green.

### M1 — Validate formulation
- [x] Write D1 and D2 into the PRD (v1.1)
- [ ] Supervisor confirms D1 and D2; review D3–D6 (Technical Design §2) — [review sheet](M1_SUPERVISOR_REVIEW.md) ready to send
- [x] Verify gradient, subgradient, Hessian and projection — [report](M1_VERIFICATION.md)
- [x] Confirm reference cases A–C (§5.5)
- [ ] Agree solver comparison tracks T1–T3 (§6.5) — included in the review sheet

**Exit:** written approval or changes recorded; documents updated.

### M2 — Environment
- [x] `git init`, `.gitignore` (venv, results, generated SUMO files)
- [x] Virtual environment (Python 3.12), `pyproject.toml` with pinned versions
- [x] Install SUMO 1.28.0 (pip package in the venv; no `SUMO_HOME` setting needed)
- [x] Package skeleton, config loader with validation, pytest with `sumo` marker

**Exit:** `pytest` runs; a script starts SUMO headless and closes it through TraCI. ✅ Met.

### M3 — Intersection (FR-01)
- [ ] Network sources and `netconvert` build
- [ ] Signal program with yellow and all-red
- [ ] Seeded route generator for all six scenarios
- [ ] Measure saturation flow (D6) and re-check scenario demand levels

**Exit:** vehicles enter and leave; no collisions or teleports in all scenarios; same seed gives an identical route file.

### M4 — State collection (FR-02, FR-03)
- [ ] TraCI client and direction mapping check
- [ ] State collector with validity handling
- [ ] Sliding-window demand estimator with warm-up behaviour

**Exit:** estimates match generated demand within sampling error; invalid-input tests pass.

### M5 — Model and objective (FR-04, FR-05)
- [ ] Queue prediction
- [ ] J, J_ns, gradient, Hessian, subgradient
- [ ] Reduced 1-D problem, projection, feasibility check
- [ ] Oracle (grid and bisection)
- [ ] Hand-case, finite-difference and boundary tests

**Exit:** cases A–C reproduced; derivative checks pass; no SUMO import in these modules.

### M6 — Solvers (FR-06)
Build in this order; each ships with tests before the next starts.
- [ ] Base interface, `SolverResult`, line searches
- [ ] Projected GD (needed first by M8)
- [ ] Gradient descent
- [ ] Momentum
- [ ] Newton
- [ ] BFGS
- [ ] Conjugate gradient (PR+)
- [ ] Subgradient on J_ns
- [ ] SGD on the sampled objective
- [ ] T2 penalty and T3 test problems
- [ ] Short note per solver: assumptions, variant, parameters

**Exit:** every solver meets its oracle or known optimum within its stated tolerance, or the exclusion is justified in writing.

### M7 — Baselines and signal control (FR-07, FR-08, FR-09)
- [ ] Signal state machine
- [ ] Validator and fallback
- [ ] Fixed equal, fixed calibrated, queue-proportional controllers
- [ ] `run.py` for a single run

**Exit:** observed signal log shows correct sequence and durations; conflicting green never occurs; injected invalid plans trigger fallback.

### M8 — Adaptive control
- [ ] Adaptive controller using a configurable solver
- [ ] Integer rounding and time budget
- [ ] Per-cycle logging
- [ ] Failure injection: solver error, timeout, invalid state

**Exit:** a full run completes for every scenario; plans change only at cycle boundaries; all fallbacks have logged reasons.

### M9 — Experiments (FR-10)
- [ ] Metrics from tripinfo and per-step data
- [ ] Batch runner, resumable
- [ ] Tune parameters on seeds 1–5, then freeze config
- [ ] Run the evaluation matrix on seeds 101–120
- [ ] Solver comparison T1–T3
- [ ] β and observation-window sensitivity sweeps
- [ ] Optional: actuated baseline
- [ ] Paired statistics and figures

**Exit:** every run accounted for (done, failed or invalid); rerunning a sample reproduces its metrics.

### M10 — Report and demonstration
- [ ] Report: formulation, algorithms, experimental design, results, limitations
- [ ] README with reproduction steps
- [ ] Demo script using `sumo-gui`
- [ ] Walk through the PRD §12 checklist below
- [ ] Optional dashboard, only if everything above is complete

**Exit:** a fresh checkout reproduces a headline result by following the README.

---

## 3. Acceptance checklist (PRD §12)

| # | Criterion | Milestone | Evidence |
|---|---|---|---|
| 1 | Intersection runs in SUMO | M3 | integration test |
| 2 | Two phases operate correctly | M7 | signal log test |
| 3 | Data collected through TraCI | M4 | integration test |
| 4 | Queue and arrival estimates | M4, M5 | unit tests |
| 5 | Objective correct | M5 | hand cases |
| 6 | Gradient passes checks | M5 | finite differences |
| 7 | Algorithms tested or exclusions justified | M6 | solver tests and notes |
| 8 | Feasible allocations | M6, M8 | property tests, violation count |
| 9 | Timings applied safely | M8 | signal log, failure injection |
| 10 | Baselines available | M7 | run outputs |
| 11 | Multiple scenarios | M9 | `runs.csv` |
| 12 | Metrics collected and compared | M9 | `summary.csv` |
| 13 | Reproducible | M9 | rerun check |
| 14 | Report with assumptions and limits | M10 | report |

---

## 4. If time runs short

Cut in this order: dashboard → actuated baseline → sensitivity sweeps → T3 beyond quadratics.

Minimum viable result: M1–M5, projected GD plus Newton, M7, M8 and a reduced experiment (fewer seeds, stated in the report). Dropping any other required algorithm needs written justification (PRD §12.7).

---

## 5. Risks

| Risk | Early signal | Response |
|---|---|---|
| Solver comparison looks trivial | M6: identical iterations in 1-D | use tracks T2 and T3 (D2) |
| Adaptive does not beat calibrated baseline | M9 on tuning seeds | check estimator window and saturation flow; report honestly |
| Model mismatch with SUMO | M3 discharge measurement | set `sᵢ` from data; check predicted against observed queues |
| Spillback hides arrivals | insertion delay in high demand | longer approaches, report insertion delay |
| SUMO setup problems | M2 | start M5 in parallel; it needs no SUMO |
| Scope growth | new features before M9 | defer to PRD §15 |

---

## 6. Open questions

1. Team size, deadline and required report format?
2. Does the supervisor accept the PRD 1.1 changes: D1 (nonsmooth objective) and D2 (extra comparison formulations)?
3. Is the actuated baseline expected?

## 7. First actions

1. Send the PRD 1.1 changes to the supervisor.
2. Do M2.
3. Start M5 with the three reference cases as the first tests.
