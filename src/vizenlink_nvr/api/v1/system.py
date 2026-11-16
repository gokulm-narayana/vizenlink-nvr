"""Recorder identity, site clock and installed software version."""

import json
from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, Field, StringConstraints, field_validator

from vizenlink_nvr import __version__
from vizenlink_nvr.api.dependencies import CurrentUser, DbSession, RequireOwner
from vizenlink_nvr.db.models import AppSetting
from vizenlink_nvr.services.audit import AuditService
from vizenlink_nvr.services.settings import SITE_TIMEZONE_KEY, put_setting, read_site_timezone
from vizenlink_nvr.timeutil import validate_zone

system_router = APIRouter(prefix="/system", tags=["settings"])


class SystemSettings(BaseModel):
    recorder_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    site_timezone: str = Field(min_length=1, max_length=100)

    @field_validator("site_timezone")
    @classmethod
    def valid_zone(cls, value: str) -> str:
        validate_zone(value)
        return value


class SystemInfo(SystemSettings):
    version: str = __version__


@system_router.get("", response_model=SystemInfo)
async def read_system(user: CurrentUser, db: DbSession) -> SystemInfo:
    row = await db.get(AppSetting, "recorder_name")
    return SystemInfo(
        recorder_name=json.loads(row.value) if row else "VizenLink NVR",
        site_timezone=await read_site_timezone(db),
    )


@system_router.put("", response_model=SystemInfo)
async def update_system(payload: SystemSettings, user: RequireOwner, db: DbSession) -> SystemInfo:
    await put_setting(db, "recorder_name", payload.recorder_name)
    await put_setting(db, SITE_TIMEZONE_KEY, payload.site_timezone)
    await AuditService.record_event(
        session=db,
        action="system.update",
        resource_type="recorder",
        actor_id=user.id,
        actor_username=user.username,
        details=payload.model_dump(),
        commit=True,
    )
    return SystemInfo(**payload.model_dump())
