"""Integration tests for certificate change detection and acceptance (CAM-05, D-25)."""

import asyncio
import json
import re
from pathlib import Path

import pytest
from fake_camera.faults import Status
from fake_camera.pytest_plugin import ControllableFakeCamera
from fake_camera.state import Account, CameraRole
from sqlalchemy import select
from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app
from vizenlink_nvr.db.engine import create_engine_for
from vizenlink_nvr.db.models import Camera


@pytest.mark.behavior("CAM-05")
async def test_tls_changed_returns_exit_19_and_marks_state(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Replacing camera certificate triggers TLS_CHANGED exit 19, marks state,
    and sends zero requests with credentials (D-25).
    """
    cam: ControllableFakeCamera = await fake_camera(
        serial="VZL-CAM-TLS-01",
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

    # 2. Restart camera with a new certificate on the same port
    orig_pin = cam.cert_sha256
    await cam.restart_with_new_certificate()
    new_pin = cam.cert_sha256
    assert new_pin != orig_pin

    cam.requests.clear()

    # 3. Run reprobe without --accept-new-certificate (human mode to verify exact wording)
    res_reprobe = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "reprobe",
            "--serial",
            "VZL-CAM-TLS-01",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert res_reprobe.exit_code == 19

    expected_msg = (
        "The camera's certificate has changed since it was added. "
        "If you replaced or updated this camera, run: "
        "nvr cameras reprobe VZL-CAM-TLS-01 --accept-new-certificate"
    )
    assert expected_msg in " ".join(res_reprobe.output.split())

    # 4. Check DB state is tls_changed
    engine = create_engine_for(tmp_path / "nvr.db")
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                select(Camera.state, Camera.tls_fingerprint_sha256).where(Camera.serial == "VZL-CAM-TLS-01")
            )
        ).one()
        assert row.state == "tls_changed"
        assert row.tls_fingerprint_sha256 == orig_pin
    await engine.dispose()

    # 5. Invariant D-25: zero credentialed requests reached the simulator
    assert len(cam.requests_with_credentials()) == 0


@pytest.mark.behavior("CAM-05")
async def test_reprobe_accept_new_certificate_success(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """reprobe --accept-new-certificate verifies serial, fetches new pin,
    and updates registry state to active (CAM-05, D-25).
    """
    cam: ControllableFakeCamera = await fake_camera(
        serial="VZL-CAM-TLS-02",
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

    # Restart camera with new cert
    await cam.restart_with_new_certificate()
    new_pin = cam.cert_sha256

    # Run reprobe --accept-new-certificate
    res_reprobe = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "reprobe",
            "--serial",
            "VZL-CAM-TLS-02",
            "--accept-new-certificate",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert res_reprobe.exit_code == 0, f"Reprobe failed: {res_reprobe.output}"

    report = json.loads(res_reprobe.stdout)
    assert report["kind"] == "OK"
    assert report["refreshed"] is True

    # Verify DB has new certificate fingerprint and active state
    engine = create_engine_for(tmp_path / "nvr.db")
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                select(Camera.state, Camera.tls_fingerprint_sha256).where(Camera.serial == "VZL-CAM-TLS-02")
            )
        ).one()
        assert row.state == "active"
        assert row.tls_fingerprint_sha256 == new_pin
    await engine.dispose()


@pytest.mark.behavior("CAM-05")
async def test_reprobe_accept_new_certificate_fails_if_serial_mismatch(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """reprobe --accept-new-certificate fails and changes nothing if
    unauthenticated serial check returns 421.
    """
    cam: ControllableFakeCamera = await fake_camera(
        serial="VZL-CAM-TLS-03",
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
    orig_pin = cam.cert_sha256

    # Restart camera with different serial and different cert
    await cam.restart_with_new_certificate()
    cam.state.serial = "VZL-DIFFERENT-CAMERA"

    res_reprobe = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "reprobe",
            "--serial",
            "VZL-CAM-TLS-03",
            "--accept-new-certificate",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert res_reprobe.exit_code != 0

    # Verify pin was NOT updated
    engine = create_engine_for(tmp_path / "nvr.db")
    async with engine.connect() as conn:
        row_pin = (
            await conn.execute(select(Camera.tls_fingerprint_sha256).where(Camera.serial == "VZL-CAM-TLS-03"))
        ).scalar_one()
        assert row_pin == orig_pin
    await engine.dispose()


def test_automated_wording_guard_no_false_tls_claims() -> None:
    """Automated guard: verify no production code claims certificate fingerprints
    authenticate camera identity or provide MITM protection (D-25).
    """
    forbidden_patterns = [
        re.compile(r"authenticates\s+camera\s+identity", re.IGNORECASE),
        re.compile(r"provides?\s+(?:full\s+)?mitm\s+protection", re.IGNORECASE),
        re.compile(r"provides?\s+man-in-the-middle\s+protection", re.IGNORECASE),
    ]

    src_dir = Path(__file__).resolve().parents[2] / "src" / "vizenlink_nvr"
    for py_file in src_dir.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        for pat in forbidden_patterns:
            match = pat.search(text)
            assert match is None, f"Forbidden claim '{match.group(0)}' found in {py_file} (violates D-25)"
