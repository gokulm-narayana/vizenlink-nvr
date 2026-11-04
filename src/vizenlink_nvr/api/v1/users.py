"""User management endpoints for VizenLink NVR (AUTH-04, AUTH-05)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from vizenlink_nvr.api.dependencies import DbSession, RequireOwner
from vizenlink_nvr.db.models import Camera, User, UserCameraPermission
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.session_manager import SessionManager
from vizenlink_nvr.services.setup import MIN_PASSWORD_LENGTH
from vizenlink_nvr.timeutil import utc_now

users_router = APIRouter(prefix="/users", tags=["users"])


class UserDetailResponse(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    cognito_sub: str | None = None
    created_at: str
    updated_at: str
    permissions: list[str] = []


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=MIN_PASSWORD_LENGTH)
    role: str = Field(default="viewer")
    permissions: list[str] = Field(default_factory=list)


class UpdateUserRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    permissions: list[str] | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=MIN_PASSWORD_LENGTH)


VALID_ROLES = {"owner", "operator", "viewer"}


def _serialize_user(user: User) -> UserDetailResponse:
    perms: list[str] = []
    if "permissions" in user.__dict__ and user.permissions:
        perms = [p.camera_serial for p in user.permissions]
    return UserDetailResponse(
        id=user.id,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        cognito_sub=user.cognito_sub,
        created_at=user.created_at.isoformat(),
        updated_at=user.updated_at.isoformat(),
        permissions=perms,
    )


@users_router.get("", response_model=list[UserDetailResponse])
async def list_users(
    db: DbSession,
    _: RequireOwner,
) -> list[UserDetailResponse]:
    """List all user accounts and their camera permissions (Admin/Owner only)."""
    stmt = (
        select(User)
        .options(selectinload(User.permissions))
        .order_by(User.id.asc())
    )
    users = (await db.execute(stmt)).scalars().all()
    return [_serialize_user(u) for u in users]


@users_router.post("", response_model=UserDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest,
    db: DbSession,
    _: RequireOwner,
) -> UserDetailResponse:
    """Create a new user account with role and optional camera whitelist (Admin/Owner only)."""
    username = payload.username.strip()
    if not username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username cannot be empty",
        )

    # Check username uniqueness
    existing = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User '{username}' already exists",
        )

    role = payload.role.strip().lower()
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role '{payload.role}'. Must be one of: {sorted(VALID_ROLES)}",
        )

    now = utc_now()
    perms: list[UserCameraPermission] = []

    # Assign camera permissions if specified
    if payload.permissions:
        # Validate that cameras exist
        cams = (
            await db.execute(select(Camera.serial).where(Camera.serial.in_(payload.permissions)))
        ).scalars().all()
        existing_serials = set(cams)
        invalid_serials = set(payload.permissions) - existing_serials
        if invalid_serials:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown camera serial(s): {sorted(invalid_serials)}",
            )

        perms = [
            UserCameraPermission(
                camera_serial=serial,
                created_at=now,
            )
            for serial in payload.permissions
        ]

    new_user = User(
        username=username,
        password_hash=hash_password(payload.password),
        role=role,
        is_active=True,
        cognito_sub=None,
        created_at=now,
        updated_at=now,
        permissions=perms,
    )
    db.add(new_user)
    await db.commit()

    # Eagerly load user with permissions
    stmt = select(User).where(User.id == new_user.id).options(selectinload(User.permissions))
    loaded = (await db.execute(stmt)).scalar_one()
    return _serialize_user(loaded)


@users_router.get("/{user_id}", response_model=UserDetailResponse)
async def get_user(
    user_id: int,
    db: DbSession,
    _: RequireOwner,
) -> UserDetailResponse:
    """Retrieve detailed user account information (Admin/Owner only)."""
    stmt = select(User).where(User.id == user_id).options(selectinload(User.permissions))
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found",
        )
    return _serialize_user(user)


@users_router.patch("/{user_id}", response_model=UserDetailResponse)
async def update_user(
    user_id: int,
    payload: UpdateUserRequest,
    db: DbSession,
    current_user: RequireOwner,
) -> UserDetailResponse:
    """Update user role, active status, and camera whitelist (Admin/Owner only)."""
    stmt = select(User).where(User.id == user_id).options(selectinload(User.permissions))
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found",
        )

    # Self-modification protection for owner
    if user.id == current_user.id:
        if payload.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Owners cannot disable their own account",
            )
        if payload.role is not None and payload.role.strip().lower() != "owner":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Owners cannot demote their own account",
            )

    now = utc_now()

    if payload.role is not None:
        role = payload.role.strip().lower()
        if role not in VALID_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role '{payload.role}'. Must be one of: {sorted(VALID_ROLES)}",
            )
        user.role = role

    if payload.is_active is not None:
        user.is_active = payload.is_active
        if not payload.is_active:
            # Invalidate all active sessions for disabled user
            await SessionManager.invalidate_user_sessions(db, user.id)

    if payload.permissions is not None:
        # Validate cameras
        if payload.permissions:
            cams = (
                await db.execute(select(Camera.serial).where(Camera.serial.in_(payload.permissions)))
            ).scalars().all()
            existing_serials = set(cams)
            invalid_serials = set(payload.permissions) - existing_serials
            if invalid_serials:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unknown camera serial(s): {sorted(invalid_serials)}",
                )

        current_serials = {p.camera_serial for p in user.permissions}
        target_serials = set(payload.permissions)

        # Retain permissions that are still in target
        user.permissions = [p for p in user.permissions if p.camera_serial in target_serials]

        # Add newly granted permissions
        for s in target_serials:
            if s not in current_serials:
                user.permissions.append(
                    UserCameraPermission(
                        user_id=user.id,
                        camera_serial=s,
                        created_at=now,
                    )
                )

    user.updated_at = now
    await db.commit()
    return _serialize_user(user)


@users_router.post("/{user_id}/reset-password", response_model=dict[str, Any])
async def reset_password(
    user_id: int,
    payload: ResetPasswordRequest,
    db: DbSession,
    _: RequireOwner,
) -> dict[str, Any]:
    """Admin reset of a user's password; invalidates user's existing sessions (Admin/Owner only)."""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found",
        )

    user.password_hash = hash_password(payload.new_password)
    user.updated_at = utc_now()

    # Invalidate all existing sessions so old logins cannot continue
    await SessionManager.invalidate_user_sessions(db, user.id)
    await db.commit()

    return {"success": True, "message": f"Password reset successfully for user '{user.username}'"}
