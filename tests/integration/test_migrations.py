"""Integration tests for database migrations, UtcDateTime, runtime, and status."""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import select

from vizenlink_nvr.config import NvrSettings
from vizenlink_nvr.db.engine import (
    alembic_config,
    current_revision,
    head_revision,
    upgrade_to_head,
)
from vizenlink_nvr.db.models import AppSetting
from vizenlink_nvr.paths import db_path
from vizenlink_nvr.services.runtime import open_runtime
from vizenlink_nvr.services.status import get_status
from vizenlink_nvr.timeutil import EPOCH, UTC, FakeClock


def test_migration_upgrade_and_drift_check(tmp_path: Path) -> None:
    """Test idempotent upgrade and assert alembic check detects no drift."""
    database_file = tmp_path / "nvr.db"
    assert not database_file.exists()

    # Initial upgrade
    upgrade_to_head(database_file)
    assert database_file.exists()

    cur = current_revision(database_file)
    head = head_revision()
    assert cur == head

    # Idempotent second upgrade
    upgrade_to_head(database_file)
    assert current_revision(database_file) == head

    # Check for schema drift against Base.metadata
    cfg = alembic_config(database_file)
    command.check(cfg)


@pytest.mark.asyncio
async def test_runtime_open_and_permissions(tmp_path: Path) -> None:
    """Test open_runtime sets 0o600 mode on POSIX and reports healthy status."""
    settings = NvrSettings(data_dir=tmp_path)
    database_file = db_path(settings)

    fake_now = datetime(2026, 10, 27, 10, 0, 0, tzinfo=UTC)
    clock = FakeClock(fake_now)

    async with open_runtime(settings, clock=clock) as rt:
        if os.name == "posix":
            mode = os.stat(database_file).st_mode & 0o777
            assert mode == 0o600

        report = await get_status(rt)
        assert report.db_ok is True
        expected_head = head_revision()
        assert report.schema_revision == expected_head
        assert report.schema_head == expected_head
        assert report.data_dir == str(tmp_path)


@pytest.mark.asyncio
async def test_utc_datetime_column_handling(tmp_path: Path) -> None:
    """Test UtcDateTime stores epoch microseconds, handles timezones, and rejects naive datetimes."""
    settings = NvrSettings(data_dir=tmp_path)
    clock = FakeClock(EPOCH)

    async with open_runtime(settings, clock=clock) as rt:
        # 1. Round-trip at epoch (1970-01-01T00:00:00Z)
        async with rt.sessions() as session:
            setting_epoch = AppSetting(
                key="test_epoch",
                value='"val1"',
                updated_at=EPOCH,
            )
            session.add(setting_epoch)
            await session.commit()

        async with rt.sessions() as session:
            stmt = select(AppSetting).where(AppSetting.key == "test_epoch")
            res = (await session.execute(stmt)).scalar_one()
            assert res.updated_at == EPOCH
            assert res.updated_at.tzinfo == UTC

        # 2. Round-trip with 999999 microseconds
        dt_us = datetime(2026, 10, 27, 15, 30, 45, 999999, tzinfo=UTC)
        async with rt.sessions() as session:
            setting_us = AppSetting(
                key="test_us",
                value='"val2"',
                updated_at=dt_us,
            )
            session.add(setting_us)
            await session.commit()

        async with rt.sessions() as session:
            stmt = select(AppSetting).where(AppSetting.key == "test_us")
            res = (await session.execute(stmt)).scalar_one()
            assert res.updated_at == dt_us

        # 3. Aware non-UTC datetime (e.g. +05:30) converted to UTC
        ist = timezone(timedelta(hours=5, minutes=30))
        dt_ist = datetime(2026, 10, 27, 21, 0, 0, 0, tzinfo=ist)
        async with rt.sessions() as session:
            setting_ist = AppSetting(
                key="test_ist",
                value='"val3"',
                updated_at=dt_ist,
            )
            session.add(setting_ist)
            await session.commit()

        async with rt.sessions() as session:
            stmt = select(AppSetting).where(AppSetting.key == "test_ist")
            res = (await session.execute(stmt)).scalar_one()
            assert res.updated_at == dt_ist.astimezone(UTC)
            assert res.updated_at.tzinfo == UTC

        # 4. Naive datetime raises ValueError on bind
        naive_dt = datetime(2026, 10, 27, 12, 0, 0)  # noqa: DTZ001
        async with rt.sessions() as session:
            setting_naive = AppSetting(
                key="test_naive",
                value='"val4"',
                updated_at=naive_dt,
            )
            session.add(setting_naive)
            with pytest.raises((ValueError, Exception), match="Naive datetime"):
                await session.commit()
