"""Contract and integration tests for MediaMTX CLI commands and configuration validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.media.binary import resolve_binary, validate_config

pytestmark = pytest.mark.mediamtx

runner = CliRunner()


def test_cli_mediamtx_check_json(tmp_path: Path) -> None:
    """nvr mediamtx check --json exits 0 with validate_ok true."""
    res = runner.invoke(app, ["mediamtx", "check", "--json", "--data-dir", str(tmp_path)])
    assert res.exit_code == 0, res.stdout

    data = json.loads(res.stdout)
    assert data["validate_ok"] is True
    assert data["ok"] is True
    assert "mediamtx.yml" in data["config_path"]
    assert "v1.21.3" in data["binary_version"]


def test_cli_mediamtx_check_human(tmp_path: Path) -> None:
    """nvr mediamtx check human output renders table."""
    res = runner.invoke(app, ["mediamtx", "check", "--data-dir", str(tmp_path)])
    assert res.exit_code == 0, res.stdout
    assert "MediaMTX Check Report" in res.stdout
    assert "True" in res.stdout


def test_strict_validation_detects_typo(tmp_path: Path) -> None:
    """MediaMTX validator strictly rejects misspelled configuration keys (drift guard)."""
    settings = load_settings(data_dir=tmp_path)
    binary = resolve_binary(settings)

    # Valid baseline config
    valid_file = tmp_path / "valid.yml"
    valid_file.write_text("paths:\n  all_others: {}\n", encoding="utf-8")
    ok, out = validate_config(binary, valid_file)
    assert ok is True

    # Bad config with typo key
    bad_file = tmp_path / "bad.yml"
    bad_file.write_text("recrdDeleteAfter: 0s\npaths:\n  all_others: {}\n", encoding="utf-8")
    bad_ok, bad_out = validate_config(binary, bad_file)
    assert bad_ok is False
    assert "unknown field" in bad_out.lower() or "ERR" in bad_out


def test_cli_mediamtx_check_probe_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """nvr mediamtx check --probe --json runs live probes and exits 0."""
    import socket

    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])

    test_ports = f"{_free_port()},{_free_port()},{_free_port()},{_free_port()},{_free_port()},{_free_port()}"
    monkeypatch.setenv("NVR_MEDIAMTX_TEST_PORTS", test_ports)

    res = runner.invoke(app, ["mediamtx", "check", "--probe", "--json", "--data-dir", str(tmp_path)])
    assert res.exit_code == 0, res.stdout

    data = json.loads(res.stdout)
    assert data["validate_ok"] is True
    assert data["ok"] is True
    assert data["probes"] is not None
    assert len(data["probes"]) > 0
    assert all(p["ok"] for p in data["probes"])
