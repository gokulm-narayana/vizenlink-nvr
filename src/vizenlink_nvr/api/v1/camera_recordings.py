"""Authenticated camera SD clip playback and bounded-memory export."""

import re
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from vizenlink_nvr.api.dependencies import CurrentUser, DbSession, verify_camera_access
from vizenlink_nvr.api.v1.camera_features import FeaturesDep
from vizenlink_nvr.api.v1.camera_settings import VaultDep
from vizenlink_nvr.camera.http import HttpResponse
from vizenlink_nvr.camera.result import Failure, Timeout
from vizenlink_nvr.services.audit import AuditService
from vizenlink_nvr.services.camera_features import require_success

camera_recordings_router = APIRouter(prefix="/cameras/{serial}/sd-recordings", tags=["camera-recordings"])
CHUNK = 1024 * 1024


def checked_chunk(result: HttpResponse | Failure | Timeout) -> tuple[bytes, int, int, int]:
    if isinstance(result, Timeout):
        raise HTTPException(504, "Camera recording request timed out")
    if isinstance(result, Failure):
        raise HTTPException(502, result.reason)
    if result.status == 404:
        raise HTTPException(404, "This clip is no longer available on the camera")
    if result.status == 416:
        raise HTTPException(416, "Recording byte range is unavailable")
    headers = {key.lower(): value for key, value in result.headers}
    if result.status == 200 and 0 < len(result.body) <= CHUNK:
        return result.body, 0, len(result.body) - 1, len(result.body)
    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", headers.get("content-range", ""))
    if result.status != 206 or match is None:
        raise HTTPException(502, "Camera did not return a valid MP4 byte range")
    start, end, total = map(int, match.groups())
    if not 0 <= start <= end < total or len(result.body) != end - start + 1 or len(result.body) > CHUNK:
        raise HTTPException(502, "Camera recording response was incomplete")
    return result.body, start, end, total


@camera_recordings_router.get("/{clip_id}/clip")
async def camera_clip(
    serial: str,
    clip_id: int,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    vault: VaultDep,
    service: FeaturesDep,
    download: bool = False,
) -> Response:
    verify_camera_access(serial, user)
    if clip_id < 0:
        raise HTTPException(422, "Invalid camera recording ID")
    camera = await service.client(db, vault, serial)
    caps = require_success(await camera.request("GET", "/nuraeye/capabilities"))
    if caps.get("local_storage_capable") is not True:
        raise HTTPException(422, "This camera does not support SD recording")
    start, end = 0, CHUNK - 1
    raw_range = request.headers.get("range")
    if raw_range and not download:
        match = re.fullmatch(r"bytes=(\d+)-(\d*)", raw_range)
        if match is None:
            raise HTTPException(416, "Use a single recording byte range")
        start = int(match[1])
        end = min(int(match[2]), start + CHUNK - 1) if match[2] else start + CHUNK - 1
        if end < start:
            raise HTTPException(416, "Invalid recording byte range")
    body, received_start, received_end, total = checked_chunk(
        await camera.recording_chunk(clip_id, f"bytes={start}-{end}")
    )
    if received_start != start or received_end > end:
        raise HTTPException(502, "Camera returned bytes outside the requested recording range")
    headers = {
        "Cache-Control": "private, no-store",
        "Accept-Ranges": "bytes",
        "X-Content-Type-Options": "nosniff",
    }
    if raw_range and not download:
        headers["Content-Range"] = f"bytes {received_start}-{received_end}/{total}"
        return Response(body, status_code=206, media_type="video/mp4", headers=headers)

    if download:
        await AuditService.record_event(
            session=db,
            action="camera.recording.export",
            resource_type="camera",
            resource_id=serial,
            actor_id=user.id,
            actor_username=user.username,
            details={"clip_id": clip_id},
            commit=True,
        )

    async def content() -> AsyncIterator[bytes]:
        yield body
        next_start = received_end + 1
        while next_start < total:
            next_end = min(total - 1, next_start + CHUNK - 1)
            chunk, actual_start, actual_end, actual_total = checked_chunk(
                await camera.recording_chunk(clip_id, f"bytes={next_start}-{next_end}")
            )
            if actual_start != next_start or actual_end > next_end or actual_total != total:
                raise RuntimeError("Camera recording changed during streaming; retry after the clip closes")
            yield chunk
            next_start = actual_end + 1

    headers["Content-Length"] = str(total)
    if download:
        headers["Content-Disposition"] = f'attachment; filename="camera-recording-{clip_id}.mp4"'
    return StreamingResponse(content(), media_type="video/mp4", headers=headers)
