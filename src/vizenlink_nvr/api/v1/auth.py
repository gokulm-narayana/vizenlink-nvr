"""Authentication and setup endpoints for VizenLink NVR."""

from __future__ import annotations

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
from vizenlink_nvr.services.auth_hasher import hash_password, verify_password
from vizenlink_nvr.services.rate_limiter import login_rate_limiter
from vizenlink_nvr.services.session_manager import (
    SESSION_COOKIE_NAME,
    SessionManager,
)
from vizenlink_nvr.services.setup import MIN_PASSWORD_LENGTH, SetupService
from vizenlink_nvr.timeutil import utc_now

auth_router = APIRouter(prefix="/auth", tags=["auth"])


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

    if current_user is not None:
        user_resp = UserResponse(
            id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            is_active=current_user.is_active,
            cognito_sub=current_user.cognito_sub,
            permissions=[p.camera_serial for p in current_user.permissions],
        )

    return AuthStatusResponse(
        initialized=is_init,
        authenticated=current_user is not None,
        user=user_resp,
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

    return {"success": True}