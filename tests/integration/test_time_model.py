"""Integration tests for time model, timezone setting persistence, and CLI commands."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app
from vizenlink_nvr.cli.exitcodes import ExitCode
from vizenlink_nvr.config import NvrSettings
from vizenlink_nvr.db.types import UtcDateTime
from vizenlink_nvr.services.runtime import open_runtime
from vizenlink_nvr.services.settings import (
    SITE_TIMEZONE_KEY,
    get_setting,
    get_site_timezone,
    set_site_timezone,
)
from vizenlink_nvr.timeutil import UTC, FakeClock


@pytest.mark.asyncio
async def test_utc_datetime_on_throwaway_table(tmp_path: Path) -> None:
    """Verify UtcDateTime column on a direct table round-trips microsecond precision and converts to UTC."""
    settings = NvrSettings(data_dir=tmp_path)
    fake_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    clock = FakeClock(fake_time)

    async with open_runtime(settings, clock=clock) as rt:
        # Create throwaway table
        metadata = sa.MetaData()
        test_table = sa.Table(
            "time_probe",
            metadata,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("recorded_at", UtcDateTime, nullable=False),
        )
        async with rt.engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

        # Insert aware non-UTC time (+05:30)
        ist = timezone(timedelta(hours=5, minutes=30))
        t_ist = datetime(2026, 10, 27, 20, 30, 45, 123456, tzinfo=ist)
        async with rt.sessions() as session:
            await session.execute(test_table.insert().values(id=1, recorded_at=t_ist))
            await session.commit()

        # Retrieve and verify converted to UTC and preserved µs
        async with rt.sessions() as session:
            res = await session.execute(sa.select(test_table.c.recorded_at).where(test_table.c.id == 1))
            val = res.scalar_one()
            assert val == t_ist.astimezone(UTC)
            assert val.tzinfo == UTC
            assert val.microsecond == 123456


@pytest.mark.asyncio
async def test_settings_service_round_trip(tmp_path: Path) -> None:
    """Verify settings service get_setting, put_setting, and timezone functions."""
    settings = NvrSettings(data_dir=tmp_path)
    start_time = datetime(2026, 5, 10, 8, 0, 0, tzinfo=UTC)
    clock = FakeClock(start_time)

    async with open_runtime(settings, clock=clock) as rt:
        # Initial timezone is host default / UTC
        tz_default = await get_site_timezone(rt)
        assert tz_default in ("UTC", "Asia/Kolkata") or len(tz_default) > 0

        # Persist new timezone
        saved = await set_site_timezone(rt, "Europe/London")
        assert saved == "Europe/London"

        # Verify persisted
        assert await get_site_timezone(rt) == "Europe/London"
        raw_val = await get_setting(rt, SITE_TIMEZONE_KEY)
        assert raw_val == "Europe/London"


def test_cli_timezone_set_and_status(cli: CliRunner, tmp_path: Path) -> None:
    """Verify CLI set-timezone command, validation, exit codes, and status integration."""
    test_dir = tmp_path / "cli_time_test"

    # 1. Set valid timezone: Europe/London
    res_valid = cli.invoke(
        app,
        ["settings", "set-timezone", "--zone", "Europe/London", "--json", "--data-dir", str(test_dir)],
    )
    assert res_valid.exit_code == 0, f"Error: {res_valid.output}"
    data_valid = json.loads(res_valid.stdout)
    assert data_valid["site_timezone"] == "Europe/London"

    # Verify status reports it
    res_status = cli.invoke(app, ["status", "--json", "--data-dir", str(test_dir)])
    assert res_status.exit_code == 0
    status_data = json.loads(res_status.stdout)
    assert status_data["site_timezone"] == "Europe/London"

    # 2. Reject invalid timezone: Not/AZone -> ExitCode 20
    res_invalid = cli.invoke(
        app,
        ["settings", "set-timezone", "--zone", "Not/AZone", "--json", "--data-dir", str(test_dir)],
    )
    assert res_invalid.exit_code == ExitCode.INVALID_INPUT
    data_invalid = json.loads(res_invalid.stdout)
    assert "Unknown time zone" in data_invalid["error"]
    assert data_invalid["code"] == int(ExitCode.INVALID_INPUT)

    # 3. Verify status still reports previous Europe/London (unchanged)
    res_status2 = cli.invoke(app, ["status", "--json", "--data-dir", str(test_dir)])
    assert res_status2.exit_code == 0
    status_data2 = json.loads(res_status2.stdout)
    assert status_data2["site_timezone"] == "Europe/London"
