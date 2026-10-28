"""Integration tests for serial-based silent re-IP recovery (CAM-10, HEAL-05)."""

import asyncio
import json
from pathlib import Path

import pytest
from fake_camera.discovery import DiscoveryResponder
from fake_camera.faults import Status
from fake_camera.server import FakeCamera
from fake_camera.state import Account, CameraRole
from sqlalchemy import update
from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app
from vizenlink_nvr.db.engine import create_engine_for
from vizenlink_nvr.db.models import Camera


@pytest.mark.behavior("HEAL-05")
async def test_tracer_reprobe_heals_moved_camera_address(
    cli: CliRunner,
    discovery_responder: DiscoveryResponder,
    fake_camera: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Reprobe detects 421 on moved camera address, re-discovers by serial
    with blank creds, and updates host.
    """
    monkeypatch.setenv("NVR_DISCOVERY_MULTICAST_GROUP", "127.0.0.1")
    monkeypatch.setenv("NVR_DISCOVERY_PORT", str(discovery_responder.port))

    # 1. Spin up Camera A (serial S1) and Camera B (serial S2)
    cam_a: FakeCamera = await fake_camera(
        serial="VZL-CAM-REIP-A01",
        accounts={"admin": Account("Pass-Owner-A", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )
    cam_b: FakeCamera = await fake_camera(
        serial="VZL-CAM-REIP-B02",
        accounts={"admin": Account("Pass-Owner-B", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )

    # 2. Onboard Camera A
    cam_a.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
    )
    res_add = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "add",
            "--host",
            cam_a.host,
            "--port",
            str(cam_a.port),
            "--password-stdin",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
        input="Pass-Owner-A\n",
    )
    assert res_add.exit_code == 0, f"Add failed: {res_add.output}"

    # 3. Simulate DHCP address shift: point Camera A's stored port at Camera B!
    # Now when the NVR probes A's stored address, B answers and returns HTTP 421 ID mismatch.
    db_file = tmp_path / "nvr.db"
    engine = create_engine_for(db_file)
    async with engine.connect() as conn:
        await conn.execute(
            update(Camera).where(Camera.serial == "VZL-CAM-REIP-A01").values(https_port=cam_b.port)
        )
        await conn.commit()
    await engine.dispose()

    # 4. Clear request history on both cameras before reprobe
    cam_a.requests.clear()
    cam_b.requests.clear()

    # 5. Run cameras reprobe for S1
    res_reprobe = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "reprobe",
            "--serial",
            "VZL-CAM-REIP-A01",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert res_reprobe.exit_code == 0, f"Reprobe failed: {res_reprobe.output}"

    # 6. Verify reprobe report
    report = json.loads(res_reprobe.stdout)
    assert report["kind"] == "HEALED"
    assert report["serial"] == "VZL-CAM-REIP-A01"
    assert report["address"] == f"{cam_a.host}:{cam_a.port}"

    # 7. Verify registry has exactly 1 row for S1 with restored port, and S2 was never registered
    res_list = await asyncio.to_thread(
        cli.invoke,
        app,
        ["cameras", "list", "--json", "--data-dir", str(tmp_path)],
    )
    assert res_list.exit_code == 0
    cameras = json.loads(res_list.stdout)
    assert len(cameras) == 1
    assert cameras[0]["serial"] == "VZL-CAM-REIP-A01"
    assert cameras[0]["https_port"] == cam_a.port

    # 8. Invariant D-12: blank-credential discovery read only. Neither A nor B received credentialed requests.
    assert len(cam_a.requests_with_credentials()) == 0
    assert len(cam_b.requests_with_credentials()) == 0
