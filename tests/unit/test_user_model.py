"""Unit tests for User, UserCameraPermission, Session, AuditLog, and CameraOutage models."""

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from vizenlink_nvr.db.engine import create_engine_for, upgrade_to_head
from vizenlink_nvr.db.models import (
    AuditLog,
    Camera,
    CameraOutage,
    Session,
    User,
    UserCameraPermission,
)
from vizenlink_nvr.timeutil import UTC


@pytest.mark.asyncio
async def test_user_model_attributes_and_defaults(tmp_path: Path) -> None:
    """Test User model default values and cognito_sub nullable support (AUTH-08)."""
    db_file = tmp_path / "test_user_model.db"
    upgrade_to_head(db_file)

    engine = create_engine_for(db_file)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    now = datetime(2026, 11, 3, 12, 0, 0, tzinfo=UTC)

    async with session_factory() as session:
        user = User(
            username="admin_user",
            password_hash="$argon2id$v=19$m=65536,t=3,p=4$dummy$dummy",
            role="owner",
            is_active=True,
            cognito_sub=None,  # Nullable per AUTH-08
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        await session.commit()

        # Query back
        stmt = select(User).where(User.username == "admin_user")
        loaded = (await session.execute(stmt)).scalar_one()

        assert loaded.id is not None
        assert loaded.username == "admin_user"
        assert loaded.role == "owner"
        assert loaded.is_active is True
        assert loaded.cognito_sub is None
        assert loaded.created_at == now
        assert loaded.updated_at == now

        # Update with cognito_sub
        loaded.cognito_sub = "us-east-1:12345678-abcd-ef01-2345-6789abcdef01"
        await session.commit()

        stmt2 = select(User).where(User.username == "admin_user")
        loaded2 = (await session.execute(stmt2)).scalar_one()
        assert loaded2.cognito_sub == "us-east-1:12345678-abcd-ef01-2345-6789abcdef01"

    await engine.dispose()


@pytest.mark.asyncio
async def test_user_session_and_permission_relationships(tmp_path: Path) -> None:
    """Test relationship navigation across User, Session, and UserCameraPermission."""
    db_file = tmp_path / "test_user_rel.db"
    upgrade_to_head(db_file)

    engine = create_engine_for(db_file)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    now = datetime(2026, 11, 3, 12, 0, 0, tzinfo=UTC)

    async with session_factory() as session:
        # Create camera
        cam = Camera(
            serial="CAM-TEST-REL-01",
            host="192.168.1.50",
            tls_fingerprint_sha256="abc123sha",
            added_at=now,
            host_updated_at=now,
        )
        session.add(cam)

        # Create user
        user = User(
            username="viewer_bob",
            password_hash="$argon2id$v=19$m=65536,t=3,p=4$dummy$dummy",
            role="viewer",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        await session.flush()

        # Create permission
        perm = UserCameraPermission(
            user_id=user.id,
            camera_serial=cam.serial,
            created_at=now,
        )
        session.add(perm)

        # Create session token
        sess = Session(
            id="a" * 64,
            user_id=user.id,
            created_at=now,
            expires_at=now,
            last_active_at=now,
            user_agent="Mozilla/5.0",
            ip_address="192.168.1.100",
        )
        session.add(sess)

        # Create outage
        outage = CameraOutage(
            camera_serial=cam.serial,
            started_at=now,
            ended_at=now,
            duration_seconds=120.5,
            reason="stream_timeout",
        )
        session.add(outage)

        # Create audit log
        audit = AuditLog(
            timestamp=now,
            actor_id=user.id,
            actor_username=user.username,
            ip_address="192.168.1.100",
            action="login_success",
            resource_type="auth",
            resource_id=None,
            details_json='{"method": "password"}',
        )
        session.add(audit)

        await session.commit()

        # Query back
        res_user = (await session.execute(select(User).where(User.id == user.id))).scalar_one()
        assert res_user.username == "viewer_bob"

        audit_stmt = select(AuditLog).where(AuditLog.action == "login_success")
        res_audit = (await session.execute(audit_stmt)).scalar_one()
        assert res_audit.actor_username == "viewer_bob"
        assert res_audit.details_json == '{"method": "password"}'

        outage_stmt = select(CameraOutage).where(CameraOutage.camera_serial == cam.serial)
        res_outage = (await session.execute(outage_stmt)).scalar_one()
        assert res_outage.duration_seconds == 120.5

    await engine.dispose()
