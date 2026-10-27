"""Pytest plugin providing fake_camera and discovery_responder fixtures."""

from collections.abc import AsyncGenerator, Callable
from typing import Any

import pytest

from fake_camera.discovery import DiscoveryResponder
from fake_camera.server import FakeCamera
from fake_camera.state import CameraState

CameraFactory = Callable[..., Any]


@pytest.fixture
async def discovery_responder() -> AsyncGenerator[DiscoveryResponder, None]:
    """Async fixture providing loopback WS-Discovery responder."""
    responder = DiscoveryResponder()
    await responder.start()
    try:
        yield responder
    finally:
        await responder.close()


@pytest.fixture
async def fake_camera(
    request: pytest.FixtureRequest,
) -> AsyncGenerator[CameraFactory, None]:
    """Async fixture factory creating and tracking simulated cameras."""
    servers: list[FakeCamera] = []

    async def _factory(serial: str = "VZL-CAM-000001", **state_overrides: Any) -> FakeCamera:
        state = CameraState(serial=serial, **state_overrides)
        cam = FakeCamera(state=state)
        await cam.start()
        servers.append(cam)
        if "discovery_responder" in request.fixturenames:
            disc: DiscoveryResponder = request.getfixturevalue("discovery_responder")
            disc.attach(cam)
        return cam

    try:
        yield _factory
    finally:
        for cam in servers:
            await cam.close()
