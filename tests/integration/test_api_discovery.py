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
        scan.side_effect = TimeoutError()
        assert (await client.post("/api/v1/cameras/discover")).status_code == 504
        assert not app.state.camera_scan_running
