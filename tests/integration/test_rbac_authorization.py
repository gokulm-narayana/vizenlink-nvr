"""Integration tests for server-side RBAC authorization and role hierarchy (AUTH-03)."""

from pathlib import Path

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.api.dependencies import (
    CurrentUser,
    RequireOperator,
    RequireOwner,
    RequireViewer,
    verify_camera_access,
)
from vizenlink_nvr.db.engine import create_engine_for, upgrade_to_head
from vizenlink_nvr.db.models import Camera, User, UserCameraPermission
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.session_manager import SessionManager
from vizenlink_nvr.timeutil import utc_now

# Test router to verify RBAC hierarchy
rbac_test_router = APIRouter(prefix="/test-rbac")


@rbac_test_router.get("/viewer-only")
async def viewer_endpoint(user: RequireViewer) -> dict[str, str]:
    return {"message": f"Hello {user.username}, viewer access granted"}


@rbac_test_router.get("/operator-only")
async def operator_endpoint(user: RequireOperator) -> dict[str, str]:
    return {"message": f"Hello {user.username}, operator access granted"}


@rbac_test_router.get("/owner-only")
async def owner_endpoint(user: RequireOwner) -> dict[str, str]:
    return {"message": f"Hello {user.username}, owner access granted"}


@rbac_test_router.get("/camera/{serial}")
async def camera_access_endpoint(serial: str, user: CurrentUser) -> dict[str, str]:
    verify_camera_access(serial, user)
    return {"message": f"Access granted to camera {serial}"}


@pytest.mark.asyncio
async def test_rbac_hierarchy_and_camera_permissions(tmp_path: Path) -> None:
    """Test RBAC role enforcement and camera whitelist filtering."""
    db_file = tmp_path / "test_rbac.db"
    upgrade_to_head(db_file)
    engine = create_engine_for(db_file)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    now = utc_now()

    # Seed users and cameras
    async with session_factory() as session:
        cam1 = Camera(
            serial="CAM-01",
            host="192.168.1.10",
            tls_fingerprint_sha256="fake1",
            added_at=now,
            host_updated_at=now,
        )
        cam2 = Camera(
            serial="CAM-02",
            host="192.168.1.11",
            tls_fingerprint_sha256="fake2",
            added_at=now,
            host_updated_at=now,
        )
        session.add_all([cam1, cam2])

        owner = User(
            username="owner_user",
            password_hash=hash_password("OwnerPassword123!"),
            role="owner",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        operator = User(
            username="operator_user",
            password_hash=hash_password("OperatorPassword123!"),
            role="operator",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        viewer = User(
            username="viewer_user",
            password_hash=hash_password("ViewerPassword123!"),
            role="viewer",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add_all([owner, operator, viewer])
        await session.flush()

        # Grant viewer permission only to CAM-01
        perm = UserCameraPermission(
            user_id=viewer.id,
            camera_serial="CAM-01",
            created_at=now,
        )
        session.add(perm)

        # Create sessions
        sess_owner = await SessionManager.create_session(session, owner.id)
        sess_operator = await SessionManager.create_session(session, operator.id)
        sess_viewer = await SessionManager.create_session(session, viewer.id)

        token_owner = sess_owner.id
        token_operator = sess_operator.id
        token_viewer = sess_viewer.id

    app = create_app(session_factory=session_factory)
    app.include_router(rbac_test_router)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Unauthenticated request -> 401
        res = await client.get("/test-rbac/viewer-only")
        assert res.status_code == 401

        # 2. Viewer access
        client.cookies.set("session_id", token_viewer)
        # Viewer can access viewer endpoint
        assert (await client.get("/test-rbac/viewer-only")).status_code == 200
        # Viewer CANNOT access operator or owner endpoints -> 403
        assert (await client.get("/test-rbac/operator-only")).status_code == 403
        assert (await client.get("/test-rbac/owner-only")).status_code == 403

        # Viewer can access permitted camera CAM-01
        res_cam1 = await client.get("/test-rbac/camera/CAM-01")
        assert res_cam1.status_code == 200
        # Viewer CANNOT access unpermitted camera CAM-02 -> 403
        res_cam2 = await client.get("/test-rbac/camera/CAM-02")
        assert res_cam2.status_code == 403
        assert "Access denied to camera 'CAM-02'" in res_cam2.json()["detail"]

        # 3. Operator access
        client.cookies.set("session_id", token_operator)
        # Operator can access viewer and operator endpoints
        assert (await client.get("/test-rbac/viewer-only")).status_code == 200
        assert (await client.get("/test-rbac/operator-only")).status_code == 200
        # Operator CANNOT access owner endpoint -> 403
        assert (await client.get("/test-rbac/owner-only")).status_code == 403
        # Operator has universal camera access
        assert (await client.get("/test-rbac/camera/CAM-01")).status_code == 200
        assert (await client.get("/test-rbac/camera/CAM-02")).status_code == 200

        # 4. Owner access
        client.cookies.set("session_id", token_owner)
        # Owner can access everything
        assert (await client.get("/test-rbac/viewer-only")).status_code == 200
        assert (await client.get("/test-rbac/operator-only")).status_code == 200
        assert (await client.get("/test-rbac/owner-only")).status_code == 200
        assert (await client.get("/test-rbac/camera/CAM-01")).status_code == 200
        assert (await client.get("/test-rbac/camera/CAM-02")).status_code == 200

    await engine.dispose()
