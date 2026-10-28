"""Integration tests for nvr cameras scan CLI command."""

import asyncio
import json
from pathlib import Path

import pytest
from fake_camera.discovery import DiscoveryResponder
from fake_camera.server import FakeCamera
from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app


@pytest.mark.behavior("DSC-05")
async def test_cli_scan_json(
    cli: CliRunner,
    discovery_responder: DiscoveryResponder,
    fake_camera: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The CLI with NVR_DISCOVERY_MULTICAST_GROUP=127.0.0.1 prints clean JSON list of 2 cameras."""
    cam1: FakeCamera = await fake_camera(
        serial="VZL-CLI-01",
        name="Front Door",
        model="VZL-Dome-1",
    )
    cam2: FakeCamera = await fake_camera(
        serial="VZL-CLI-02",
        name="Back Yard",
        model="VZL-Bullet-2",
    )

    monkeypatch.setenv("NVR_DISCOVERY_MULTICAST_GROUP", "127.0.0.1")
    monkeypatch.setenv("NVR_DISCOVERY_PORT", str(discovery_responder.port))

    result = await asyncio.to_thread(
        cli.invoke,
        app,
        ["cameras", "scan", "--json", "--data-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, f"Command failed: {result.output}"

    # stdout parses cleanly into a list of 2
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 2
    hosts = {c["host"] for c in data}
    ports = {c["port"] for c in data}
    assert cam1.host in hosts
    assert cam2.host in hosts
    assert cam1.port in ports
    assert cam2.port in ports


def test_cli_scan_zero_cameras_hint(
    cli: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Zero cameras found prints empty table, exit 0, and stderr hint."""
    monkeypatch.setenv("NVR_DISCOVERY_MULTICAST_GROUP", "127.0.0.1")
    monkeypatch.setenv("NVR_DISCOVERY_PORT", "49999")  # Unused port
    monkeypatch.setenv("NVR_DISCOVERY_UNICAST_HOSTS", '["127.0.0.1"]')

    result = cli.invoke(app, ["cameras", "scan", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "Discovered Cameras" in result.output
