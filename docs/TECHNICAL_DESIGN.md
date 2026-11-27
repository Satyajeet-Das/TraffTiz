# Technical Design — OptiTraffic

**Version:** 1.0 (draft for review)  
**Based on:** [PRD.md](PRD.md) v1.1  
**Companion:** [WORK_PLAN.md](WORK_PLAN.md)

Values marked *default* are proposed starting points, not PRD requirements. All are configurable.

---

## 1. Summary

A single four-way SUMO intersection with two phases (NS, EW). Once per cycle, at a safe boundary, the system reads queues and arrival rates, solves a small constrained optimization problem for the two green times, validates the plan and executes it through a signal state machine. Controllers are compared on identical traffic using paired random seeds.

---

## 2. PRD clarifications (review in M1 with the supervisor)

D1 and D2 are written into PRD 1.1 and still need supervisor confirmation. D3–D7 are proposals.

| # | Finding | Decision |
|---|---|---|
| D1 | `Q² = max(0, a)²` is **continuously differentiable** (C¹). Only the second derivative jumps. A subgradient method on J is just gradient descent. | **In PRD §6.4.** J stays the control objective. `J_ns = Σ wᵢQᵢ + β Σ λᵢ(C − gᵢ)²` is used for the subgradient study and reported separately. |
| D2 | With two phases and `g₁ + g₂ = G`, the problem is **one-dimensional**. BFGS reduces to the secant method and conjugate gradient has no conjugate directions to build. | **In PRD §6.7.** Solvers are n-dimensional and compared on the reduced 1-D problem, a 2-D penalty form and test functions (§6.5). |
| D3 | "Queue per approach or phase" is ambiguous. Each phase serves two approaches that discharge at the same time. | *Default:* critical approach. `qᵢ`, `λᵢ` come from the approach in the phase with the largest `qᵢ + λᵢC`; `sᵢ` is per approach (all its lanes). |
| D4 | Effective green (optimizer) differs from displayed green (controller). | **Decided after M3** (effective green measured about 1 s shorter, [results](M3_INTERSECTION.md)): displayed = effective + 1 s, `L = 2·(yellow + all_red + 1)`. Bounds apply to effective green. |
| D5 | `J` adds veh² and veh·s terms, so β carries units and its value matters. | Tune β and wᵢ on tuning seeds only; report a sensitivity sweep. |
| D6 | Saturation flow 1800 veh/h may not match SUMO's car-following behaviour. | **Measured in M3: 1862 veh/h; config uses 1860** ([results](M3_INTERSECTION.md)). |
| D7 | A full road hides new arrivals, so road counts underestimate demand. | *Default:* also count vehicles waiting to enter as arrivals (`include_pending`) and add them to the queue (`pending_in_queue`). Relies on perfect detection ([results](M4_STATE_COLLECTION.md)). |

---

## 3. Architecture

### 3.1 Data flow (once per cycle)

```text
SUMO ──TraCI──> StateCollector ──> DemandEstimator ──> TrafficState
                                                          │
                                                          v
SignalController <── Validator/Fallback <── TimingPlan <── Controller (Solver + Model)
      │
      └──TraCI──> SUMO                     Logger / MetricsCollector observe every stage
```

### 3.2 Repository layout

```text
TraffTiz/
├─ CLAUDE.md
├─ pyproject.toml
├─ configs/            default.yaml, experiments.yaml, scenarios/*.yaml
├─ sumo/               nodes, edges, connections, tls sources; built net.xml
├─ src/optitraffic/
│  ├─ config.py        load and validate YAML
│  ├─ types.py         shared dataclasses
│  ├─ simulation/      route generation, SUMO launch
│  ├─ integration/     TraCI client, state collector
│  ├─ modelling/       demand estimator, queue prediction
│  ├─ optimization/
│  │  ├─ objective.py  J, J_ns, gradient, Hessian, subgradient
│  │  ├─ constraints.py projection, feasibility
│  │  ├─ problems.py   reduced 1-D, penalty 2-D, stochastic, test functions
│  │  └─ solvers/      one file per algorithm + base.py, linesearch.py, oracle.py
│  ├─ control/         controllers, validator, fallback, signal_controller
│  ├─ evaluation/      metrics, experiment runner, statistics, plots
│  ├─ run.py           one simulation run
│  └─ experiments.py   batch runs
├─ tests/              mirrors src/; tests/integration marked `sumo`
├─ scripts/            setup checks
├─ verification/       M1 checks of the formulation
└─ results/            generated, git-ignored
```

### 3.3 Dependency rule

`modelling` and `optimization` depend only on `types` and NumPy. This satisfies FR-05 (objective independent of SUMO) and NFR-05, and lets M5–M6 proceed without SUMO.

### 3.4 Core types

```python
@dataclass(frozen=True)
class TrafficState:
    sim_time: float
    queue: tuple[float, float]          # veh, (NS, EW)
    arrival_rate: tuple[float, float]   # veh/s
    vehicle_count: tuple[int, int]
    waiting_time: tuple[float, float]   # s
    pending: tuple[int, int]            # waiting to enter a full road
    signal_state: str
    approaches: tuple[ApproachState, ...]
    valid: bool
    issues: tuple[str, ...]

@dataclass(frozen=True)
class SignalParams:
    cycle: int; lost_time: int; g_min: int; g_max: int
    @property
    def green_budget(self) -> int: return self.cycle - self.lost_time

@dataclass(frozen=True)
class TimingPlan:
    green: tuple[int, int]
    source: str                         # controller/solver name, or "fallback"
    reason: str = ""

@dataclass(frozen=True)
class SolverResult:
    x0: np.ndarray; x: np.ndarray; objective: float
    grad: np.ndarray | None
    residual: float                     # projected-gradient norm
    iterations: int
    converged: bool; status: str        # converged | max_iter | stalled | time_budget | numerical_error
    runtime_s: float
    feasible: bool
    history: tuple[float, ...]          # objective per iteration
```

`SolverResult` covers every item FR-06 requires each algorithm to expose.

---

## 4. Simulation and integration

### 4.1 Network (FR-01)

- One junction, four approaches of *default* 300 m, one through lane each, through movements only, passenger cars only.
- Long approaches reduce spillback to the entry point, which would hide arrivals.
- Source files (`.nod.xml`, `.edg.xml`, `.con.xml`) are kept in `sumo/`; `netconvert` builds `net.xml`.
- *Default* step length 1 s; teleporting disabled (`--time-to-teleport -1`). Any collision or teleport marks the run invalid.

### 4.2 Demand and reproducibility (NFR-04)

Route files are **pre-generated in Python** from `(scenario, seed)` with explicit departure times (Poisson process per approach). Every controller then receives the identical vehicle list, independent of how its signal decisions affect SUMO's internal random stream. The same seed is also passed to SUMO.

*Default* scenarios, arrival rate per approach in veh/s (N=S, E=W). `Y = Σλᵢ/μᵢ` with the measured `μ = 1860/3600`; capacity requires roughly `Y < G/C ≈ 0.87`.

| Scenario | λ_NS | λ_EW | Y |
|---|---|---|---|
| low | 0.05 | 0.05 | 0.19 |
| medium | 0.12 | 0.12 | 0.46 |
| high | 0.20 | 0.20 | 0.77 |
| ns_dominant | 0.28 | 0.10 | 0.74 |
| ew_dominant | 0.10 | 0.28 | 0.74 |
| changing | NS-dominant for the first half of the measured period, EW-dominant for the second | | 0.74 |

Checked against the measured saturation flow in M3. An optional oversaturated case may be added as a stress test.

### 4.3 State collection (FR-02)

| Quantity | Source |
|---|---|
| Queue | `lane.getLastStepHaltingNumber` on incoming lanes, sampled at the decision instant |
| Arrivals | new vehicle IDs seen on each incoming edge or waiting to enter it (D7), accumulated every step |
| Waiting to enter | `simulation.getPendingVehicles` |
| Vehicle count | `lane.getLastStepVehicleNumber` |
| Waiting time | `lane.getWaitingTime` |
| Signal state | `trafficlight.getRedYellowGreenState` |
| Time | `simulation.getTime` |

Direction mapping comes from config and is checked against the network at startup. Negative, non-finite or missing readings set `valid = False` with a reason, and the fallback plan is used.

### 4.4 Demand estimation (FR-03)

Sliding window: `λᵢ = Nᵢ / Δt`, *default* Δt = 180 s (two cycles). Before a full window exists, use the elapsed time if at least one cycle has passed, otherwise report "not ready" and use the fallback plan. Exponential smoothing is an optional later variant.

---

## 5. Mathematical model

The model uses the measured saturation flow (1860 veh/h) and G = 78; the worked examples in §5.5 use 1800 veh/h and G = 80.

*Defaults:* C = 90 s, yellow = 3 s, all-red = 2 s, lost green = 1 s per phase, L = 12 s, G = 78 s, g_min = 10 s, g_max = 70 s, wᵢ = 1, β = 0.1.

### 5.1 Queue prediction (FR-04)

With `μᵢ = sᵢ/3600` (veh/s):  `aᵢ(gᵢ) = qᵢ + λᵢC − μᵢgᵢ`,  `Qᵢ = max(0, aᵢ)`

This is a cycle-level approximation. It ignores when vehicles arrive within the cycle.

### 5.2 Objective and derivatives (FR-05)

```text
J(g)       = Σ wᵢQᵢ² + β Σ λᵢ(C − gᵢ)²
∂J/∂gᵢ     = −2wᵢQᵢμᵢ − 2βλᵢ(C − gᵢ)
∂²J/∂gᵢ²   = 2wᵢμᵢ²·[aᵢ > 0] + 2βλᵢ          (off-diagonals are zero)
```

At `aᵢ = 0` the gradient is continuous. The Hessian is not defined there; use the generalized value with `[aᵢ > 0] = 0`.

For `J_ns`: choose the subgradient element `−wᵢμᵢ·[aᵢ > 0] − 2βλᵢ(C − gᵢ)`; at the kink any value in `[−wᵢμᵢ, 0]` is valid for the first term. The reduced component is `v₁ − v₂`.

### 5.3 Reduced problem

Let `g = g_NS`, `g_EW = G − g`:

```text
φ(g)  = J(g, G − g)
φ'(g) = ∂J/∂g₁ − ∂J/∂g₂
φ''(g)= ∂²J/∂g₁² + ∂²J/∂g₂²
g ∈ [ℓ, u],  ℓ = max(g_min, G − g_max),  u = min(g_max, G − g_min)
```

Properties:

- φ is convex and piecewise quadratic, so every local minimum is global.
- `β(λ₁ + λ₂) > 0` makes φ strongly convex and the minimizer unique.
- φ' is Lipschitz with `L_φ = Σ(2wᵢμᵢ² + 2βλᵢ)`.
- Config is rejected unless `ℓ ≤ u`, which requires `2·g_min ≤ G ≤ 2·g_max`.
- If both arrival rates are zero and predicted queues are zero over an interval, φ is flat. Return the projection of the initial point (*default:* G/2) onto the minimizing set.

### 5.4 Projection

`P(g) = min(u, max(ℓ, g))`, then `g_EW = G − g`.

Convergence test for constrained solvers on smooth problems: `|g − P(g − φ'(g))| ≤ tol` (*default* 1e-6). Testing `|φ'| ≈ 0` is wrong because optima on a bound have a nonzero derivative.

Neither test works for `J_ns`: at a minimizer on a kink, the chosen subgradient need not be zero. The subgradient method stops on its iteration budget or a stalled best value, and tests compare the best value with the oracle.

### 5.5 Reference test cases

`C=90, G=80, μ=(0.5,0.5), λ=(0.2,0.1), w=(1,1), β=0.1`

| Case | q | J at g=(40,40) | Optimal g_NS | J* |
|---|---|---|---|---|
| A (optimum on bound) | (40, 10) | 1519 | 70 | 797 |
| B (interior optimum) | (20, 15) | 415 | 57.4/1.06 ≈ 54.1509 | ≈ 308.868 |

Case A at (40,40): `Q = (38, 0)`, `∂J/∂g = (−40, −1)`, `φ' = −39`.

**Case C (`J_ns`, minimizer on a kink):** `q = (20, 1)`, same parameters. The minimizer is `g_NS = 60` with `J_ns = 75`. There `Q = (8, 0)`, and the one-sided derivatives of the reduced objective are −0.3 (left) and +0.2 (right), so 0 is a subgradient although no derivative vanishes. Confirmed by grid search in M1 ([report](M1_VERIFICATION.md)).

### 5.6 Rounding

SUMO steps are 1 s. Round `g_NS` to the better of floor and ceiling (by φ) inside `[ℓ, u]`, set `g_EW = G − g_NS`, then validate. Record both continuous and integer solutions.

---

## 6. Optimization algorithms (FR-06)

### 6.1 Interface

```python
class Solver(Protocol):
    name: str
    def solve(self, problem: Problem, x0: np.ndarray) -> SolverResult: ...

class Problem(Protocol):
    def value(self, x) -> float: ...
    def gradient(self, x) -> np.ndarray: ...      # or a subgradient
    def hessian(self, x) -> np.ndarray: ...       # optional
    def project(self, x) -> np.ndarray: ...       # identity if unconstrained
```

Stochastic problems add `sample_gradient(x, rng, batch)`.

### 6.2 Variants

| Algorithm | Variant | Step / safeguard | Notes |
|---|---|---|---|
| Gradient descent | fixed step, projected each iteration (identity when unconstrained) | `α < 2/L_φ`, default `1/L_φ` | The fixed-step counterpart of projected GD |
| Projected GD | `x ← P(x − α∇f)` | Armijo along the projection arc | *Default online solver* |
| Momentum | heavy ball with projection | α, momentum 0.9 → tune; restart if objective rises sharply | Not monotone |
| SGD | mini-batch over sampled arrival counts | `αₖ = α₀/(1+k)^p`, p ∈ (0.5, 1]; seeded; average iterates | Minimizes the expected objective; see §6.3 |
| Newton | damped, projected, semismooth Hessian | Armijo; fall back to gradient step if Hessian ≤ ε | Plain Newton can cycle across the Hessian jumps |
| BFGS | inverse-Hessian update, projected | Armijo/Wolfe; skip update if `yᵀs ≤ ε` | Scalar secant in 1-D |
| Conjugate gradient | **nonlinear Polak–Ribière+**, restart every n steps; linear CG only in quadratic tests | strong Wolfe or exact 1-D search; restart when a bound becomes active | |
| Subgradient | on `J_ns`, projected | `αₖ = α₀/√(k+1)`; track best iterate | Stop on max iterations or stalled best value |

### 6.3 Stochastic formulation

Sample arrivals per cycle `Aᵢ ~ Poisson(λᵢC)`, replacing `λᵢC` in the queue term, and minimize `E[J]`. The reference answer uses the exact expectation, summed over the Poisson probabilities. Its optimum differs from the deterministic one because `max(0,·)²` is convex.

### 6.4 Reference oracle

- Dense grid on `[ℓ, u]` (*default* step 1e-3 s).
- Bisection on the one-sided derivatives (exact to tolerance because they are nondecreasing). This covers both J and `J_ns`.
- The grid also contains the kink points and G/2.

A solver passes when `f(x) − f* ≤ tol_f` and the result is feasible.

### 6.5 Comparison study

| Track | Problem | Purpose |
|---|---|---|
| T1 | Reduced 1-D φ on a fixed set of states recorded from simulation | Accuracy, iterations, runtime in the real use case |
| T2 | 2-D: `J(g) + (ρ/2)(g₁+g₂−G)²`, bounds by projection, ρ ∈ {1, 10, 100} | Study GD, momentum, Newton, BFGS and CG as conditioning worsens. Result is only approximately feasible, so it is never applied to signals |
| T3 | Convex quadratics and Rosenbrock | Verify implementations in n-D |

Report convergence curves, iterations to tolerance, runtime distribution and failure counts, using the same initial points and tolerances.

**T2 details**

```text
P_ρ(g)   = J(g) + (ρ/2)·r²,   r = g₁ + g₂ − G
∂P_ρ/∂gᵢ = ∂J/∂gᵢ + ρr
∇²P_ρ    = diag(∂²J/∂g₁², ∂²J/∂g₂²) + ρ·[[1, 1], [1, 1]]
```

- The condition number grows roughly linearly with ρ.
- At a solution with inactive bounds, `r = −(∂J/∂gᵢ)/ρ ≥ 0`, so the plan overshoots the green budget by an amount that shrinks as ρ grows. Report `r` for every run.
- The reference answer for each ρ is a high-accuracy Newton solution checked against a 2-D grid.
- The projected Newton and BFGS variants need an active-set or projection-arc line search, since simply clipping a full step is not guaranteed to descend.
- Two dimensions remain small: do not draw conclusions about large-scale behaviour.

---

## 7. Control layer

### 7.1 Controllers (FR-09)

All implement `plan(state: TrafficState) -> TimingPlan`.

| Controller | Rule |
|---|---|
| Fixed equal | `g = (G/2, G/2)` |
| Fixed calibrated | split G in proportion to `λᵢ/μᵢ` from the scenario's long-run average rates, fixed for the run, then bounded |
| Queue-proportional | `g₁ = G·q₁/(q₁+q₂)`, equal split if both zero, then bounded |
| Adaptive | solver from config on the §5 model |
| Actuated (optional) | SUMO actuated program with matching min/max greens and clearances |

Note for the report: the calibrated baseline knows the true average demand, which the adaptive controller does not. For the changing scenario it uses the whole-run average.

### 7.2 Validation and fallback (FR-07)

Checks: values finite and integer; within bounds; sum equals G; solver result feasible, and either `converged` or not worse than the start (*configurable*); wall time within budget (NFR-03, *default* 100 ms, of which the solver may use 80 %); state valid.

Fallback order: fixed equal split (verified feasible at startup). Every fallback is logged with its reason and counted.

### 7.3 Signal state machine (FR-08, NFR-02)

```text
NS_GREEN → NS_YELLOW → ALL_RED_1 → EW_GREEN → EW_YELLOW → ALL_RED_2 → (decision) → NS_GREEN
```

- Only transitions in this order exist.
- A new plan is accepted only at the boundary after ALL_RED_2, and is immutable for the cycle.
- State strings are generated from the network's link order and checked at startup so no state gives green to both phases.
- The simulation does not advance while the solver runs; wall time is still measured against the budget.
- If the controller raises an exception, apply fallback and continue. If TraCI disconnects, end the run and mark it failed.

---

## 8. Evaluation

### 8.1 Metrics (FR-10)

| Metric | Definition / source |
|---|---|
| Average waiting time | mean `waitingTime` from tripinfo |
| Average travel time | mean `duration` from tripinfo |
| Insertion delay | mean `departDelay` (reported so blocked vehicles are not hidden) |
| Average / max queue | per-step halting count per approach |
| Throughput | arrived vehicles in the measurement period |
| Stops per vehicle | mean `waitingCount` |
| Worst-approach delay | highest per-approach mean `timeLoss` |
| Solver time, iterations, status | `SolverResult` per cycle |
| Feasibility violations, fallbacks | validator counters |

Use `--tripinfo-output.write-unfinished` so vehicles still in the network are counted. Report finished and unfinished numbers separately.

### 8.2 Experiment protocol

- *Default* run: 3600 s measured after a 600 s warm-up.
- Tuning seeds 1–5; evaluation seeds 101–120. Tune baselines and adaptive parameters with equal care (as designed, the baselines have no free parameters).
- Primary metric, fixed before evaluation: waiting time per vehicle including waiting to enter. The adaptive β and window are chosen by the smallest geometric mean over scenarios, relative to the defaults. Chosen values are in `configs/frozen.yaml`; the defaults above are the starting values.
- Matrix: 6 scenarios × 4 controllers × 20 seeds = 480 runs, plus the solver comparison.
- Statistics: per-seed paired differences, mean with 95% confidence interval, Wilcoxon signed-rank test, Holm correction across comparisons.

### 8.3 Outputs

```text
results/<experiment_id>/
├─ config.yaml, environment.json (Python, SUMO, package versions)
├─ runs.csv          one row per run
├─ cycles.csv        state, plan, solver result per cycle
├─ summary.csv       paired statistics
└─ figures/
```

---

## 9. Configuration, logging, errors

- One YAML tree, merged as default → scenario → command line, validated into dataclasses at startup. Unknown keys are errors.
- The resolved config is saved with each run.
- Structured per-cycle records (NFR-07) plus standard `logging` for events.
- Configuration errors stop the program; runtime control errors use the fallback.

---

## 10. Testing

| Level | Content |
|---|---|
| Unit | queue and objective hand cases A–C (§5.5); penalty value, gradient and Hessian; estimator; projection; validator; state machine with a fake TraCI |
| Numerical | central-difference gradient and Hessian checks away from kinks; gradient continuity at kinks for J; subgradient inequality for J_ns |
| Property | randomized states: solver output feasible, finite, no worse than start (monotone solvers), matches oracle |
| Integration (`sumo`) | network loads; vehicles enter and leave; phase sequence and durations observed; same seed reproduces metrics |
| Regression | fixed small run with stored expected summary |

---

## 11. Technology

Python 3.12, SUMO (pip `eclipse-sumo`, `traci`, `sumolib`, pinned), NumPy, Pandas, Matplotlib, PyYAML, pytest. SciPy only for statistics and test cross-checks (addition to PRD §9). Plotly and Streamlit are optional and deferred.

---

## 12. Traceability

| Requirement | Design |
|---|---|
| FR-01 | §4.1, §4.2 |
| FR-02, FR-03 | §4.3, §4.4 |
| FR-04, FR-05, PRD §6 | §5 |
| FR-06 | §6 |
| FR-07, FR-08, FR-09 | §7 |
| FR-10, PRD §11 | §8, §4.2 |
| NFR-01 | §10 |
| NFR-02, NFR-03 | §7.2, §7.3 |
| NFR-04 | §4.2, §8.3 |
| NFR-05, NFR-06 | §3.3, §6.1 |
| NFR-07 | §9 |

---

## 13. Known limitations

Single intersection; through movements only; cycle-level queue model; red-time term is a proxy; fixed cycle length; perfect detection from the simulator; one-step lookahead. With a 1-D convex objective, differences in traffic performance between converged solvers are expected to be negligible, so solver comparison is about numerical behaviour and controller comparison is about traffic performance.
