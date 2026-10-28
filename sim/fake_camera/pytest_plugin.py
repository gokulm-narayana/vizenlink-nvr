"""Pytest plugin providing fake_camera and discovery_responder fixtures."""

import asyncio
from collections.abc import AsyncGenerator, Callable
from typing import Any

import pytest

from fake_camera.certs import generate_self_signed_cert
from fake_camera.discovery import DiscoveryResponder
from fake_camera.server import FakeCamera, _create_server_ssl_context
from fake_camera.state import CameraState

CameraFactory = Callable[..., Any]


class ControllableFakeCamera(FakeCamera):
    """FakeCamera subclass allowing certificate customization and restart on same port."""

    def __init__(
        self,
        state: CameraState | None = None,
        faults: Any | None = None,
        certificate: tuple[bytes, bytes, str] | None = None,
    ) -> None:
        super().__init__(state=state, faults=faults)
        self._custom_cert = certificate

    async def start(self) -> None:
        """Start the fake camera TLS server."""
        if self._custom_cert is not None:
            cert_pem, key_pem, fingerprint = self._custom_cert
            self.cert_sha256 = fingerprint
            self._cert_pem = cert_pem
            self._key_pem = key_pem
        else:
            cert_pem, key_pem, fingerprint = generate_self_signed_cert()
            self.cert_sha256 = fingerprint
            self._cert_pem = cert_pem
            self._key_pem = key_pem

        ssl_ctx = _create_server_ssl_context(cert_pem, key_pem)
        self._server = await asyncio.start_server(
            self._handle_client,
            host=self.host,
            port=self.port,
            ssl=ssl_ctx,
        )
        self.port = self._server.sockets[0].getsockname()[1]

    async def restart_with_new_certificate(
        self,
        certificate: tuple[bytes, bytes, str] | None = None,
    ) -> None:
        """Restart server on same port using a new TLS certificate."""
        old_port = self.port
        await self.close()
        self.port = old_port
        self._custom_cert = certificate or generate_self_signed_cert()
        await self.start()


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

    async def _factory(
        serial: str = "VZL-CAM-000001",
        certificate: tuple[bytes, bytes, str] | None = None,
        **state_overrides: Any,
    ) -> ControllableFakeCamera:
        state = CameraState(serial=serial, **state_overrides)
        cam = ControllableFakeCamera(state=state, certificate=certificate)
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
