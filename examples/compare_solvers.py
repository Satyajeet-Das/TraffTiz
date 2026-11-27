"""Run every algorithm on the worked examples and print a comparison.

Run:  python examples/compare_solvers.py

A demonstration on single problem instances, not the experiment of milestone M9.
Run times depend on the machine.
"""

from __future__ import annotations

import numpy as np

from optitraffic.optimization.problems import PenaltyProblem, ReducedProblem, StochasticProblem
from optitraffic.optimization.solvers import (
    BFGS,
    SGD,
    ConjugateGradient,
    GradientDescent,
    Momentum,
    Newton,
    ProjectedGradient,
    Subgradient,
)
from optitraffic.optimization.solvers.oracle import minimize_bisection
from optitraffic.optimization.test_functions import Rosenbrock
from optitraffic.types import ObjectiveData

SMOOTH = (GradientDescent, ProjectedGradient, Momentum, Newton, BFGS, ConjugateGradient)
START = [40.0]


def data(queue):
    return ObjectiveData(queue, (0.2, 0.1), (0.5, 0.5), (1.0, 1.0), beta=0.1, cycle_s=90.0)


def header(title, columns):
    print(f"\n{title}\n  " + "".join(f"{c:>{w}}" for c, w in columns))


def reduced_table(title, problem, solvers):
    best = minimize_bisection(problem)
    header(f"{title}   (reference g_NS = {best.x:.4f}, value = {best.value:.4f})",
           [("solver", 20), ("g_NS", 10), ("error", 11), ("iter", 7), ("status", 13), ("ms", 9)])
    for solver in solvers:
        r = solver.solve(problem, START)
        print(f"  {solver.name:>20}{r.x[0]:10.4f}{abs(r.x[0] - best.x):11.1e}"
              f"{r.iterations:7d}{r.status:>13}{1000 * r.runtime_s:9.2f}")


def main() -> None:
    options = dict(max_iterations=500)
    for name, queue in (("A", (40, 10)), ("B", (20, 15))):
        reduced_table(f"Case {name}, smooth objective J, start g_NS = 40",
                      ReducedProblem(data(queue), 10, 70, 80), [s(**options) for s in SMOOTH])
    reduced_table("Case C, nonsmooth objective J_ns",
                  ReducedProblem(data((20, 1)), 10, 70, 80, nonsmooth=True),
                  [Subgradient(**options)])
    reduced_table("Case B, expected objective with random arrivals",
                  StochasticProblem(data((20, 15)), 10, 70, 80),
                  [SGD(seed=0, **options), SGD(seed=1, **options)])

    header("Case B, two-variable penalty form: iterations from (40, 40)",
           [("solver", 20), ("rho=1", 9), ("rho=10", 9), ("rho=100", 9)])
    for solver in SMOOTH:
        cells = []
        for rho in (1, 10, 100):
            problem = PenaltyProblem(data((20, 15)), 10, 70, 80, rho)
            r = solver(max_iterations=100_000).solve(problem, [40.0, 40.0])
            cells.append(f"{r.iterations if r.converged else r.status:>9}")
        print(f"  {solver.name:>20}" + "".join(cells))

    header("Rosenbrock function from (-1.2, 1)",
           [("solver", 20), ("iter", 9), ("status", 13), ("error", 11)])
    for solver in (ProjectedGradient, Newton, BFGS, ConjugateGradient):
        r = solver(max_iterations=50_000).solve(Rosenbrock(), [-1.2, 1.0])
        print(f"  {solver.name:>20}{r.iterations:9d}{r.status:>13}{np.linalg.norm(r.x - 1):11.1e}")


if __name__ == "__main__":
    main()
