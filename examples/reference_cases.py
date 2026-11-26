"""Solve reference cases A-C of Technical Design section 5.5.

Run:  python examples/reference_cases.py
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from optitraffic.config import load_config
from optitraffic.modelling.queue import predict_queue
from optitraffic.optimization.problems import ReducedProblem
from optitraffic.optimization.solvers.oracle import minimize_bisection
from optitraffic.types import ObjectiveData

DEFAULT = Path(__file__).resolve().parents[1] / "configs" / "default.yaml"
ARRIVAL_RATE = (0.2, 0.1)  # veh/s
SATURATION_FLOW_VPH = (1800.0, 1800.0)  # the documented examples, not the measured value
CASES = [
    ("A", (40, 10), False, "optimum on a bound"),
    ("B", (20, 15), False, "interior optimum"),
    ("C", (20, 1), True, "J_ns optimum on a kink"),
]


def main() -> None:
    config = load_config(DEFAULT)
    model = replace(config.model, saturation_flow_vph=SATURATION_FLOW_VPH)
    equal = config.signal.green_budget_s / 2
    for name, queue, nonsmooth, description in CASES:
        data = ObjectiveData.from_params(queue, ARRIVAL_RATE, model, config.signal)
        problem = ReducedProblem.from_signal(data, config.signal, nonsmooth)
        result = minimize_bisection(problem)
        left_over = predict_queue(data, result.green)
        label = "J_ns" if nonsmooth else "J"
        print(f"Case {name}: {description}, queues (NS, EW) = {queue}")
        print(f"  equal split  g = ({equal:.2f}, {equal:.2f}) s   {label} = {problem.value([equal]):.3f}")
        print(f"  optimum      g = ({result.green[0]:.2f}, {result.green[1]:.2f}) s   "
              f"{label} = {result.value:.3f}")
        print(f"  predicted queues at optimum = ({left_over[0]:.2f}, {left_over[1]:.2f}) veh")


if __name__ == "__main__":
    main()
