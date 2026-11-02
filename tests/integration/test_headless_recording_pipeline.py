"""End-to-end headless recording pipeline tracer integration test.

Validates FND-01, FND-02, REC-01, REC-07, REC-09, HLTH-01, HLTH-03.
"""

from __future__ import annotations

import json
import struct
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.db.models import (
    Camera,
    CameraCredential,
    CameraStream,
    RecordingSettings,
    Segment,
)
from vizenlink_nvr.media.reconciler import compute_desired_paths
from vizenlink_nvr.secrets.vault import open_vault
from vizenlink_nvr.services.janitor import enforce_disk_low_water_mark
from vizenlink_nvr.services.runtime import open_runtime
from vizenlink_nvr.timeutil import utc_now


def build_synthetic_fmp4(part_count: int = 5) -> bytes:
    """Generate a valid fragmented MP4 (fMP4) byte sequence for pipeline testing."""
    buffer = bytearray()
    ftyp_payload = b"isom" + struct.pack(">I", 512) + b"isomiso2mp41"
    buffer.extend(struct.pack(">I", 8 + len(ftyp_payload)) + b"ftyp" + ftyp_payload)

    mvhd_payload = b"\x00" * 4 + b"\x00" * 96
    mvhd = struct.pack(">I", 8 + len(mvhd_payload)) + b"mvhd" + mvhd_payload
    trex_payload = b"\x00" * 4 + struct.pack(">IIII", 1, 1, 1000, 0)
    trex = struct.pack(">I", 8 + len(trex_payload)) + b"trex" + trex_payload
    mvex = struct.pack(">I", 8 + len(trex)) + b"mvex" + trex

    moov_payload = mvhd + mvex
    buffer.extend(struct.pack(">I", 8 + len(moov_payload)) + b"moov" + moov_payload)

    for seq in range(1, part_count + 1):
        mfhd_payload = b"\x00" * 4 + struct.pack(">I", seq)
        mfhd = struct.pack(">I", 8 + len(mfhd_payload)) + b"mfhd" + mfhd_payload
        tfhd_payload = b"\x00" * 4 + struct.pack(">I", 1)
        tfhd = struct.pack(">I", 8 + len(tfhd_payload)) + b"tfhd" + tfhd_payload
        trun_payload = b"\x00" * 4 + struct.pack(">I", 1) + struct.pack(">II", 1000, 256)
        trun = struct.pack(">I", 8 + len(trun_payload)) + b"trun" + trun_payload
        traf_payload = tfhd + trun
        traf = struct.pack(">I", 8 + len(traf_payload)) + b"traf" + traf_payload
        moof_payload = mfhd + traf
        buffer.extend(struct.pack(">I", 8 + len(moof_payload)) + b"moof" + moof_payload)

        media_bytes = b"\x00\x00\x00\x01\x67" + b"\xFF" * 251
        buffer.extend(struct.pack(">I", 8 + len(media_bytes)) + b"mdat" + media_bytes)

    return bytes(buffer)


@pytest.fixture
def pipeline_env(tmp_path: Path, cli: CliRunner) -> tuple[Path, Path]:
    """Initialize NVR environment and database for the end-to-end pipeline tracer."""
    data_dir = tmp_path / "nvr_pipeline_data"
    rec_dir = data_dir / "recordings"

    # Initialize DB migrations
    init_res = cli.invoke(app, ["status", "--data-dir", str(data_dir)])
    assert init_res.exit_code == 0, init_res.output

    return data_dir, rec_dir


def test_headless_recording_pipeline_e2e(
    cli: CliRunner,
    pipeline_env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Execute complete headless recording lifecycle tracer from onboarding to camera removal.

    Lifecycle:
    1. Camera added to database with encrypted credentials & RTSP stream.
    2. Reconciler synthesizes declarative MediaMTX recording path with 60s fMP4 parameters.
    3. MediaMTX hook executes with environment variables to index 60s fMP4 segment.
    4. nvr recording status displays green ONLINE and RECORDING health badges.
    5. Janitor proactively prunes oldest segments under disk low-water condition.
    6. Camera removed with --keep-recordings preserving footage on disk (CAM-09).
    """
    data_dir, rec_dir = pipeline_env
    settings = load_settings(data_dir=data_dir)
    serial = "VZL-PIPELINE-01"
    now = utc_now()

    # Step 1: Seed Camera and Stream in Database with encrypted credentials
    async def _onboard() -> None:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                cam = Camera(
                    serial=serial,
                    host="127.0.0.1",
                    https_port=443,
                    mac="00:11:22:33:44:55",
                    name="Pipeline Test Camera",
                    location="Main Gate",
                    group_tag="perimeter",
                    manufacturer="NuraEye",
                    model="NE-4K",
                    firmware_version="v2.1.0",
                    hardware_id="HW-PIPE-01",
                    tls_fingerprint_sha256="sha256_pipeline_cert",
                    state="active",
                    camera_id_check=True,
                    added_at=now,
                    host_updated_at=now,
                )
                stream = CameraStream(
                    serial=serial,
                    role="main",
                    profile_token="prof1",
                    profile_name="MainProfile",
                    venc_token="venc1",
                    codec="h264",
                    width=3840,
                    height=2160,
                    transport="tcp",
                    scheme="rtsp",
                    port=554,
                    path="/live/main",
                    source="nuraeye",
                    sub_is_main=False,
                    probed_at=now,
                )
                rec_settings = RecordingSettings(
                    camera_serial=serial,
                    mode="continuous",
                    audio_enabled=False,
                    retention_days=7,
                    created_at=now,
                    updated_at=now,
                )
                session.add_all([cam, stream, rec_settings])

                # Store camera password securely in vault
                from pydantic import SecretStr

                vault = await open_vault(rt)
                sealed = vault.seal(serial, "admin", SecretStr("secure_camera_secret_xyz"))
                cred = CameraCredential(
                    serial=serial,
                    username="admin",
                    ciphertext=sealed.ciphertext,
                    nonce=sealed.nonce,
                    key_id=sealed.key_id,
                    enc_version=sealed.enc_version,
                    updated_at=now,
                )
                session.add(cred)

                await session.commit()

    import asyncio

    asyncio.run(_onboard())

    # Step 2: Reconciler computes MediaMTX path configuration
    async def _check_reconcile() -> None:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                vault = await open_vault(rt)
                paths = await compute_desired_paths(
                    session=session,
                    storage_path=rec_dir,
                    volume_ok=True,
                    tz_name="UTC",
                    vault=vault,
                )
                # Verify path format
                path_name = f"cam/{serial.lower()}/main"
                assert path_name in paths
                spec = paths[path_name]
                assert spec.record is True
                assert spec.record_format == "fmp4"
                assert spec.record_part_duration == "1s"
                assert spec.record_segment_duration == "60s"
                assert spec.record_delete_after == "0s"
                assert "%path" in spec.record_path
                assert "%f" in spec.record_path
                assert spec.run_on_record_segment_complete == "nvr recording hook-segment-complete"

    asyncio.run(_check_reconcile())

    # Step 3: Simulate MediaMTX completed fMP4 segment and hook invocation
    seg_dir = rec_dir / "cam" / serial.lower() / now.strftime("%Y/%m/%d")
    seg_dir.mkdir(parents=True, exist_ok=True)
    seg_time_str = now.strftime("%Y-%m-%dT%H-%M-%SZ-000000")
    seg_file = seg_dir / f"{seg_time_str}.mp4"

    # Write valid synthetic fMP4 segment (60 parts = 60s)
    fmp4_content = build_synthetic_fmp4(part_count=60)
    seg_file.write_bytes(fmp4_content)

    hook_env = {
        "MTX_PATH": f"cam/{serial.lower()}/main",
        "MTX_SEGMENT_PATH": str(seg_file),
        "MTX_SEGMENT_DURATION": "60.05",
    }
    for k, v in hook_env.items():
        monkeypatch.setenv(k, v)

    # Invoke real-time hook without arguments (REC-09)
    hook_res = cli.invoke(
        app,
        ["recording", "hook-segment-complete", "--data-dir", str(data_dir)],
    )
    assert hook_res.exit_code == 0, hook_res.output

    # Step 4: Verify segment is indexed into SQLite segments table
    async def _verify_segment_indexed() -> None:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                stmt = select(Segment).where(Segment.camera_serial == serial)
                res = await session.execute(stmt)
                indexed_segs = res.scalars().all()
                assert len(indexed_segs) == 1
                s = indexed_segs[0]
                assert s.file_path == str(seg_file)
                assert s.duration_seconds == 60.05
                assert s.file_size_bytes == len(fmp4_content)
                assert s.status == "active"
                assert s.is_protected is False

    asyncio.run(_verify_segment_indexed())

    # Step 5: Verify nvr recording status displays dual health badges (HLTH-01, HLTH-03)
    status_res = cli.invoke(
        app,
        ["recording", "status", "--json", "--data-dir", str(data_dir)],
    )
    assert status_res.exit_code == 0, status_res.output
    status_data = json.loads(status_res.stdout)
    cam_status = [c for c in status_data["cameras"] if c["camera_serial"] == serial][0]

    assert cam_status["online_state"] == "online"
    assert cam_status["recording_state"] == "recording"
    assert cam_status["gap_alarm"] is False
    assert cam_status["mode"] == "continuous"

    # Step 6: Janitor low-water mark pruning test
    # Mark the current active segment as protected to prove immune to disk pruning
    async def _protect_active_segment() -> None:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                stmt = select(Segment).where(Segment.file_path == str(seg_file))
                s = (await session.execute(stmt)).scalar_one()
                s.is_protected = True
                await session.commit()

    asyncio.run(_protect_active_segment())

    # Add an older unprotected segment to verify low-water mark pruning under low disk space
    old_file = seg_dir / "2026-11-02T10-00-00Z-000000.mp4"
    old_file.write_bytes(b"\x00" * 8192)

    async def _add_old_and_prune() -> None:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                old_seg = Segment(
                    camera_serial=serial,
                    stream_type="main",
                    file_path=str(old_file),
                    start_time=now - timedelta(hours=2),
                    end_time=now - timedelta(hours=2, seconds=-60),
                    duration_seconds=60.0,
                    file_size_bytes=8192,
                    status="active",
                    is_protected=False,
                    created_at=now - timedelta(hours=2),
                )
                session.add(old_seg)
                await session.commit()

                # Mock disk usage to trigger low-water pruning: 5 GB free < 10 GB reserve
                from collections import namedtuple

                DiskUsage = namedtuple("DiskUsage", ["total", "used", "free"])
                monkeypatch.setattr(
                    "shutil.disk_usage",
                    lambda p: DiskUsage(total=100 * 1024**3, used=95 * 1024**3, free=5 * 1024**3),
                )

                report = await enforce_disk_low_water_mark(
                    session=session,
                    storage_path=rec_dir,
                    reserve_bytes=10 * 1024**3,
                )
                assert report.triggered is True
                assert report.deleted_count >= 1
                assert not old_file.exists()
                # Protected segment MUST be preserved
                assert seg_file.exists()

    asyncio.run(_add_old_and_prune())

    # Step 7: Camera removal with --keep-recordings (CAM-09)
    # The active segment file must remain intact on disk after camera deletion
    assert seg_file.exists()

    rem_res = cli.invoke(
        app,
        [
            "cameras",
            "remove",
            "--serial",
            serial,
            "--keep-recordings",
            "--data-dir",
            str(data_dir),
        ],
    )
    assert rem_res.exit_code == 0, rem_res.output
    assert "successfully removed" in rem_res.output

    # Crucial CAM-09 verification: file remains on disk
    assert seg_file.exists()

    # Verify camera row is removed from registry
    async def _verify_removed() -> None:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                cam = await session.get(Camera, serial)
                assert cam is None

    asyncio.run(_verify_removed())

    # Step 8: Security verification - secret password must NEVER appear in outputs or logs
    assert "secure_camera_secret_xyz" not in hook_res.output
    assert "secure_camera_secret_xyz" not in status_res.output
    assert "secure_camera_secret_xyz" not in rem_res.output
