"""Integration tests for 0003_recording_core migration, cascading deletes, and rollback."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from vizenlink_nvr.db.engine import (
    alembic_config,
    create_engine_for,
    current_revision,
    upgrade_to_head,
)
from vizenlink_nvr.db.models import Camera, RecordingSettings, Segment, StorageSettings
from vizenlink_nvr.timeutil import UTC


def test_migration_0003_upgrade_and_downgrade(tmp_path: Path) -> None:
    """Test upgrade to 0003, downgrade to 0002, and re-upgrade."""
    db_file = tmp_path / "test_migration.db"
    assert not db_file.exists()

    cfg = alembic_config(db_file)

    # 1. Upgrade to 0003
    command.upgrade(cfg, "0003_recording_core")
    assert current_revision(db_file) == "0003_recording_core"

    # 2. Downgrade to 0002
    command.downgrade(cfg, "0002_camera_registry")
    assert current_revision(db_file) == "0002_camera_registry"

    # 3. Re-upgrade to 0003
    command.upgrade(cfg, "0003_recording_core")
    assert current_revision(db_file) == "0003_recording_core"


@pytest.mark.asyncio
async def test_cascading_deletes_on_camera_removal(tmp_path: Path) -> None:
    """Test foreign key cascading delete: deleting camera deletes recording_settings and segments."""
    db_file = tmp_path / "cascade_test.db"
    upgrade_to_head(db_file)

    engine = create_engine_for(db_file)

    now = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_maker() as session:
        # Insert camera
        cam = Camera(
            serial="VZL-CAM-CASCADE",
            host="127.0.0.1",
            https_port=443,
            tls_fingerprint_sha256="dummy",
            added_at=now,
            host_updated_at=now,
        )
        session.add(cam)
        await session.flush()

        # Insert recording settings
        rec = RecordingSettings(
            camera_serial="VZL-CAM-CASCADE",
            mode="continuous",
            schedule_json="{}",
            audio_enabled=False,
            created_at=now,
            updated_at=now,
        )
        session.add(rec)

        rec_dir = tmp_path / "recordings"
        seg_file = rec_dir / "seg1.mp4"

        # Insert segment
        seg = Segment(
            camera_serial="VZL-CAM-CASCADE",
            stream_type="main",
            file_path=str(seg_file),
            start_time=now,
            end_time=now,
            duration_seconds=60.0,
            file_size_bytes=1024,
            status="active",
            created_at=now,
        )
        session.add(seg)

        # Insert storage settings
        storage = StorageSettings(
            id=1,
            storage_path=str(rec_dir),
            allow_system_disk=True,
            reserve_bytes=1000,
            created_at=now,
            updated_at=now,
        )
        session.add(storage)

        await session.commit()

    # Verify rows exist
    async with session_maker() as session:
        r = await session.execute(
            select(RecordingSettings).where(RecordingSettings.camera_serial == "VZL-CAM-CASCADE")
        )
        assert r.scalar_one() is not None

        s = await session.execute(
            select(Segment).where(Segment.camera_serial == "VZL-CAM-CASCADE")
        )
        assert s.scalar_one() is not None

    # Delete the camera
    async with session_maker() as session:
        await session.execute(delete(Camera).where(Camera.serial == "VZL-CAM-CASCADE"))
        await session.commit()

    # Verify cascade deleted recording_settings and segments
    async with session_maker() as session:
        r = await session.execute(
            select(RecordingSettings).where(RecordingSettings.camera_serial == "VZL-CAM-CASCADE")
        )
        assert r.scalar_one_or_none() is None

        s = await session.execute(
            select(Segment).where(Segment.camera_serial == "VZL-CAM-CASCADE")
        )
        assert s.scalar_one_or_none() is None

        # Storage settings should remain intact
        st = await session.execute(select(StorageSettings).where(StorageSettings.id == 1))
        assert st.scalar_one() is not None

    await engine.dispose()
