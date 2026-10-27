"""Pytest plugin providing fake_camera fixture."""

from collections.abc import AsyncGenerator, Callable
from typing import Any

import pytest

from fake_camera.server import FakeCamera
from fake_camera.state import CameraState

CameraFactory = Callable[..., Any]


@pytest.fixture
async def fake_camera() -> AsyncGenerator[CameraFactory, None]:
    """Async fixture factory creating and tracking simulated cameras."""
    servers: list[FakeCamera] = []

    async def _factory(serial: str = "VZL-CAM-000001", **state_overrides: Any) -> FakeCamera:
        state = CameraState(serial=serial, **state_overrides)
        cam = FakeCamera(state=state)
        await cam.start()
        servers.append(cam)
        return cam

    try:
        yield _factory
    finally:
        for cam in servers:
            await cam.close()
