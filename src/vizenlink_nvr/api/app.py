"""FastAPI application factory and route registration for VizenLink NVR."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vizenlink_nvr.api.cam_proxy import cam_proxy_router
from vizenlink_nvr.api.v1.assistant import assistant_router
from vizenlink_nvr.api.v1.audit import audit_router
from vizenlink_nvr.api.v1.auth import auth_router
from vizenlink_nvr.api.v1.camera_accounts import camera_accounts_router
from vizenlink_nvr.api.v1.camera_features import camera_features_router
from vizenlink_nvr.api.v1.camera_recordings import camera_recordings_router
from vizenlink_nvr.api.v1.camera_settings import camera_settings_router
from vizenlink_nvr.api.v1.cameras import cameras_router
from vizenlink_nvr.api.v1.events import events_router
from vizenlink_nvr.api.v1.gallery import gallery_router
from vizenlink_nvr.api.v1.health import health_router
from vizenlink_nvr.api.v1.mobile import mobile_router
from vizenlink_nvr.api.v1.playback import playback_router
from vizenlink_nvr.api.v1.recording import recording_router
from vizenlink_nvr.api.v1.search import search_router
from vizenlink_nvr.api.v1.storage import storage_router
from vizenlink_nvr.api.v1.system import system_router
from vizenlink_nvr.api.v1.users import users_router
from vizenlink_nvr.config import NvrSettings, load_settings
from vizenlink_nvr.services.runtime import open_runtime


def create_app(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    runtime: Any | None = None,
    *,
    settings: NvrSettings | None = None,
    recorder_port: int | None = None,
    recorder_lan_access: bool = False,
) -> FastAPI:
    """Create and configure the FastAPI application instance.

    ``recorder_port`` (the port this API listens on) starts MediaMTX and the recorder
    loops for the life of the app; ``nvr run`` sets it. Tests leave it unset.
    """

    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            owns_runtime = fastapi_app.state.session_factory is None and fastapi_app.state.runtime is None
            if owns_runtime:
                fastapi_app.state.runtime = await stack.enter_async_context(
                    open_runtime(settings if settings is not None else load_settings())
                )
            recorder = None
            if recorder_port is not None and fastapi_app.state.runtime is not None:
                from vizenlink_nvr.services.recorder import RecorderSupervisor

                recorder = RecorderSupervisor(
                    fastapi_app.state.runtime,
                    nvr_port=recorder_port,
                    lan_access=recorder_lan_access,
                    mdns=getattr(fastapi_app.state, "mdns", None),
                )
                fastapi_app.state.mediamtx_webrtc_port = recorder.ports.webrtc
                fastapi_app.state.mediamtx_hls_port = recorder.ports.hls
                await recorder.start()
            fastapi_app.state.recorder = recorder
            try:
                yield
            finally:
                if recorder is not None:
                    await recorder.stop()
                    fastapi_app.state.recorder = None
                if owns_runtime:
                    fastapi_app.state.runtime = None
                camera_settings = getattr(fastapi_app.state, "camera_settings_service", None)
                if camera_settings is not None:
                    await camera_settings.http.aclose()

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
    v1_router.include_router(system_router)
    v1_router.include_router(users_router)
    v1_router.include_router(cameras_router)
    v1_router.include_router(camera_settings_router)
    v1_router.include_router(camera_accounts_router)
    v1_router.include_router(camera_features_router)
    v1_router.include_router(camera_recordings_router)
    v1_router.include_router(recording_router)
    v1_router.include_router(storage_router)
    v1_router.include_router(health_router)
    v1_router.include_router(audit_router)
    v1_router.include_router(search_router)
    v1_router.include_router(assistant_router)
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
            return FileResponse(index_file, headers={"Cache-Control": "no-cache"})

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

            return FileResponse(index_file, headers={"Cache-Control": "no-cache"})

    return app


# Default ASGI application instance
app = create_app()
