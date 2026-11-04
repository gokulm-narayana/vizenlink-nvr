"""Unit tests for GalleryItem model and GalleryService (GAL-01, GAL-02, PLAY-06)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vizenlink_nvr.db.models import Base, Camera, GalleryItem, User
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.gallery import GalleryService
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
async def session_factory(tmp_path: Path):
    db_path = tmp_path / "test_gallery.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_gallery_item_crud_and_check_constraint(session_factory, tmp_path: Path):
    storage_root = tmp_path / "recordings"
    storage_root.mkdir()
    now = utc_now()

    async with session_factory() as session:
        cam = Camera(
            serial="CAM-GALLERY",
            host="192.168.1.50",
            name="Garden Camera",
            tls_fingerprint_sha256="",
            added_at=now,
            host_updated_at=now,
        )
        user = User(
            username="gallery_user",
            password_hash=hash_password("UserPass123!"),
            role="operator",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add_all([cam, user])
        await session.commit()

        # 1. Create snapshot item
        rel_snap = GalleryService.generate_relative_path("CAM-GALLERY", "snapshot", now, "snap1.jpg")
        snap_file = storage_root / rel_snap
        snap_file.parent.mkdir(parents=True, exist_ok=True)
        snap_file.write_bytes(b"\xFF\xD8\xFF\xE0" + b"\x00" * 100)

        item = await GalleryService.create_item(
            session=session,
            camera_serial="CAM-GALLERY",
            item_type="snapshot",
            title="Driveway Motion",
            file_path=rel_snap,
            file_size_bytes=snap_file.stat().st_size,
            captured_at=now,
            user_id=user.id,
        )
        assert item.id is not None
        assert item.item_type == "snapshot"
        assert item.title == "Driveway Motion"

        # 2. Query items
        items, total = await GalleryService.query_items(session, camera_serials=["CAM-GALLERY"])
        assert total == 1
        assert len(items) == 1
        assert items[0].id == item.id

        # 3. Path traversal protection
        traversal = GalleryService.resolve_file_path(storage_root, "../../etc/passwd")
        assert traversal is None

        resolved = GalleryService.resolve_file_path(storage_root, rel_snap)
        assert resolved is not None and resolved.exists()

        # 4. Delete item
        deleted = await GalleryService.delete_item(session, item.id, storage_root)
        assert deleted is not None
        assert not snap_file.exists()

        # Check DB count after deletion
        items_after, total_after = await GalleryService.query_items(session)
        assert total_after == 0


@pytest.mark.asyncio
async def test_gallery_invalid_type_rejected(session_factory):
    now = utc_now()
    async with session_factory() as session:
        cam = Camera(
            serial="CAM-REJECT",
            host="192.168.1.51",
            name="Reject Cam",
            tls_fingerprint_sha256="",
            added_at=now,
            host_updated_at=now,
        )
        session.add(cam)
        await session.commit()

        # Python service check
        with pytest.raises(ValueError, match="Invalid item_type"):
            await GalleryService.create_item(
                session=session,
                camera_serial="CAM-REJECT",
                item_type="invalid_format",
                title="Bad item",
                file_path="dummy.mp4",
                file_size_bytes=100,
                captured_at=now,
            )

        # Database CheckConstraint check
        bad_item = GalleryItem(
            camera_serial="CAM-REJECT",
            item_type="unsupported",
            title="DB check",
            file_path="dummy.mp4",
            file_size_bytes=100,
            captured_at=now,
            created_at=now,
        )
        session.add(bad_item)
        with pytest.raises(IntegrityError):
            await session.commit()
