"""Integration tests for 0004_auth_and_audit migration, cascading deletes, and rollback."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from vizenlink_nvr.db.engine import (
    alembic_config,
    create_engine_for,
    current_revision,
    head_revision,
    upgrade_to_head,
)
from vizenlink_nvr.db.models import (
    Camera,
    CameraOutage,
    Session,
    User,
    UserCameraPermission,
)
from vizenlink_nvr.timeutil import UTC


def test_migration_0004_upgrade_and_downgrade(tmp_path: Path) -> None:
    """Test upgrade to 0004, alembic check, downgrade to 0003, and re-upgrade."""
    db_file = tmp_path / "test_auth_migration.db"
    assert not db_file.exists()

    # 1. Upgrade to head (0004)
    upgrade_to_head(db_file)
    assert current_revision(db_file) == "0004_auth_and_audit"
    assert head_revision() == "0004_auth_and_audit"

    # 2. Schema drift check against Base.metadata
    cfg = alembic_config(db_file)
    command.check(cfg)

    # 3. Downgrade to 0003
    command.downgrade(cfg, "0003_recording_core")
    assert current_revision(db_file) == "0003_recording_core"

    # 4. Re-upgrade to head
    command.upgrade(cfg, "head")
    assert current_revision(db_file) == "0004_auth_and_audit"
    command.check(cfg)


@pytest.mark.asyncio
async def test_cascading_deletes_on_user_and_camera_removal(tmp_path: Path) -> None:
    """Test cascading deletes when user or camera is deleted."""
    db_file = tmp_path / "test_cascade.db"
    upgrade_to_head(db_file)

    engine = create_engine_for(db_file)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    now = datetime(2026, 11, 3, 12, 0, 0, tzinfo=UTC)

    async with session_factory() as session:
        # Create camera
        cam = Camera(
            serial="CAM-CASCADE-01",
            host="192.168.1.10",
            tls_fingerprint_sha256="sha256fake",
            added_at=now,
            host_updated_at=now,
        )
        session.add(cam)

        # Create user
        user = User(
            username="test_user_del",
            password_hash="$argon2id$v=19$m=65536,t=3,p=4$dummy$dummy",
            role="operator",
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        await session.flush()

        # Add session
        sess = Session(
            id="s" * 64,
            user_id=user.id,
            created_at=now,
            expires_at=now,
            last_active_at=now,
        )
        session.add(sess)

        # Add permission
        perm = UserCameraPermission(
            user_id=user.id,
            camera_serial=cam.serial,
            created_at=now,
        )
        session.add(perm)

        # Add outage
        outage = CameraOutage(
            camera_serial=cam.serial,
            started_at=now,
            reason="manual_disconnect",
        )
        session.add(outage)

        await session.commit()

        # Delete user -> session and permission should cascade delete
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()

        sess_stmt = select(Session).where(Session.user_id == user.id)
        sessions_left = (await session.execute(sess_stmt)).scalars().all()
        assert len(sessions_left) == 0

        perm_stmt = select(UserCameraPermission).where(UserCameraPermission.user_id == user.id)
        perms_left = (await session.execute(perm_stmt)).scalars().all()
        assert len(perms_left) == 0

        # Outage and camera still exist
        outage_stmt = select(CameraOutage).where(CameraOutage.camera_serial == cam.serial)
        outages_left = (await session.execute(outage_stmt)).scalars().all()
        assert len(outages_left) == 1

        # Delete camera -> outage should cascade delete
        await session.execute(delete(Camera).where(Camera.serial == cam.serial))
        await session.commit()

        outages_after_cam_del = (await session.execute(outage_stmt)).scalars().all()
        assert len(outages_after_cam_del) == 0

    await engine.dispose()
