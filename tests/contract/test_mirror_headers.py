"""Contract test verifying mirror-header integrity against camera_api.lock.json.

Enforces FND-05 and D-17:
- Every `# mirrors: <path>@<sha12>` line in src/vizenlink_nvr/camera/ matches
  a lock entry's path and sha256 prefix.
- Every module named in a lock entry's mirrored_by (under src/vizenlink_nvr/camera/)
  exists and carries that header.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LOCK_PATH = REPO_ROOT / "contracts" / "camera_api.lock.json"
CAMERA_SRC = REPO_ROOT / "src" / "vizenlink_nvr" / "camera"

HEADER_RE = re.compile(r"#\s*mirrors:\s*([^\s@]+)@([0-9a-fA-F]{12})")


def _load_lock_entries() -> dict[str, dict[str, Any]]:
    assert LOCK_PATH.exists(), f"Missing lock file: {LOCK_PATH}"
    lock_data: dict[str, Any] = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    files = lock_data.get("files", [])
    return {f["path"]: f for f in files}


@pytest.mark.behavior("FND-05")
def test_camera_mirror_headers_to_lock() -> None:
    """Direction 1 (Header -> Lock): Every mirror header corresponds to a valid lockfile entry."""
    files_by_path = _load_lock_entries()
    header_count = 0

    for py_file in CAMERA_SRC.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for match in HEADER_RE.finditer(content):
            path, sha12 = match.groups()
            assert path in files_by_path, (
                f"{py_file.relative_to(REPO_ROOT)}: mirror target '{path}' not found in lockfile"
            )
            expected_prefix = files_by_path[path]["sha256"][:12].lower()
            assert sha12.lower() == expected_prefix, (
                f"{py_file.relative_to(REPO_ROOT)}: sha prefix mismatch for {path} "
                f"(expected {expected_prefix}, got {sha12.lower()})"
            )
            header_count += 1

    assert header_count > 0, "No mirror headers discovered in camera source files"


@pytest.mark.behavior("FND-05")
def test_lock_mirrored_by_to_headers() -> None:
    """Direction 2 (Lock -> Header): Every mirrored_by entry in camera carries matching header."""
    files_by_path = _load_lock_entries()
    verified_count = 0

    for path, entry in files_by_path.items():
        mirrored_by = entry.get("mirrored_by", [])
        if isinstance(mirrored_by, str):
            mirrored_by = [mirrored_by]

        for mirror_path_str in mirrored_by:
            if not mirror_path_str.startswith("src/vizenlink_nvr/camera"):
                continue

            target_file = REPO_ROOT / mirror_path_str
            assert target_file.exists(), (
                f"Lockfile {path} specifies mirrored_by {mirror_path_str}, but file does not exist"
            )

            content = target_file.read_text(encoding="utf-8")
            expected_header = f"# mirrors: {path}@{entry['sha256'][:12]}"
            assert expected_header in content, (
                f"{mirror_path_str} missing required header: {expected_header}"
            )
            verified_count += 1

    assert verified_count > 0, "No mirrored_by entries verified"

