# OptiTraffic — The Mathematics Explained

Companion to [PRD.md](PRD.md) and [TECHNICAL_DESIGN.md](TECHNICAL_DESIGN.md). Open in a Markdown preview that renders equations (`Ctrl+Shift+V` in VS Code).

**Contents**

1. The problem
2. Queue model
3. Objective function
4. Constraints and reduction to one variable
5. Gradient and Hessian
6. Convexity, existence and uniqueness
7. Optimality conditions (projection and KKT)
8. Optimization algorithms with worked iterations
9. Nonsmooth objective and subgradient method
10. Stochastic objective and SGD
11. Penalty formulation and conditioning
12. Numerical error analysis
13. Convergence summary
14. Assumptions and limitations
15. Questions you may be asked
16. Optional extension: several cycles

---

## 1. The problem

A four-way intersection has two phases: North–South (index 1) and East–West (index 2). One signal cycle lasts $C$ seconds, of which $L$ seconds are lost to yellow and all-red. **How should the remaining green time be divided?**

| Symbol | Meaning | Unit | Example value |
|---|---|---|---|
| $g_i$ | effective green time of phase $i$ (unknown) | s | — |
| $q_i$ | queue at the start of the cycle | veh | measured |
| $\lambda_i$ | arrival rate | veh/s | 0.2, 0.1 |
| $s_i$ | saturation flow | veh/h | 1800 |
| $\mu_i = s_i/3600$ | discharge rate during green | veh/s | 0.5 |
| $C$ | cycle length | s | 90 |
| $L$ | lost time | s | 10 |
| $G = C - L$ | green budget | s | 80 |
| $g_{min}, g_{max}$ | green bounds | s | 10, 70 |
| $w_i$ | queue weight | — | 1 |
| $\beta$ | red-time weight | veh/s | 0.1 |
| $Q_i$ | predicted queue after the cycle | veh | computed |

All worked examples use the example values above.

---

## 2. Queue model

### Derivation

Count vehicles in one approach over one cycle (conservation of vehicles):

$$\text{final queue} = \text{initial queue} + \text{arrivals} - \text{departures}$$

- Arrivals: $\lambda_i C$.
- Departures: at most $\mu_i g_i$, because vehicles leave only during green.
- A queue cannot be negative.

Therefore

$$Q_i(g_i) = \max(0,\; a_i(g_i)), \qquad a_i(g_i) = q_i + \lambda_i C - \mu_i g_i$$

Here $a_i$ is the queue that would remain if it could be negative. When $a_i<0$, the green time was longer than needed.

### Unit check

veh $+$ (veh/s)(s) $-$ (veh/s)(s) $=$ veh. ✓

### Arrival rate

$$\lambda_i = \frac{N_i}{\Delta t}$$

$N_i$ vehicles observed in a window of $\Delta t$ seconds. If arrivals are Poisson, this is the maximum-likelihood estimate, with variance $\lambda_i/\Delta t$. A longer window is less noisy but reacts more slowly to changes.

### Example

$q=(40,10)$, $\lambda=(0.2,0.1)$, $g=(40,40)$:

- $a_1 = 40 + 18 - 20 = 38$, so $Q_1 = 38$.
- $a_2 = 10 + 9 - 20 = -1$, so $Q_2 = 0$.

---

## 3. Objective function

$$J(g_1,g_2) = \underbrace{\sum_{i=1}^{2} w_i Q_i^2}_{\text{queue penalty}} + \underbrace{\beta\sum_{i=1}^{2}\lambda_i (C-g_i)^2}_{\text{red-time proxy}}$$

**Why square the queue?** One queue of 20 vehicles costs $400$, while two queues of 10 cost $200$. Squaring penalizes imbalance, so neither direction is starved.

**Why the second term?** $C - g_i$ is the time phase $i$ is not green. Vehicles arrive at rate $\lambda_i$ while waiting, so long red periods on busy approaches cost more. This is a **proxy** for delay, not an exact delay formula.

**Units.** The first term has veh², the second has (veh/s)(s²) $=$ veh·s. So $\beta$ carries units of veh/s, and its value sets the balance between the two terms.

**Example.** At $g=(40,40)$ with $q=(40,10)$:

$$J = 38^2 + 0 + 0.1\,(0.2\cdot 50^2 + 0.1\cdot 50^2) = 1444 + 75 = 1519$$

---

## 4. Constraints and reduction to one variable

$$\min_{g_1,g_2} J(g_1,g_2) \quad\text{subject to}\quad g_1+g_2 = G,\quad g_{min}\le g_i\le g_{max}$$

The equality gives $g_2 = G - g_1$. Write $g = g_1$. The bounds on $g_2$ become bounds on $g$:

$$g_{min}\le G-g\le g_{max} \iff G-g_{max}\le g\le G-g_{min}$$

Combine with $g_{min}\le g\le g_{max}$:

$$g\in[\ell,u], \qquad \ell=\max(g_{min},\,G-g_{max}), \qquad u=\min(g_{max},\,G-g_{min})$$

The reduced problem is

$$\min_{g\in[\ell,u]} \varphi(g), \qquad \varphi(g) = J(g,\;G-g)$$

**Feasibility.** A solution exists only if $\ell\le u$, which requires $2g_{min}\le G\le 2g_{max}$.

**Example.** $\ell=\max(10,10)=10$ and $u=\min(70,70)=70$.

### Projection

The projection of a trial value onto $[\ell,u]$ is the nearest feasible value:

$$P(g) = \min(u,\max(\ell,g))$$

Then set $g_2 = G - P(g)$. Both constraints hold automatically.

In the original two variables, the nearest feasible point to $(y_1,y_2)$ in the Euclidean sense is $g_1 = P\big((y_1-y_2+G)/2\big)$. Clipping $y_1$ alone is correct only when the step is taken on the reduced variable, using $\varphi'$.

---

## 5. Gradient and Hessian

### Derivative of $\max(0,a)^2$

Let $h(a) = \max(0,a)^2$. Then $h'(a)=2a$ for $a>0$ and $h'(a)=0$ for $a<0$. At $a=0$:

$$\lim_{t\to0^+}\frac{t^2 - 0}{t} = 0, \qquad \lim_{t\to0^-}\frac{0-0}{t}=0$$

Both one-sided derivatives are $0$, so $h'(a) = 2\max(0,a)$ everywhere. This is continuous, so $h$ is **continuously differentiable** ($C^1$).

The second derivative is $2$ for $a>0$ and $0$ for $a<0$. It jumps at $a=0$, so $h$ is not $C^2$.

### Gradient

By the chain rule, with $a_i' = -\mu_i$:

$$\frac{\partial J}{\partial g_i} = -2w_i\mu_i Q_i - 2\beta\lambda_i(C-g_i)$$

Both terms are non-positive for $g_i\le C$: more green never increases the cost of that phase. The trade-off comes only from the shared budget.

### Hessian

$$\nabla^2 J = \begin{bmatrix} d_1 & 0\\ 0 & d_2\end{bmatrix}, \qquad d_i = 2w_i\mu_i^2\,[a_i>0] + 2\beta\lambda_i$$

$[a_i>0]$ equals 1 if true and 0 otherwise. The matrix is diagonal because $J$ has no term containing both $g_1$ and $g_2$.

### Reduced derivatives

Since $g_2 = G-g$ and $dg_2/dg=-1$:

$$\varphi'(g) = \frac{\partial J}{\partial g_1} - \frac{\partial J}{\partial g_2}, \qquad \varphi''(g) = d_1 + d_2$$

### Example

At $g=(40,40)$, $q=(40,10)$:

- $\partial J/\partial g_1 = -2(0.5)(38) - 2(0.1)(0.2)(50) = -38 - 2 = -40$
- $\partial J/\partial g_2 = 0 - 2(0.1)(0.1)(50) = -1$
- $\varphi'(40) = -40-(-1) = -39$

The derivative is negative, so increasing North–South green reduces the cost.

---

## 6. Convexity, existence and uniqueness

### Theorem 1: $J$ is convex

*Proof.* $a_i(g_i)$ is affine. $h(a)=\max(0,a)^2$ is convex because $h'(a)=2\max(0,a)$ is non-decreasing. A convex function of an affine function is convex. Each $\lambda_i(C-g_i)^2$ is convex since $\lambda_i\ge0$. A sum of convex functions with non-negative weights $w_i,\beta$ is convex. $\;\blacksquare$

### Corollary

$\varphi(g)=J(g,G-g)$ is $J$ restricted to a line, so it is convex. **Every local minimum is a global minimum.**

### Theorem 2: a minimizer exists

$\varphi$ is continuous and $[\ell,u]$ is closed and bounded. By the Weierstrass theorem a minimum is attained. $\;\blacksquare$

### Theorem 3: it is unique if $\beta(\lambda_1+\lambda_2)>0$

$\varphi'$ is continuous and piecewise linear, with slope

$$\varphi''(g)\ge m = 2\beta(\lambda_1+\lambda_2) > 0$$

wherever it is defined. So $\varphi'$ is strictly increasing, $\varphi$ is **strongly convex**, and the minimizer is unique. $\;\blacksquare$

If both arrival rates are zero, $\varphi$ can be flat on an interval and many solutions are optimal. The program must then choose one by a fixed rule.

### Lipschitz constant of the derivative

$$|\varphi'(x)-\varphi'(y)|\le L_\varphi|x-y|, \qquad L_\varphi=\sum_{i=1}^{2}\left(2w_i\mu_i^2+2\beta\lambda_i\right)$$

For the example: $L_\varphi = 0.5+0.5+0.04+0.02 = 1.06$ and $m = 0.06$.

---

## 7. Optimality conditions

### Projected-gradient condition

$g^*$ minimizes the convex $\varphi$ on $[\ell,u]$ exactly when

$$g^* = P\big(g^* - \alpha\,\varphi'(g^*)\big) \quad\text{for any } \alpha>0$$

| Location | Condition | Meaning |
|---|---|---|
| Interior, $\ell<g^*<u$ | $\varphi'(g^*)=0$ | flat point |
| Lower bound, $g^*=\ell$ | $\varphi'(g^*)\ge0$ | cost would fall only below the bound |
| Upper bound, $g^*=u$ | $\varphi'(g^*)\le0$ | cost would fall only above the bound |

The solvers therefore stop when $r(g) = |g - P(g-\varphi'(g))|$ is below a tolerance.

### KKT conditions

For the two-variable problem, introduce multiplier $\nu$ for the equality and $\eta_i,\zeta_i\ge0$ for the lower and upper bounds:

$$\mathcal L = J + \nu(g_1+g_2-G) + \sum_i \eta_i(g_{min}-g_i) + \sum_i\zeta_i(g_i-g_{max})$$

| Condition | Equation |
|---|---|
| Stationarity | $\partial J/\partial g_i + \nu - \eta_i + \zeta_i = 0$ |
| Primal feasibility | $g_1+g_2=G,\;\; g_{min}\le g_i\le g_{max}$ |
| Dual feasibility | $\eta_i\ge0,\;\;\zeta_i\ge0$ |
| Complementary slackness | $\eta_i(g_{min}-g_i)=0,\;\;\zeta_i(g_i-g_{max})=0$ |

Because $J$ is convex and the constraints are linear, these conditions are **necessary and sufficient**.

### Case B: interior optimum, $q=(20,15)$

When both queues are positive:

$$\frac{\partial J}{\partial g_1} = -41.6+0.54g_1, \qquad \frac{\partial J}{\partial g_2} = -25.8+0.52g_2$$

With $g_2=80-g$:

$$\varphi'(g) = -57.4+1.06g = 0 \;\Rightarrow\; g^* = \frac{57.4}{1.06}\approx 54.1509$$

So $g^*\approx(54.15,\,25.85)$, queues $Q\approx(10.92,\,11.08)$ and $J^*\approx308.87$. Both queues are positive, confirming the assumption.

No bound is active, so all $\eta_i=\zeta_i=0$ and stationarity gives $\nu = -\partial J/\partial g_i \approx 12.36$ for both phases.

**Interpretation.** At the optimum, one extra second of green is equally valuable to either phase. $\nu$ is the **shadow price**: one more second of budget $G$ lowers $J^*$ by about 12.36 (with $C$ held fixed).

### Case A: optimum on the bounds, $q=(40,10)$

At $g=(70,10)$: $Q=(23,14)$, $\partial J/\partial g_1=-23.8$, $\partial J/\partial g_2=-15.6$, and $\varphi'(70)=-8.2\le0$.

Here $g_1$ is at its upper bound and $g_2$ at its lower bound:

$$-23.8+\nu+\zeta_1=0, \qquad -15.6+\nu-\eta_2=0$$

$\zeta_1,\eta_2\ge0$ holds for any $\nu\in[15.6,\,23.8]$. So the conditions are satisfied and $J^*=797$. The multipliers are not unique because the three active constraints are linearly dependent.

### Effect of $\beta$ (case B)

$$g^*(\beta) = \frac{54+34\beta}{1+0.6\beta}$$

This gives $54$ at $\beta=0$ (queues exactly equal), $54.15$ at $\beta=0.1$ and $55$ at $\beta=1$. The formula holds while both queues stay positive and no bound is active.

---

## 8. Optimization algorithms

All examples use **case B**, start $g_0=40$ (unless stated), where $\varphi'(40)=-15$ and $\varphi(40)=415$. On the interval $32<g<70$:

$$\varphi(g)\approx 308.87 + 0.53\,(g-54.1509)^2, \qquad \varphi'(g)=-57.4+1.06g$$

### 8.1 Gradient descent

**Idea:** move against the slope.

$$g_{k+1}=g_k-\alpha\,\varphi'(g_k)$$

**Step size.** For an $L_\varphi$-Lipschitz derivative,

$$\varphi(g_{k+1})\le\varphi(g_k)-\alpha\left(1-\frac{\alpha L_\varphi}{2}\right)\varphi'(g_k)^2$$

so the cost decreases if $0<\alpha<2/L_\varphi\approx1.887$.

With $\alpha=0.5$:

| $k$ | $g_k$ | $\varphi'(g_k)$ | error $\lvert g_k-g^*\rvert$ |
|---|---|---|---|
| 0 | 40.000 | −15.000 | 14.151 |
| 1 | 47.500 | −7.050 | 6.651 |
| 2 | 51.025 | −3.314 | 3.126 |
| 3 | 52.682 | −1.557 | 1.469 |

Each error is $1-\alpha(1.06)=0.47$ times the previous one. This is **linear convergence**.

### 8.2 Projected gradient descent

$$g_{k+1}=P\big(g_k-\alpha\,\varphi'(g_k)\big)$$

**Case A**, $g_0=40$, $\alpha=1/L_\varphi$: trial $40+39/1.06\approx76.79$, projected to $70$. Then $r(70)=0$, so it has converged in one step.

**Armijo line search** (when $L_\varphi$ is unknown): start with a large $\alpha$ and halve it until, with $g^+=P(g-\alpha\varphi'(g))$ and a constant $c\in(0,\tfrac12]$ (here $0.25$),

$$\varphi(g^+)\le\varphi(g)+c\,\varphi'(g)\,(g^+-g)$$

On a quadratic with curvature $L$ this accepts $\alpha\le 2(1-c)/L$. A very small $c$ therefore allows steps of almost $2/L$, which overshoot to nearly the mirror point and converge very slowly.

### 8.3 Momentum (heavy ball)

**Idea:** keep part of the previous step.

$$v_{k+1}=\gamma v_k-\alpha\varphi'(g_k), \qquad g_{k+1}=P(g_k+v_{k+1})$$

With $\alpha=0.5$, $\gamma=0.3$, $v_0=0$:

| $k$ | $v_k$ | $g_k$ |
|---|---|---|
| 1 | 7.500 | 47.500 |
| 2 | 5.775 | 53.275 |
| 3 | 2.197 | 55.472 |

It moves faster than gradient descent but **overshoots** $g^*\approx54.15$ before settling. The cost need not decrease at every step.

### 8.4 Newton's method

**Idea:** minimize the local quadratic model $\varphi(g_k)+\varphi'(g_k)p+\tfrac12\varphi''(g_k)p^2$. Setting its derivative to zero gives

$$g_{k+1}=P\left(g_k-t_k\frac{\varphi'(g_k)}{\varphi''(g_k)}\right)$$

with damping $t_k\in(0,1]$ chosen by line search.

From $g_0=40$: $g_1=40+15/1.06\approx54.1509$. **Exact in one step**, because the function is quadratic there.

From $g_0=20$, where $Q_2=0$:

| $k$ | $g_k$ | $\varphi'$ | $\varphi''$ | full step result |
|---|---|---|---|---|
| 0 | 20 | −30.2 | 0.56 | 73.93, projected to 70 |
| 1 | 70 | 16.8 | 1.06 | 54.15 |
| 2 | 54.15 | 0 | — | converged |

The first step is poor because the quadratic piece changed at $g=32$, but the cost still falls (891 to about 442). In general, undamped Newton can fail on piecewise quadratics, which is why the line search is kept. In $n$ dimensions, solve $\nabla^2f(x_k)\,p_k=-\nabla f(x_k)$.

### 8.5 BFGS (quasi-Newton)

**Idea:** build an approximation $H_k$ of the inverse Hessian from observed gradient changes. With $s_k=x_{k+1}-x_k$, $y_k=\nabla f_{k+1}-\nabla f_k$ and $\rho_k=1/(y_k^Ts_k)$:

$$H_{k+1}=(I-\rho_ks_ky_k^T)\,H_k\,(I-\rho_ky_ks_k^T)+\rho_ks_ks_k^T$$

It satisfies the **secant condition** $H_{k+1}y_k=s_k$. $H_{k+1}$ stays positive definite if $H_k$ is and $y_k^Ts_k>0$; otherwise skip the update. The step is $x_{k+1}=x_k-t_kH_k\nabla f_k$.

**In one dimension** the formula collapses to $H_{k+1}=s_k/y_k$, the secant method.

With $H_0=0.5$, $t=1$: $g_1=47.5$. Then $s_0=7.5$, $y_0=-7.05-(-15)=7.95$, $H_1=7.5/7.95\approx0.9434=1/1.06$. So $g_2=47.5+0.9434(7.05)\approx54.1509$.

### 8.6 Conjugate gradient

**Idea:** choose directions that do not undo earlier progress. For a quadratic $\tfrac12x^TAx-b^Tx$, directions are **conjugate** if $d_i^TAd_j=0$, and exact minimization along $n$ of them solves the problem in at most $n$ steps (in exact arithmetic).

Nonlinear Polak–Ribière+ form, with $r_k=\nabla f(x_k)$:

$$d_0=-r_0, \qquad x_{k+1}=x_k+\alpha_kd_k$$

$$\beta_{k+1}=\max\left(0,\frac{r_{k+1}^T(r_{k+1}-r_k)}{r_k^Tr_k}\right), \qquad d_{k+1}=-r_{k+1}+\beta_{k+1}d_k$$

($\beta_{k}$ here is the CG coefficient, not the red-time weight.) $\alpha_k$ comes from a line search; for a quadratic, $\alpha_k=-r_k^Td_k/(d_k^TAd_k)$. Restart with $d=-r$ every $n$ steps, when $d$ is not a descent direction, or when a bound becomes active.

**In one dimension** there is only one direction, so one exact line search solves a quadratic. Study CG on the 2-D form in §11.

---

## 9. Nonsmooth objective and subgradient method

### Objective

$$J_{ns}=\sum_iw_i\max(0,a_i)+\beta\sum_i\lambda_i(C-g_i)^2$$

Now each queue term has a **kink** at $a_i=0$: the slope jumps from $-w_i\mu_i$ to $0$.

### Subgradient

$v$ is a subgradient of a convex $f$ at $x$ if

$$f(y)\ge f(x)+v^T(y-x)\quad\text{for all }y$$

The set of all subgradients is $\partial f(x)$. For this problem:

$$v_i=-w_i\mu_i\theta_i-2\beta\lambda_i(C-g_i), \qquad \theta_i\begin{cases}=1&a_i>0\\\in[0,1]&a_i=0\\=0&a_i<0\end{cases}$$

The reduced subgradient is $v=v_1-v_2$. On an interval, $g^*$ is optimal if some subgradient satisfies $g^*=P(g^*-v)$; in the interior this means $0\in\partial\varphi_{ns}(g^*)$.

### Case C: optimum on a kink, $q=(20,1)$

- $a_1=38-0.5g$, zero at $g=76$ (outside the interval).
- $a_2=-30+0.5g$, zero at $g=60$.

$$\varphi_{ns}'(g)=\begin{cases}-3.9+0.06g&g<60\\-3.4+0.06g&g>60\end{cases}$$

At $g=60$, $\partial\varphi_{ns}=[-0.3,\;0.2]$, which contains $0$. So $g^*=60$ and $J_{ns}^*=75$, although the derivative is never zero.

### Method

$$g_{k+1}=P(g_k-\alpha_kv_k), \qquad \alpha_k=\frac{\alpha_0}{\sqrt{k+1}}$$

With $\alpha_0=10$:

| $k$ | $g_k$ | $v_k$ | $\alpha_k$ |
|---|---|---|---|
| 0 | 40.000 | −1.500 | 10.000 |
| 1 | 55.000 | −0.600 | 7.071 |
| 2 | 59.243 | −0.345 | 5.774 |
| 3 | 61.237 | +0.274 | 5.000 |
| 4 | 59.866 | −0.308 | 4.472 |
| 5 | 61.244 | | |

The iterates **oscillate** around 60 because $v$ does not shrink to zero. Only the shrinking step size makes them settle. A step need not reduce the cost, so keep the **best value found**.

### Guarantee

With $R=|g_0-g^*|$ and $|v_k|\le M$:

$$\min_{j\le k}\varphi_{ns}(g_j)-\varphi_{ns}^*\le\frac{R^2+M^2\sum_{j\le k}\alpha_j^2}{2\sum_{j\le k}\alpha_j}$$

The bound tends to zero if $\alpha_j\to0$ and $\sum\alpha_j=\infty$. For $\alpha_j\propto1/\sqrt{j+1}$ it decays like $\log k/\sqrt k$, much slower than the smooth methods.

---

## 10. Stochastic objective and SGD

Real arrivals are random. Let $A_i\sim\text{Poisson}(\lambda_iC)$ and minimize the **expected** cost:

$$F(g)=\mathbb E\left[\sum_iw_i\max(0,q_i+A_i-\mu_ig_i)^2\right]+\beta\sum_i\lambda_i(C-g_i)^2$$

**Stochastic gradient.** Draw a mini-batch of $B$ samples and average:

$$\hat\nabla_i=-\frac{2w_i\mu_i}{B}\sum_{b=1}^{B}\max\big(0,q_i+A_i^{(b)}-\mu_ig_i\big)-2\beta\lambda_i(C-g_i)$$

Because the sample cost is $C^1$ with an integrable derivative bound, $\mathbb E[\hat\nabla_i]=\partial F/\partial g_i$: the estimate is **unbiased**.

$$g_{k+1}=P\big(g_k-\alpha_k(\hat\nabla_1-\hat\nabla_2)\big), \qquad \alpha_k=\frac{\alpha_0}{(1+k)^p},\;\;p\in(0.5,1]$$

These steps satisfy $\sum\alpha_k=\infty$ (can travel far enough) and $\sum\alpha_k^2<\infty$ (noise dies out). A larger batch gives lower variance but costs more per step.

**Why the answer differs from the deterministic one.** By Jensen's inequality, for convex $h$, $\mathbb E[h(a+\varepsilon)]\ge h(a)$ when $\mathbb E[\varepsilon]=0$. So $F\ge J$, and the minimizers can differ, mainly when a queue is near zero.

---

## 11. Penalty formulation and conditioning

Replace the equality constraint with a penalty, giving a true 2-D problem:

$$P_\rho(g_1,g_2)=J(g_1,g_2)+\frac\rho2(g_1+g_2-G)^2$$

$$\nabla P_\rho=\begin{bmatrix}\partial J/\partial g_1+\rho r\\\partial J/\partial g_2+\rho r\end{bmatrix}, \qquad \nabla^2P_\rho=\begin{bmatrix}d_1+\rho&\rho\\\rho&d_2+\rho\end{bmatrix}, \qquad r=g_1+g_2-G$$

### Closed-form solution for case B

With both queues positive and no bound active, setting $\nabla P_\rho=0$ gives

$$g_1=\frac{21.632+57.4\rho}{0.2808+1.06\rho}, \qquad g_2=\frac{13.932+27.4\rho}{0.2808+1.06\rho}$$

| $\rho$ | $g_1$ | $g_2$ | violation $r$ | condition number $\kappa$ |
|---|---|---|---|---|
| 1 | 58.944 | 30.826 | 9.770 | 4.8 |
| 10 | 54.742 | 26.462 | 1.204 | 38.7 |
| 100 | 54.211 | 25.912 | 0.123 | 378 |
| $\to\infty$ | 54.151 | 25.849 | 0 | $\to\infty$ |

**The trade-off:** larger $\rho$ satisfies the constraint better but makes the problem **ill-conditioned**. Also $\rho r\to\nu\approx12.36$, so the penalty recovers the KKT multiplier.

### Effect on the algorithms

$\kappa=\lambda_{max}/\lambda_{min}$ measures how stretched the contour ellipses are.

- Gradient descent with $\alpha=1/L$ needs a number of iterations roughly proportional to $\kappa$ and zig-zags.
- Momentum with well-chosen parameters scales roughly with $\sqrt\kappa$ on quadratics.
- Newton solves a single quadratic piece in one step regardless of $\kappa$.
- CG with exact line search needs at most 2 steps on a 2-D quadratic.
- BFGS with exact line search also finishes in 2 steps on a 2-D quadratic.

---

## 12. Numerical error analysis

### Gradient check

$$D_h=\frac{J(g+he_i)-J(g-he_i)}{2h}$$

| Error source | Size |
|---|---|
| Truncation, within one quadratic piece | zero in exact arithmetic ($J$ is quadratic) |
| Truncation, straddling a queue kink | $O(h)$ |
| Truncation, general smooth function | $O(h^2)$ |
| Rounding | $O(\epsilon\lvert J\rvert/h)$, with $\epsilon\approx2.2\times10^{-16}$ |

For general smooth functions the best $h$ is near $\epsilon^{1/3}\approx6\times10^{-6}$ (times the variable's scale). Compare with the relative error $\lvert D_h-\text{exact}\rvert/\max(1,\lvert\text{exact}\rvert)$.

### Integer rounding

Signals use whole seconds. Near an interior optimum inside one quadratic piece, an error $\delta$ costs $\tfrac12\varphi''\delta^2$. With $\delta\le0.5$ this is at most about $0.13$. Case B rounds to $g=54$, costing about $0.012$.

### Reference solution

Check every solver against a fine grid on $[\ell,u]$, or against bisection on $\varphi'$, which halves the interval each step: after $k$ steps the error is at most $(u-\ell)/2^{k+1}$ at the midpoint.

---

## 13. Convergence summary

| Method | Uses | Typical rate | Assumptions | Cost per step ($n$ variables) |
|---|---|---|---|---|
| Gradient / projected GD | gradient | linear | strongly convex, Lipschitz gradient | $O(n)$ |
| Momentum | gradient | faster linear on quadratics | tuned parameters; no general guarantee for all convex problems | $O(n)$ |
| Newton | gradient, Hessian | quadratic near solution | smooth, positive-definite Hessian | $O(n^3)$ |
| BFGS | gradient | superlinear | smooth, suitable line search | $O(n^2)$ |
| Conjugate gradient | gradient | at most $n$ steps on quadratics | exact line search for that property | $O(n)$ |
| Subgradient | subgradient | $O(1/\sqrt k)$ in best value | convex, diminishing step | $O(n)$ |
| SGD | sampled gradient | sublinear | unbiased, bounded-variance gradient | $O(nB)$ |

Costs exclude function and gradient evaluation. $J$ is piecewise quadratic, so the textbook smooth-Newton theory applies only within one piece.

---

## 14. Assumptions and limitations

- Arrivals are spread over the cycle; their exact timing is ignored.
- Discharge is constant during green.
- Only the next cycle is considered.
- The cycle length is fixed.
- The red-time term is a proxy for delay.
- A lower $J$ does not by itself prove better traffic; the SUMO measurements test that.

---

## 15. Questions you may be asked

**Why optimization instead of a formula?** This two-phase case can be solved almost directly. It is used because every algorithm can be checked against a known answer, and the same solvers extend to more variables.

**Why is $\max(0,a)^2$ differentiable but $\max(0,a)$ not?** Squaring makes the slope tend to zero from both sides at $a=0$.

**Why can't you test $\varphi'=0$ for convergence?** On a bound the optimal derivative is generally not zero (case A: $-8.2$).

**What does the multiplier $\nu$ mean?** The marginal value of one more second of green budget.

**Why does Newton converge so fast here?** The function is quadratic on each piece, so the quadratic model is exact there.

**Why is the subgradient method slow?** The subgradient does not vanish near a kink, so progress depends on shrinking the step.

---

## 16. Optional extension: several cycles

*Not part of the current PRD.* Plan $H$ cycles together, with $g_k$ the North–South green in cycle $k$:

$$q_{i,k+1}=\max(0,\;q_{i,k}+\lambda_iC-\mu_ig_{i,k})$$

$$J_H=\sum_{k=1}^{H}\sum_i\left[w_iq_{i,k+1}^2+\beta\lambda_i(C-g_{i,k})^2\right], \qquad g_{1,k}=g_k,\;\;g_{2,k}=G-g_k$$

- There are $H$ coupled variables, so BFGS and CG become meaningful.
- **Convex:** each queue is the maximum of zero and a convex expression, and $t\mapsto\max(0,t)^2$ is convex and non-decreasing.
- **Not smooth in general:** if an earlier queue reaches zero while a later one stays positive, the gradient jumps. Gradient-based methods then need smoothing or a subgradient approach.
