"""Solver comparison, tracks T1 to T3 (Technical Design section 6.5).

T1: the one-variable control problem on states recorded from simulation.
T2: the two-variable penalty form as conditioning worsens.
T3: quadratics and the Rosenbrock function in higher dimensions.

Solvers run one at a time with no time budget, from the same starting point and
with the same tolerance. Run times depend on the machine. J, J_ns and the
expected objective have different minimisers; their results are listed
separately and their values are never compared.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from optitraffic.control.adaptive import round_green
from optitraffic.optimization import objective
from optitraffic.optimization.problems import PenaltyProblem, ReducedProblem, StochasticProblem
from optitraffic.optimization.solvers import (
    BFGS,
    SGD,
    ConjugateGradient,
    GradientDescent,
    Momentum,
    Newton,
    ProjectedGradient,
    Solver,
    Subgradient,
)
from optitraffic.optimization.solvers.oracle import minimize_bisection
from optitraffic.optimization.test_functions import Quadratic, Rosenbrock
from optitraffic.types import Config, ObjectiveData, SolverResult

SMOOTH: tuple[type[Solver], ...] = (
    GradientDescent, ProjectedGradient, Momentum, Newton, BFGS, ConjugateGradient,
)
State = tuple[float, float, float, float]  # queue NS, queue EW, rate NS, rate EW


def make_data(state: State, config: Config) -> ObjectiveData:
    return ObjectiveData.from_params(state[:2], state[2:], config.model, config.signal)


def sample(items: Sequence, count: int, seed: int) -> list:
    """A reproducible subset, in the original order."""
    if count >= len(items):
        return list(items)
    chosen = np.random.default_rng(seed).choice(len(items), size=count, replace=False)
    return [items[i] for i in sorted(chosen)]


# ------------------------------------------------------------------------- T1
def reduced_runs(states: Sequence[State], config: Config, settings: Mapping) -> pd.DataFrame:
    """One row per (problem, solver, state)."""
    s = config.signal
    limit = settings["max_iterations"]
    rows = []

    def record(problem_name, label, index, problem, oracle, result):
        x = float(result.x[0])
        low, high = oracle.minimiser_interval
        best_integer = min(
            (problem.value([g]), g)
            for g in range(int(problem.lower), int(problem.upper) + 1)
        )[0]
        chosen = problem.value([round_green(problem, result.x)[0]])
        rows.append({
            "problem": problem_name, "solver": label, "state": index,
            **_result_columns(result),
            "error_s": max(low - x, x - high, 0.0),
            "gap": result.objective - oracle.value,
            "integer_plan_optimal": bool(chosen <= best_integer + 1e-9 * max(1, abs(best_integer))),
        })

    def bounds(data, **kwargs):
        return ReducedProblem.from_signal(data, s, **kwargs)

    start = [s.green_budget_s / 2]
    for index, state in enumerate(states):
        data = make_data(state, config)
        smooth, nonsmooth = bounds(data), bounds(data, nonsmooth=True)
        oracle, oracle_ns = minimize_bisection(smooth), minimize_bisection(nonsmooth)
        for cls in (*SMOOTH, Subgradient):
            result = cls(max_iterations=limit).solve(smooth, start)
            record("J", cls.name, index, smooth, oracle, result)
        result = Subgradient(max_iterations=limit).solve(nonsmooth, start)
        record("J_ns", Subgradient.name, index, nonsmooth, oracle_ns, result)

    seed = settings["seed"]
    for index in sample(range(len(states)), settings["sgd_states"], seed):
        problem = StochasticProblem(
            make_data(states[index], config), s.g_min_s, s.g_max_s, s.green_budget_s
        )
        oracle = minimize_bisection(problem)
        for label, iterations in (
            (f"sgd ({config.solver.sgd_max_iterations} it.)", config.solver.sgd_max_iterations),
            (f"sgd ({limit} it.)", limit),
        ):
            result = SGD(max_iterations=iterations, seed=(seed, index)).solve(problem, start)
            record("expected J", label, index, problem, oracle, result)
    return pd.DataFrame(rows)


def convergence_curves(states: Sequence[State], config: Config, settings: Mapping) -> pd.DataFrame:
    """Median objective gap against iteration, over states where there is work to do.

    States are used if the minimiser is strictly inside the bounds and at least
    1 s from the starting point. A finished run keeps its last value.
    """
    s = config.signal
    start = s.green_budget_s / 2
    usable = []
    for state in states:
        problem = ReducedProblem.from_signal(make_data(state, config), s)
        best = minimize_bisection(problem)
        if problem.lower + 0.01 < best.x < problem.upper - 0.01 and abs(best.x - start) > 1:
            usable.append((problem, best.value))
    usable = sample(usable, settings["curve_states"], settings["seed"])
    limit = settings["max_iterations"]
    rows = []
    for cls in (*SMOOTH, Subgradient):
        gaps = np.empty((len(usable), limit + 1))
        for i, (problem, best) in enumerate(usable):
            history = np.array(cls(max_iterations=limit).solve(problem, [start]).history)
            gaps[i] = history[-1] - best
            gaps[i, : len(history)] = history - best
        median = np.median(np.maximum(gaps, 0.0), axis=0)
        rows += [
            {"solver": cls.name, "iteration": k, "median_gap": float(v), "states": len(usable)}
            for k, v in enumerate(median)
        ]
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------- T2
def penalty_runs(
    states: Sequence[State], config: Config, settings: Mapping
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Solver rows, and a grid check of the Newton reference solutions."""
    s = config.signal
    chosen = sample(states, settings["penalty_states"], settings["seed"])
    start = [s.green_budget_s / 2] * 2
    rows, checks = [], []
    for rho in settings["penalty_rho"]:
        for index, state in enumerate(chosen):
            problem = PenaltyProblem(
                make_data(state, config), s.g_min_s, s.g_max_s, s.green_budget_s, rho
            )
            reference = Newton(tolerance=1e-9, max_iterations=1000).solve(problem, start)
            if index < settings["penalty_grid_checks"]:
                checks.append(_grid_check(problem, reference, rho, index))
            for cls in SMOOTH:
                result = cls(max_iterations=settings["penalty_max_iterations"]).solve(problem, start)
                rows.append({
                    "rho": rho, "solver": cls.name, "state": index,
                    **_result_columns(result),
                    "gap": result.objective - reference.objective,
                    "violation_s": problem.violation(result.x),
                })
    return pd.DataFrame(rows), pd.DataFrame(checks)


def _grid_check(problem: PenaltyProblem, reference: SolverResult, rho, index, step=0.05) -> dict:
    axis = np.arange(problem.g_min, problem.g_max + step / 2, step)
    a, b = np.meshgrid(axis, axis)
    points = np.stack([a, b], axis=-1)
    values = objective.value(problem.data, points) + 0.5 * rho * (a + b - problem.budget) ** 2
    best = float(values.min())
    return {
        "rho": rho, "state": index, "reference": reference.objective, "grid_best": best,
        "reference_ok": bool(reference.converged and reference.objective <= best + 1e-9),
    }


# ------------------------------------------------------------------------- T3
def random_quadratic(n: int, condition: float, rng: np.random.Generator) -> Quadratic:
    basis, _ = np.linalg.qr(rng.normal(size=(n, n)))
    matrix = basis @ np.diag(np.geomspace(1, condition, n)) @ basis.T
    return Quadratic((matrix + matrix.T) / 2, rng.normal(size=n))


def benchmark_runs(settings: Mapping) -> pd.DataFrame:
    """Gradient descent and momentum need a Lipschitz constant, which the
    Rosenbrock function lacks globally; SGD needs sampled gradients. They are
    not run where they do not apply."""
    rows = []
    rng = np.random.default_rng(settings["seed"])
    for n in settings["quadratic_dimensions"]:
        for condition in settings["quadratic_conditions"]:
            for index in range(settings["quadratic_problems"]):
                problem = random_quadratic(n, condition, rng)
                for cls in SMOOTH:
                    result = cls(max_iterations=20_000).solve(problem, np.zeros(n))
                    rows.append({
                        "problem": "quadratic", "n": n, "condition": condition, "state": index,
                        "solver": cls.name, **_result_columns(result),
                        "error": float(np.linalg.norm(result.x - problem.minimiser())),
                    })
    for n, start in ((2, [-1.2, 1.0]), (5, [0.5] * 5)):
        for cls in (ProjectedGradient, Newton, BFGS, ConjugateGradient):
            solver = cls(max_iterations=settings["rosenbrock_max_iterations"])
            result = solver.solve(Rosenbrock(), start)
            rows.append({
                "problem": "rosenbrock", "n": n, "condition": None, "state": 0,
                "solver": cls.name, **_result_columns(result),
                "error": float(np.linalg.norm(result.x - 1.0)),
            })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------- tables
def _result_columns(result: SolverResult) -> dict:
    return {
        "status": result.status, "converged": result.converged,
        "iterations": result.iterations, "runtime_ms": 1000 * result.runtime_s,
    }


def summarise(runs: pd.DataFrame, keys: Sequence[str], extra: Mapping[str, tuple]) -> pd.DataFrame:
    """Per group: counts, iterations and run time, plus the `extra` aggregations."""
    grouped = runs.groupby(list(keys), sort=False, dropna=False)
    table = grouped.agg(
        problems=("status", "size"),
        converged=("converged", "sum"),
        iterations_median=("iterations", "median"),
        iterations_p95=("iterations", lambda v: float(np.percentile(v, 95))),
        iterations_max=("iterations", "max"),
        runtime_ms_median=("runtime_ms", "median"),
        runtime_ms_p95=("runtime_ms", lambda v: float(np.percentile(v, 95))),
        runtime_ms_max=("runtime_ms", "max"),
        statuses=("status", lambda s: ";".join(
            f"{k}:{v}" for k, v in sorted(s.value_counts().items()))),
        **extra,
    )
    return table.reset_index()
