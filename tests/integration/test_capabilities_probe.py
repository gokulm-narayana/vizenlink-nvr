"""Integration tests for capabilities caching, missing WAN flags, and camera_id_check (CAM-05)."""

import asyncio
import json
from datetime import datetime
from pathlib import Path

import pytest
from fake_camera.faults import Status
from fake_camera.routes.rest_session import rest_settings
from fake_camera.server import FakeCamera
from fake_camera.state import Account, CameraRole
from sqlalchemy import select
from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app
from vizenlink_nvr.db.engine import create_engine_for
from vizenlink_nvr.db.models import Camera, CameraCapabilitiesRow


async def test_capabilities_cached_raw_json_and_clock(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Camera capabilities are cached verbatim in camera_capabilities, matching sim output."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAPS-01",
        accounts={"admin": Account("Admin-Pass-01", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
    )

    sim_caps = rest_settings(cam).capabilities
    assert "siren_capable" in sim_caps

    result = await asyncio.to_thread(
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
        input="Admin-Pass-01\n",
    )
    assert result.exit_code == 0, f"Add failed: {result.output}"

    db_file = tmp_path / "nvr.db"
    engine = create_engine_for(db_file)
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                select(
                    CameraCapabilitiesRow.raw_json,
                    CameraCapabilitiesRow.probed_at,
                ).where(CameraCapabilitiesRow.serial == "VZL-CAPS-01")
            )
        ).one()
        stored_dict = json.loads(row.raw_json)
        assert stored_dict == sim_caps
        assert isinstance(row.probed_at, datetime)
    await engine.dispose()


async def test_missing_wan_flags_still_adds_and_stores_camera_id_check(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Missing WAN flags log a warning but onboarding succeeds; parsed camera_id_check is persisted."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAPS-02",
        accounts={"admin": Account("Admin-Pass-01", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
    )

    # Remove wan_live_view_capable and set camera_id_check to False
    settings = rest_settings(cam)
    custom_caps = dict(settings.capabilities)
    custom_caps.pop("wan_live_view_capable", None)
    custom_caps["camera_id_check"] = False
    settings.capabilities = custom_caps

    result = await asyncio.to_thread(
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
        input="Admin-Pass-01\n",
    )
    assert result.exit_code == 0, f"Add failed: {result.output}"

    # Verify camera_id_check persisted as False on Camera row
    db_file = tmp_path / "nvr.db"
    engine = create_engine_for(db_file)
    async with engine.connect() as conn:
        camera_id_check = (
            await conn.execute(select(Camera.camera_id_check).where(Camera.serial == "VZL-CAPS-02"))
        ).scalar_one()
        assert camera_id_check is False
    await engine.dispose()
