# PRD — OptiTraffic
## Numerical Optimization-Based Adaptive Traffic Signal Management

**Document Version:** 1.1  
**Project Type:** Academic / Numerical Optimization  
**Status:** Proposed  
**Primary Domain:** Intelligent Transportation Systems

**Changes in 1.1:** corrected the smoothness of the objective and added a nonsmooth objective for the subgradient study (§6.4, FR-06); added formulations for comparing algorithms beyond one dimension (§6.7).

---

# 1. Product Overview

## 1.1 Introduction

OptiTraffic is a simulation-based adaptive traffic signal management system that applies numerical optimization techniques to improve traffic signal timing.

Traditional traffic signals often operate using predefined green-light durations, regardless of changing traffic conditions. This can result in unnecessary waiting times, uneven queue distribution, and inefficient utilization of intersection capacity.

OptiTraffic aims to address this problem by dynamically allocating green-light durations based on observed traffic conditions, such as queue lengths and vehicle arrival rates.

The project will use SUMO (Simulation of Urban MObility) to simulate traffic and Python with TraCI to interact with the simulation.

## 1.2 Problem Statement

Fixed-time traffic signal systems do not necessarily adapt to variations in traffic demand across different directions.

For example:
- North–South traffic may have 40 waiting vehicles.
- East–West traffic may have only 10 waiting vehicles.
- A fixed-time signal may still allocate equal green time to both directions.

This can lead to inefficient traffic management.

We want to formulate this as a constrained numerical optimization problem and investigate whether optimization-based green-time allocation improves traffic flow.

## 1.3 Product Vision

Develop a simulation-based system that demonstrates how numerical optimization algorithms can be applied to adaptive traffic signal management.

The system should:
- Observe traffic conditions.
- Estimate traffic demand.
- Formulate an optimization problem.
- Calculate suitable green-light durations.
- Apply timings safely in the simulation.
- Measure and compare traffic performance.

---

# 2. Goals and Objectives

## 2.1 Primary Goals

1. Develop a simulated four-way traffic intersection.
2. Collect traffic information from SUMO using TraCI.
3. Formulate a mathematical optimization model for green-time allocation.
4. Implement multiple numerical optimization algorithms.
5. Dynamically adjust traffic signal timings.
6. Compare optimized traffic management against traditional approaches.
7. Analyze algorithm performance and traffic improvements.

## 2.2 Academic Objectives

The project should demonstrate practical applications of numerical optimization concepts, including:

- Gradient-based optimization.
- Momentum-based optimization.
- Second-order optimization.
- Quasi-Newton methods.
- Conjugate gradient methods.
- Nonsmooth optimization.
- Constrained optimization.
- Numerical convergence and error analysis.

## 2.3 Non-Goals

The initial version will not attempt to:

- Control real-world traffic signals.
- Coordinate multiple intersections.
- Build a city-wide traffic management platform.
- Implement complete pedestrian and emergency vehicle management.
- Model every possible turning movement.
- Claim real-world traffic improvements based only on simulation results.

These may be considered future extensions.

---

# 3. Target Users and Stakeholders

| Stakeholder | Responsibility |
|---|---|
| Project team | Design, implement, test and evaluate the system |
| Project supervisor | Validate mathematical formulation and academic relevance |
| Researchers/students | Understand and compare numerical optimization algorithms |
| Evaluators | Assess mathematical correctness and experimental results |

The initial system is a research and demonstration prototype, not a public-facing commercial product.

---

# 4. Project Scope

## 4.1 Initial Intersection

The first version will simulate a single four-way intersection.

It will contain two non-conflicting traffic phases:

- **Phase 1:** North–South traffic.
- **Phase 2:** East–West traffic.

The first implementation will focus on through movements to keep the mathematical model manageable.

## 4.2 Operating Cycle

Each traffic signal cycle consists of:
- North–South green.
- Required yellow and clearance transitions.
- East–West green.
- Required yellow and clearance transitions.

The optimizer will determine the effective green durations. A separate signal controller will handle safe phase transitions.

## 4.3 Optimization Frequency

The system will operate in repeated decision cycles.

At a safe cycle boundary:
1. Read the latest traffic state.
2. Estimate demand.
3. Calculate optimized green durations.
4. Validate the proposed timing plan.
5. Apply the plan to the next cycle.

The optimizer must not interrupt an active green phase.

---

# 5. Functional Requirements

## FR-01: Traffic Simulation

The system must:
- Initialize a SUMO traffic simulation.
- Load a predefined four-way intersection.
- Support multiple traffic demand scenarios.
- Simulate vehicle arrivals, movement, waiting and departures.
- Support reproducible experiments using random seeds.

**Acceptance Criteria:**
- The intersection runs successfully in SUMO.
- Vehicles can enter and leave through configured routes.
- Traffic-light phases operate correctly.
- Simulation metrics can be collected.

## FR-02: Traffic State Collection

The system must collect traffic information through TraCI.

Required information:
- Current queue length per approach or phase.
- Vehicle arrival rate.
- Vehicle count.
- Waiting time.
- Traffic-light state.
- Simulation time.

**Acceptance Criteria:**
- Measurements are associated with the correct traffic direction.
- Data is collected at consistent decision intervals.
- Missing or invalid measurements are handled safely.

## FR-03: Demand Estimation

The system must estimate traffic arrival rates using observed vehicle arrivals over a configurable measurement window.

For direction \(i\):

\[
\lambda_i = \frac{N_i}{\Delta t}
\]

Where:
- \(N_i\) is the number of observed arrivals.
- \(\Delta t\) is the observation window in seconds.
- \(\lambda_i\) is the estimated arrival rate in vehicles per second.

**Acceptance Criteria:**
- Arrival rates are calculated separately for both phases.
- The measurement window is configurable.
- Estimated rates are nonnegative and finite.

## FR-04: Queue Prediction

The system must estimate the residual queue after a candidate signal cycle.

\[
Q_i = \max\left(0,\ q_i+\lambda_iC-\frac{s_ig_i}{3600}\right)
\]

Where:
- \(q_i\): current queue.
- \(\lambda_i\): arrival rate.
- \(C\): cycle length.
- \(s_i\): saturation flow in vehicles per hour of effective green.
- \(g_i\): allocated green time in seconds.
- \(Q_i\): predicted residual queue.

**Acceptance Criteria:**
- The model produces nonnegative predicted queues.
- Units are consistent.
- The output matches manually calculated test cases.

## FR-05: Mathematical Optimization

The system must determine a feasible allocation of green time by minimizing a mathematical objective.

The initial objective is:

\[
J(\mathbf{x}) =
\sum_{i=1}^{2}w_iQ_i^2
+
\beta\sum_{i=1}^{2}\lambda_i(C-g_i)^2
\]

Where:
- \(Q_i\): predicted residual queue.
- \(w_i\): queue penalty weight.
- \(\beta\): red-time proxy weight.
- \(C-g_i\): simplified red-time exposure proxy.

The optimization problem is:

\[
\min_{\mathbf{x}} J(\mathbf{x})
\]

Subject to:

\[
g_1+g_2=C-L
\]

\[
g_{\min}\leq g_i\leq g_{\max}
\]

The red-time term is a simplified proxy, not an exact vehicle-level delay model. The objective must be evaluated against independent SUMO traffic metrics.

**Acceptance Criteria:**
- The objective function is implemented independently of SUMO.
- Constraints are enforced.
- The optimizer returns finite, feasible green allocations.
- Objective and gradient calculations are unit-tested.

## FR-06: Optimization Algorithms

The system should support the following algorithms:

| Algorithm | Requirement |
|---|---|
| Gradient Descent | Implement first-order optimization |
| Momentum | Implement gradient updates with velocity |
| Stochastic Gradient Descent | Use sampled traffic observations or scenarios |
| Newton's Method | Implement second-order optimization |
| BFGS | Implement quasi-Newton optimization |
| Conjugate Gradient | Specify and implement a suitable linear or nonlinear variant |
| Subgradient Method | Minimize the nonsmooth linear-queue objective \(J_{ns}\) (§6.4) |
| Projected Gradient Descent | Enforce feasible timing constraints through projection |

Each algorithm should expose:
- Initial solution.
- Objective value.
- Gradient information where applicable.
- Iteration count.
- Convergence status.
- Execution time.
- Final solution.
- Feasibility status.

Not all algorithms are equally suitable for every objective formulation. Their assumptions and implementation variants must be documented. Solvers must accept problems of any dimension and be compared on the formulations in §6.7.

## FR-07: Timing Plan Validation

Before applying a timing plan, the system must verify:

- Green durations are finite.
- Green durations satisfy minimum and maximum limits.
- Total effective green equals the available budget.
- Optimizer execution completed successfully.
- The proposed plan is compatible with the signal controller.

If validation fails, the system must use a predefined safe fallback plan.

## FR-08: Adaptive Signal Control

The system must apply validated green-time allocations to the next traffic cycle.

Requirements:
- Preserve the correct phase sequence.
- Include yellow and all-red clearance where configured.
- Never activate conflicting green phases simultaneously.
- Never interrupt an active phase to apply a new plan.
- Maintain a fallback strategy.

## FR-09: Baseline Controllers

The system must support comparison against:

1. Fixed-time equal green split.
2. Fixed-time demand-calibrated split.
3. Queue-proportional heuristic.
4. Optimization-based adaptive controller.

If practical, SUMO's actuated traffic-light controller may be included as an additional baseline.

## FR-10: Performance Evaluation

The system must record:

- Average waiting time.
- Average travel time.
- Average queue length.
- Maximum queue length.
- Vehicle throughput.
- Number of stops per vehicle.
- Worst-approach delay.
- Optimization execution time.
- Iterations and convergence information.
- Feasibility violations.
- Fallback count.

Results must be available for comparison across controllers and scenarios.

---

# 6. Mathematical and Optimization Requirements

## 6.1 Decision Variables

\[
\mathbf{x} =
\begin{bmatrix}
g_{NS}\\
g_{EW}
\end{bmatrix}
\]

## 6.2 Cycle Constraint

\[
G=C-L
\]

\[
g_{NS}+g_{EW}=G
\]

## 6.3 Bounds

\[
g_{\min}\leq g_{NS},g_{EW}\leq g_{\max}
\]

## 6.4 Gradient and Smoothness

### Primary objective

\[
\frac{\partial J}{\partial g_i}
=
-2w_iQ_i\frac{s_i}{3600}
-2\beta\lambda_i(C-g_i)
\]

This holds everywhere. Although \(Q_i\) has a kink where it reaches zero, \(Q_i^2\) does not: the queue term of the gradient tends to zero from both sides. \(J\) is therefore convex and continuously differentiable. Only its second derivative jumps at the queue boundary.

### Nonsmooth objective

A subgradient method applied to \(J\) is ordinary gradient descent. The subgradient study therefore uses a linear queue penalty:

\[
J_{ns}(\mathbf{x}) =
\sum_{i=1}^{2}w_iQ_i
+
\beta\sum_{i=1}^{2}\lambda_i(C-g_i)^2
\]

subject to the same constraints. \(J_{ns}\) is convex and not differentiable where a predicted queue reaches zero. With \(a_i = q_i+\lambda_iC-\frac{s_ig_i}{3600}\), a valid subgradient component is:

\[
v_i = -w_i\theta_i\frac{s_i}{3600} - 2\beta\lambda_i(C-g_i),
\qquad
\theta_i
\begin{cases}
=1 & a_i>0\\
\in[0,1] & a_i=0\\
=0 & a_i<0
\end{cases}
\]

\(J\) remains the objective used for signal control. \(J\) and \(J_{ns}\) have different units and minimizers, so their objective values must not be compared with each other.

## 6.5 Constraint Projection

For the two-phase system, define:

\[
g_{EW}=G-g_{NS}
\]

The feasible interval for the first phase is:

\[
\ell=\max(g_{\min},G-g_{\max})
\]

\[
u=\min(g_{\max},G-g_{\min})
\]

After a gradient step, project:

\[
g_{NS}^{new}=\min(u,\max(\ell,g_{NS}^{trial}))
\]

\[
g_{EW}^{new}=G-g_{NS}^{new}
\]

This ensures both the equality constraint and the green bounds are satisfied.

## 6.6 Numerical Correctness

The implementation must be tested using:
- Finite-difference gradient checks.
- Manual objective calculations.
- Projection tests.
- Convergence tests.
- Comparison against a dense one-dimensional grid search.
- Gradient continuity tests for \(J\) at queue boundaries.
- Subgradient inequality tests for \(J_{ns}\) at nonsmooth queue boundaries.
- A test whose \(J_{ns}\) minimizer lies on a queue boundary.

## 6.7 Formulations for Algorithm Comparison

With two phases and the cycle constraint, the control problem has only one free variable. In one dimension, BFGS reduces to the secant method, and conjugate gradient has no conjugate directions to build. Algorithms must therefore be compared on three formulations:

| Formulation | Definition | Purpose |
|---|---|---|
| Reduced (1-D) | \(g_{EW}=G-g_{NS}\) | Signal control; accuracy and run time in real use |
| Penalty (2-D) | \(J(\mathbf{x})+\frac{\rho}{2}(g_{NS}+g_{EW}-G)^2\), with the green bounds | Study convergence as conditioning worsens with increasing \(\rho\) |
| Test functions (n-D) | Convex quadratics and the Rosenbrock function | Verify implementations in higher dimensions |

The penalty form satisfies the cycle constraint only approximately. Its constraint violation must be reported, and its solutions must never be applied to the signals. The 2-D form shows differences in conditioning but is still small, so conclusions about scaling must come with that limitation.

---

# 7. User Workflow

The initial system is an experimental control pipeline rather than a user-account application.

### Simulation workflow

1. Researcher selects a traffic demand scenario.
2. Simulation loads the intersection and vehicle routes.
3. SUMO begins generating and moving vehicles.
4. TraCI collects traffic information.
5. The demand estimator calculates arrival rates.
6. The optimization engine calculates green-time allocations.
7. The timing validator checks feasibility.
8. The controller applies the plan at the next safe cycle boundary.
9. The simulation continues.
10. The evaluation module records traffic and optimization metrics.
11. Results are exported for analysis.

---

# 8. Non-Functional Requirements

## NFR-01: Correctness

All mathematical operations must be tested against hand-calculated examples and numerical checks.

## NFR-02: Safety

The optimizer must not directly perform unsafe traffic-light transitions. A separate controller must maintain phase sequencing and clearance intervals.

## NFR-03: Performance

Optimization should complete within a configurable decision-time budget so that the next signal cycle can be planned without disrupting simulation execution.

## NFR-04: Reproducibility

Experiments must support fixed random seeds and saved configuration files.

## NFR-05: Modularity

Traffic simulation, optimization algorithms, mathematical models, controllers and evaluation logic must be independent modules.

## NFR-06: Maintainability

Each algorithm must have a consistent interface and its own tests.

## NFR-07: Observability

The system must log optimizer decisions, signal timings, queue measurements, solver status and performance metrics.

---

# 9. Technology Stack

| Component | Technology |
|---|---|
| Traffic simulation | SUMO |
| Simulation integration | TraCI |
| Main programming language | Python |
| Numerical computing | NumPy |
| Data processing | Pandas |
| Visualization | Matplotlib / Plotly |
| Testing | pytest |
| Configuration | YAML |
| Optional dashboard | Streamlit |

A dashboard is optional and should only be developed after the core simulation and optimization pipeline works.

---

# 10. System Architecture

The system will follow a modular architecture:

```text
OptiTraffic
|
|-- Simulation Layer
|   |-- SUMO Network
|   |-- Vehicle Routes
|   |-- Traffic Light Configuration
|
|-- Integration Layer
|   |-- TraCI Client
|   |-- Traffic State Collector
|
|-- Traffic Modelling Layer
|   |-- Queue Estimator
|   |-- Arrival Rate Estimator
|   |-- Queue Prediction Model
|
|-- Optimization Layer
|   |-- Objective Function
|   |-- Gradient and Hessian
|   |-- Constraints and Projection
|   |-- Optimization Algorithms
|
|-- Control Layer
|   |-- Timing Plan Validator
|   |-- Signal Phase Controller
|   |-- Fallback Controller
|
|-- Evaluation Layer
    |-- Metrics Collector
    |-- Experiment Runner
    |-- Statistical Analysis
    |-- Visualization
```

---

# 11. Experiment Scenarios

The system must be evaluated using multiple traffic demand scenarios.

| Scenario | Description |
|---|---|
| Low traffic | Low arrival rates in both directions |
| Medium traffic | Moderate and balanced traffic |
| High traffic | High demand in both directions |
| NS dominant | Higher demand in North–South direction |
| EW dominant | Higher demand in East–West direction |
| Changing demand | Traffic dominance changes during simulation |

Each scenario should be repeated with multiple random seeds.

The same seeds should be used for each controller wherever possible to support fair paired comparisons.

---

# 12. Acceptance Criteria

The project will be considered functionally complete when:

1. A four-way intersection runs successfully in SUMO.
2. Two traffic phases operate correctly.
3. Traffic data is collected through TraCI.
4. Queue and arrival-rate estimates are generated.
5. The objective function produces correct results.
6. The gradient implementation passes numerical checks.
7. The required optimization algorithms are implemented and tested, or any excluded methods are justified.
8. Feasible green-time allocations are generated.
9. The controller safely applies optimized timings.
10. Fixed-time and heuristic baselines are available.
11. Multiple demand scenarios can be evaluated.
12. Performance metrics are collected and compared.
13. Experimental results are reproducible.
14. The final report documents assumptions, results and limitations.

---

# 13. Project Milestones

| Milestone | Description |
|---|---|
| M1 | Validate project idea and mathematical formulation |
| M2 | Set up Python and SUMO environment |
| M3 | Build the four-way intersection |
| M4 | Implement traffic-state collection through TraCI |
| M5 | Implement queue prediction and objective functions |
| M6 | Implement and test optimization algorithms |
| M7 | Implement baseline traffic controllers |
| M8 | Integrate adaptive signal control |
| M9 | Run experiments and compare results |
| M10 | Prepare final report and demonstration |

---

# 14. Risks and Limitations

| Risk | Mitigation |
|---|---|
| Simplified mathematical model | Validate with SUMO's microscopic simulation |
| Incorrect demand estimates | Test different observation windows |
| Infeasible optimization output | Implement projection and validation |
| Unsafe signal transitions | Separate optimizer from safety controller |
| Unfair baseline comparison | Document and tune baseline configurations |
| Random simulation variation | Use repeated seeds and statistical summaries |
| Excessive project scope | Complete one intersection before extending |

The project is a simulation-based academic study. Improvements observed in SUMO cannot automatically be interpreted as real-world traffic improvements.

---

# 15. Future Enhancements

After completing the initial version, possible extensions include:

- Multiple intersections and coordinated signal timing.
- Dedicated turning movement phases.
- Pedestrian and emergency vehicle handling.
- Adaptive cycle-length optimization.
- More detailed traffic demand prediction.
- Comparison with reinforcement learning approaches.
- A visualization dashboard showing queues and optimized timings.
- Robust optimization under uncertain traffic demand.

These enhancements are outside the initial release scope.

---

# 16. Project Success Definition

OptiTraffic will be successful if it demonstrates a mathematically correct, reproducible optimization pipeline that:

1. Models green-time allocation as a constrained optimization problem.
2. Implements and compares appropriate numerical optimization methods.
3. Integrates optimization with a working SUMO simulation.
4. Produces feasible signal timing decisions.
5. Evaluates those decisions against meaningful baselines.
6. Explains both improvements and limitations using experimental evidence.

**Core principle:** The optimizer proposes the timing plan, the safety controller validates and executes it, and the simulation provides evidence of its effectiveness.