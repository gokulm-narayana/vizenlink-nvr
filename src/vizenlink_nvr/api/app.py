"""FastAPI application factory and route registration for VizenLink NVR."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vizenlink_nvr.api.v1.audit import audit_router
from vizenlink_nvr.api.v1.auth import auth_router
from vizenlink_nvr.api.v1.cameras import cameras_router
from vizenlink_nvr.api.v1.health import health_router
from vizenlink_nvr.api.v1.recording import recording_router
from vizenlink_nvr.api.v1.storage import storage_router
from vizenlink_nvr.api.v1.users import users_router


def create_app(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    runtime: Any | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="VizenLink NVR API",
        description="VizenLink Network Video Recorder REST API",
        version="1.0.0",
        openapi_url="/api/v1/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Attach database session factory or runtime
    app.state.session_factory = session_factory
    app.state.runtime = runtime

    # V1 API Router
    v1_router = APIRouter(prefix="/api/v1")
    v1_router.include_router(auth_router)
    v1_router.include_router(users_router)
    v1_router.include_router(cameras_router)
    v1_router.include_router(recording_router)
    v1_router.include_router(storage_router)
    v1_router.include_router(health_router)
    v1_router.include_router(audit_router)

    app.include_router(v1_router)

    return app


# Default ASGI application instance
app = create_app()

