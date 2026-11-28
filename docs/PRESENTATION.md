# Presentation Guide: what to explain, and how

About **10 minutes**, plus questions. If you get only 5, do parts 1, 2, 3 and 6.

| Part | Topic | Minutes | Show |
|---|---|---|---|
| 1 | The problem | 1 | spoken, one sketch |
| 2 | The mathematical model | 2 | board |
| 3 | Solving one example by hand | 2 | board, then terminal |
| 4 | The algorithms | 1.5 | terminal, one table |
| 5 | The simulation | 1.5 | `sumo-gui` |
| 6 | Results and what went wrong | 2 | dashboard |

**The one sentence to remember:**

> I choose how long each light stays green by minimizing a convex function of the predicted queues, and test it in a traffic simulator against other signals.

---

## Part 1. The problem

**Say:**
> At a crossing, North–South and East–West take turns. A fixed timer gives the same green even if one road has 40 cars and the other has 10. My question: can I calculate a better split every cycle?

**How:** draw a cross. Label the two directions "phase 1" and "phase 2". Write: one cycle = 90 s, of which 12 s are lost to yellow, all-red and starting up, so **78 s of green to share**.

**Say clearly:** this is a simulation study. It does not control real signals.

---

## Part 2. The model

Build it in three steps. Write each line, then say what it means.

**Step 1: predict the queue** (cars in = cars out + cars left):

$$Q_i=\max(0,\; q_i+\lambda_iC-\mu_ig_i)$$

> Cars waiting now, plus cars arriving in one cycle, minus cars that leave during green. A queue cannot be negative, hence the max.

**Step 2: score a choice of green times:**

$$J=\sum_i w_iQ_i^2+\beta\sum_i\lambda_i(C-g_i)^2$$

> The first part punishes cars left waiting. Squaring makes one queue of 20 (400) worse than two queues of 10 (200), so no road is ignored. The second part punishes long red on busy roads.

**Step 3: constraints:**

$$g_1+g_2=G,\qquad g_{min}\le g_i\le g_{max}$$

> Because the two greens add to a fixed total, only one unknown is left: $g_2=G-g_1$.

**Three facts to state, with a one-line reason each:**

| Fact | Reason |
|---|---|
| $J$ is **convex** | squared max of a linear expression is convex, and sums of convex functions are convex |
| So any local minimum is **the** minimum | property of convex functions |
| $J$ has a **continuous first derivative** but not a second | $\max(0,a)^2$ has slope $2\max(0,a)$, which has a corner at $a=0$ |

---

## Part 3. One example by hand

This is the part that shows you understand the mathematics. **Practise it until you can do it without notes.**

Textbook numbers (the experiments use slightly different, measured ones): $C=90$, $G=80$, $\mu=0.5$, $\lambda=(0.2,\,0.1)$, $q=(20,\,15)$, $\beta=0.1$, $w=1$. Let $g=g_1$.

1. Queues: $Q_1=38-0.5g$ and $Q_2=-16+0.5g$ (both positive near the answer).
2. Derivative of the one-variable function:
$$\varphi'(g)=\frac{\partial J}{\partial g_1}-\frac{\partial J}{\partial g_2}=-57.4+1.06g$$
3. Set it to zero: $g^*=57.4/1.06\approx\mathbf{54.15}$ s, so East–West gets $25.85$ s.
4. Compare: $J=415$ at an equal split, $J\approx308.87$ at the optimum. The two queues become nearly equal (10.9 and 11.1).

**Where step 2 comes from** (be ready to show it):
$\frac{\partial J}{\partial g_i}=-2\mu_iQ_i-2\beta\lambda_i(C-g_i)$, giving $-41.6+0.54g_1$ and $-25.8+0.52g_2$; then substitute $g_2=80-g$ and subtract.

**Then the important subtlety.** For $q=(40,10)$ the best answer is $g=70$, at the upper limit, where $\varphi'(70)=-8.2\neq0$.

> At a limit the derivative need not be zero. So the correct test is: taking a gradient step and pushing it back into the allowed range leaves the point unchanged.

**Show:** `python examples/reference_cases.py`. It prints both answers.

---

## Part 4. The algorithms

Explain **three** properly and name the rest. Starting at $g=40$, where $\varphi'(40)=-15$:

| Method | Idea to say | On this example |
|---|---|---|
| Gradient descent | walk downhill: $g\leftarrow g-\alpha\varphi'(g)$ | with $\alpha=0.5$: 40 → 47.5 → 51.0 → 52.7 |
| Newton | use the curvature too: $g\leftarrow g-\varphi'/\varphi''$ | $40+15/1.06=54.15$, done in **one step** |
| Projected gradient | take a step, then clip to $[10,70]$ | handles the limits; used by my controller |

Also implemented: momentum, stochastic gradient descent, BFGS, conjugate gradient, subgradient. All **written by hand**, not from a library.

**Show:** `python examples/compare_solvers.py`

In this output gradient descent finishes case B in one step, because the program uses the step size $1/L$. The three-step table above uses $lpha=0.5$ to show the idea; say so if asked.

**Main finding to say:**
> With one variable, all the exact methods give the same green times, so the choice does not change traffic. To compare them I also solved a harder two-variable version. There, gradient descent needed from 54 up to about 3000 steps as the problem became ill-conditioned, while Newton needed about 2.

---

## Part 5. The simulation

**Say:**
> Once per cycle the program counts the waiting cars and arrival rates, solves the problem, checks the answer is safe, and only then changes the lights.

**Show:**

```powershell
python scripts/demo.py --scenario ns_dominant
```

The first window is the fixed 50/50 signal, the second is your controller, on identical traffic.

**How:** the windows start slowly. Lower the **Delay** value in `sumo-gui` (try 10 ms) so queues build quickly. Point at the long North–South queue in the first run. Close the window to start the second.

**Safety, one sentence:** yellow and all-red are never skipped, and if the calculation fails or is late the signal uses an equal split.

---

## Part 6. Results and what went wrong

This is your strongest part. Tell it as a story.

**Show:** `python dashboard/build.py --open`

**1. First attempt (choose experiment `m9`).**
> My controller lost to a well-chosen fixed timer in 4 of 6 traffic types.

**2. Finding the cause.**
> The solver was converging, so I checked its inputs. I measured both queues just before North–South turned green. North–South had been waiting; East–West had just been cleared. With equal heavy traffic it read about 12 cars against 5.

**3. Fix and fair test (choose `m9b`).**
> I read each queue just before its own green. Because I found this after seeing results, I tested it on new random traffic.

| Waiting per vehicle (s) | Before | After | Best fixed timer | Actuated |
|---|---|---|---|---|
| High | 35.6 | 24.6 | 25.3 | 21.4 |
| Mostly North–South | 38.0 | 18.2 | 17.9 | 13.9 |
| Changing demand | 29.7 | 19.7 | 221.3 | 13.6 |

*"Before" and "After" are your controller, on the same traffic. "Actuated" is a standard sensor-based signal.*

**4. Conclusion, including the loss.**
> After the fix it is about equal to a fixed timer that was told the true demand, in 5 of 6 cases, and far better when demand changes. It beats the simple queue-based rule in all 6. The actuated signal is better than mine in all 6, because it reacts every second and mine decides once every 90 seconds. I cannot say how much each of those two differences contributes.

**How we know it is reliable:** 20 different random traffic samples per case, same traffic for every controller, 95% confidence intervals, and 840 runs with no collisions.

---

## Likely questions, with honest answers

| Question | Answer |
|---|---|
| Why optimize, when one variable can be solved directly? | Every algorithm can be checked against a known answer, and the same code extends to more variables. |
| Why square the queue? | It penalizes imbalance, and makes the derivative continuous. |
| Why is it convex? | Each term is a convex function of a linear expression; sums stay convex. |
| What if the derivative is not zero at the optimum? | The optimum is on a limit. Use the projected-gradient or KKT condition. |
| What does the multiplier of $g_1+g_2=G$ mean? | How much $J$ would fall with one more second of green (about 12.4 in the example). |
| Which algorithm is best? | Here Newton, BFGS and conjugate gradient finish in about 1 step. For traffic it makes no difference. |
| Why did you need a subgradient version? | $J$ is differentiable, so I used a version with $\max(0,a)$ not squared, which has a corner. |
| What did β do? | Tuning chose β = 0 for the fixed controller: the red-time term did not help. When both queues can be cleared, it then gives a 50/50 split. |
| Is the improvement from your fix or from retuning? | From the fix, for the large gains. I ran all four combinations; changing the settings alone made three cases worse. |
| Did you tune on the test traffic? | No. Tuning used seeds 1–5; testing used other seeds. |
| Would it work on a real road? | Unknown. One junction, no turning, perfect detection, simulation only. |
| What would you improve? | Let the cycle length vary, plan several cycles together, and predict each queue instead of using the last reading. |
| Did you use AI help? | Answer truthfully, following your course's rules, and show that you understand the work. |

## Do not claim

- "My method is the best." The actuated signal beat it everywhere.
- "It reduces real traffic." Simulation only.
- "A lower $J$ proves better traffic." Only the simulator measurements show that.
- "One algorithm gives better traffic." They give the same signal here.

If you do not know an answer, say so and explain how you would check it.

---

## Checklist before the day

- [ ] Do Part 3 on paper twice without looking.
- [ ] Run once: `.\.venv\Scripts\Activate.ps1`, then every command above, **with the simulator windows**.
- [ ] Keep the dashboard open in a browser tab beforehand.
- [ ] Backup if the simulator fails: screenshots, and the graphs in [REPORT.md](REPORT.md).
- [ ] Read [REPORT.md](REPORT.md); look up details in [MATHEMATICS.md](MATHEMATICS.md).
- [ ] Ask your teacher the time limit and what they want to see.
