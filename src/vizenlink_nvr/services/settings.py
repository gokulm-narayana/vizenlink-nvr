from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.db.models import AppSetting
from vizenlink_nvr.timeutil import default_site_zone_name, utc_now, validate_zone

if TYPE_CHECKING:
    from vizenlink_nvr.services.runtime import Runtime

logger = logging.getLogger(__name__)

SITE_TIMEZONE_KEY = "site_timezone"

# Length of each recorded clip (one file on disk), recorder-wide.
CLIP_MINUTES_KEY = "recording_clip_minutes"
CLIP_MINUTES_CHOICES: tuple[int, ...] = (1, 5, 10, 15, 30, 60)
DEFAULT_CLIP_MINUTES = 1


async def read_clip_minutes(session: AsyncSession) -> int:
    """Clip length in minutes; anything unreadable or not offered falls back to the default."""
    stmt = select(AppSetting).where(AppSetting.key == CLIP_MINUTES_KEY)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return DEFAULT_CLIP_MINUTES
    try:
        value = json.loads(row.value)
    except Exception:
        return DEFAULT_CLIP_MINUTES
    return value if isinstance(value, int) and value in CLIP_MINUTES_CHOICES else DEFAULT_CLIP_MINUTES


async def get_setting(rt: Runtime, key: str) -> object | None:
    """Retrieve setting value by key, deserializing JSON."""
    async with rt.sessions() as session:
        stmt = select(AppSetting).where(AppSetting.key == key)
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        try:
            parsed: object = json.loads(row.value)
            return parsed
        except Exception:
            return row.value


async def put_setting(
    session: AsyncSession,
    key: str,
    value: Any,
    updated_at: datetime | None = None,
) -> None:
    """Insert or update setting with JSON-serialized value."""
    ts = updated_at if updated_at is not None else utc_now()
    json_val = json.dumps(value)

    stmt = insert(AppSetting).values(key=key, value=json_val, updated_at=ts)
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[AppSetting.key], set_={"value": json_val, "updated_at": ts}
        )
    )


async def read_site_timezone(session: AsyncSession) -> str:
    """Get site timezone name using an active session, falling back to default site zone."""
    stmt = select(AppSetting).where(AppSetting.key == SITE_TIMEZONE_KEY)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is not None:
        try:
            val: object = json.loads(row.value)
        except Exception:
            val = row.value
        if isinstance(val, str) and val:
            try:
                validate_zone(val)
                return val
            except Exception as exc:
                logger.debug("Invalid stored site timezone: %s", exc)
    return default_site_zone_name()


async def get_site_timezone(rt: Runtime) -> str:
    """Get site timezone name, falling back to host system timezone or UTC."""
    val = await get_setting(rt, SITE_TIMEZONE_KEY)
    if isinstance(val, str) and val:
        try:
            validate_zone(val)
            return val
        except Exception as exc:
            logger.debug("Invalid stored site timezone: %s", exc)
    return default_site_zone_name()


async def set_site_timezone(rt: Runtime, name: str) -> str:
    """Validate and persist site timezone."""
    validate_zone(name)
    async with rt.sessions() as session:
        await put_setting(session, SITE_TIMEZONE_KEY, name, rt.clock.now())
        await session.commit()
    return name
