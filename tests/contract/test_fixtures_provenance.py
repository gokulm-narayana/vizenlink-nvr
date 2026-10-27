"""Test provenance of golden fixtures under contracts/fixtures."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "contracts" / "fixtures"
LOCK_FILE = REPO_ROOT / "contracts" / "camera_api.lock.json"

XML_SOURCE_RE = re.compile(r"<!--\s*source:\s*([^#]+)#L(\d+)-L(\d+)\s*-->")


def _get_vendored_files() -> dict[str, int]:
    """Return map of vendored_as path to line count on disk."""
    assert LOCK_FILE.exists(), "camera_api.lock.json must exist"
    lock_data = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    vendored_paths: dict[str, int] = {}
    for entry in lock_data.get("files", []):
        v_path = entry["vendored_as"]
        disk_path = REPO_ROOT / v_path
        assert disk_path.exists(), f"Vendored file {v_path} missing on disk"
        line_count = len(disk_path.read_text(encoding="utf-8").splitlines())
        vendored_paths[v_path] = line_count
    return vendored_paths


def test_fixtures_provenance() -> None:
    """Every fixture in contracts/fixtures (except README.md) must trace to a vendored lock entry."""
    assert FIXTURES_DIR.exists(), "contracts/fixtures directory must exist"
    fixture_files = [f for f in FIXTURES_DIR.rglob("*") if f.is_file() and f.name != "README.md"]

    assert len(fixture_files) > 0, "No fixture files found under contracts/fixtures"

    vendored_map = _get_vendored_files()

    for fixture in fixture_files:
        content = fixture.read_text(encoding="utf-8")
        source_path: str | None = None
        start_line: int | None = None
        end_line: int | None = None

        if fixture.suffix == ".json":
            try:
                data = json.loads(content)
            except Exception as e:
                pytest.fail(f"Fixture {fixture} is invalid JSON: {e}")

            assert "source" in data, f"Fixture {fixture} missing 'source' object"
            source = data["source"]
            assert "path" in source, f"Fixture {fixture} source missing 'path'"
            assert "lines" in source, f"Fixture {fixture} source missing 'lines'"

            source_path = source["path"]
            line_parts = source["lines"].split("-")
            assert len(line_parts) == 2, f"Invalid lines format '{source['lines']}' in {fixture}"
            start_line = int(line_parts[0])
            end_line = int(line_parts[1])

        elif fixture.suffix == ".xml":
            match = XML_SOURCE_RE.search(content)
            assert match, f"XML fixture {fixture} missing provenance comment <!-- source: path#La-Lb -->"
            source_path = match.group(1).strip()
            start_line = int(match.group(2))
            end_line = int(match.group(3))
        else:
            pytest.fail(f"Unsupported fixture format: {fixture}")

        assert source_path in vendored_map, (
            f"Fixture {fixture} cites source path '{source_path}', which is not a vendored_as lock entry"
        )

        max_lines = vendored_map[source_path]
        msg = f"Fixture {fixture.name} range {start_line}-{end_line} invalid for {source_path} ({max_lines})"
        assert 1 <= start_line <= end_line <= max_lines, msg
