"""Integration tests for nvr storage CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app
from vizenlink_nvr.cli.exitcodes import ExitCode


def test_cli_storage_status_human(cli: CliRunner, tmp_path: Path) -> None:
    """nvr storage status renders rich table with storage metrics."""
    data_dir = tmp_path / "nvr_data"
    result = cli.invoke(app, ["storage", "status", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, result.output
    assert "VizenLink NVR Storage Status" in result.output
    assert "Storage Path" in result.output
    assert "Health State" in result.output


def test_cli_storage_status_json(cli: CliRunner, tmp_path: Path) -> None:
    """nvr storage status --json emits valid JSON with expected telemetry fields."""
    data_dir = tmp_path / "nvr_data"
    result = cli.invoke(app, ["storage", "status", "--json", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, result.output

    data = json.loads(result.stdout)
    assert "storage_path" in data
    assert "allow_system_disk" in data
    assert "reserve_bytes" in data
    assert "health_state" in data
    assert "total_bytes" in data
    assert "telemetry" in data
    assert data["telemetry"]["total_bytes"] > 0
    assert data["telemetry"]["free_bytes"] >= 0


def test_cli_storage_set_path_system_disk_refusal(
    cli: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """nvr storage set-path refuses system root path unless --allow-system-disk is passed."""
    data_dir = tmp_path / "nvr_data"
    target_rec = tmp_path / "recordings"

    # Mock is_system_drive to return True
    monkeypatch.setattr("vizenlink_nvr.services.storage.is_system_drive", lambda p: True)

    # 1. Refused without --allow-system-disk
    res_refused = cli.invoke(
        app,
        ["storage", "set-path", "--path", str(target_rec), "--data-dir", str(data_dir)],
    )
    assert res_refused.exit_code == int(ExitCode.INVALID_INPUT), res_refused.output
    assert "system root" in res_refused.output and "partition" in res_refused.output

    # 2. Refused in --json mode emits clean JSON error
    res_json_refused = cli.invoke(
        app,
        ["storage", "set-path", "--path", str(target_rec), "--json", "--data-dir", str(data_dir)],
    )
    assert res_json_refused.exit_code == int(ExitCode.INVALID_INPUT)
    err_data = json.loads(res_json_refused.stdout)
    assert "error" in err_data
    assert "system root partition" in err_data["error"]
    assert err_data["code"] == int(ExitCode.INVALID_INPUT)

    # 3. Succeeds with --allow-system-disk
    res_allowed = cli.invoke(
        app,
        [
            "storage",
            "set-path",
            "--path",
            str(target_rec),
            "--allow-system-disk",
            "--data-dir",
            str(data_dir),
        ],
    )
    assert res_allowed.exit_code == 0, res_allowed.output
    assert "Storage path updated" in res_allowed.output

    # 4. Check status reflects updated storage path
    res_status = cli.invoke(app, ["storage", "status", "--json", "--data-dir", str(data_dir)])
    assert res_status.exit_code == 0
    status_data = json.loads(res_status.stdout)
    assert status_data["storage_path"] == str(target_rec.resolve())
    assert status_data["allow_system_disk"] is True


def test_cli_storage_set_path_positional_rejected(cli: CliRunner, tmp_path: Path) -> None:
    """Passing path as positional argument is rejected (D-16)."""
    data_dir = tmp_path / "nvr_data"
    target_rec = tmp_path / "recordings"

    res = cli.invoke(
        app,
        ["storage", "set-path", str(target_rec), "--data-dir", str(data_dir)],
    )
    assert res.exit_code != 0
    assert "Got unexpected extra argument" in res.output or "Error" in res.output

