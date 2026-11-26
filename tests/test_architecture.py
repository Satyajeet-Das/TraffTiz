"""The maths layers must stay independent of SUMO and control code (NFR-05)."""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "optitraffic"
FORBIDDEN = (
    "traci", "sumolib", "sumo", "libsumo", "scipy",
    "optitraffic.simulation", "optitraffic.integration", "optitraffic.control",
)


def imported_modules(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"use absolute imports in {path}"
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


@pytest.mark.parametrize("layer", ["modelling", "optimization"])
def test_maths_layer_has_no_forbidden_imports(layer):
    files = list((PACKAGE / layer).rglob("*.py"))
    assert files
    for path in files:
        for name in imported_modules(path):
            bad = [f for f in FORBIDDEN if name == f or name.startswith(f + ".")]
            assert not bad, f"{path.name} imports {name}"
