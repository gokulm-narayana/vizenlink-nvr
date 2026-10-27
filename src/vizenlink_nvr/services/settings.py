"""Application settings persistence service."""

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.db.models import AppSetting
from vizenlink_nvr.services.runtime import Runtime
from vizenlink_nvr.timeutil import default_site_zone_name, utc_now, validate_zone

logger = logging.getLogger(__name__)

SITE_TIMEZONE_KEY = "site_timezone"


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

    stmt = select(AppSetting).where(AppSetting.key == key)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        existing.value = json_val
        existing.updated_at = ts
    else:
        session.add(AppSetting(key=key, value=json_val, updated_at=ts))


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
