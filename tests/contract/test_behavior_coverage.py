"""Contract test ensuring every behavior rule in contracts/behaviors.yaml is covered by tests.

Enforces FND-05 and D-17:
- Every rule ID in contracts/behaviors.yaml (70 rules) appears in at least one
  @pytest.mark.behavior("<id>") call under tests/ (discovered via AST parsing).
- Every behavior marker ID cited in tests exists in behaviors.yaml
  (allowing CAM-* requirement-level markers).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BEHAVIORS_PATH = REPO_ROOT / "contracts" / "behaviors.yaml"
TESTS_DIR = REPO_ROOT / "tests"


def _collect_behavior_markers(tests_dir: Path) -> set[str]:
    """Parse all test files with AST to extract @pytest.mark.behavior args."""
    found_ids: set[str] = set()

    for py_file in tests_dir.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except (SyntaxError, UnicodeDecodeError):
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue

            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue

                func = decorator.func
                # Look for pytest.mark.behavior(...)
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "behavior"
                    and isinstance(func.value, ast.Attribute)
                    and func.value.attr == "mark"
                ):
                    for arg in decorator.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            found_ids.add(arg.value)

    return found_ids


@pytest.mark.behavior("FND-05")
def test_all_behavior_rules_covered() -> None:
    """Every rule in contracts/behaviors.yaml is cited by at least one test."""
    assert BEHAVIORS_PATH.exists(), f"Missing behavior catalogue: {BEHAVIORS_PATH}"

    data: dict[str, Any] = yaml.safe_load(BEHAVIORS_PATH.read_text(encoding="utf-8"))
    rule_ids = {r["id"] for r in data.get("rules", [])}
    assert len(rule_ids) == 70, f"Expected 70 rules in behaviors.yaml, found {len(rule_ids)}"

    found_ids = _collect_behavior_markers(TESTS_DIR)

    missing_ids = rule_ids - found_ids
    assert not missing_ids, f"Missing behavior rule IDs: {sorted(missing_ids)}"

    # All cited IDs must exist in behaviors.yaml (allowing requirement-level CAM-* and FND-* tags)
    unknown_ids = {i for i in found_ids if not (i.startswith("CAM-") or i.startswith("FND-"))} - rule_ids
    assert not unknown_ids, f"Unknown behavior rule IDs cited in tests: {sorted(unknown_ids)}"

