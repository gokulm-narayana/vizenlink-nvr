"""Security tests: secrets never leak to stdout, stderr, logs, exceptions, or SQLite files (D-14, D-16)."""

import asyncio
import logging
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fake_camera.faults import Status
from fake_camera.routes.rest_session import rest_settings
from fake_camera.server import FakeCamera
from fake_camera.state import Account, CameraRole
from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app
from vizenlink_nvr.log import RedactingFilter, configure_logging

SENTINEL_CONFIGURED = "Sentinel-Pa55word!"
SENTINEL_NEW = "Sentinel-N3w-Pass!"


@pytest.mark.asyncio
async def test_secrets_never_leak_across_cli_logs_and_db(
    caplog: pytest.LogCaptureFixture,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Comprehensive secret-leak sweep across 10 CLI commands + exception path (D-14, D-16)."""
    # 0. Setup logging with DEBUG and RedactingFilter
    configure_logging("DEBUG")
    root_logger = logging.getLogger()
    redacting_filter = RedactingFilter()
    root_logger.addFilter(redacting_filter)
    caplog.set_level(logging.DEBUG)

    cli = CliRunner()
    all_stdout: list[str] = []
    all_stderr: list[str] = []

    def record_run(result: Any) -> None:
        if result.stdout:
            all_stdout.append(result.stdout)
        if result.stderr:
            all_stderr.append(result.stderr)
        if hasattr(result, "output") and result.output:
            all_stdout.append(result.output)

    serial_cfg = "VZL-CAM-LEAK-CFG"
    serial_fac = "VZL-CAM-LEAK-FAC"

    # Spin up two fake cameras: one configured, one factory-fresh
    cam_cfg: FakeCamera = await fake_camera(
        serial=serial_cfg,
        accounts={"admin": Account(SENTINEL_CONFIGURED, CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )
    rest_settings(cam_cfg.state).capabilities["default_password_in_use"] = False
    cam_cfg.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
    )

    cam_fac: FakeCamera = await fake_camera(
        serial=serial_fac,
        accounts={"admin": Account("password", CameraRole.ADMINISTRATOR)},
        default_password_in_use=True,
        first_password_gate=True,
    )

    # 1. add configured camera with SENTINEL_CONFIGURED
    res_add_cfg = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "add",
            "--host",
            cam_cfg.host,
            "--port",
            str(cam_cfg.port),
            "--password-stdin",
            "--data-dir",
            str(tmp_path),
        ],
        input=f"{SENTINEL_CONFIGURED}\n",
    )
    record_run(res_add_cfg)
    assert res_add_cfg.exit_code == 0

    # 2. add factory camera with SENTINEL_NEW (entered twice)
    res_add_fac = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "add",
            "--host",
            cam_fac.host,
            "--port",
            str(cam_fac.port),
            "--password-stdin",
            "--data-dir",
            str(tmp_path),
        ],
        input=f"{SENTINEL_NEW}\n{SENTINEL_NEW}\n",
    )
    record_run(res_add_fac)
    assert res_add_fac.exit_code == 0

    # 3. set-password for configured camera
    res_set_pw = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "set-password",
            "--serial",
            serial_cfg,
            "--password-stdin",
            "--data-dir",
            str(tmp_path),
        ],
        input=f"{SENTINEL_CONFIGURED}\n",
    )
    record_run(res_set_pw)
    assert res_set_pw.exit_code == 0

    # 4. rename camera
    res_rename = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "rename",
            "--serial",
            serial_cfg,
            "--name",
            "OfficeCam",
            "--data-dir",
            str(tmp_path),
        ],
    )
    record_run(res_rename)
    assert res_rename.exit_code == 0

    # 5. reprobe camera
    res_reprobe = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "reprobe",
            "--serial",
            serial_cfg,
            "--data-dir",
            str(tmp_path),
        ],
    )
    record_run(res_reprobe)
    assert res_reprobe.exit_code == 0

    # 6. list cameras
    res_list = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "list",
            "--data-dir",
            str(tmp_path),
        ],
    )
    record_run(res_list)
    assert res_list.exit_code == 0

    # 7. show camera
    res_show = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "show",
            "--serial",
            serial_cfg,
            "--data-dir",
            str(tmp_path),
        ],
    )
    record_run(res_show)
    assert res_show.exit_code == 0

    # 8. status
    res_status = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "status",
            "--data-dir",
            str(tmp_path),
        ],
    )
    record_run(res_status)
    assert res_status.exit_code == 0

    # 9. scan --json
    res_scan = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "scan",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
    )
    record_run(res_scan)

    # 10. failing add with wrong password
    res_fail = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "add",
            "--host",
            cam_cfg.host,
            "--port",
            str(cam_cfg.port),
            "--password-stdin",
            "--data-dir",
            str(tmp_path),
        ],
        input="WrongPasswordSentinel999!\n",
    )
    record_run(res_fail)
    assert res_fail.exit_code != 0

    # 11. Exception path: force DB failure during add
    with patch(
        "vizenlink_nvr.services.onboarding.OnboardingService.add",
        side_effect=RuntimeError("Simulated DB storage failure during onboarding"),
    ):
        res_exc = await asyncio.to_thread(
            cli.invoke,
            app,
            [
                "cameras",
                "add",
                "--host",
                cam_cfg.host,
                "--port",
                str(cam_cfg.port),
                "--password-stdin",
                "--data-dir",
                str(tmp_path),
            ],
            input=f"{SENTINEL_CONFIGURED}\n",
        )
        record_run(res_exc)

    # Assert neither sentinel appears in stdout, stderr, or caplog
    combined_outputs = "\n".join(all_stdout + all_stderr)
    assert SENTINEL_CONFIGURED not in combined_outputs, "SENTINEL_CONFIGURED leaked in CLI stdout/stderr!"
    assert SENTINEL_NEW not in combined_outputs, "SENTINEL_NEW leaked in CLI stdout/stderr!"

    log_text = caplog.text
    assert SENTINEL_CONFIGURED not in log_text, "SENTINEL_CONFIGURED leaked in application logs!"
    assert SENTINEL_NEW not in log_text, "SENTINEL_NEW leaked in application logs!"

    # Assert neither sentinel appears in raw bytes of sqlite files (nvr.db, -wal, -shm)
    db_files = [
        tmp_path / "nvr.db",
        tmp_path / "nvr.db-wal",
        tmp_path / "nvr.db-shm",
    ]
    checked_count = 0
    for db_f in db_files:
        if db_f.exists():
            checked_count += 1
            raw_bytes = db_f.read_bytes()
            assert SENTINEL_CONFIGURED.encode("utf-8") not in raw_bytes, (
                f"SENTINEL_CONFIGURED found in raw bytes of {db_f.name}!"
            )
            assert SENTINEL_NEW.encode("utf-8") not in raw_bytes, (
                f"SENTINEL_NEW found in raw bytes of {db_f.name}!"
            )

    assert checked_count >= 1, "Expected at least nvr.db to exist and be scanned"
