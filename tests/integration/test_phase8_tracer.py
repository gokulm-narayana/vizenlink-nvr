"""End-to-end integration tracer for Phase 08: Cross-Platform Packaging & Soak.

Validates:
- FND-06: Cross-platform packaging, host sleep prevention, atomic backup/restore, and soak stability.
  - Step 1: System service definitions for Linux (systemd), macOS (launchd), and Windows.
  - Step 2: PowerManager host sleep inhibition and graceful release.
  - Step 3: Atomic SQLite backup snapshotting with SHA-256 manifests and rollback restore.
  - Step 4: Multi-camera concurrent streaming, segment indexing, viewer playback, and gapless health.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from vizenlink_nvr.db.engine import create_engine_for, upgrade_to_head
from vizenlink_nvr.db.models import Camera, RecordingSettings, Segment, StorageSettings
from vizenlink_nvr.service.installer import ServiceManager
from vizenlink_nvr.service.power import PowerManager
from vizenlink_nvr.services.backup import create_backup, restore_backup, verify_backup
from vizenlink_nvr.services.health import RecordingState
from vizenlink_nvr.services.watchdog import check_camera_gaps
from vizenlink_nvr.timeutil import utc_now


@pytest.mark.asyncio
async def test_phase8_complete_e2e_tracer(tmp_path: Path) -> None:
    """Execute complete end-to-end lifecycle tracer for Phase 08."""
    # -------------------------------------------------------------------------
    # Step 1: Cross-Platform Service Packaging Validation
    # -------------------------------------------------------------------------
    for os_name, exp_kw in [
        ("linux", "Restart=always"),
        ("darwin", "<key>KeepAlive</key>"),
        ("windows", "<onfailure action=\"restart\""),
    ]:
        mgr = ServiceManager(target_os=os_name)  # type: ignore[arg-type]
        unit_text = mgr.get_service_content(exec_path="/opt/nvr/bin/nvr")
        assert exp_kw in unit_text
        filename = mgr.get_service_filename()
        svc_file = tmp_path / filename
        svc_file.write_text(unit_text, encoding="utf-8")
        assert svc_file.exists()

    # -------------------------------------------------------------------------
    # Step 2: Host Power Management & Sleep Prevention
    # -------------------------------------------------------------------------
    pm = PowerManager(target_os="darwin")
    fake_proc = MagicMock()
    fake_proc.pid = 44444

    with (
        patch("shutil.which", return_value="/usr/bin/caffeinate"),
        patch("subprocess.Popen", return_value=fake_proc),
    ):
        with pm:
            assert pm.is_inhibited is True
        assert not pm.is_inhibited
        fake_proc.terminate.assert_called_once()

    # -------------------------------------------------------------------------
    # Step 3: SQLite Online Backup, Manifest Verification & Rollback Restore
    # -------------------------------------------------------------------------
    db_file = tmp_path / "tracer_phase8.db"
    upgrade_to_head(db_file)

    # Insert initial canary data
    import sqlite3

    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE canary_data (id INTEGER PRIMARY KEY, msg TEXT)")
    conn.execute("INSERT INTO canary_data (msg) VALUES ('baseline_v1')")
    conn.commit()
    conn.close()

    backup_dir = tmp_path / "backups"
    backup_file, meta = create_backup(db_file, output_dir=backup_dir)
    assert backup_file.exists()
    assert meta["sha256"]
    assert verify_backup(backup_file)["integrity"] == "ok"

    # Mutate DB after backup
    conn = sqlite3.connect(str(db_file))
    conn.execute("INSERT INTO canary_data (msg) VALUES ('corrupted_unwanted_v2')")
    conn.commit()
    count_after_mutation = conn.execute("SELECT count(*) FROM canary_data").fetchone()[0]
    conn.close()
    assert count_after_mutation == 2

    # Safely restore backup
    restore_report = restore_backup(backup_file, db_file)
    assert restore_report["status"] == "restored"
    assert restore_report["rollback_created"] is not None

    conn = sqlite3.connect(str(db_file))
    restored_count = conn.execute("SELECT count(*) FROM canary_data").fetchone()[0]
    conn.close()
    assert restored_count == 1  # Successfully rolled back to baseline

    # -------------------------------------------------------------------------
    # Step 4: Multi-Camera Concurrency & Soak Simulation
    # -------------------------------------------------------------------------
    engine = create_engine_for(db_file)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    storage_root = tmp_path / "recordings"
    storage_root.mkdir(parents=True, exist_ok=True)

    now = utc_now()
    tracer_cameras = 8
    segments_each = 3
    duration = 10.0

    async with session_factory() as session:
        storage_setting = StorageSettings(
            id=1,
            storage_path=str(storage_root),
            allow_system_disk=True,
            reserve_bytes=1024 * 1024,
            created_at=now,
            updated_at=now,
        )
        session.add(storage_setting)

        cameras = []
        rec_settings = []
        for i in range(1, tracer_cameras + 1):
            cam_serial = f"CAM-P8-{i:02d}"
            cameras.append(
                Camera(
                    serial=cam_serial,
                    host=f"192.168.20.{i}",
                    https_port=443,
                    mac=f"AA:BB:CC:DD:EE:{i:02X}",
                    name=f"Phase 8 Cam {i:02d}",
                    tls_fingerprint_sha256="",
                    state="active",
                    added_at=now,
                    host_updated_at=now,
                )
            )
            rec_settings.append(
                RecordingSettings(
                    camera_serial=cam_serial,
                    mode="continuous",
                    retention_days=14,
                    created_at=now,
                    updated_at=now,
                )
            )
        session.add_all(cameras)
        session.add_all(rec_settings)
        await session.commit()

    async def rec_worker(cam_idx: int) -> None:
        serial = f"CAM-P8-{cam_idx:02d}"
        cam_dir = storage_root / serial
        cam_dir.mkdir(parents=True, exist_ok=True)

        for s in range(segments_each):
            s_start = now - timedelta(seconds=(segments_each - s) * duration)
            s_end = s_start + timedelta(seconds=duration)
            seg_f = cam_dir / f"p8_seg_{s}.mp4"
            seg_f.write_bytes(b"\x00\x00\x00\x18ftypiso5\x00\x00\x02\x00mp41iso5\x00\x00\x00\x08mdat")

            async with session_factory() as session:
                segment = Segment(
                    camera_serial=serial,
                    stream_type="main",
                    file_path=str(seg_f),
                    start_time=s_start,
                    end_time=s_end,
                    duration_seconds=duration,
                    file_size_bytes=len(seg_f.read_bytes()),
                    status="active",
                    is_protected=False,
                    created_at=s_end,
                )
                session.add(segment)
                await session.commit()
            await asyncio.sleep(0.005)

    async def viewer_worker() -> int:
        reads = 0
        for _ in range(5):
            async with session_factory() as session:
                res = await session.execute(select(Segment).limit(2))
                for seg in res.scalars().all():
                    if Path(seg.file_path).exists():  # noqa: ASYNC240
                        data = Path(seg.file_path).read_bytes()  # noqa: ASYNC240
                        if len(data) > 0:
                            reads += 1
            await asyncio.sleep(0.01)
        return reads

    cam_tasks = [rec_worker(i) for i in range(1, tracer_cameras + 1)]
    v_task = viewer_worker()

    _, reads = await asyncio.gather(asyncio.gather(*cam_tasks), v_task)
    assert reads > 0

    # Verify gap watchdog verifies all cameras RECORDING with no alarms
    async with session_factory() as session:
        health_map = await check_camera_gaps(session, now=now)
        assert len(health_map) == tracer_cameras
        for _c_serial, h in health_map.items():
            assert h.recording_state == RecordingState.RECORDING
            assert h.gap_alarm is False

    await engine.dispose()
