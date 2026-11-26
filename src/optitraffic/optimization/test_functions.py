"""Standard problems for checking solvers in n dimensions (track T3)."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike


class Quadratic:
    """0.5 x'Ax - b'x with symmetric positive definite A, optionally boxed."""

    def __init__(
        self, matrix: ArrayLike, vector: ArrayLike, lower: float = -np.inf, upper: float = np.inf
    ) -> None:
        self.matrix = np.array(matrix, dtype=float)
        self.vector = np.array(vector, dtype=float)
        if not np.allclose(self.matrix, self.matrix.T):
            raise ValueError("matrix must be symmetric")
        eigenvalues = np.linalg.eigvalsh(self.matrix)
        if eigenvalues[0] <= 0:
            raise ValueError("matrix must be positive definite")
        self._largest = float(eigenvalues[-1])
        self.lower, self.upper = lower, upper

    def value(self, x: np.ndarray) -> float:
        return float(0.5 * x @ self.matrix @ x - self.vector @ x)

    def gradient(self, x: np.ndarray) -> np.ndarray:
        return self.matrix @ x - self.vector

    def hessian(self, x: np.ndarray) -> np.ndarray:
        return self.matrix

    def project(self, x: np.ndarray) -> np.ndarray:
        return np.clip(x, self.lower, self.upper)

    def lipschitz_constant(self) -> float:
        return self._largest

    def minimiser(self) -> np.ndarray:
        """Unconstrained minimiser."""
        return np.linalg.solve(self.matrix, self.vector)


class Rosenbrock:
    """sum 100 (x[i+1] - x[i]^2)^2 + (1 - x[i])^2; minimum 0 at all ones."""

    def value(self, x: np.ndarray) -> float:
        return float(np.sum(100.0 * (x[1:] - x[:-1] ** 2) ** 2 + (1.0 - x[:-1]) ** 2))

    def gradient(self, x: np.ndarray) -> np.ndarray:
        g = np.zeros_like(x, dtype=float)
        gap = x[1:] - x[:-1] ** 2
        g[:-1] = -400.0 * x[:-1] * gap - 2.0 * (1.0 - x[:-1])
        g[1:] += 200.0 * gap
        return g

    def hessian(self, x: np.ndarray) -> np.ndarray:
        n = len(x)
        h = np.zeros((n, n))
        for i in range(n - 1):
            h[i, i] += 1200.0 * x[i] ** 2 - 400.0 * x[i + 1] + 2.0
            h[i + 1, i + 1] += 200.0
            h[i, i + 1] = h[i + 1, i] = -400.0 * x[i]
        return h

    def project(self, x: np.ndarray) -> np.ndarray:
        return x
