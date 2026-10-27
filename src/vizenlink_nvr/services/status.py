"""System status report service."""

import json
import logging

from pydantic import BaseModel
from sqlalchemy import select, text

from vizenlink_nvr.db.engine import current_revision, head_revision
from vizenlink_nvr.db.models import AppSetting
from vizenlink_nvr.paths import db_path
from vizenlink_nvr.services.runtime import Runtime
from vizenlink_nvr.timeutil import default_site_zone_name

logger = logging.getLogger(__name__)


class StatusReport(BaseModel):
    """System status and diagnostics."""

    data_dir: str
    db_ok: bool
    schema_revision: str | None
    schema_head: str
    site_timezone: str


async def get_status(rt: Runtime) -> StatusReport:
    """Query runtime for database connectivity, schema revisions, and site timezone."""
    db_ok = False
    try:
        async with rt.sessions() as session:
            result = await session.execute(text("SELECT 1"))
            db_ok = result.scalar() == 1
    except Exception:
        db_ok = False

    database_file = db_path(rt.settings)
    cur_rev = current_revision(database_file)
    head_rev = head_revision()

    site_tz = default_site_zone_name()
    try:
        async with rt.sessions() as session:
            stmt = select(AppSetting).where(AppSetting.key == "site_timezone")
            row = await session.execute(stmt)
            setting = row.scalar_one_or_none()
            if setting and setting.value:
                try:
                    val = json.loads(setting.value)
                    if isinstance(val, str):
                        site_tz = val
                    else:
                        site_tz = setting.value
                except Exception:
                    site_tz = setting.value
    except Exception as exc:
        logger.debug("Failed reading site_timezone setting: %s", exc)

    return StatusReport(
        data_dir=str(rt.settings.data_dir),
        db_ok=db_ok,
        schema_revision=cur_rev,
        schema_head=head_rev,
        site_timezone=site_tz,
    )
