"""Camera registry and media endpoints for VizenLink NVR."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status
from pydantic import BaseModel

from vizenlink_nvr.api.dependencies import CurrentUser, verify_camera_access
from vizenlink_nvr.services.media_token import DEFAULT_TOKEN_TTL_SECONDS, default_media_token_service

cameras_router = APIRouter(prefix="/cameras", tags=["cameras"])


class MediaTokenResponse(BaseModel):
    """Media token response schema."""

    token: str
    expires_in: int
    stream: str
    path: str


@cameras_router.post(
    "/{serial}/media-token",
    response_model=MediaTokenResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_camera_media_token(
    serial: str,
    user: CurrentUser,
    stream: Annotated[str, Query(pattern="^(main|sub)$")] = "sub",
) -> MediaTokenResponse:
    """Generate a short-lived HMAC-signed media token for stream authorization."""
    verify_camera_access(serial, user)
    token = default_media_token_service.generate_token(
        user_id=user.id,
        camera_serial=serial,
        stream=stream,
        ttl_seconds=DEFAULT_TOKEN_TTL_SECONDS,
    )
    return MediaTokenResponse(
        token=token,
        expires_in=DEFAULT_TOKEN_TTL_SECONDS,
        stream=stream,
        path=f"cam/{serial}/{stream}",
    )
