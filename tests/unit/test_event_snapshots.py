"""Unit tests for EventSnapshotManager (EVT-04)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from vizenlink_nvr.events.snapshots import (
    TINY_JPEG_BYTES,
    EventSnapshotManager,
)
from vizenlink_nvr.timeutil import utc_now


@pytest.mark.asyncio
async def test_build_snapshot_paths_and_storage(tmp_path: Path) -> None:
    """Snapshot paths follow {storage_root}/events/{serial}/{YYYY}/{MM}/{DD}/{id}.jpg."""
    storage_root = tmp_path / "rec"
    manager = EventSnapshotManager(storage_root)
    now = utc_now().replace(year=2026, month=11, day=4)

    full, rel = manager.build_snapshot_paths("CAM-01", now, 42)
    assert rel == "events/cam-01/2026/11/04/42.jpg"
    assert full == storage_root / "events/cam-01/2026/11/04/42.jpg"


@pytest.mark.asyncio
async def test_acquire_snapshot_from_camera_mock(tmp_path: Path) -> None:
    """Acquire snapshot successfully fetches JPEG from mock camera URI."""
    storage_root = tmp_path / "rec"
    manager = EventSnapshotManager(storage_root)
    now = utc_now().replace(year=2026, month=11, day=4)

    valid_jpeg = TINY_JPEG_BYTES

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/onvif/snapshot"
        return httpx.Response(200, content=valid_jpeg, headers={"Content-Type": "image/jpeg"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        rel = await manager.acquire_snapshot(
            camera_serial="CAM-01",
            trigger_time=now,
            event_id=101,
            snapshot_uri="http://camera.local/onvif/snapshot",
            client=client,
        )
        assert rel == "events/cam-01/2026/11/04/101.jpg"
        resolved = manager.resolve_snapshot_file(rel)
        assert resolved is not None
        assert resolved.exists()
        assert resolved.read_bytes() == valid_jpeg


@pytest.mark.asyncio
async def test_acquire_snapshot_fallback_on_network_error(tmp_path: Path) -> None:
    """Acquire snapshot uses fallback placeholder when camera HTTP request fails."""
    storage_root = tmp_path / "rec"
    manager = EventSnapshotManager(storage_root)
    now = utc_now().replace(year=2026, month=11, day=4)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"Server Error")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        # With fallback enabled
        rel_fallback = await manager.acquire_snapshot(
            camera_serial="CAM-01",
            trigger_time=now,
            event_id=102,
            snapshot_uri="http://camera.local/onvif/snapshot",
            client=client,
            use_fallback_on_error=True,
        )
        assert rel_fallback is not None
        file_p = manager.resolve_snapshot_file(rel_fallback)
        assert file_p is not None
        assert file_p.read_bytes() == TINY_JPEG_BYTES

        # With fallback disabled -> returns None
        rel_none = await manager.acquire_snapshot(
            camera_serial="CAM-01",
            trigger_time=now,
            event_id=103,
            snapshot_uri="http://camera.local/onvif/snapshot",
            client=client,
            use_fallback_on_error=False,
        )
        assert rel_none is None


def test_directory_traversal_protection(tmp_path: Path) -> None:
    """Path resolution prevents escaping the storage root via directory traversal."""
    storage_root = tmp_path / "rec"
    storage_root.mkdir(parents=True)
    manager = EventSnapshotManager(storage_root)

    # Attempt directory traversal
    resolved = manager.resolve_snapshot_file("../../etc/passwd")
    assert resolved is None

