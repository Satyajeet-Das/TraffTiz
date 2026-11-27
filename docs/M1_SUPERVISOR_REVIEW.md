# Project Review Request — OptiTraffic

**Numerical optimization for adaptive traffic signal timing** (simulation study)

## 1. Goal

Choose green-light durations at one four-way intersection by numerical optimization, and compare the result with fixed-time, queue-proportional and actuated signals in the SUMO traffic simulator.

## 2. Optimization problem

$$\min_{g_1,g_2}\; J=\sum_{i=1}^{2}w_iQ_i^2+\beta\sum_{i=1}^{2}\lambda_i(C-g_i)^2$$

$$g_1+g_2=C-L,\qquad g_{min}\le g_i\le g_{max},\qquad Q_i=\max\left(0,\;q_i+\lambda_iC-\tfrac{s_ig_i}{3600}\right)$$

$g_i$ green time of phase $i$ (North–South, East–West), $q_i$ queue, $\lambda_i$ arrival rate, $s_i$ saturation flow, $C$ cycle length, $L$ lost time, $w_i,\beta$ weights.

**Algorithms:** gradient descent, projected gradient, momentum, stochastic gradient descent, Newton, BFGS, conjugate gradient, subgradient.

**Current state:** formulation documented and checked numerically ([report](M1_VERIFICATION.md)). The model, algorithms, simulation, controllers and a first experiment are complete ([results](M9_RESULTS.md)); a second experiment tests D8.

## 3. Decisions for your review

### D1. Separate nonsmooth objective
**Issue:** $J$ is continuously differentiable, because squaring removes the kink of $\max(0,\cdot)$. A subgradient method on $J$ is ordinary gradient descent.  
**Proposal:** keep $J$ for signal control and study the subgradient method on $J_{ns}=\sum w_iQ_i+\beta\sum\lambda_i(C-g_i)^2$.  
**Limitation:** with equal weights and saturation flows, and both queues positive, the $J_{ns}$ split does not depend on queue sizes.

☐ Approve  ☐ Change  Comment:

### D2. Comparing algorithms beyond one variable
**Issue:** the equality constraint leaves one free variable, so BFGS and conjugate gradient become trivial.  
**Proposal:** compare on three forms (section 4).  
**Limitation:** in the 2-variable form, gradient descent slows sharply as the penalty grows (72, 643 and 6353 iterations in one test), but exact-line-search CG and BFGS both finish in 2 steps there.

☐ Approve  ☐ Change  Comment:

### D3. Queue used for each phase
Each phase serves two approaches that move together. **Proposal:** use the approach with the largest expected queue $q+\lambda C$.

☐ Approve  ☐ Change  Comment:

### D4. Lost time
**Measured:** in the simulator, effective green is about 1 s shorter than displayed green.  
**Proposal (applied):** display 1 s more than the effective green, with $L=2\times(\text{yellow}+\text{all-red}+1)=12$ s and a green budget of 78 s.

☐ Approve  ☐ Change  Comment:

### D5. Choosing the weights
$J$ adds terms with different units, so $\beta$ affects the answer. **Proposal:** tune $\beta$ and $w_i$ on separate random seeds from those used for evaluation, and report a sensitivity study.

☐ Approve  ☐ Change  Comment:

### D6. Saturation flow
**Proposal:** measure it in the simulator instead of assuming 1800 veh/h.  
**Measured since:** 1862 veh/h per lane ([results](M3_INTERSECTION.md)).

☐ Approve  ☐ Change  Comment:

### D7. Counting vehicles outside a full road
**Issue:** when a road is full, new vehicles cannot enter and road counts underestimate demand ([measurements](M4_STATE_COLLECTION.md)).  
**Proposal (applied):** also count vehicles waiting to enter, both as arrivals and in the queue. A real road sensor could not do this, so it is an assumption of perfect detection, applied equally to all controllers.

☐ Approve  ☐ Change  Comment:

### D8. When the queues are measured
**Issue:** both queues were read at the cycle start, just before the North–South green. East–West had only just been served, so its queue was systematically smaller: with equal demand the first experiment measured 12.6 against 5.6 vehicles.  
**Proposal (being tested):** read each queue just before its own green. The East–West value is then used at the next decision, so it is part of a cycle old. The objective and the signal sequence are unchanged.  
**Note:** proposed after seeing the first results, so it is evaluated on new random seeds and both versions are reported.

☐ Approve  ☐ Change  Comment:

## 4. Algorithm comparison plan

| Track | Problem | Purpose |
|---|---|---|
| T1 | One-variable problem on traffic states recorded from simulation | accuracy, iterations and run time in real use |
| T2 | Two variables with penalty $J+\frac{\rho}{2}(g_1+g_2-G)^2$ | effect of ill-conditioning |
| T3 | Convex quadratics and Rosenbrock function | correctness in higher dimensions |

☐ Approve  ☐ Change  Comment:

## 5. Questions

1. Is this scope suitable for a 50-mark project?  
   Answer:
2. Which algorithms are required?  
   Answer:
3. Is the traffic simulation required, and how is it weighted against the mathematics?  
   Answer:
4. What is the deadline and the required report format?  
   Answer:
5. A comparison with SUMO's actuated signal controller has been added. Is it appropriate, given that its cycle length is not fixed?  
   Answer:
6. Should we also optimize several cycles together? This gives more variables and a convex problem that is not differentiable everywhere. It is not in the current scope.  
   Answer:

## 6. Sign-off

Overall decision: ☐ Approved  ☐ Approved with changes  ☐ Revise and resubmit

Supervisor name:

Signature:

Date:
