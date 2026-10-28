"""Unit tests verifying GitHub Actions CI matrix and step configuration (D-30, FND-04, FND-05)."""

from pathlib import Path
from typing import Any

import yaml


def test_ci_workflow_structure() -> None:
    """Assert CI workflow defines complete three-OS matrix, python versions, and required steps."""
    ci_file = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
    assert ci_file.exists(), "ci.yml missing"

    data: dict[str, Any] = yaml.safe_load(ci_file.read_text(encoding="utf-8"))
    jobs = data.get("jobs", {})
    assert "test" in jobs, "CI missing 'test' job"

    test_job = jobs["test"]

    # 1. Environment: NVR_SECRETS_BACKEND is file
    assert test_job.get("env", {}).get("NVR_SECRETS_BACKEND") == "file"

    # 2. Strategy Matrix: three OS runners and python 3.13 + include ubuntu 3.11
    strategy = test_job.get("strategy", {})
    matrix = strategy.get("matrix", {})
    os_list = matrix.get("os", [])
    expected_os = ["ubuntu-latest", "macos-latest", "windows-latest"]
    assert sorted(os_list) == sorted(expected_os)
    assert matrix.get("python") == ["3.13"]

    includes = matrix.get("include", [])
    assert any(inc.get("os") == "ubuntu-latest" and inc.get("python") == "3.11" for inc in includes)

    # 3. Steps check
    steps = test_job.get("steps", [])
    run_commands: list[str] = [step.get("run", "") for step in steps if "run" in step]
    all_runs = "\n".join(run_commands)

    expected_sub_commands = [
        "uv sync --locked",
        "uv run pytest",
        "tools/fetch_mediamtx.py",
        "pytest -m mediamtx",
        "drift_check.py --self",
        "alembic upgrade head",
        "alembic check",
    ]

    for expected in expected_sub_commands:
        assert any(expected in run_cmd for run_cmd in run_commands), (
            f"Expected '{expected}' to be present in workflow run steps, but got:\n{all_runs}"
        )

    # 4. MediaMTX cache step exists
    cache_steps = [s for s in steps if s.get("uses", "").startswith("actions/cache@")]
    assert len(cache_steps) >= 1
    cache_step = cache_steps[0]
    key_pattern = cache_step.get("with", {}).get("key", "")
    assert "mediamtx-v1.21.3-" in key_pattern
