"""Milestone M1: numerical checks of the formulation in docs/.

This is a check tool, not the project implementation. J and J_ns are written
directly from PRD sections 5 and 6; derived formulas and the numbers quoted in
the documents are tested against them.

Run:  python verification/m1_checks.py
Exit status is non-zero if any check fails.

Phase order is (NS, EW). Units: queue veh, arrival rate veh/s, time s.
"""

from __future__ import annotations

import math
import sys

import numpy as np

# Parameters of all worked examples (Technical Design section 5.5).
C, G = 90.0, 80.0
G_MIN, G_MAX = 10.0, 70.0
MU = np.array([1800.0, 1800.0]) / 3600.0
LAM = np.array([0.2, 0.1])
W = np.array([1.0, 1.0])
BETA = 0.1
LO, HI = max(G_MIN, G - G_MAX), min(G_MAX, G - G_MIN)

CASE_A = np.array([40.0, 10.0])
CASE_B = np.array([20.0, 15.0])
CASE_C = np.array([20.0, 1.0])
B_STAR = 57.4 / 1.06

SEED = 2026
results: list[tuple[str, str, bool, str]] = []


def check(area: str, name: str, passed: bool, detail: str = "") -> None:
    results.append((area, name, bool(passed), detail))


def quoted(area: str, name: str, computed: float, document: float, decimals: int) -> None:
    """A number printed in a document must match to half a unit of its last digit."""
    tol = 0.5 * 10.0 ** (-decimals) + 1e-9
    check(area, name, abs(computed - document) <= tol,
          f"computed {computed:.6f}, document {document}")


# ---------------------------------------------------------------- definitions
def raw_queue(q, g, lam=LAM):
    return q + lam * C - MU * g


def J(q, g, beta=BETA, lam=LAM):
    queue = np.maximum(0.0, raw_queue(q, g, lam))
    return float(np.sum(W * queue**2) + beta * np.sum(lam * (C - g) ** 2))


def J_ns(q, g, beta=BETA, lam=LAM):
    queue = np.maximum(0.0, raw_queue(q, g, lam))
    return float(np.sum(W * queue) + beta * np.sum(lam * (C - g) ** 2))


# ---------------------------------------------------------- derived formulas
def grad(q, g, beta=BETA, lam=LAM):
    queue = np.maximum(0.0, raw_queue(q, g, lam))
    return -2 * W * MU * queue - 2 * beta * lam * (C - g)


def hess_diag(q, g, beta=BETA, lam=LAM):
    return 2 * W * MU**2 * (raw_queue(q, g, lam) > 0) + 2 * beta * lam


def subgrad(q, g, theta_at_kink=0.0, beta=BETA, lam=LAM):
    a = raw_queue(q, g, lam)
    theta = np.where(a > 0, 1.0, np.where(a < 0, 0.0, theta_at_kink))
    return -W * MU * theta - 2 * beta * lam * (C - g)


def split(x, total=G):
    return np.array([x, total - x])


def phi(q, x, total=G, **kw):
    return J(q, split(x, total), **kw)


def dphi(q, x, total=G, **kw):
    d = grad(q, split(x, total), **kw)
    return float(d[0] - d[1])


def phi_ns(q, x):
    return J_ns(q, split(x))


def v_ns(q, x):
    v = subgrad(q, split(x))
    return float(v[0] - v[1])


def clip(x, lo=LO, hi=HI):
    return min(hi, max(lo, x))


def argmin_1d(f, lo, hi, passes=4, n=2001):
    """Dense grid, repeatedly refined around the best point (f is convex)."""
    for _ in range(passes):
        xs = np.linspace(lo, hi, n)
        vals = [f(x) for x in xs]
        i = int(np.argmin(vals))
        lo, hi = xs[max(i - 1, 0)], xs[min(i + 1, n - 1)]
    return float(xs[i]), float(vals[i])


def central(f, x, h):
    out = np.zeros_like(x)
    for i in range(len(x)):
        e = np.zeros_like(x)
        e[i] = h
        out[i] = (f(x + e) - f(x - e)) / (2 * h)
    return out


def random_states(rng, n, min_kink_distance=0.0):
    found = 0
    while found < n:
        q = rng.uniform(0, 50, 2)
        lam = rng.uniform(0.01, 0.4, 2)
        g = rng.uniform(G_MIN, G_MAX, 2)
        if np.all(np.abs(raw_queue(q, g, lam)) > min_kink_distance):
            found += 1
            yield q, lam, g


# --------------------------------------------------------------------- checks
def check_derivatives(rng):
    area = "Derivatives"
    worst = {"J": 0.0, "Jns": 0.0, "H": 0.0, "dphi": 0.0, "d2phi": 0.0}

    def rel(approx, exact):
        return float(np.max(np.abs(approx - exact) / np.maximum(1.0, np.abs(exact))))

    for q, lam, g in random_states(rng, 500, min_kink_distance=0.01):
        kw = dict(lam=lam)
        worst["J"] = max(worst["J"], rel(central(lambda x: J(q, x, **kw), g, 1e-5), grad(q, g, **kw)))
        worst["Jns"] = max(worst["Jns"], rel(central(lambda x: J_ns(q, x, **kw), g, 1e-5), subgrad(q, g, **kw)))
        numeric_h = np.array([central(lambda x, i=i: grad(q, x, **kw)[i], g, 1e-5) for i in range(2)])
        worst["H"] = max(worst["H"], rel(numeric_h, np.diag(hess_diag(q, g, **kw))))
        x = g[0]
        if np.all(np.abs(raw_queue(q, split(x), lam)) > 0.01):
            d1 = (phi(q, x + 1e-5, **kw) - phi(q, x - 1e-5, **kw)) / 2e-5
            d2 = (dphi(q, x + 1e-5, **kw) - dphi(q, x - 1e-5, **kw)) / 2e-5
            worst["dphi"] = max(worst["dphi"], rel(np.array(d1), np.array(dphi(q, x, **kw))))
            exact = np.sum(hess_diag(q, split(x), **kw))
            worst["d2phi"] = max(worst["d2phi"], rel(np.array(d2), np.array(exact)))
    labels = {"J": "gradient of J", "Jns": "gradient of J_ns away from kinks",
              "H": "Hessian of J", "dphi": "reduced first derivative",
              "d2phi": "reduced second derivative"}
    for key, label in labels.items():
        check(area, label, worst[key] < 1e-6, f"max relative error {worst[key]:.1e} (limit 1e-6)")


def check_smoothness(rng):
    area = "Smoothness (D1)"
    h = 1e-7
    worst_jump, smallest_ns_jump = 0.0, math.inf
    for _ in range(200):
        lam = rng.uniform(0.01, 0.4, 2)
        q = rng.uniform(0, 20, 2)
        g = rng.uniform(G_MIN, G_MAX, 2)
        q[0] = MU[0] * g[0] - lam[0] * C  # put approach 1 exactly on its kink
        e = np.array([h, 0.0])
        for f, is_ns in ((J, False), (J_ns, True)):
            left = (f(q, g, lam=lam) - f(q, g - e, lam=lam)) / h
            right = (f(q, g + e, lam=lam) - f(q, g, lam=lam)) / h
            if is_ns:
                smallest_ns_jump = min(smallest_ns_jump, right - left)
            else:
                worst_jump = max(worst_jump, abs(right - left))
    check(area, "J one-sided slopes agree at kinks", worst_jump < 1e-5, f"largest gap {worst_jump:.1e}")
    check(area, "J_ns slopes jump by w*mu at kinks", abs(smallest_ns_jump - 0.5) < 1e-5,
          f"smallest jump {smallest_ns_jump:.6f}, expected 0.5")
    second = (hess_diag(CASE_B, split(31.999))[1], hess_diag(CASE_B, split(32.001))[1])
    check(area, "second derivative of J jumps", abs(second[1] - second[0] - 0.5) < 1e-12,
          f"values {second[0]:.3f} and {second[1]:.3f}")


def check_inequalities(rng):
    area = "Subgradient and convexity"
    worst_sub = worst_convex = worst_lip = worst_strong = 0.0
    for q, lam, x in random_states(rng, 4000):
        y = rng.uniform(G_MIN, G_MAX, 2)
        if rng.random() < 0.5:  # force a kink at x on one approach
            i = rng.integers(2)
            q = q.copy()
            q[i] = MU[i] * x[i] - lam[i] * C
        theta = rng.random()
        gap = J_ns(q, x, lam=lam) + subgrad(q, x, theta, lam=lam) @ (y - x) - J_ns(q, y, lam=lam)
        worst_sub = max(worst_sub, gap)
        t = rng.random()
        for f in (J, J_ns):
            mid = f(q, t * x + (1 - t) * y, lam=lam)
            worst_convex = max(worst_convex, mid - t * f(q, x, lam=lam) - (1 - t) * f(q, y, lam=lam))
        a, b = x[0], y[0]
        diff = abs(dphi(q, a, lam=lam) - dphi(q, b, lam=lam))
        L = float(np.sum(2 * W * MU**2 + 2 * BETA * lam))
        m = float(2 * BETA * np.sum(lam))
        worst_lip = max(worst_lip, diff - L * abs(a - b))
        worst_strong = max(worst_strong, m * abs(a - b) - diff)
    check(area, "subgradient inequality, including kinks", worst_sub <= 1e-8, f"largest violation {worst_sub:.1e}")
    check(area, "J and J_ns convex", worst_convex <= 1e-8, f"largest violation {worst_convex:.1e}")
    check(area, "Lipschitz bound on reduced derivative", worst_lip <= 1e-8, f"largest violation {worst_lip:.1e}")
    check(area, "strong convexity bound", worst_strong <= 1e-8, f"largest violation {worst_strong:.1e}")
    quoted(area, "L_phi in examples", float(np.sum(2 * W * MU**2 + 2 * BETA * LAM)), 1.06, 2)
    quoted(area, "m in examples", float(2 * BETA * np.sum(LAM)), 0.06, 2)


def check_projection(rng):
    area = "Projection"
    ok_feasible = ok_idem = True
    worst_1d = worst_2d = 0.0
    for _ in range(500):
        lo_b, hi_b = sorted(rng.uniform(5, 75, 2))
        total = rng.uniform(2 * lo_b, 2 * hi_b)
        lo, hi = max(lo_b, total - hi_b), min(hi_b, total - lo_b)
        y = rng.uniform(-50, 150, 2)
        p = clip(y[0], lo, hi)
        g = split(p, total)
        ok_feasible &= bool(np.all(g >= lo_b - 1e-9) and np.all(g <= hi_b + 1e-9)
                            and abs(g.sum() - total) < 1e-9)
        ok_idem &= clip(p, lo, hi) == p
        xs = np.linspace(lo, hi, 4001)
        step = (hi - lo) / 4000
        worst_1d = max(worst_1d, abs(xs[np.argmin((xs - y[0]) ** 2)] - p) - step)
        nearest = xs[np.argmin((xs - y[0]) ** 2 + (total - xs - y[1]) ** 2)]
        worst_2d = max(worst_2d, abs(nearest - clip((y[0] - y[1] + total) / 2, lo, hi)) - step)
    check(area, "result satisfies bounds and budget", ok_feasible)
    check(area, "idempotent", ok_idem)
    check(area, "1-D clip is the nearest point", worst_1d <= 1e-9, "compared with dense grid")
    check(area, "2-D formula P((y1-y2+G)/2) is the nearest point", worst_2d <= 1e-9, "compared with dense grid")


def check_cases():
    area = "Reference cases"
    g40 = split(40.0)
    quoted(area, "A: J(40,40)", J(CASE_A, g40), 1519, 0)
    quoted(area, "A: dJ/dg1", grad(CASE_A, g40)[0], -40, 0)
    quoted(area, "A: dJ/dg2", grad(CASE_A, g40)[1], -1, 0)
    quoted(area, "A: reduced derivative", dphi(CASE_A, 40), -39, 0)
    x, val = argmin_1d(lambda s: phi(CASE_A, s), LO, HI)
    quoted(area, "A: optimal g_NS", x, 70, 4)
    quoted(area, "A: J*", val, 797, 3)
    quoted(area, "B: J(40,40)", J(CASE_B, g40), 415, 0)
    quoted(area, "B: reduced derivative at 40", dphi(CASE_B, 40), -15, 0)
    x, val = argmin_1d(lambda s: phi(CASE_B, s), LO, HI)
    quoted(area, "B: optimal g_NS", x, 54.1509, 4)
    check(area, "B: g* equals 57.4/1.06", abs(x - B_STAR) < 1e-5, f"difference {abs(x - B_STAR):.1e}")
    quoted(area, "B: J*", val, 308.868, 3)
    queue = raw_queue(CASE_B, split(x))
    quoted(area, "B: queue NS", queue[0], 10.92, 2)
    quoted(area, "B: queue EW", queue[1], 11.08, 2)
    quoted(area, "C: J_ns at 40", phi_ns(CASE_C, 40), 93, 0)
    quoted(area, "C: subgradient at 40", v_ns(CASE_C, 40), -1.5, 1)
    x, val = argmin_1d(lambda s: phi_ns(CASE_C, s), LO, HI)
    quoted(area, "C: optimal g_NS", x, 60, 4)
    quoted(area, "C: J_ns*", val, 75, 4)
    h = 1e-7
    quoted(area, "C: left slope", (phi_ns(CASE_C, 60) - phi_ns(CASE_C, 60 - h)) / h, -0.3, 4)
    quoted(area, "C: right slope", (phi_ns(CASE_C, 60 + h) - phi_ns(CASE_C, 60)) / h, 0.2, 4)


def check_kkt_and_beta():
    area = "KKT and beta"
    d = grad(CASE_B, split(B_STAR))
    check(area, "B: stationarity gives one multiplier", abs(d[0] - d[1]) < 1e-9, f"gradient {d.round(6)}")
    quoted(area, "B: multiplier nu", -d[0], 12.36, 2)
    h = 1e-3
    values = [argmin_1d(lambda s, t=t: phi(CASE_B, s, total=t), LO, HI)[1] for t in (G - h, G + h)]
    shadow = -(values[1] - values[0]) / (2 * h)
    check(area, "B: nu equals the value of one more second of budget", abs(shadow + d[0]) < 1e-3,
          f"perturbation {shadow:.5f}, multiplier {-d[0]:.5f}")
    d = grad(CASE_A, split(70.0))
    quoted(area, "A: dJ/dg1 at optimum", d[0], -23.8, 1)
    quoted(area, "A: dJ/dg2 at optimum", d[1], -15.6, 1)
    quoted(area, "A: reduced derivative at optimum", dphi(CASE_A, 70), -8.2, 1)
    feasible = [nu for nu in np.linspace(0, 40, 4001)
                if (-d[0] - nu) >= -1e-9 and (d[1] + nu) >= -1e-9]  # zeta1, eta2 >= 0
    quoted(area, "A: smallest valid nu", min(feasible), 15.6, 1)
    quoted(area, "A: largest valid nu", max(feasible), 23.8, 1)
    for beta, expected in ((0.0, 54.0), (0.1, 54.15), (1.0, 55.0)):
        x, _ = argmin_1d(lambda s, b=beta: phi(CASE_B, s, beta=b), LO, HI)
        formula = (54 + 34 * beta) / (1 + 0.6 * beta)
        check(area, f"g*(beta={beta}) formula matches grid", abs(x - formula) < 1e-5, f"grid {x:.6f}")
        quoted(area, f"g*(beta={beta}) quoted value", x, expected, 2)


def check_iterations():
    area = "Worked iterations"
    # Gradient descent, section 8.1
    x = 40.0
    table = [(40.000, -15.000, 14.151), (47.500, -7.050, 6.651),
             (51.025, -3.314, 3.126), (52.682, -1.557, 1.469)]
    for k, (gk, dk, ek) in enumerate(table):
        quoted(area, f"GD k={k} g", x, gk, 3)
        quoted(area, f"GD k={k} derivative", dphi(CASE_B, x), dk, 3)
        quoted(area, f"GD k={k} error", abs(x - B_STAR), ek, 3)
        x -= 0.5 * dphi(CASE_B, x)
    quoted(area, "GD step-size limit 2/L", 2 / 1.06, 1.887, 3)
    # Projected gradient, section 8.2
    x = clip(40 - dphi(CASE_A, 40) / 1.06)
    quoted(area, "PGD trial point", 40 - dphi(CASE_A, 40) / 1.06, 76.79, 2)
    check(area, "PGD converges in one step",
          x == 70 and abs(x - clip(x - dphi(CASE_A, x))) == 0)
    # Momentum, section 8.3
    x, v = 40.0, 0.0
    for k, (vk, gk) in enumerate([(7.500, 47.500), (5.775, 53.275), (2.197, 55.472)], 1):
        v = 0.3 * v - 0.5 * dphi(CASE_B, x)
        x = clip(x + v)
        quoted(area, f"momentum k={k} velocity", v, vk, 3)
        quoted(area, f"momentum k={k} g", x, gk, 3)
    # Newton, section 8.4
    d2 = lambda s: float(np.sum(hess_diag(CASE_B, split(s))))
    quoted(area, "Newton from 40", 40 - dphi(CASE_B, 40) / d2(40), 54.1509, 4)
    quoted(area, "Newton 20: derivative", dphi(CASE_B, 20), -30.2, 1)
    quoted(area, "Newton 20: second derivative", d2(20), 0.56, 2)
    full = 20 - dphi(CASE_B, 20) / d2(20)
    quoted(area, "Newton 20: full step", full, 73.93, 2)
    quoted(area, "Newton 70: derivative", dphi(CASE_B, 70), 16.8, 1)
    quoted(area, "Newton 70: second derivative", d2(70), 1.06, 2)
    quoted(area, "Newton 70: next point", 70 - dphi(CASE_B, 70) / d2(70), 54.15, 2)
    quoted(area, "Newton: cost at 20", phi(CASE_B, 20), 891, 0)
    quoted(area, "Newton: cost at 70", phi(CASE_B, 70), 442, 0)
    # BFGS, section 8.5
    x1 = 40 - 0.5 * dphi(CASE_B, 40)
    s, y = x1 - 40, dphi(CASE_B, x1) - dphi(CASE_B, 40)
    quoted(area, "BFGS s0", s, 7.5, 1)
    quoted(area, "BFGS y0", y, 7.95, 2)
    quoted(area, "BFGS H1", s / y, 0.9434, 4)
    quoted(area, "BFGS g2", x1 - s / y * dphi(CASE_B, x1), 54.1509, 4)
    # Subgradient, section 9
    x = 40.0
    table = [(40.000, -1.500, 10.000), (55.000, -0.600, 7.071), (59.243, -0.345, 5.774),
             (61.237, 0.274, 5.000), (59.866, -0.308, 4.472)]
    start_distance, best, steps, norms = 20.0, math.inf, [], []
    bound_holds = True
    for k, (gk, vk, ak) in enumerate(table):
        alpha, v = 10 / math.sqrt(k + 1), v_ns(CASE_C, x)
        quoted(area, f"subgradient k={k} g", x, gk, 3)
        quoted(area, f"subgradient k={k} v", v, vk, 3)
        quoted(area, f"subgradient k={k} step", alpha, ak, 3)
        best, steps, norms = min(best, phi_ns(CASE_C, x)), steps + [alpha], norms + [abs(v)]
        bound = (start_distance**2 + max(norms) ** 2 * sum(a * a for a in steps)) / (2 * sum(steps))
        bound_holds &= best - 75 <= bound
        x = clip(x - alpha * v)
    quoted(area, "subgradient k=5 g", x, 61.244, 3)
    check(area, "subgradient error bound holds", bound_holds)


def penalty(rho, q=CASE_B):
    gradient = lambda g: grad(q, g) + rho * (g.sum() - G)
    hessian = lambda g: np.diag(hess_diag(q, g)) + rho
    return gradient, hessian


def check_penalty():
    area = "Penalty form (D2)"
    table = {1: (58.944, 30.826, 9.770, 4.8, 1), 10: (54.742, 26.462, 1.204, 38.7, 1),
             100: (54.211, 25.912, 0.123, 378, 0)}
    gd_counts, conditions = [], []
    for rho, (g1, g2, r, kappa, kd) in table.items():
        gradient, hessian = penalty(rho)
        start = np.array([40.0, 40.0])
        newton = start - np.linalg.solve(hessian(start), gradient(start))
        check(area, f"rho={rho}: Newton solves in one step inside bounds",
              np.linalg.norm(gradient(newton)) < 1e-8 and np.all((newton >= G_MIN) & (newton <= G_MAX)))
        den = 0.2808 + 1.06 * rho
        closed = np.array([21.632 + 57.4 * rho, 13.932 + 27.4 * rho]) / den
        check(area, f"rho={rho}: closed form matches", np.allclose(closed, newton, atol=1e-8))
        quoted(area, f"rho={rho}: g1", newton[0], g1, 3)
        quoted(area, f"rho={rho}: g2", newton[1], g2, 3)
        quoted(area, f"rho={rho}: violation", newton.sum() - G, r, 3)
        ev = np.linalg.eigvalsh(hessian(newton))
        conditions.append(ev[-1] / ev[0])
        quoted(area, f"rho={rho}: condition number", conditions[-1], kappa, kd)

        def exact_step(x, d):
            return -(gradient(x) @ d) / (d @ hessian(x) @ d)

        for method in ("CG", "BFGS"):
            x, H = start.copy(), np.eye(2)
            r0 = gradient(x)
            d = -r0
            for _ in range(2):
                alpha = exact_step(x, d)
                x_new = x + alpha * d
                r1 = gradient(x_new)
                if method == "CG":
                    d = -r1 + max(0.0, r1 @ (r1 - r0) / (r0 @ r0)) * d
                else:
                    s, y = x_new - x, r1 - r0
                    c = 1 / (y @ s)
                    V = np.eye(2) - c * np.outer(s, y)
                    H = V @ H @ V.T + c * np.outer(s, s)
                    d = -H @ r1
                x, r0 = x_new, r1
            check(area, f"rho={rho}: {method} finishes in 2 exact steps",
                  np.linalg.norm(x - newton) < 1e-6, f"error {np.linalg.norm(x - newton):.1e}")

        x, count = start.copy(), 0
        while np.linalg.norm(x - newton) > 1e-6 and count < 100000:
            x = x - gradient(x) / ev[-1]
            count += 1
        gd_counts.append(count)
    ratios = [n / k for n, k in zip(gd_counts, conditions)]
    check(area, "gradient descent iterations grow with condition number",
          gd_counts == sorted(gd_counts) and max(ratios) / min(ratios) < 2,
          f"iterations {gd_counts} for rho 1, 10, 100")
    newton = np.linalg.solve(penalty(100)[1](split(54.0)),
                             -penalty(100)[0](split(54.0))) + split(54.0)
    nu = -grad(CASE_B, split(B_STAR))[0]
    check(area, "rho*r approaches nu", abs(100 * (newton.sum() - G) - nu) < 0.05,
          f"rho*r {100 * (newton.sum() - G):.4f}, nu {nu:.4f}")


def check_numerics_and_stochastic():
    area = "Numerics and stochastic"
    quoted(area, "rounding loss in case B", phi(CASE_B, 54) - phi(CASE_B, B_STAR), 0.012, 3)
    quoted(area, "worst rounding loss", 0.5 * 1.06 * 0.5**2, 0.13, 2)
    errors = []
    for h in (1e-2, 1e-3):  # straddle the EW kink at g_NS = 32
        x = 32 + h / 2
        errors.append(abs((phi(CASE_B, x + h) - phi(CASE_B, x - h)) / (2 * h) - dphi(CASE_B, x)))
    check(area, "central difference error is O(h) across a kink",
          8 < errors[0] / errors[1] < 12, f"error ratio {errors[0] / errors[1]:.2f} for h ratio 10")

    # Exact Poisson expectations (section 10), truncated far in the tail.
    def pmf(mean, n=150):
        p = np.empty(n)
        p[0] = math.exp(-mean)
        for k in range(1, n):
            p[k] = p[k - 1] * mean / k
        return p

    probs = [pmf(l * C) for l in LAM]
    arrivals = np.arange(150)

    def F(g):
        queue = sum(W[i] * probs[i] @ np.maximum(0, CASE_B[i] + arrivals - MU[i] * g[i]) ** 2
                    for i in range(2))
        return float(queue + BETA * np.sum(LAM * (C - g) ** 2))

    def expected_gradient(g):
        queue = np.array([probs[i] @ np.maximum(0, CASE_B[i] + arrivals - MU[i] * g[i]) for i in range(2)])
        return -2 * W * MU * queue - 2 * BETA * LAM * (C - g)

    points = [split(x) for x in np.linspace(LO + 0.3, HI - 0.3, 25)]
    worst = max(np.max(np.abs(central(F, g, 1e-5) - expected_gradient(g))) for g in points)
    check(area, "expected sample gradient equals gradient of F", worst < 1e-4, f"max error {worst:.1e}")
    check(area, "F is at least J (Jensen)", all(F(g) >= J(CASE_B, g) - 1e-9 for g in points))


def check_multicycle(rng):
    area = "Optional extension (section 16)"

    def J_H(g, q0, lam):
        q, total = q0.copy(), 0.0
        for x in g:
            green = split(x)
            q = np.maximum(0, q + lam * C - MU * green)
            total += np.sum(W * q**2) + BETA * np.sum(lam * (C - green) ** 2)
        return float(total)

    worst = 0.0
    for _ in range(2000):
        q0, lam = rng.uniform(0, 30, 2), rng.uniform(0.01, 0.4, 2)
        x, y, t = rng.uniform(LO, HI, 4), rng.uniform(LO, HI, 4), rng.random()
        worst = max(worst, J_H(t * x + (1 - t) * y, q0, lam)
                    - t * J_H(x, q0, lam) - (1 - t) * J_H(y, q0, lam))
    check(area, "multi-cycle objective convex", worst <= 1e-7, f"largest violation {worst:.1e}")
    # NS queue empties exactly after cycle 1 and refills in cycle 2.
    q0 = np.array([22.0, 0.0])  # 22 + 18 - 0.5*g1 = 0 at g1 = 80, so use g1 = 60
    q0[0] = 0.5 * 60 - 18
    g, h = np.array([60.0, 20.0]), 1e-7
    e = np.array([h, 0.0])
    left = (J_H(g, q0, LAM) - J_H(g - e, q0, LAM)) / h
    right = (J_H(g + e, q0, LAM) - J_H(g, q0, LAM)) / h
    check(area, "multi-cycle objective is not differentiable everywhere", abs(right - left) > 1,
          f"one-sided slopes {left:.3f} and {right:.3f}")


def main() -> int:
    rng = np.random.default_rng(SEED)
    check_derivatives(rng)
    check_smoothness(rng)
    check_inequalities(rng)
    check_projection(rng)
    check_cases()
    check_kkt_and_beta()
    check_iterations()
    check_penalty()
    check_numerics_and_stochastic()
    check_multicycle(rng)

    areas: dict[str, list[bool]] = {}
    for area, name, passed, detail in results:
        areas.setdefault(area, []).append(passed)
        print(f"{'PASS' if passed else 'FAIL'}  {area}: {name}" + (f"  [{detail}]" if detail else ""))
    print("\nSummary")
    for area, flags in areas.items():
        print(f"  {area}: {sum(flags)}/{len(flags)}")
    failed = sum(not r[2] for r in results)
    print(f"  total: {len(results) - failed}/{len(results)} passed (seed {SEED}, NumPy {np.__version__})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
