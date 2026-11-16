"""Recording configuration and status REST API endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from vizenlink_nvr.api.dependencies import (
    CurrentUser,
    DbSession,
    RequireOperator,
)
from vizenlink_nvr.db.models import Camera
from vizenlink_nvr.services.audit import AuditService
from vizenlink_nvr.services.health import RecordingState
from vizenlink_nvr.services.recording_settings import (
    AudioNotSupportedError,
    get_or_create_recording_settings,
    set_recording_audio,
    set_recording_mode,
    set_recording_retention,
    set_recording_schedule,
)
from vizenlink_nvr.services.settings import (
    CLIP_MINUTES_CHOICES,
    CLIP_MINUTES_KEY,
    put_setting,
    read_clip_minutes,
)
from vizenlink_nvr.services.watchdog import check_camera_gaps

recording_router = APIRouter(prefix="/recording", tags=["recording"])


class RecordingStatusItem(BaseModel):
    """Recording status and policy schema for a camera."""

    camera_serial: str
    mode: str
    schedule_json: str
    audio_enabled: bool
    retention_days: int | None = None
    retention_max_gb: int | None = None
    # Phase 10 honest status: what is actually happening, not just the policy.
    is_recording: bool | None = None
    last_segment_at: datetime | None = None
    recording_detail: str | None = None


class RecordingSettingsUpdate(BaseModel):
    """Payload for updating per-camera recording settings."""

    mode: str | None = None
    schedule_json: str | None = None
    audio_enabled: bool | None = None
    retention_days: int | None = None
    retention_max_gb: int | None = None


class RecordingOptions(BaseModel):
    """Recorder-wide recording options."""

    clip_minutes: int
    clip_minutes_choices: list[int] = Field(default_factory=lambda: list(CLIP_MINUTES_CHOICES))


class RecordingOptionsUpdate(BaseModel):
    clip_minutes: int


@recording_router.get("/options", response_model=RecordingOptions)
async def get_recording_options(user: CurrentUser, db: DbSession) -> RecordingOptions:
    """Length of each recorded clip, and the lengths that can be chosen."""
    return RecordingOptions(clip_minutes=await read_clip_minutes(db))


@recording_router.put("/options", response_model=RecordingOptions)
async def update_recording_options(
    payload: RecordingOptionsUpdate, user: RequireOperator, db: DbSession
) -> RecordingOptions:
    """Change the clip length. The recorder applies it to every camera within about 30 s."""
    if payload.clip_minutes not in CLIP_MINUTES_CHOICES:
        raise HTTPException(
            status_code=422,
            detail=f"Clip length must be one of {list(CLIP_MINUTES_CHOICES)} minutes.",
        )
    previous = await read_clip_minutes(db)
    await put_setting(db, CLIP_MINUTES_KEY, payload.clip_minutes)
    await AuditService.record_event(
        session=db,
        action="recording.update_options",
        resource_type="recorder",
        actor_id=user.id,
        actor_username=user.username,
        details={"clip_minutes": payload.clip_minutes, "previous_clip_minutes": previous},
        commit=True,
    )
    return RecordingOptions(clip_minutes=payload.clip_minutes)


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

    # Evidence of recording = a recent indexed segment (same rule as the gap watchdog).
    try:
        live_state = await check_camera_gaps(db)
    except Exception:
        live_state = {}

    items: list[RecordingStatusItem] = []
    for cam in cams:
        rec_settings = await get_or_create_recording_settings(db, cam.serial)
        health = live_state.get(cam.serial)
        items.append(
            RecordingStatusItem(
                camera_serial=rec_settings.camera_serial,
                mode=rec_settings.mode,
                schedule_json=rec_settings.schedule_json,
                audio_enabled=rec_settings.audio_enabled,
                retention_days=rec_settings.retention_days,
                retention_max_gb=rec_settings.retention_max_gb,
                is_recording=(health.recording_state == RecordingState.RECORDING) if health else None,
                last_segment_at=health.last_segment_at if health else None,
                recording_detail=health.details if health else None,
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
    result = await _apply_policy(db, serial, payload)
    await db.commit()
    return result


async def _apply_policy(db: DbSession, serial: str, payload: RecordingSettingsUpdate) -> RecordingStatusItem:
    cam = await db.get(Camera, serial)
    if cam is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{serial}' not found",
        )

    try:
        if payload.mode is not None:
            await set_recording_mode(db, serial, payload.mode, commit=False)
        if payload.schedule_json is not None:
            await set_recording_schedule(db, serial, payload.schedule_json, commit=False)
        if payload.audio_enabled is not None:
            await set_recording_audio(db, serial, payload.audio_enabled, commit=False)
        if {"retention_days", "retention_max_gb"} & payload.model_fields_set:
            current = await get_or_create_recording_settings(db, serial, commit=False)
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
            await set_recording_retention(db, serial, days, max_gb, commit=False)

        updated = await get_or_create_recording_settings(db, serial, commit=False)
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


class BulkPolicyUpdate(BaseModel):
    serials: list[str] = Field(min_length=1, max_length=256)
    changes: RecordingSettingsUpdate


@recording_router.post("/apply")
async def apply_recording_policies(
    payload: BulkPolicyUpdate, user: RequireOperator, db: DbSession
) -> dict[str, int]:
    serials = list(dict.fromkeys(payload.serials))
    for serial in serials:
        await _apply_policy(db, serial, payload.changes)
    await db.commit()
    return {"updated": len(serials)}
