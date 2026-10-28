"""Unit test ensuring the built wheel packages all required migration and media assets."""

from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

import pytest


@pytest.mark.behavior("FND-05")
def test_wheel_package_contains_migrations_and_pins(tmp_path: Path) -> None:
    """The built wheel contains db/migrations (0001_initial, 0002_camera_registry) and media/pins.json."""
    cmd = ["uv", "build", "--wheel", "--out-dir", str(tmp_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
    assert result.returncode == 0, f"uv build failed: {result.stderr}\n{result.stdout}"

    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1, f"Expected 1 wheel file in {tmp_path}, found {len(wheels)}"
    wheel_path = wheels[0]

    with zipfile.ZipFile(wheel_path, "r") as zf:
        namelist = zf.namelist()

        required_files = [
            "vizenlink_nvr/db/migrations/versions/0001_initial.py",
            "vizenlink_nvr/db/migrations/versions/0002_camera_registry.py",
            "vizenlink_nvr/db/migrations/env.py",
            "vizenlink_nvr/media/pins.json",
        ]

        for req in required_files:
            assert any(name.endswith(req) for name in namelist), (
                f"Missing required artifact {req} in wheel archive {wheel_path.name}"
            )

