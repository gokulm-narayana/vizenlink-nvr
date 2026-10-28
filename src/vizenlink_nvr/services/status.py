"""System status report service."""

import logging

from pydantic import BaseModel, Field
from sqlalchemy import text

from vizenlink_nvr.db.engine import current_revision, head_revision
from vizenlink_nvr.paths import db_path
from vizenlink_nvr.secrets.vault import check_canary
from vizenlink_nvr.services.registry import camera_counts
from vizenlink_nvr.services.runtime import Runtime
from vizenlink_nvr.services.settings import get_site_timezone

logger = logging.getLogger(__name__)


class StatusReport(BaseModel):
    """System status and diagnostics."""

    data_dir: str
    db_ok: bool
    schema_revision: str | None
    schema_head: str
    site_timezone: str
    credentials_status: str
    key_source: str | None = None
    key_id: str | None = None
    cameras_total: int = 0
    cameras_by_state: dict[str, int] = Field(default_factory=dict)


async def get_status(rt: Runtime) -> StatusReport:
    """Query runtime for database connectivity, schema revisions, site timezone, and credentials."""
    db_ok = False
    try:
        async with rt.sessions() as session:
            result = await session.execute(text("SELECT 1"))
            db_ok = result.scalar() == 1
    except Exception as exc:
        logger.debug("Database probe failed: %s", exc)
        db_ok = False

    cameras_total = 0
    cameras_by_state: dict[str, int] = {}
    if db_ok:
        try:
            async with rt.sessions() as session:
                counts = await camera_counts(session)
                cameras_total = counts.get("total", 0)
                cameras_by_state = {k: v for k, v in counts.items() if k != "total" and v > 0}
        except Exception as exc:
            logger.debug("Failed to count cameras: %s", exc)

    database_file = db_path(rt.settings)
    cur_rev = current_revision(database_file)
    head_rev = head_revision()
    site_tz = await get_site_timezone(rt)
    canary = await check_canary(rt)

    return StatusReport(
        data_dir=str(rt.settings.data_dir),
        db_ok=db_ok,
        schema_revision=cur_rev,
        schema_head=head_rev,
        site_timezone=site_tz,
        credentials_status=canary.status,
        key_source=canary.key_source,
        key_id=canary.key_id,
        cameras_total=cameras_total,
        cameras_by_state=cameras_by_state,
    )
