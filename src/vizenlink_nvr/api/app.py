"""FastAPI application factory and route registration for VizenLink NVR."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vizenlink_nvr.api.cam_proxy import cam_proxy_router
from vizenlink_nvr.api.v1.audit import audit_router
from vizenlink_nvr.api.v1.auth import auth_router
from vizenlink_nvr.api.v1.camera_settings import camera_settings_router
from vizenlink_nvr.api.v1.cameras import cameras_router
from vizenlink_nvr.api.v1.events import events_router
from vizenlink_nvr.api.v1.gallery import gallery_router
from vizenlink_nvr.api.v1.health import health_router
from vizenlink_nvr.api.v1.mobile import mobile_router
from vizenlink_nvr.api.v1.playback import playback_router
from vizenlink_nvr.api.v1.recording import recording_router
from vizenlink_nvr.api.v1.storage import storage_router
from vizenlink_nvr.api.v1.users import users_router


def create_app(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    runtime: Any | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application instance."""

    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI):
        has_sf = getattr(fastapi_app.state, "session_factory", None) is not None
        has_rt = getattr(fastapi_app.state, "runtime", None) is not None
        if not has_sf and not has_rt:
            from vizenlink_nvr.config import load_settings
            from vizenlink_nvr.db.engine import create_engine_for, upgrade_to_head
            from vizenlink_nvr.paths import db_path, ensure_data_dir

            settings = load_settings()
            ensure_data_dir(settings)
            db_p = db_path(settings)
            upgrade_to_head(db_p)
            engine = create_engine_for(db_p)
            fastapi_app.state.engine = engine
            fastapi_app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
        yield
        engine = getattr(fastapi_app.state, "engine", None)
        if engine is not None:
            await engine.dispose()

    app = FastAPI(
        title="VizenLink NVR API",
        description="VizenLink Network Video Recorder REST API",
        version="1.0.0",
        openapi_url="/api/v1/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Attach database session factory or runtime
    app.state.session_factory = session_factory
    app.state.runtime = runtime

    # V1 API Router
    v1_router = APIRouter(prefix="/api/v1")
    v1_router.include_router(auth_router)
    v1_router.include_router(users_router)
    v1_router.include_router(cameras_router)
    v1_router.include_router(camera_settings_router)
    v1_router.include_router(recording_router)
    v1_router.include_router(storage_router)
    v1_router.include_router(health_router)
    v1_router.include_router(audit_router)
    v1_router.include_router(events_router)
    v1_router.include_router(playback_router)
    v1_router.include_router(gallery_router)
    v1_router.include_router(mobile_router, prefix="/mobile")

    app.include_router(v1_router)
    app.include_router(cam_proxy_router)

    # Mount React Web SPA build if available
    web_dist = Path(__file__).resolve().parent.parent / "web" / "dist"
    if web_dist.exists() and (web_dist / "index.html").exists():
        index_file = web_dist / "index.html"

        if (web_dist / "assets").exists():
            app.mount(
                "/assets",
                StaticFiles(directory=str(web_dist / "assets")),
                name="assets",
            )

        @app.get("/", include_in_schema=False)
        async def serve_index() -> FileResponse:
            return FileResponse(index_file)

        @app.exception_handler(404)
        async def spa_404_handler(request: Request, exc: Exception) -> Response:
            path = request.url.path
            if (
                path.startswith("/api/")
                or path.startswith("/docs")
                or path.startswith("/redoc")
                or path.startswith("/test-")
            ):
                return JSONResponse({"detail": "Not Found"}, status_code=404)

            candidate = web_dist / path.lstrip("/")
            if candidate.is_file():
                return FileResponse(candidate)

            return FileResponse(index_file)

    return app


# Default ASGI application instance
app = create_app()
