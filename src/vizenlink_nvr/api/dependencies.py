"""FastAPI dependency injection utilities."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.db.models import User
from vizenlink_nvr.services.session_manager import SESSION_COOKIE_NAME, SessionManager


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield an active asynchronous database session from app.state."""
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        runtime = getattr(request.app.state, "runtime", None)
        if runtime is not None:
            session_factory = runtime.sessions
    if session_factory is None:
        raise RuntimeError("Database session factory not configured on app.state")

    async with session_factory() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user_optional(
    request: Request,
    db: DbSession,
    session_id: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> User | None:
    """Retrieve the authenticated user from session cookie or Bearer token, if present."""
    token = session_id
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()

    if not token:
        return None

    result = await SessionManager.validate_session(db, token)
    if result is None:
        return None
    _, user = result
    return user


CurrentUserOptional = Annotated[User | None, Depends(get_current_user_optional)]


async def get_current_user(
    user: CurrentUserOptional,
) -> User:
    """Require an authenticated active user or raise HTTP 401."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]

ROLE_HIERARCHY: dict[str, int] = {
    "viewer": 1,
    "operator": 2,
    "owner": 3,
}


def require_role(min_role: str) -> Callable[[User], Awaitable[User]]:
    """Return a dependency enforcing that the user has at least min_role privileges."""
    min_rank = ROLE_HIERARCHY.get(min_role, 99)

    async def _role_checker(user: CurrentUser) -> User:
        user_rank = ROLE_HIERARCHY.get(user.role, 0)
        if user_rank < min_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires '{min_role}' role or higher",
            )
        return user

    return _role_checker


RequireOwner = Annotated[User, Depends(require_role("owner"))]
RequireOperator = Annotated[User, Depends(require_role("operator"))]
RequireViewer = Annotated[User, Depends(require_role("viewer"))]


def verify_camera_access(serial: str, user: User) -> None:
    """Verify that user is permitted to view or access the given camera serial.
    
    Owners and Operators have universal access.
    Viewers must have an explicit UserCameraPermission entry for the serial.
    """
    if user.role in ("owner", "operator"):
        return
    allowed = {p.camera_serial for p in user.permissions}
    if serial not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied to camera '{serial}'",
        )
