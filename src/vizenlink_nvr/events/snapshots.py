"""Event trigger snapshot capture and filesystem management (EVT-04)."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# Minimal valid 1x1 JPEG byte sequence
TINY_JPEG_BYTES = bytes(
    [
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x01, 0x00, 0x48, 0x00, 0x48, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
        0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
        0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
        0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F,
        0x00, 0x7F, 0x00, 0x3F, 0xFF, 0xD9,
    ]
)


class EventSnapshotManager:
    """Manages acquisition and disk storage of event snapshots."""

    def __init__(self, storage_root: Path) -> None:
        self.storage_root = storage_root.resolve()

    def build_snapshot_paths(
        self,
        camera_serial: str,
        trigger_time: datetime,
        event_id: int,
    ) -> tuple[Path, str]:
        """Construct full filesystem path and storage-relative path for snapshot."""
        safe_serial = camera_serial.lower().replace("/", "_").replace("\\", "_")
        year_str = trigger_time.strftime("%Y")
        month_str = trigger_time.strftime("%m")
        day_str = trigger_time.strftime("%d")

        rel_path = f"events/{safe_serial}/{year_str}/{month_str}/{day_str}/{event_id}.jpg"
        full_path = self.storage_root / rel_path
        return full_path, rel_path

    async def acquire_snapshot(
        self,
        camera_serial: str,
        trigger_time: datetime,
        event_id: int,
        snapshot_uri: str | None = None,
        auth: tuple[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
        use_fallback_on_error: bool = True,
    ) -> str | None:
        """Capture JPEG snapshot from camera URI or fallback to placeholder.
        
        Returns relative path on success, or None on failure without raising.
        """
        full_path, rel_path = self.build_snapshot_paths(camera_serial, trigger_time, event_id)
        jpeg_bytes: bytes | None = None

        if snapshot_uri:
            try:
                if client is not None:
                    res = await client.get(snapshot_uri, auth=auth, timeout=3.0)
                else:
                    async with httpx.AsyncClient(timeout=3.0) as temp_client:
                        res = await temp_client.get(snapshot_uri, auth=auth)

                if res.status_code == 200 and len(res.content) > 4:
                    if res.content.startswith(b"\xFF\xD8\xFF"):
                        jpeg_bytes = res.content
                    else:
                        logger.warning("Snapshot response from %s was not valid JPEG", snapshot_uri)
            except Exception as exc:
                logger.warning("Failed to fetch camera snapshot for event %d: %s", event_id, exc)

        if jpeg_bytes is None and use_fallback_on_error:
            jpeg_bytes = TINY_JPEG_BYTES

        if jpeg_bytes is None:
            return None

        # Write to disk
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(jpeg_bytes)
            if os.name == "posix":
                os.chmod(full_path, 0o640)
            return rel_path
        except Exception as exc:
            logger.error("Failed to write snapshot file %s: %s", full_path, exc)
            return None

    def resolve_snapshot_file(self, rel_path: str) -> Path | None:
        """Safely resolve relative path to existing file, preventing directory traversal."""
        # Sanitize and resolve
        resolved = (self.storage_root / rel_path).resolve()
        try:
            # Check if within storage root
            resolved.relative_to(self.storage_root)
        except ValueError:
            logger.warning("Directory traversal attempt blocked: %s", rel_path)
            return None

        return resolved if resolved.is_file() else None

