"""Authenticated, path-restricted WHEP reverse proxy to loopback MediaMTX (D-14)."""

from __future__ import annotations

import logging
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.requests import ClientDisconnect

from vizenlink_nvr.api.dependencies import DbSession, get_current_user_optional, verify_camera_access
from vizenlink_nvr.db.models import User
from vizenlink_nvr.media.config import MediaMtxPorts
from vizenlink_nvr.services.session_manager import SESSION_COOKIE_NAME

logger = logging.getLogger(__name__)

cam_proxy_router = APIRouter(include_in_schema=False)

MAX_BODY_BYTES = 65536
FORWARDED_RESPONSE_HEADERS = ("content-type", "location", "etag", "accept-patch", "link")


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
    except ClientDisconnect:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client disconnected",
        )

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
    path = f"/cam/{serial}/{stream}/whep"
    if session_id is not None:
        path = f"{path}/{session_id}"
    return f"http://127.0.0.1:{port}{path}"


async def _proxy_request(
    request: Request,
    serial: str,
    stream: str,
    session_id: str | None = None,
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
        async with httpx.AsyncClient(timeout=10.0, transport=transport) as client:
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

    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers=out_headers,
    )


@cam_proxy_router.post("/cam/{serial}/{stream}/whep")
async def whep_post(
    request: Request,
    serial: Annotated[str, Path(pattern=r"^[A-Za-z0-9._-]{1,64}$")],
    stream: Literal["main", "sub"],
    user: CamUser,
) -> Response:
    _validate_serial(serial)
    verify_camera_access(serial, user)
    return await _proxy_request(request, serial, stream)


@cam_proxy_router.patch("/cam/{serial}/{stream}/whep/{session_id}")
async def whep_patch(
    request: Request,
    serial: Annotated[str, Path(pattern=r"^[A-Za-z0-9._-]{1,64}$")],
    stream: Literal["main", "sub"],
    session_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9-]{1,128}$")],
    user: CamUser,
) -> Response:
    _validate_serial(serial)
    verify_camera_access(serial, user)
    return await _proxy_request(request, serial, stream, session_id)


@cam_proxy_router.delete("/cam/{serial}/{stream}/whep/{session_id}")
async def whep_delete(
    request: Request,
    serial: Annotated[str, Path(pattern=r"^[A-Za-z0-9._-]{1,64}$")],
    stream: Literal["main", "sub"],
    session_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9-]{1,128}$")],
    user: CamUser,
) -> Response:
    _validate_serial(serial)
    verify_camera_access(serial, user)
    return await _proxy_request(request, serial, stream, session_id)


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