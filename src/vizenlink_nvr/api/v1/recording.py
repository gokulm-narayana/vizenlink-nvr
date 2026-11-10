"""Recording configuration and status REST API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from vizenlink_nvr.api.dependencies import (
    CurrentUser,
    DbSession,
    RequireOperator,
)
from vizenlink_nvr.db.models import Camera
from vizenlink_nvr.services.recording_settings import (
    AudioNotSupportedError,
    get_or_create_recording_settings,
    set_recording_audio,
    set_recording_mode,
    set_recording_retention,
    set_recording_schedule,
)

recording_router = APIRouter(prefix="/recording", tags=["recording"])


class RecordingStatusItem(BaseModel):
    """Recording status and policy schema for a camera."""

    camera_serial: str
    mode: str
    schedule_json: str
    audio_enabled: bool
    retention_days: int | None = None
    retention_max_gb: int | None = None


class RecordingSettingsUpdate(BaseModel):
    """Payload for updating per-camera recording settings."""

    mode: str | None = None
    schedule_json: str | None = None
    audio_enabled: bool | None = None
    retention_days: int | None = None
    retention_max_gb: int | None = None


@recording_router.get("/status", response_model=list[RecordingStatusItem])
async def get_all_recording_status(
    user: CurrentUser,
    db: DbSession,
) -> list[RecordingStatusItem]:
    """Retrieve recording policies for all accessible cameras."""
    cams = (await db.execute(select(Camera))).scalars().all()
    if user.role not in ("owner", "operator"):
        allowed = {p.camera_serial for p in user.permissions}
        cams = [c for c in cams if c.serial in allowed]

    items: list[RecordingStatusItem] = []
    for cam in cams:
        rec_settings = await get_or_create_recording_settings(db, cam.serial)
        items.append(
            RecordingStatusItem(
                camera_serial=rec_settings.camera_serial,
                mode=rec_settings.mode,
                schedule_json=rec_settings.schedule_json,
                audio_enabled=rec_settings.audio_enabled,
                retention_days=rec_settings.retention_days,
                retention_max_gb=rec_settings.retention_max_gb,
            )
        )
    return items


@recording_router.patch("/{serial}", response_model=RecordingStatusItem)
async def update_recording_settings(
    serial: str,
    payload: RecordingSettingsUpdate,
    user: RequireOperator,
    db: DbSession,
) -> RecordingStatusItem:
    """Update recording mode, schedule, audio, or retention for a camera (Operator+)."""
    cam = await db.get(Camera, serial)
    if cam is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{serial}' not found",
        )

    try:
        if payload.mode is not None:
            await set_recording_mode(db, serial, payload.mode)
        if payload.schedule_json is not None:
            await set_recording_schedule(db, serial, payload.schedule_json)
        if payload.audio_enabled is not None:
            await set_recording_audio(db, serial, payload.audio_enabled)
        if {"retention_days", "retention_max_gb"} & payload.model_fields_set:
            current = await get_or_create_recording_settings(db, serial)
            days = (
                payload.retention_days
                if "retention_days" in payload.model_fields_set
                else current.retention_days
            )
            max_gb = (
                payload.retention_max_gb
                if "retention_max_gb" in payload.model_fields_set
                else current.retention_max_gb
            )
            await set_recording_retention(db, serial, days, max_gb)

        updated = await get_or_create_recording_settings(db, serial)
        return RecordingStatusItem(
            camera_serial=updated.camera_serial,
            mode=updated.mode,
            schedule_json=updated.schedule_json,
            audio_enabled=updated.audio_enabled,
            retention_days=updated.retention_days,
            retention_max_gb=updated.retention_max_gb,
        )
    except AudioNotSupportedError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
