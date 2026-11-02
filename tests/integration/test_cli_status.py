"""Integration tests for NVR status CLI command."""

import json
from pathlib import Path

from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app


def test_cli_status_json(cli: CliRunner, tmp_path: Path) -> None:
    """Test nvr status --json generates database, applies migrations, and emits JSON."""
    test_dir = tmp_path / "cli_status_json"
    result = cli.invoke(app, ["status", "--json", "--data-dir", str(test_dir)])
    assert result.exit_code == 0, f"Command failed: {result.output}"

    data = json.loads(result.stdout)
    assert data["db_ok"] is True
    assert data["schema_revision"] == "0003_recording_core"
    assert data["schema_head"] == "0003_recording_core"
    assert data["data_dir"] == str(test_dir)
    assert "site_timezone" in data

    # Idempotent re-run
    result2 = cli.invoke(app, ["status", "--json", "--data-dir", str(test_dir)])
    assert result2.exit_code == 0
    data2 = json.loads(result2.stdout)
    assert data2["db_ok"] is True
    assert data2["schema_revision"] == "0003_recording_core"


def test_cli_status_human(cli: CliRunner, tmp_path: Path) -> None:
    """Test nvr status renders human table and database is ok."""
    test_dir = tmp_path / "cli_status_human"
    result = cli.invoke(app, ["status", "--data-dir", str(test_dir)])
    assert result.exit_code == 0
    assert "VizenLink NVR Status" in result.output
    assert "Database OK" in result.output
