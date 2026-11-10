"""Phase 10: health must never report storage OK when the recording folder is unusable.

Regression for 2026-11-10: /api/v1/health returned storage_ok=true and no alerts while
/api/v1/storage/status reported "unmounted" (Permission denied), so the UI showed "Healthy"
while nothing could be recorded.
"""

from __future__ import annotations

import os
import types
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.engine import create_engine_for, upgrade_to_head
from vizenlink_nvr.secrets.vault import Vault


@pytest.mark.asyncio
async def test_health_and_alerts_reflect_unusable_storage(tmp_path: Path) -> None:
    db_file = tmp_path / "nvr.db"
    upgrade_to_head(db_file)
    engine = create_engine_for(db_file)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    good_dir = tmp_path / "recordings"
    good_dir.mkdir()
    locked_parent = tmp_path / "locked"
    locked_parent.mkdir()

    app = create_app(
        session_factory=sessions,
        runtime=types.SimpleNamespace(vault=Vault(b"0" * 32, "test-vault-key", "memory")),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.post(
            "/api/v1/auth/setup",
            json={
                "owner_username": "owner",
                "owner_password": "OwnerSecurePassword123!",
                "timezone": "UTC",
                "storage_path": str(good_dir),
                "allow_system_disk": True,
            },
        )
        assert res.status_code == 200

        healthy = (await client.get("/api/v1/health")).json()
        assert healthy["storage_ok"] is True
        assert healthy["details"]["storage_state"] == "ok"
        alerts = (await client.get("/api/v1/health/alerts")).json()
        assert all(a["id"] != "storage_unavailable" for a in alerts)

        # Point storage at a folder that cannot be created.
        os.chmod(locked_parent, 0o500)
        try:
            async with sessions() as db:
                await db.execute(
                    text("UPDATE storage_settings SET storage_path = :p WHERE id = 1"),
                    {"p": str(locked_parent / "nvr" / "recordings")},
                )
                await db.commit()

            broken = (await client.get("/api/v1/health")).json()
            assert broken["storage_ok"] is False
            assert broken["status"] != "healthy"
            assert broken["details"]["storage_state"] == "unmounted"

            alerts = (await client.get("/api/v1/health/alerts")).json()
            storage_alerts = [a for a in alerts if a["id"] == "storage_unavailable"]
            assert len(storage_alerts) == 1
            assert storage_alerts[0]["severity"] == "critical"
        finally:
            os.chmod(locked_parent, 0o700)

    await engine.dispose()


@pytest.mark.asyncio
async def test_system_metrics_endpoint(tmp_path: Path) -> None:
    db_file = tmp_path / "nvr.db"
    upgrade_to_head(db_file)
    engine = create_engine_for(db_file)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    rec = tmp_path / "recordings"
    rec.mkdir()

    app = create_app(
        session_factory=sessions,
        runtime=types.SimpleNamespace(vault=Vault(b"0" * 32, "test-vault-key", "memory")),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        assert (await client.get("/api/v1/health/system")).status_code == 401
        await client.post(
            "/api/v1/auth/setup",
            json={
                "owner_username": "owner",
                "owner_password": "OwnerSecurePassword123!",
                "timezone": "UTC",
                "storage_path": str(rec),
                "allow_system_disk": True,
            },
        )
        body = (await client.get("/api/v1/health/system")).json()
        assert 0 <= body["cpu_percent"] <= 100
        assert body["cpu_count"] >= 1
        assert 0 < body["memory_used_bytes"] <= body["memory_total_bytes"]
        assert body["nvr_uptime_seconds"] >= 0
        assert body["host_uptime_seconds"] > 0
        assert body["version"]

    await engine.dispose()
