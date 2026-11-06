"""Authentication and setup endpoints for VizenLink NVR."""

from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from vizenlink_nvr.api.dependencies import (
    CurrentUser,
    CurrentUserOptional,
    DbSession,
)
from vizenlink_nvr.db.models import User
from vizenlink_nvr.media.config import CONTROL_USER
from vizenlink_nvr.services.audit import AuditService
from vizenlink_nvr.services.auth_hasher import hash_password, verify_password
from vizenlink_nvr.services.media_token import default_media_token_service
from vizenlink_nvr.services.rate_limiter import login_rate_limiter
from vizenlink_nvr.services.session_manager import (
    SESSION_COOKIE_NAME,
    SessionManager,
)
from vizenlink_nvr.services.settings import read_site_timezone
from vizenlink_nvr.services.setup import MIN_PASSWORD_LENGTH, SetupService
from vizenlink_nvr.timeutil import utc_now

auth_router = APIRouter(prefix="/auth", tags=["auth"])


class MediaMtxAuthRequest(BaseModel):
    ip: str = ""
    user: str = ""
    password: str = ""
    path: str = ""
    protocol: str = ""
    id: str = ""
    action: str = ""
    query: str = ""


class SetupRequest(BaseModel):
    owner_username: str = Field(..., min_length=1)
    owner_password: str = Field(..., min_length=MIN_PASSWORD_LENGTH)
    timezone: str = Field(..., min_length=1)
    storage_path: str = Field(..., min_length=1)
    allow_system_disk: bool = False


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=MIN_PASSWORD_LENGTH)


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    cognito_sub: str | None = None
    permissions: list[str] = []


class AuthStatusResponse(BaseModel):
    initialized: bool
    authenticated: bool
    user: UserResponse | None = None
    site_timezone: str | None = None


def _get_client_ip(request: Request) -> str:
    """Extract client IP address from request."""
    if request.client:
        return request.client.host
    return "127.0.0.1"


@auth_router.get("/status", response_model=AuthStatusResponse)
async def get_auth_status(
    db: DbSession,
    current_user: CurrentUserOptional = None,
) -> AuthStatusResponse:
    """Return whether first-run setup is complete and current authentication status."""
    is_init = await SetupService.is_initialized(db)
    user_resp: UserResponse | None = None
    site_tz: str | None = None

    if current_user is not None:
        user_resp = UserResponse(
            id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            is_active=current_user.is_active,
            cognito_sub=current_user.cognito_sub,
            permissions=[p.camera_serial for p in current_user.permissions],
        )
        site_tz = await read_site_timezone(db)

    return AuthStatusResponse(
        initialized=is_init,
        authenticated=current_user is not None,
        user=user_resp,
        site_timezone=site_tz,
    )


@auth_router.post("/setup", response_model=dict[str, Any])
async def setup_nvr(
    payload: SetupRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> dict[str, Any]:
    """Execute first-run setup wizard: create owner account, set timezone and storage path."""
    try:
        owner = await SetupService.initialize_nvr(
            db=db,
            owner_username=payload.owner_username,
            owner_password=payload.owner_password,
            timezone=payload.timezone,
            storage_path=Path(payload.storage_path),
            allow_system_disk=payload.allow_system_disk,
        )
    except RuntimeError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err

    # Create session for new owner
    ip = _get_client_ip(request)
    ua = request.headers.get("user-agent")
    sess = await SessionManager.create_session(db, owner.id, ip, ua)
    SessionManager.set_cookie(response, sess.id)

    await AuditService.record_event(
        session=db,
        action="system.setup",
        resource_type="system",
        actor_id=owner.id,
        actor_username=owner.username,
        ip_address=ip,
        details={"timezone": payload.timezone, "storage_path": payload.storage_path},
        commit=True,
    )

    return {
        "success": True,
        "user": {
            "id": owner.id,
            "username": owner.username,
            "role": owner.role,
        },
    }


@auth_router.post("/login", response_model=dict[str, Any])
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> dict[str, Any]:
    """Authenticate user with local account credentials, rate-limiting repeated failures."""
    ip = _get_client_ip(request)
    username = payload.username.strip()

    # Check brute-force lockout
    if login_rate_limiter.is_locked(username):
        rem = login_rate_limiter.remaining_lockout_seconds(username)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account temporarily locked due to too many failed attempts. Try again in {rem} seconds.",
        )
    if login_rate_limiter.is_locked(ip):
        rem = login_rate_limiter.remaining_lockout_seconds(ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"IP temporarily locked due to too many failed attempts. Try again in {rem} seconds.",
        )

    # Query user
    stmt = (
        select(User)
        .where(User.username == username)
        .options(selectinload(User.permissions))
    )
    user = (await db.execute(stmt)).scalar_one_or_none()

    if user is None or not user.is_active or not verify_password(user.password_hash, payload.password):
        login_rate_limiter.record_failure(username)
        login_rate_limiter.record_failure(ip)
        await AuditService.record_event(
            session=db,
            action="auth.login_failure",
            resource_type="user",
            actor_username=username,
            ip_address=ip,
            commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Reset rate limiting on success
    login_rate_limiter.reset(username)
    login_rate_limiter.reset(ip)

    # Create session
    ua = request.headers.get("user-agent")
    sess = await SessionManager.create_session(db, user.id, ip, ua)
    SessionManager.set_cookie(response, sess.id)

    await AuditService.record_event(
        session=db,
        action="auth.login_success",
        resource_type="user",
        resource_id=str(user.id),
        actor_id=user.id,
        actor_username=user.username,
        ip_address=ip,
        commit=True,
    )

    return {
        "success": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "permissions": [p.camera_serial for p in user.permissions],
        },
    }


@auth_router.post("/logout", response_model=dict[str, Any])
async def logout(
    request: Request,
    response: Response,
    db: DbSession,
    session_id: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> dict[str, Any]:
    """Invalidate current session and clear session cookie."""
    token = session_id
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()

    if token:
        await SessionManager.invalidate_session(db, token)
        await AuditService.record_event(
            session=db,
            action="auth.logout",
            resource_type="session",
            resource_id=token,
            commit=True,
        )

    SessionManager.clear_cookie(response)
    return {"success": True}


@auth_router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: CurrentUser,
) -> UserResponse:
    """Return authenticated caller's profile and permitted cameras."""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        is_active=current_user.is_active,
        cognito_sub=current_user.cognito_sub,
        permissions=[p.camera_serial for p in current_user.permissions],
    )


@auth_router.post("/password", response_model=dict[str, Any])
async def change_password(
    payload: PasswordChangeRequest,
    response: Response,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> dict[str, Any]:
    """Change authenticated user's password."""
    if not verify_password(current_user.password_hash, payload.current_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    if len(payload.new_password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"New password must be at least {MIN_PASSWORD_LENGTH} characters long",
        )

    # Invalidate other existing sessions
    await SessionManager.invalidate_user_sessions(db, current_user.id)

    # Update password
    current_user.password_hash = hash_password(payload.new_password)
    current_user.updated_at = utc_now()
    await db.commit()

    # Re-create fresh session for the user so they stay logged in
    ip = _get_client_ip(request)
    ua = request.headers.get("user-agent")
    sess = await SessionManager.create_session(db, current_user.id, ip, ua)
    SessionManager.set_cookie(response, sess.id)

    await AuditService.record_event(
        session=db,
        action="auth.password_change",
        resource_type="user",
        resource_id=str(current_user.id),
        actor_id=current_user.id,
        actor_username=current_user.username,
        ip_address=ip,
        commit=True,
    )

    return {"success": True}


def _is_loopback(host: str | None) -> bool:
    """Check if IP or hostname is loopback."""
    if not host:
        return False
    return host in ("127.0.0.1", "::1", "localhost", "testclient") or host.startswith("127.")


@auth_router.post("/mediamtx", status_code=status.HTTP_200_OK)
async def mediamtx_auth_webhook(
    payload: MediaMtxAuthRequest,
    request: Request,
    db: DbSession,
) -> dict[str, str]:
    """MediaMTX HTTP authentication webhook (authMethod: http).

    Verifies internal API control calls and ephemeral signed media tokens for stream reads.
    """
    client_host = request.client.host if request.client else None
    
    # Case 1: Internal API control
    if payload.action == "api":
        if not (_is_loopback(client_host) or _is_loopback(payload.ip)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="MediaMTX API action must originate from loopback",
            )
        if payload.user != CONTROL_USER:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid control user",
            )
        # Check password against configured secret if present
        expected_pw: str | None = getattr(request.app.state, "control_password", None)
        if expected_pw is None and getattr(request.app.state, "runtime", None) is not None:
            from vizenlink_nvr.media.reconciler import get_control_password
            expected_pw = get_control_password(request.app.state.runtime.settings)
        if expected_pw is not None and payload.password != expected_pw:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid control credentials",
            )
        return {"status": "ok"}

    # Case 2: Streaming read or recorded playback
    if payload.action in ("read", "playback"):
        # Parse query string
        params = urllib.parse.parse_qs(payload.query)
        token_list = params.get("token")
        if not token_list or not token_list[0]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing media token in query parameters",
            )

        token_str = token_list[0]
        verified = default_media_token_service.verify_token(token_str)
        if verified is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired media token",
            )

        token_serial = verified.get("serial")
        token_stream = verified.get("stream")
        expected_path = f"cam/{token_serial}/{token_stream}"
        req_path = payload.path.strip("/")
        if req_path != expected_path and not req_path.startswith(f"{expected_path}/"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Token path mismatch (expected {expected_path}, got {req_path})",
            )

        # Verify user still exists, is active, and retains permissions
        user_id = verified.get("sub")
        stmt = select(User).options(selectinload(User.permissions)).where(User.id == user_id)
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is inactive or not found",
            )

        if user.role not in ("owner", "operator"):
            allowed_cameras = {p.camera_serial for p in user.permissions}
            if token_serial not in allowed_cameras:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied to camera '{token_serial}'",
                )

        return {"status": "ok"}

    # Case 3: Reject all other actions
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Action '{payload.action}' forbidden",
    )
