"""Unit tests for retention storage footprint estimation (REC-06)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.db.engine import create_engine_for
from vizenlink_nvr.db.models import Base, Camera, RecordingSettings
from vizenlink_nvr.services.janitor import estimate_retention
from vizenlink_nvr.timeutil import utc_now


@pytest.mark.asyncio
async def test_retention_estimation_calculations(tmp_path: Path) -> None:
    """estimate_retention calculates daily GB and projects retention days accurately."""
    db_file = tmp_path / "test_retention_est.db"
    engine = create_engine_for(db_file)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    now = utc_now()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        cam = Camera(
            serial="VZL-CAM-EST",
            host="192.168.1.10",
            https_port=443,
            mac="AA:BB:CC:DD:EE:01",
            name="Est Cam",
            state="active",
            tls_fingerprint_sha256="fp_est",
            added_at=now,
            host_updated_at=now,
        )
        session.add(cam)

        # Configured: 30 days, 200 GB cap
        rec_set = RecordingSettings(
            camera_serial="VZL-CAM-EST",
            mode="continuous",
            schedule_json="{}",
            audio_enabled=False,
            retention_days=30,
            retention_max_gb=200,
            created_at=now,
            updated_at=now,
        )
        session.add(rec_set)
        await session.commit()

        # At 4000 kbps:
        # bytes_per_day = (4000 * 1000 / 8) * 86400 = 43,200,000,000 bytes
        # gb_per_day = 43,200,000,000 / (1024^3) = ~40.23 GB
        # At 200 GB quota: 200 / 40.23 = ~5.0 days
        # Configured days: 30
        # Effective days: min(30, 5.0) = 5.0 days
        est = await estimate_retention(session, "VZL-CAM-EST", avg_bitrate_kbps=4000)

        assert est.camera_serial == "VZL-CAM-EST"
        assert est.gb_per_day > 0
        assert est.configured_days == 30
        assert est.configured_max_gb == 200
        assert est.effective_days == 5.0

        # Now test with larger quota: 2000 GB
        rec_set.retention_max_gb = 2000  # 2000 / 40.23 = ~49.7 days
        # Effective days: min(30, 49.7) = 30.0 days (bounded by configured_days)
        await session.commit()

        est_large = await estimate_retention(session, "VZL-CAM-EST", avg_bitrate_kbps=4000)
        assert est_large.effective_days == 30.0

        # Unbounded retention
        rec_set.retention_days = None
        rec_set.retention_max_gb = None
        await session.commit()

        est_unbounded = await estimate_retention(session, "VZL-CAM-EST", avg_bitrate_kbps=4000)
        assert est_unbounded.effective_days is None

    await engine.dispose()

