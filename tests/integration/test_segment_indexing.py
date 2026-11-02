"""Integration tests for real-time segment completion hook indexing (REC-09)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.db.models import Camera, Segment
from vizenlink_nvr.services.runtime import open_runtime
from vizenlink_nvr.timeutil import utc_now


def test_hook_segment_complete_cli(
    cli: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """nvr recording hook-segment-complete indexes segment into SQLite via environment variables."""
    data_dir = tmp_path / "nvr_data"
    settings = load_settings(data_dir=data_dir)

    # Initialize DB
    cli.invoke(app, ["status", "--data-dir", str(data_dir)])

    import asyncio

    # Seed registered camera
    async def _seed_camera() -> None:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                now = utc_now()
                cam = Camera(
                    serial="VZL-CAM-001",
                    host="192.168.1.100",
                    https_port=443,
                    mac="AA:BB:CC:DD:EE:01",
                    name="Front Door",
                    state="active",
                    tls_fingerprint_sha256="fp_front",
                    added_at=now,
                    host_updated_at=now,
                )
                session.add(cam)
                await session.commit()

    asyncio.run(_seed_camera())

    # Create mock video segment on disk
    rec_dir = tmp_path / "recordings" / "cam" / "vzl-cam-001" / "main" / "2026" / "11" / "02"
    rec_dir.mkdir(parents=True, exist_ok=True)
    seg_file = rec_dir / "2026-11-02T15-30-00Z-000000.mp4"
    seg_file.write_bytes(b"\x00" * 8192)  # 8 KB mock segment

    # Set MediaMTX environment variables
    monkeypatch.setenv("MTX_PATH", "cam/vzl-cam-001/main")
    monkeypatch.setenv("MTX_SEGMENT_PATH", str(seg_file))
    monkeypatch.setenv("MTX_SEGMENT_DURATION", "60.05")

    # Run hook CLI command (takes zero arguments!)
    res = cli.invoke(app, ["recording", "hook-segment-complete", "--data-dir", str(data_dir)])
    assert res.exit_code == 0, res.output

    # Verify segment in database
    async def _verify_segment() -> Segment:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                stmt = select(Segment).where(Segment.file_path == str(seg_file.resolve()))
                seg = (await session.execute(stmt)).scalar_one_or_none()
                assert seg is not None, "Segment was not inserted into database"
                return seg

    seg = asyncio.run(_verify_segment())
    assert seg.camera_serial == "VZL-CAM-001"
    assert seg.stream_type == "main"
    assert seg.file_size_bytes == 8192
    assert seg.duration_seconds == 60.05
    assert seg.status == "active"
    assert seg.is_protected is False
