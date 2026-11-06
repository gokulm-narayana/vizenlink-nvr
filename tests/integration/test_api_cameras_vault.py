"""Integration tests for Runtime.vault and production credential sealing (D-18)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.db.models import User
from vizenlink_nvr.secrets.vault import CredentialsUnreadable, Vault, open_vault
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.registry import load_connection
from vizenlink_nvr.services.runtime import open_runtime
from vizenlink_nvr.services.session_manager import SESSION_COOKIE_NAME, SessionManager
from vizenlink_nvr.timeutil import utc_now


@pytest.mark.asyncio
async def test_open_runtime_provides_healthy_vault(tmp_path: Path) -> None:
    """open_runtime on a fresh tmp data dir sets rt.vault matching vault_status."""
    settings = load_settings(data_dir=tmp_path)
    async with open_runtime(settings) as rt:
        assert rt.vault is not None
        assert rt.vault_status is not None
        assert rt.vault_status.status == "ok"
        assert rt.vault.key_id == rt.vault_status.key_id


@pytest.mark.asyncio
async def test_open_runtime_unhealthy_vault_leaves_none(tmp_path: Path) -> None:
    """When open_vault fails with CredentialsUnreadable, rt.vault is None and open_runtime succeeds."""
    settings = load_settings(data_dir=tmp_path)

    async def _failing_open_vault(rt: Any) -> Vault:
        raise CredentialsUnreadable("Simulated canary failure")

    with patch("vizenlink_nvr.services.runtime.open_vault", side_effect=_failing_open_vault):
        async with open_runtime(settings) as rt:
            assert rt.vault is None


@pytest.mark.asyncio
async def test_production_factory_credential_round_trip(tmp_path: Path) -> None:
    """POST /api/v1/cameras with create_app(runtime=rt) seals with rt.vault and recorder can open it."""
    settings = load_settings(data_dir=tmp_path)
    async with open_runtime(settings) as rt:
        app = create_app(session_factory=rt.sessions, runtime=rt)

        # Create operator user
        now = utc_now()
        async with rt.sessions() as session:
            operator = User(
                username="op_user",
                password_hash=hash_password("OperatorPass123!"),
                role="operator",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(operator)
            await session.commit()
            await session.refresh(operator)
            sess = await SessionManager.create_session(session, operator.id, "127.0.0.1", "test")
            session_token = sess.id

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            cookies={SESSION_COOKIE_NAME: session_token},
        ) as client:
            cam_payload = {
                "serial": "CAM-VAULT-1",
                "host": "192.0.2.10",
                "username": "admin",
                "password": "Cam-Secret-1",
                "name": "Vault Front",
                "streams": [
                    {
                        "role": "main",
                        "profile_token": "prof1",
                        "profile_name": "Main",
                        "venc_token": "venc1",
                        "codec": "H264",
                        "width": 1920,
                        "height": 1080,
                        "transport": "unicast",
                        "scheme": "rtsp",
                        "port": 554,
                    }
                ],
            }
            res = await client.post("/api/v1/cameras", json=cam_payload)
            assert res.status_code == 201

        # 1. load_connection with rt.vault opens the password
        async with rt.sessions() as session:
            conn = await load_connection(session, rt.vault, "CAM-VAULT-1")
            assert conn.password.get_secret_value() == "Cam-Secret-1"

        # 2. load_connection with freshly opened vault (recorder path) opens it
        recorder_vault = await open_vault(rt)
        async with rt.sessions() as session:
            conn_rec = await load_connection(session, recorder_vault, "CAM-VAULT-1")
            assert conn_rec.password.get_secret_value() == "Cam-Secret-1"

        # 3. load_connection with all-zero test key fails with CredentialsUnreadable
        zero_vault = Vault(b"0" * 32, "test-vault-key", "memory")
        async with rt.sessions() as session:
            with pytest.raises(CredentialsUnreadable):
                await load_connection(session, zero_vault, "CAM-VAULT-1")
