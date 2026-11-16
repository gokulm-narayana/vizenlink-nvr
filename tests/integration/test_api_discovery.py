"""Web camera discovery uses recorder settings, enforces roles, and releases scan state."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.api.dependencies import get_current_user
from vizenlink_nvr.config import NvrSettings
from vizenlink_nvr.services.scan import ScannedCamera, ScanReport


@pytest.mark.asyncio
async def test_discovery_permissions_and_results(monkeypatch, tmp_path):
    settings = NvrSettings(data_dir=tmp_path)
    app = create_app(runtime=SimpleNamespace(settings=settings))
    role = "viewer"
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role=role)
    scan = AsyncMock(
        return_value=ScanReport(
            cameras=[ScannedCamera(host="192.168.1.8", port=443, model="Camera", name="Entrance")],
            tiers_used=["multicast"],
        )
    )
    monkeypatch.setattr("vizenlink_nvr.services.scan.run_scan", scan)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/api/v1/cameras/discover")).status_code == 403
        scan.assert_not_called()
        role = "operator"
        response = await client.post("/api/v1/cameras/discover")
        assert response.status_code == 200
        assert response.json()["cameras"][0]["host"] == "192.168.1.8"
        scan.assert_awaited_once_with(settings, timeout=2.0)
        assert not app.state.camera_scan_running
        app.state.camera_scan_running = True
        assert (await client.post("/api/v1/cameras/discover")).status_code == 409
        app.state.camera_scan_running = False
        scan.side_effect = OSError("network unavailable")
        assert (await client.post("/api/v1/cameras/discover")).status_code == 503
        assert not app.state.camera_scan_running
        scan.side_effect = PermissionError("local network blocked")
        blocked = await client.post("/api/v1/cameras/discover")
        assert blocked.status_code == 503
        assert "denied access to the local network" in blocked.json()["detail"]
        assert not app.state.camera_scan_running
        scan.side_effect = TimeoutError()
        assert (await client.post("/api/v1/cameras/discover")).status_code == 504
        assert not app.state.camera_scan_running


@pytest.mark.asyncio
async def test_web_onboarding_verifies_credentials_and_reads_camera_streams(tmp_path, fake_camera):
    camera = await fake_camera(serial="VZL-WEB-ONBOARD", name="Front door")
    camera.state.set_password("admin", "CameraTest123!")
    app = create_app(settings=NvrSettings(data_dir=tmp_path, secrets_backend="file"))
    role = "viewer"
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        role=role, id=None, username="operator"
    )
    payload = {"host": camera.host, "port": camera.port, "username": "admin", "password": "incorrect"}

    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.post("/api/v1/cameras/onboard", json=payload)).status_code == 403
        role = "operator"
        failed = await client.post("/api/v1/cameras/onboard", json=payload)
        assert failed.status_code == 400
        assert (await client.get("/api/v1/cameras")).json() == []
        payload["password"] = "CameraTest123!"
        added = await client.post("/api/v1/cameras/onboard", json=payload)
        assert added.status_code == 201, added.text
        assert added.json()["serial"] == "VZL-WEB-ONBOARD"
        assert added.json()["streams"]
        assert payload["password"] not in added.text
        assert (await client.post("/api/v1/cameras/onboard", json=payload)).status_code == 409
        # A registered address is refused before any camera sign-in, so a wrong
        # password cannot spend the camera's login attempts.
        repeat = await client.post("/api/v1/cameras/onboard", json={**payload, "password": "incorrect"})
        assert repeat.status_code == 409


@pytest.mark.asyncio
async def test_web_onboarding_prompts_and_sets_new_camera_password(tmp_path, fake_camera):
    from fake_camera.state import Account, CameraRole

    camera = await fake_camera(
        serial="VZL-WEB-FACTORY",
        name="New Cam",
        accounts={"admin": Account("password", CameraRole.ADMINISTRATOR)},
        default_password_in_use=True,
        first_password_gate=True,
    )
    app = create_app(settings=NvrSettings(data_dir=tmp_path, secrets_backend="file"))
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        role="operator", id=None, username="operator"
    )
    payload = {"host": camera.host, "port": camera.port, "username": "admin", "password": "password"}

    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post("/api/v1/cameras/onboard", json=payload)
        assert first.status_code == 400
        assert first.json()["detail"] == "Set a new password on the camera before adding it."

        invalid = await client.post(
            "/api/v1/cameras/onboard", json={**payload, "new_camera_password": "short"}
        )
        assert invalid.status_code == 400
        assert invalid.json()["detail"] == "Use 8 to 32 characters."

        ok = await client.post(
            "/api/v1/cameras/onboard", json={**payload, "new_camera_password": "NewCameraPass123!"}
        )
        assert ok.status_code == 201, ok.text
        assert ok.json()["serial"] == "VZL-WEB-FACTORY"
        assert camera.state.accounts["admin"].password == "NewCameraPass123!"
        assert camera.state.first_password_gate is False
