"""Authenticated, path-restricted WHEP and HLS reverse proxy to loopback MediaMTX (D-14)."""

from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.requests import ClientDisconnect

from vizenlink_nvr.api.dependencies import DbSession, get_current_user_optional, verify_camera_access
from vizenlink_nvr.db.models import User
from vizenlink_nvr.media.config import MediaMtxPorts, camera_path_name
from vizenlink_nvr.services.media_token import default_media_token_service
from vizenlink_nvr.services.session_manager import SESSION_COOKIE_NAME

logger = logging.getLogger(__name__)

cam_proxy_router = APIRouter(include_in_schema=False)

MAX_BODY_BYTES = 65536
PROXY_TIMEOUT_SECONDS = 20.0
FORWARDED_RESPONSE_HEADERS = ("content-type", "location", "etag", "accept-patch", "accept-post", "link")
HLS_FORWARDED_RESPONSE_HEADERS = (
    "content-type",
    "content-length",
    "content-range",
    "accept-ranges",
    "cache-control",
    "etag",
)
_HLS_ASSET_RE = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")


async def _resolve_user_from_media_token(
    token: str,
    serial: str,
    stream: str,
    db: AsyncSession,
) -> User | None:
    """Validate a signed media token and load its active user with permissions."""
    verified = default_media_token_service.verify_token(token)
    if verified is None:
        return None

    token_serial = verified.get("serial")
    token_stream = verified.get("stream")
    if token_serial != serial or token_stream != stream:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Media token does not match requested camera stream",
        )

    user_id = verified.get("sub")
    if user_id is None:
        return None
    res = await db.execute(
        select(User).options(selectinload(User.permissions)).where(User.id == user_id)
    )
    user = res.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    return user


async def _authenticate_cam_request(
    request: Request,
    serial: str,
    stream: str,
    db: AsyncSession,
) -> tuple[User, bool]:
    """Authenticate caller via session cookie, paired Bearer token, or signed media token.

    Returns ``(user, used_media_token_only)``.
    """
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    user = await get_current_user_optional(request, db, session_id=cookie_token)
    if user is not None:
        return user, False

    media_token = request.query_params.get("token")
    if not media_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            media_token = auth_header.split(" ", 1)[1].strip()

    if media_token:
        media_user = await _resolve_user_from_media_token(media_token, serial, stream, db)
        if media_user is not None:
            return media_user, True

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )


async def get_cam_proxy_user(request: Request, db: DbSession) -> User:
    """Authenticate caller via session cookie or Authorization Bearer header."""
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    user = await get_current_user_optional(request, db, session_id=cookie_token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


CamUser = Annotated[User, Depends(get_cam_proxy_user)]


def _validate_serial(serial: str) -> None:
    if ".." in serial or serial == ".":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid camera serial",
        )


def _validate_hls_asset(asset: str) -> None:
    segments = asset.split("/")
    if (
        not asset
        or asset.startswith("/")
        or "\\" in asset
        or "" in segments
        or ".." in segments
        or not _HLS_ASSET_RE.fullmatch(asset)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid HLS asset path",
        )


async def _read_capped_body(request: Request) -> bytes:
    cl = request.headers.get("content-length")
    if cl is not None:
        try:
            if int(cl) > MAX_BODY_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Payload too large",
                )
        except ValueError:
            pass

    try:
        body = await request.body()
    except ClientDisconnect as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client disconnected",
        ) from exc

    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Payload too large",
        )
    return body


def _forwarded_headers(request: Request) -> dict[str, str]:
    headers: dict[str, str] = {}
    if "content-type" in request.headers:
        headers["content-type"] = request.headers["content-type"]
    if "if-match" in request.headers:
        headers["if-match"] = request.headers["if-match"]
    return headers


def _forwarded_params(request: Request) -> dict[str, str]:
    params: dict[str, str] = {}
    token = request.query_params.get("token")
    if token is not None:
        params["token"] = token
    return params


def _build_upstream_url(
    request: Request,
    serial: str,
    stream: str,
    session_id: str | None = None,
) -> str:
    port = getattr(request.app.state, "mediamtx_webrtc_port", None) or MediaMtxPorts().webrtc
    path = f"/{camera_path_name(serial, stream)}/whep"
    if session_id is not None:
        path = f"{path}/{session_id}"
    return f"http://127.0.0.1:{port}{path}"


def _build_hls_upstream_url(request: Request, serial: str, stream: str, asset: str) -> str:
    port = getattr(request.app.state, "mediamtx_hls_port", None) or MediaMtxPorts().hls
    return f"http://127.0.0.1:{port}/{camera_path_name(serial, stream)}/{asset}"


async def _proxy_request(
    request: Request,
    serial: str,
    stream: str,
    session_id: str | None = None,
    *,
    append_query_token: bool = False,
) -> Response:
    try:
        body = await _read_capped_body(request)
    except ClientDisconnect:
        return Response(status_code=status.HTTP_400_BAD_REQUEST)
    headers = _forwarded_headers(request)
    params = _forwarded_params(request)
    url = _build_upstream_url(request, serial, stream, session_id)

    transport = getattr(request.app.state, "cam_proxy_transport", None)
    try:
        async with httpx.AsyncClient(timeout=PROXY_TIMEOUT_SECONDS, transport=transport) as client:
            upstream_resp = await client.request(
                method=request.method,
                url=url,
                params=params,
                headers=headers,
                content=body,
            )
    except (httpx.TransportError, httpx.TimeoutException):
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": "Live video service unavailable"},
        )

    out_headers: dict[str, str] = {}
    for h in FORWARDED_RESPONSE_HEADERS:
        if h in upstream_resp.headers:
            out_headers[h] = upstream_resp.headers[h]

    # MediaMTX paths are lower-case; hand the session URL back with the caller's serial
    # so the follow-up PATCH/DELETE passes the same per-camera access check.
    location = next((k for k in out_headers if k.lower() == "location"), None)
    if location is not None:
        upstream_prefix = f"/{camera_path_name(serial, stream)}/"
        if out_headers[location].startswith(upstream_prefix):
            out_headers[location] = f"/cam/{serial}/{stream}/" + out_headers[location][len(upstream_prefix):]
        token = params.get("token")
        if append_query_token and token and "token=" not in out_headers[location]:
            sep = "&" if "?" in out_headers[location] else "?"
            out_headers[location] = f"{out_headers[location]}{sep}token={urllib.parse.quote(token, safe='')}"

    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers=out_headers,
    )


@cam_proxy_router.options("/cam/{serial}/{stream}/whep")
async def whep_options(
    request: Request,
    serial: Annotated[str, Path(pattern=r"^[A-Za-z0-9._-]{1,64}$")],
    stream: Literal["main", "sub"],
    db: DbSession,
) -> Response:
    _validate_serial(serial)
    user, _ = await _authenticate_cam_request(request, serial, stream, db)
    verify_camera_access(serial, user)
    return await _proxy_request(request, serial, stream)


@cam_proxy_router.post("/cam/{serial}/{stream}/whep")
async def whep_post(
    request: Request,
    serial: Annotated[str, Path(pattern=r"^[A-Za-z0-9._-]{1,64}$")],
    stream: Literal["main", "sub"],
    db: DbSession,
) -> Response:
    _validate_serial(serial)
    user, used_media_token = await _authenticate_cam_request(request, serial, stream, db)
    verify_camera_access(serial, user)
    return await _proxy_request(request, serial, stream, append_query_token=used_media_token)


@cam_proxy_router.patch("/cam/{serial}/{stream}/whep/{session_id}")
async def whep_patch(
    request: Request,
    serial: Annotated[str, Path(pattern=r"^[A-Za-z0-9._-]{1,64}$")],
    stream: Literal["main", "sub"],
    session_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9-]{1,128}$")],
    db: DbSession,
) -> Response:
    _validate_serial(serial)
    user, _ = await _authenticate_cam_request(request, serial, stream, db)
    verify_camera_access(serial, user)
    return await _proxy_request(request, serial, stream, session_id)


@cam_proxy_router.delete("/cam/{serial}/{stream}/whep/{session_id}")
async def whep_delete(
    request: Request,
    serial: Annotated[str, Path(pattern=r"^[A-Za-z0-9._-]{1,64}$")],
    stream: Literal["main", "sub"],
    session_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9-]{1,128}$")],
    db: DbSession,
) -> Response:
    _validate_serial(serial)
    user, _ = await _authenticate_cam_request(request, serial, stream, db)
    verify_camera_access(serial, user)
    return await _proxy_request(request, serial, stream, session_id)


@cam_proxy_router.api_route(
    "/cam/{serial}/{stream}/hls/{token}/{asset:path}",
    methods=["GET", "HEAD"],
)
async def hls_proxy(
    request: Request,
    serial: Annotated[str, Path(pattern=r"^[A-Za-z0-9._-]{1,64}$")],
    stream: Literal["main", "sub"],
    token: Annotated[str, Path(min_length=1, max_length=512)],
    asset: str,
    db: DbSession,
) -> Response:
    """Proxy authenticated HLS playlist and fMP4 segment requests to loopback MediaMTX."""
    _validate_serial(serial)
    _validate_hls_asset(asset)
    user = await _resolve_user_from_media_token(token, serial, stream, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired media token",
        )
    verify_camera_access(serial, user)

    upstream_url = _build_hls_upstream_url(request, serial, stream, asset)
    headers: dict[str, str] = {}
    for h in ("range", "if-none-match"):
        if h in request.headers:
            headers[h] = request.headers[h]
    params = dict(request.query_params)
    params["token"] = token

    transport = getattr(request.app.state, "cam_proxy_transport", None)
    try:
        async with httpx.AsyncClient(
            timeout=PROXY_TIMEOUT_SECONDS,
            follow_redirects=True,
            transport=transport,
        ) as client:
            upstream_resp = await client.request(
                method=request.method,
                url=upstream_url,
                params=params,
                headers=headers,
            )
    except (httpx.TransportError, httpx.TimeoutException):
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": "Live video service unavailable"},
        )

    out_headers: dict[str, str] = {}
    for h in HLS_FORWARDED_RESPONSE_HEADERS:
        if h in upstream_resp.headers:
            out_headers[h] = upstream_resp.headers[h]

    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers=out_headers,
    )


@cam_proxy_router.api_route(
    "/cam/{rest:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def cam_catchall(rest: str) -> JSONResponse:
    """Ensure invalid /cam paths return 404 JSON and never hit SPA fallback."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "Not Found"},
    )