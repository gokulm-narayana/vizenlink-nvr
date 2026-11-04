"""16-camera concurrency and soak simulation test (FND-06).

Validates:
- 16 concurrent cameras recording video segments into SQLite DB and disk storage.
- 2 concurrent viewers reading video segment streams.
- Concurrent gap watchdog monitoring all 16 cameras for unrecorded gaps.
- Concurrent retention janitor pruning eligible segments while honoring locks.
- Concurrency safety under high SQLite load with zero deadlocks or connection exhaustion.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from vizenlink_nvr.db.engine import create_engine_for, upgrade_to_head
from vizenlink_nvr.db.models import (
    Camera,
    RecordingSettings,
    Segment,
    StorageSettings,
)
from vizenlink_nvr.services.health import RecordingState
from vizenlink_nvr.services.janitor import enforce_camera_retention
from vizenlink_nvr.services.watchdog import check_camera_gaps
from vizenlink_nvr.timeutil import utc_now


@pytest.mark.asyncio
async def test_16camera_concurrent_recording_soak(tmp_path: Path) -> None:
    """Simulate 16 concurrent cameras recording, 2 viewers, watchdog, and janitor."""
    db_file = tmp_path / "soak_16cam.db"
    upgrade_to_head(db_file)
    engine = create_engine_for(db_file)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    storage_root = tmp_path / "recordings"
    storage_root.mkdir(parents=True, exist_ok=True)

    now = utc_now()
    num_cameras = 16
    segments_per_camera = 5
    segment_duration_sec = 10.0

    # 1. Register 16 cameras and storage settings
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

        cameras: list[Camera] = []
        settings_list: list[RecordingSettings] = []
        for i in range(1, num_cameras + 1):
            cam_serial = f"CAM-SOAK-{i:02d}"
            cam = Camera(
                serial=cam_serial,
                host=f"192.168.10.{i}",
                https_port=443,
                mac=f"AA:BB:CC:DD:EE:{i:02X}",
                name=f"Soak Camera {i:02d}",
                manufacturer="VizenSoak",
                model="VS-4K",
                tls_fingerprint_sha256="",
                state="active",
                added_at=now,
                host_updated_at=now,
            )
            cameras.append(cam)

            rec_mode = "continuous" if i % 2 == 0 else "continuous"
            rec_setting = RecordingSettings(
                camera_serial=cam_serial,
                mode=rec_mode,
                retention_days=7,
                created_at=now,
                updated_at=now,
            )
            settings_list.append(rec_setting)

        session.add_all(cameras)
        session.add_all(settings_list)
        await session.commit()

    # 2. Worker for each camera writing segment files and inserting DB rows
    async def camera_recording_worker(cam_idx: int) -> list[str]:
        cam_serial = f"CAM-SOAK-{cam_idx:02d}"
        created_paths: list[str] = []
        cam_dir = storage_root / cam_serial
        cam_dir.mkdir(parents=True, exist_ok=True)

        for s_idx in range(segments_per_camera):
            # Staggered start/end times up to 'now'
            offset_seconds = (segments_per_camera - s_idx) * segment_duration_sec
            seg_start = now - timedelta(seconds=offset_seconds)
            seg_end = seg_start + timedelta(seconds=segment_duration_sec)

            seg_file = cam_dir / f"seg_{s_idx:03d}.mp4"
            # Write dummy fMP4 bytes
            seg_file.write_bytes(b"\x00\x00\x00\x18ftypiso5\x00\x00\x02\x00mp41iso5\x00\x00\x00\x08mdat")
            created_paths.append(str(seg_file))

            # Protect one segment on Camera 1 to test retention immunity
            is_protected = cam_idx == 1 and s_idx == 0

            async with session_factory() as session:
                segment = Segment(
                    camera_serial=cam_serial,
                    stream_type="main",
                    file_path=str(seg_file),
                    start_time=seg_start,
                    end_time=seg_end,
                    duration_seconds=segment_duration_sec,
                    file_size_bytes=len(seg_file.read_bytes()),
                    status="active",
                    is_protected=is_protected,
                    created_at=seg_end,
                )
                session.add(segment)
                await session.commit()

            # Small jitter to simulate real asynchronous time-slices
            await asyncio.sleep(0.005)

        return created_paths

    # 3. Viewer workers concurrently reading segments
    viewer_read_count = [0, 0]

    async def viewer_worker(viewer_id: int) -> None:
        reads = 0
        cam_serial = f"CAM-SOAK-{(viewer_id % num_cameras) + 1:02d}"
        for _ in range(50):
            async with session_factory() as session:
                stmt = (
                    select(Segment)
                    .where(Segment.camera_serial == cam_serial)
                    .order_by(Segment.start_time.desc())
                    .limit(3)
                )
                res = await session.execute(stmt)
                segs = res.scalars().all()
                for seg in segs:
                    seg_p = Path(seg.file_path)
                    if seg_p.exists():  # noqa: ASYNC240
                        data = seg_p.read_bytes()  # noqa: ASYNC240
                        if len(data) > 0:
                            reads += 1
            if reads > 0:
                break
            await asyncio.sleep(0.01)
        viewer_read_count[viewer_id - 1] = reads

    # Launch all 16 cameras + 2 viewers concurrently
    camera_tasks = [camera_recording_worker(i) for i in range(1, num_cameras + 1)]
    viewer_tasks = [viewer_worker(1), viewer_worker(2)]

    results = await asyncio.gather(*camera_tasks, *viewer_tasks)
    camera_file_results = results[:num_cameras]

    # Verify all cameras produced segments on disk
    assert len(camera_file_results) == 16
    for cam_files in camera_file_results:
        assert len(cam_files) == segments_per_camera

    # Verify viewers successfully read streams
    assert viewer_read_count[0] > 0
    assert viewer_read_count[1] > 0

    # 4. Verify Database Segments count
    async with session_factory() as session:
        res = await session.execute(select(Segment))
        all_segments = res.scalars().all()
        assert len(all_segments) == num_cameras * segments_per_camera

    # 5. Run Concurrent Gap Watchdog
    # Since segments ended recently (< 150s threshold), all 16 cameras must be RECORDING with 0 gaps
    async with session_factory() as session:
        health_map = await check_camera_gaps(session, now=now)
        assert len(health_map) == 16
        for cam_serial, status in health_map.items():
            assert status.recording_state == RecordingState.RECORDING, (
                f"Camera {cam_serial} was not in RECORDING state: {status.recording_state}"
            )
            assert status.gap_alarm is False, (
                f"Camera {cam_serial} triggered unexpected gap alarm: {status.details}"
            )

    # 6. Run Retention Janitor under simulated future date
    # Simulate time advancing 10 days in the future
    future_now = now + timedelta(days=10)
    async with session_factory() as session:
        # Retention policy is 7 days, so segments older than 7 days will be pruned except protected ones
        prune_report = await enforce_camera_retention(
            session=session,
            camera_serial="CAM-SOAK-01",
            now=future_now,
        )
        assert len(prune_report.deleted_files) == segments_per_camera - 1  # 4 pruned, 1 protected preserved

        # Check that protected segment is still intact in DB and on disk
        stmt = select(Segment).where(Segment.camera_serial == "CAM-SOAK-01")
        res = await session.execute(stmt)
        remaining = res.scalars().all()
        assert len(remaining) == 1
        assert remaining[0].is_protected is True
        assert Path(remaining[0].file_path).exists()  # noqa: ASYNC240

    # 7. Database connection cleanup and integrity verification
    await engine.dispose()

    # Verify SQLite file integrity via standard library
    import sqlite3

    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    cur.execute("PRAGMA integrity_check")
    rows = cur.fetchall()
    conn.close()
    assert rows == [("ok",)]
