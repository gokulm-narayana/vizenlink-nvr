"""Integration tests proving independent process supervision and core crash survivability (FND-01)."""

from __future__ import annotations

import json
import socket
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.db.models import Camera, CameraStream
from vizenlink_nvr.media.binary import resolve_binary
from vizenlink_nvr.media.config import (
    MediaMtxPorts,
    build_config,
    hash_control_password,
    write_config,
)
from vizenlink_nvr.media.process import MediaMtxProcess
from vizenlink_nvr.media.reconciler import get_control_password
from vizenlink_nvr.services.recording_settings import RecordingMode, set_recording_mode
from vizenlink_nvr.services.runtime import open_runtime
from vizenlink_nvr.timeutil import utc_now

pytestmark = [pytest.mark.mediamtx, pytest.mark.timeout(60)]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_core_crash_survivability_and_resync(
    cli: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MediaMTX continues running after NVR Core exits, and restarted Core re-syncs state cleanly."""
    data_dir = tmp_path / "nvr_data"
    api_port = _free_port()
    ports = MediaMtxPorts(
        api=api_port,
        playback=_free_port(),
        rtsp=_free_port(),
        hls=_free_port(),
        webrtc=_free_port(),
        webrtc_udp=_free_port(),
    )

    settings = load_settings(data_dir=data_dir)
    # Ensure control password is created and matches config
    control_pw = get_control_password(settings)
    cfg = build_config(ports, hash_control_password(control_pw))
    cfg_path = tmp_path / "mediamtx.yml"
    write_config(cfg_path, cfg)

    binary = resolve_binary(settings)
    proc = MediaMtxProcess(binary, cfg_path)
    proc.start()

    # Route CLI reconcile calls to this live test MediaMTX instance
    api_base = f"http://127.0.0.1:{api_port}"
    monkeypatch.setenv("NVR_MEDIAMTX_API_URL", api_base)

    try:
        # 1. Initialize NVR database and seed a registered camera with continuous recording
        cli.invoke(app, ["status", "--data-dir", str(data_dir)])

        import asyncio

        async def _seed_cam() -> None:
            async with open_runtime(settings) as rt:
                async with rt.sessions() as session:
                    now = utc_now()
                    cam = Camera(
                        serial="VZL-CAM-001",
                        host="192.168.1.100",
                        https_port=443,
                        mac="AA:BB:CC:DD:EE:01",
                        name="Front Gate",
                        state="active",
                        tls_fingerprint_sha256="sha256_cam_fp",
                        added_at=now,
                        host_updated_at=now,
                    )
                    stream = CameraStream(
                        serial="VZL-CAM-001",
                        role="main",
                        profile_token="p1",
                        profile_name="Main",
                        venc_token="v1",
                        codec="H264",
                        width=1920,
                        height=1080,
                        transport="tcp",
                        scheme="rtsp",
                        port=554,
                        path="/live/main",
                        source="nuraeye",
                        sub_is_main=False,
                        probed_at=now,
                    )
                    session.add_all([cam, stream])
                    await set_recording_mode(session, "VZL-CAM-001", RecordingMode.CONTINUOUS)
                    await session.commit()

        asyncio.run(_seed_cam())

        # Allow system disk for testing in tmp_path
        cli.invoke(
            app,
            [
                "storage",
                "set-path",
                "--path",
                str(data_dir / "recordings"),
                "--allow-system-disk",
                "--data-dir",
                str(data_dir),
            ],
        )

        # 2. Run reconcile: MediaMTX acquires the camera path
        res1 = cli.invoke(app, ["recording", "reconcile", "--json", "--data-dir", str(data_dir)])
        assert res1.exit_code == 0, res1.output
        data1 = json.loads(res1.stdout)
        assert "cam/vzl-cam-001/main" in data1["added"]

        # 3. Simulate Core crash / exit: the Python CLI process has exited.
        # MediaMTX must remain actively running.
        assert proc.popen is not None
        assert proc.popen.poll() is None, "MediaMTX daemon crashed after Core exit!"

        # Direct loopback API check confirms MediaMTX retains the path
        async def _check_mtx_path() -> dict[str, object]:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{api_base}/v3/config/paths/get/cam/vzl-cam-001/main",
                    auth=("nvr-control", control_pw),
                )
                assert resp.status_code == 200
                return resp.json()  # type: ignore[no-any-return]

        path_info = asyncio.run(_check_mtx_path())
        assert path_info["record"] is True

        # 4. Restart Core: run reconcile again, verify state is clean (unchanged)
        res2 = cli.invoke(app, ["recording", "reconcile", "--json", "--data-dir", str(data_dir)])
        assert res2.exit_code == 0, res2.output
        data2 = json.loads(res2.stdout)
        assert data2["added"] == []
        assert data2["patched"] == []
        assert data2["deleted"] == []
        assert "cam/vzl-cam-001/main" in data2["unchanged"]

        # 5. Core updates policy: toggle camera recording off
        res_off = cli.invoke(
            app,
            [
                "recording",
                "set-mode",
                "--serial",
                "VZL-CAM-001",
                "--mode",
                "off",
                "--data-dir",
                str(data_dir),
            ],
        )
        assert res_off.exit_code == 0, res_off.output

        # 6. Reconciler applies update: MediaMTX patches path to record=False
        res3 = cli.invoke(app, ["recording", "reconcile", "--json", "--data-dir", str(data_dir)])
        assert res3.exit_code == 0, res3.output
        data3 = json.loads(res3.stdout)
        assert "cam/vzl-cam-001/main" in data3["patched"]

        path_info_patched = asyncio.run(_check_mtx_path())
        assert path_info_patched["record"] is False
    finally:
        proc.stop()
