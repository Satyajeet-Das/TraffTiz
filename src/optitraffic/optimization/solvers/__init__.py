"""Optimization algorithms. All are hand-written and return `SolverResult`."""

from optitraffic.optimization.solvers.base import Solver
from optitraffic.optimization.solvers.bfgs import BFGS
from optitraffic.optimization.solvers.conjugate_gradient import ConjugateGradient
from optitraffic.optimization.solvers.gradient_descent import GradientDescent
from optitraffic.optimization.solvers.momentum import Momentum
from optitraffic.optimization.solvers.newton import Newton
from optitraffic.optimization.solvers.projected_gradient import ProjectedGradient
from optitraffic.optimization.solvers.sgd import SGD
from optitraffic.optimization.solvers.subgradient import Subgradient
from optitraffic.types import SolverParams

SOLVERS: dict[str, type[Solver]] = {
    cls.name: cls
    for cls in (
        GradientDescent, ProjectedGradient, Momentum, SGD,
        Newton, BFGS, ConjugateGradient, Subgradient,
    )
}


def create_solver(params: SolverParams, **options) -> Solver:
    """Build the solver named in the configuration; `options` are solver-specific."""
    if params.name not in SOLVERS:
        raise ValueError(f"unknown solver {params.name!r}")
    return SOLVERS[params.name](
        tolerance=params.tolerance,
        max_iterations=params.max_iterations,
        time_budget_s=params.time_budget_s,
        **options,
    )


__all__ = [
    "BFGS", "SGD", "SOLVERS", "ConjugateGradient", "GradientDescent", "Momentum",
    "Newton", "ProjectedGradient", "Solver", "Subgradient", "create_solver",
]
