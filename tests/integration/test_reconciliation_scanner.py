"""Integration tests for two-source disk reconciliation scanner and nvr storage scan CLI (REC-09)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.db.models import Camera
from vizenlink_nvr.services.runtime import open_runtime
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
def scanner_setup(tmp_path: Path, cli: CliRunner) -> tuple[Path, Path]:
    """Setup NVR with registered camera and storage directory."""
    data_dir = tmp_path / "nvr_data"
    rec_dir = tmp_path / "recordings"
    rec_dir.mkdir(parents=True, exist_ok=True)

    # Initialize NVR database
    cli.invoke(app, ["status", "--data-dir", str(data_dir)])

    # Configure storage path
    res = cli.invoke(
        app,
        [
            "storage",
            "set-path",
            "--path",
            str(rec_dir),
            "--allow-system-disk",
            "--data-dir",
            str(data_dir),
        ],
    )
    assert res.exit_code == 0, res.output

    settings = load_settings(data_dir=data_dir)

    import asyncio

    # Seed cameras
    async def _seed_cams() -> None:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                now = utc_now()
                c1 = Camera(
                    serial="VZL-CAM-001",
                    host="192.168.1.10",
                    https_port=443,
                    mac="AA:BB:CC:DD:EE:01",
                    name="Gate",
                    state="active",
                    tls_fingerprint_sha256="fp1",
                    added_at=now,
                    host_updated_at=now,
                )
                c2 = Camera(
                    serial="VZL-CAM-002",
                    host="192.168.1.20",
                    https_port=443,
                    mac="AA:BB:CC:DD:EE:02",
                    name="Lobby",
                    state="active",
                    tls_fingerprint_sha256="fp2",
                    added_at=now,
                    host_updated_at=now,
                )
                session.add_all([c1, c2])
                await session.commit()

    asyncio.run(_seed_cams())
    return data_dir, rec_dir


def test_reconciliation_scanner_lifecycle(
    cli: CliRunner,
    scanner_setup: tuple[Path, Path],
) -> None:
    """Scanner adopts unindexed files, detects deletions, and flags truncated files."""
    data_dir, rec_dir = scanner_setup

    # 1. Simulate unindexed footage written to disk (e.g. MediaMTX recorded during core restart)
    cam1_dir = rec_dir / "cam" / "vzl-cam-001" / "main" / "2026" / "11" / "02"
    cam1_dir.mkdir(parents=True, exist_ok=True)

    file1 = cam1_dir / "2026-11-02T10-00-00Z-000000.mp4"
    file1.write_bytes(b"\x00" * 4096)  # 4 KB valid

    file2 = cam1_dir / "2026-11-02T10-01-00Z-000000.mp4"
    file2.write_bytes(b"\x00" * 4096)  # 4 KB valid

    cam2_dir = rec_dir / "cam" / "vzl-cam-002" / "main" / "2026" / "11" / "02"
    cam2_dir.mkdir(parents=True, exist_ok=True)
    file3 = cam2_dir / "2026-11-02T10-00-00Z-000000.mp4"
    file3.write_bytes(b"\x00" * 4096)

    # 2. Run scan via CLI
    res_scan1 = cli.invoke(app, ["storage", "scan", "--json", "--data-dir", str(data_dir)])
    assert res_scan1.exit_code == 0, res_scan1.output
    data1 = json.loads(res_scan1.stdout)
    assert data1["adopted"] == 3
    assert data1["total_valid"] == 3
    assert data1["missing_marked"] == 0
    assert data1["truncated_marked"] == 0

    # 3. Idempotent re-scan: 0 adopted, 3 valid
    res_scan2 = cli.invoke(app, ["storage", "scan", "--json", "--data-dir", str(data_dir)])
    assert res_scan2.exit_code == 0
    data2 = json.loads(res_scan2.stdout)
    assert data2["adopted"] == 0
    assert data2["total_valid"] == 3

    # 4. Out-of-band deletion: delete file2 from disk
    file2.unlink()
    res_scan3 = cli.invoke(app, ["storage", "scan", "--json", "--data-dir", str(data_dir)])
    assert res_scan3.exit_code == 0
    data3 = json.loads(res_scan3.stdout)
    assert data3["missing_marked"] == 1
    assert data3["total_valid"] == 2

    # 5. Out-of-band corruption/truncation: overwrite file1 with < 1024 bytes
    file1.write_bytes(b"\x00" * 300)
    res_scan4 = cli.invoke(app, ["storage", "scan", "--json", "--data-dir", str(data_dir)])
    assert res_scan4.exit_code == 0
    data4 = json.loads(res_scan4.stdout)
    assert data4["truncated_marked"] == 1
    assert data4["total_valid"] == 1

    # 6. Test serial filter: only scan VZL-CAM-002
    res_filtered = cli.invoke(
        app,
        [
            "storage",
            "scan",
            "--serial",
            "VZL-CAM-002",
            "--json",
            "--data-dir",
            str(data_dir),
        ],
    )
    assert res_filtered.exit_code == 0
    data_filtered = json.loads(res_filtered.stdout)
    assert data_filtered["total_valid"] == 1

    # 7. Test human table rendering
    res_human = cli.invoke(app, ["storage", "scan", "--data-dir", str(data_dir)])
    assert res_human.exit_code == 0
    assert "Reconciliation" in res_human.output
    assert "Adopted Segments" in res_human.output
