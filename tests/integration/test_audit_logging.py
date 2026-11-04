"""Integration tests for persistent audit logging and query endpoint (AUTH-07)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.models import Base, User
from vizenlink_nvr.services.audit import AuditService
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.session_manager import SessionManager
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
async def app_fixture(tmp_path: Path):
    db_path = tmp_path / "test_audit.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app = create_app(session_factory=session_factory)

    async with session_factory() as session:
        owner = User(
            username="owner_audit",
            password_hash=hash_password("OwnerPassword123!"),
            role="owner",
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        viewer = User(
            username="viewer_audit",
            password_hash=hash_password("ViewerPassword123!"),
            role="viewer",
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add_all([owner, viewer])
        await session.commit()
        await session.refresh(owner)
        await session.refresh(viewer)

        s_owner = await SessionManager.create_session(session, owner.id, "127.0.0.1", "test")
        s_viewer = await SessionManager.create_session(session, viewer.id, "127.0.0.1", "test")

        owner_session = s_owner.id
        viewer_session = s_viewer.id

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client, owner_session, viewer_session, session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_audit_log_rbac_and_query_filtering(app_fixture) -> None:
    """Audit logs require owner role, record events accurately, and support filtering."""
    client, owner_session, viewer_session, session_factory = app_fixture

    # 1. Anonymous query rejected with 401
    res_anon = await client.get("/api/v1/audit-logs")
    assert res_anon.status_code == 401

    # 2. Viewer query rejected with 403 (Owner only)
    client.cookies.set("session_id", viewer_session)
    res_viewer = await client.get("/api/v1/audit-logs")
    assert res_viewer.status_code == 403

    # 3. Simulate actions that generate audit events
    # a) Failed login
    res_bad_login = await client.post(
        "/api/v1/auth/login",
        json={"username": "unknown_intruder", "password": "WrongPassword123!"},
    )
    assert res_bad_login.status_code == 401

    # b) Successful login
    res_ok_login = await client.post(
        "/api/v1/auth/login",
        json={"username": "owner_audit", "password": "OwnerPassword123!"},
    )
    assert res_ok_login.status_code == 200

    # c) Owner creates a user
    client.cookies.set("session_id", owner_session)
    res_create_user = await client.post(
        "/api/v1/users",
        json={
            "username": "new_operator",
            "password": "Password123!",
            "role": "operator",
            "permissions": [],
        },
    )
    assert res_create_user.status_code == 201

    # 4. Owner queries audit logs
    res_logs = await client.get("/api/v1/audit-logs?limit=50")
    assert res_logs.status_code == 200
    data = res_logs.json()
    assert "items" in data
    assert data["total"] >= 3
    actions = [item["action"] for item in data["items"]]
    assert "auth.login_failure" in actions
    assert "auth.login_success" in actions
    assert "user.create" in actions

    # 5. Filter by action
    res_filter_action = await client.get("/api/v1/audit-logs?action=user.create")
    assert res_filter_action.status_code == 200
    action_items = res_filter_action.json()["items"]
    assert len(action_items) == 1
    assert action_items[0]["action"] == "user.create"
    assert action_items[0]["actor_username"] == "owner_audit"

    # 6. Filter by actor
    res_filter_actor = await client.get("/api/v1/audit-logs?actor=unknown_intruder")
    assert res_filter_actor.status_code == 200
    actor_items = res_filter_actor.json()["items"]
    assert len(actor_items) == 1
    assert actor_items[0]["action"] == "auth.login_failure"


@pytest.mark.asyncio
async def test_audit_service_direct_unit(app_fixture) -> None:
    """Verify AuditService direct record_event and query_events."""
    _, _, _, session_factory = app_fixture
    async with session_factory() as session:
        await AuditService.record_event(
            session=session,
            action="custom.test_event",
            resource_type="system",
            actor_username="test_runner",
            details={"key": "value"},
            commit=True,
        )

        events = await AuditService.query_events(session, action="custom.test_event")
        assert len(events) == 1
        assert events[0].action == "custom.test_event"
        assert events[0].actor_username == "test_runner"
        assert events[0].details_json == '{"key":"value"}'

