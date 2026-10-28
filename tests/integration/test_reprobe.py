"""Integration tests for reprobe refreshing capabilities and streams (CAM-05, D-25)."""

import asyncio
import json
from pathlib import Path

import pytest
from fake_camera.discovery import DiscoveryResponder
from fake_camera.faults import Status
from fake_camera.routes.rest_session import rest_settings
from fake_camera.server import FakeCamera
from fake_camera.state import Account, CameraRole
from sqlalchemy import select, update
from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app
from vizenlink_nvr.db.engine import create_engine_for
from vizenlink_nvr.db.models import Camera, CameraCapabilitiesRow, CameraStream


@pytest.mark.behavior("CAM-05")
async def test_reprobe_refreshes_capabilities_streams_and_name(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Reprobe re-reads capabilities, stream profiles, and camera name,
    replacing them in a single transaction (CAM-05, CAM-07, D-13).
    """
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-REPROBE-01",
        accounts={"admin": Account("Pass-Owner-1", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
    )

    # 1. Onboard camera
    res_add = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "add",
            "--host",
            cam.host,
            "--port",
            str(cam.port),
            "--password-stdin",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
        input="Pass-Owner-1\n",
    )
    assert res_add.exit_code == 0

    # 2. Mutate camera on simulator:
    # Change max_users to 3 in capabilities
    rest_settings(cam.state).capabilities["max_users"] = 3
    # Change camera name
    cam.state.name = "Updated Gate Camera"

    # 3. Run reprobe
    res_reprobe = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "reprobe",
            "--serial",
            "VZL-CAM-REPROBE-01",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert res_reprobe.exit_code == 0, f"Reprobe failed: {res_reprobe.output}"

    report = json.loads(res_reprobe.stdout)
    assert report["kind"] == "OK"
    assert report["refreshed"] is True
    assert report["serial"] == "VZL-CAM-REPROBE-01"

    # 4. Verify DB rows updated
    engine = create_engine_for(tmp_path / "nvr.db")
    async with engine.connect() as conn:
        cam_name = (
            await conn.execute(select(Camera.name).where(Camera.serial == "VZL-CAM-REPROBE-01"))
        ).scalar_one()
        assert cam_name == "Updated Gate Camera"

        raw_json = (
            await conn.execute(
                select(CameraCapabilitiesRow.raw_json).where(
                    CameraCapabilitiesRow.serial == "VZL-CAM-REPROBE-01"
                )
            )
        ).scalar_one()
        raw_caps = json.loads(raw_json)
        assert raw_caps["max_users"] == 3

        streams_res = (
            (await conn.execute(select(CameraStream.role).where(CameraStream.serial == "VZL-CAM-REPROBE-01")))
            .scalars()
            .all()
        )
        assert len(streams_res) == 2
    await engine.dispose()


@pytest.mark.behavior("CAM-05")
async def test_reprobe_partial_failure_leaves_previous_capabilities_and_streams_unchanged(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """When GetProfiles fails during reprobe, existing capabilities and stream rows
    are kept completely untouched (atomic all-or-nothing refresh).
    """
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-REPROBE-02",
        accounts={"admin": Account("Pass-Owner-1", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )
    cam.faults.add(
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
            cam.host,
            "--port",
            str(cam.port),
            "--password-stdin",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
        input="Pass-Owner-1\n",
    )
    assert res_add.exit_code == 0

    engine = create_engine_for(tmp_path / "nvr.db")
    async with engine.connect() as conn:
        orig_caps = (
            await conn.execute(
                select(CameraCapabilitiesRow.raw_json).where(
                    CameraCapabilitiesRow.serial == "VZL-CAM-REPROBE-02"
                )
            )
        ).scalar_one()
        orig_streams = (
            await conn.execute(
                select(
                    CameraStream.role,
                    CameraStream.profile_token,
                    CameraStream.width,
                    CameraStream.height,
                ).where(CameraStream.serial == "VZL-CAM-REPROBE-02")
            )
        ).all()
    await engine.dispose()

    # Mutate capabilities on camera, BUT inject fault on GetProfiles (Media2)
    rest_settings(cam.state).capabilities["max_users"] = 99
    cam.faults.add(
        "POST /onvif/media2_service",
        Status(500, json_body={"error": "Media2 server error"}),
    )

    res_reprobe = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "reprobe",
            "--serial",
            "VZL-CAM-REPROBE-02",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert res_reprobe.exit_code != 0

    # Verify DB rows are byte-identical to before reprobe
    engine = create_engine_for(tmp_path / "nvr.db")
    async with engine.connect() as conn:
        new_caps = (
            await conn.execute(
                select(CameraCapabilitiesRow.raw_json).where(
                    CameraCapabilitiesRow.serial == "VZL-CAM-REPROBE-02"
                )
            )
        ).scalar_one()
        assert new_caps == orig_caps

        new_streams = (
            await conn.execute(
                select(
                    CameraStream.role,
                    CameraStream.profile_token,
                    CameraStream.width,
                    CameraStream.height,
                ).where(CameraStream.serial == "VZL-CAM-REPROBE-02")
            )
        ).all()
        assert new_streams == orig_streams
    await engine.dispose()


@pytest.mark.behavior("CAM-05")
async def test_reprobe_after_heal_also_refreshes(
    cli: CliRunner,
    discovery_responder: DiscoveryResponder,
    fake_camera: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Reprobe after an address heal also refreshes capabilities and streams at the new address."""
    monkeypatch.setenv("NVR_DISCOVERY_MULTICAST_GROUP", "127.0.0.1")
    monkeypatch.setenv("NVR_DISCOVERY_PORT", str(discovery_responder.port))

    cam_a: FakeCamera = await fake_camera(
        serial="VZL-CAM-REPROBE-HEAL-01",
        accounts={"admin": Account("Pass-Owner-A", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )
    cam_b: FakeCamera = await fake_camera(
        serial="VZL-CAM-REPROBE-HEAL-02",
        accounts={"admin": Account("Pass-Owner-B", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )

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
    assert res_add.exit_code == 0

    # Mutate name on Cam A
    cam_a.state.name = "Healed Name A"

    # Simulate DHCP shift: point stored port of A to B
    db_file = tmp_path / "nvr.db"
    engine = create_engine_for(db_file)
    async with engine.connect() as conn:
        await conn.execute(
            update(Camera).where(Camera.serial == "VZL-CAM-REPROBE-HEAL-01").values(https_port=cam_b.port)
        )
        await conn.commit()
    await engine.dispose()

    # Reprobe S1
    res_reprobe = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "reprobe",
            "--serial",
            "VZL-CAM-REPROBE-HEAL-01",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert res_reprobe.exit_code == 0
    report = json.loads(res_reprobe.stdout)
    assert report["kind"] == "HEALED"
    assert report["refreshed"] is True
    assert report["address"] == f"{cam_a.host}:{cam_a.port}"

    # Verify updated name in database
    engine = create_engine_for(db_file)
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                select(Camera.name, Camera.https_port).where(Camera.serial == "VZL-CAM-REPROBE-HEAL-01")
            )
        ).one()
        assert row.name == "Healed Name A"
        assert row.https_port == cam_a.port
    await engine.dispose()
