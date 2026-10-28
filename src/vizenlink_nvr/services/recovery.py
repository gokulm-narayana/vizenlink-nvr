"""Camera address recovery service for silent re-IP healing (CAM-10, D-11, D-12)."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.discovery.ws_discovery import DiscoveredDevice, WsDiscoveryClient
from vizenlink_nvr.camera.events import (
    CameraEventBus,
    CameraIdMismatchEvent,
    CameraUnreachableEvent,
)
from vizenlink_nvr.camera.layer import CameraLayer
from vizenlink_nvr.camera.onvif.device import OnvifDeviceClient
from vizenlink_nvr.camera.result import Success
from vizenlink_nvr.config import NvrSettings
from vizenlink_nvr.services.registry import get_camera, update_host
from vizenlink_nvr.services.runtime import Runtime
from vizenlink_nvr.timeutil import Clock

logger = logging.getLogger(__name__)

ReadSerial = Callable[[str, int], Awaitable[str | None]]


class HealTrigger(StrEnum):
    """Trigger source that initiated the address healing attempt."""

    ID_MISMATCH = "ID_MISMATCH"
    UNREACHABLE = "UNREACHABLE"
    EXPLICIT = "EXPLICIT"


class HealKind(StrEnum):
    """Categorized outcome of a camera address heal."""

    HEALED = "HEALED"
    VERIFIED_IN_PLACE = "VERIFIED_IN_PLACE"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"
    SKIPPED_BACKOFF = "SKIPPED_BACKOFF"
    SKIPPED_IN_FLIGHT = "SKIPPED_IN_FLIGHT"
    IGNORED = "IGNORED"


class HealOutcome(BaseModel):
    """Result of an address healing attempt."""

    kind: HealKind
    serial: str
    old_address: str | None = None
    new_address: str | None = None
    claimants: int = 0
    next_attempt_at: datetime | None = None


class AddressHealer:
    """Orchestrate silent discovery-based recovery for moved cameras."""

    def __init__(
        self,
        rt: Runtime,
        layer: CameraLayer,
        *,
        discover: Callable[[bool], Awaitable[list[DiscoveredDevice]]],
        read_serial: ReadSerial,
        clock: Clock,
        verified_window: timedelta = timedelta(seconds=60),
        base_backoff: timedelta = timedelta(seconds=30),
        max_backoff: timedelta = timedelta(minutes=10),
    ) -> None:
        self.rt = rt
        self.layer = layer
        self._discover = discover
        self._read_serial = read_serial
        self.clock = clock
        self.verified_window = verified_window
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff
        self._in_flight: set[str] = set()
        self._failures: dict[str, int] = {}
        self._not_before: dict[str, datetime] = {}
        self._verified_until: dict[str, datetime] = {}
        self._tasks: set[asyncio.Task[Any]] = set()

    def _schedule_retry(self, serial: str) -> None:
        """Calculate and store exponential backoff timestamp."""
        n = self._failures.get(serial, 0) + 1
        self._failures[serial] = n
        wait_sec = min(
            self.base_backoff.total_seconds() * (2 ** (n - 1)),
            self.max_backoff.total_seconds(),
        )
        self._not_before[serial] = self.clock.now() + timedelta(seconds=wait_sec)

    async def _match_candidates(
        self,
        candidates: list[DiscoveredDevice],
        serial: str,
        stored_host: str,
        stored_port: int,
    ) -> set[tuple[str, int]]:
        """Query serial on candidates with blank credentials, excluding stored address."""
        matches: set[tuple[str, int]] = set()
        for c in candidates:
            if c.host == stored_host and c.port == stored_port:
                continue
            read = await self._read_serial(c.host, c.port)
            if read == serial:
                matches.add((c.host, c.port))
        return matches

    async def heal(
        self,
        serial: str,
        trigger: HealTrigger,
        *,
        reported_host: str | None = None,
        reported_port: int | None = None,
        force: bool = False,
    ) -> HealOutcome:
        """Attempt to find and update the IP address of a moved camera."""
        # 1. Confirm stored camera exists and matches reported host
        async with self.rt.sessions() as session:
            cam = await get_camera(session, serial)

        if cam is None:
            return HealOutcome(kind=HealKind.IGNORED, serial=serial)

        if reported_host is not None and cam.host != reported_host:
            return HealOutcome(
                kind=HealKind.IGNORED,
                serial=serial,
                old_address=f"{cam.host}:{cam.https_port}",
            )

        # 2. In-flight guard (deduplication)
        if serial in self._in_flight:
            return HealOutcome(
                kind=HealKind.SKIPPED_IN_FLIGHT,
                serial=serial,
                old_address=f"{cam.host}:{cam.https_port}",
            )

        # 3. Backoff guard unless forced
        now = self.clock.now()
        if not force:
            not_before = self._not_before.get(serial)
            if not_before is not None and now < not_before:
                return HealOutcome(
                    kind=HealKind.SKIPPED_BACKOFF,
                    serial=serial,
                    old_address=f"{cam.host}:{cam.https_port}",
                    next_attempt_at=not_before,
                )

        self._in_flight.add(serial)
        try:
            # 4. Unreachable pre-check: verify at stored address if not a placeholder
            if trigger == HealTrigger.UNREACHABLE:
                if cam.host and cam.host != "0.0.0.0" and not cam.host.startswith("cloud-"):  # noqa: S104
                    verified = self._verified_until.get(serial)
                    if verified is not None and now < verified:
                        return HealOutcome(
                            kind=HealKind.VERIFIED_IN_PLACE,
                            serial=serial,
                            old_address=f"{cam.host}:{cam.https_port}",
                        )

                    serial_there = await self._read_serial(cam.host, cam.https_port)
                    if serial_there == serial:
                        self._verified_until[serial] = now + self.verified_window
                        self._failures.pop(serial, None)
                        self._not_before.pop(serial, None)
                        return HealOutcome(
                            kind=HealKind.VERIFIED_IN_PLACE,
                            serial=serial,
                            old_address=f"{cam.host}:{cam.https_port}",
                        )

            # 5. Search: Multicast first, then unicast sweep
            candidates = await self._discover(False)
            matches = await self._match_candidates(candidates, serial, cam.host, cam.https_port)

            if not matches:
                candidates = await self._discover(True)
                matches = await self._match_candidates(candidates, serial, cam.host, cam.https_port)

            # 6. Process match outcomes
            if len(matches) == 1:
                new_host, new_port = next(iter(matches))
                async with self.rt.sessions() as session:
                    async with session.begin():
                        await update_host(session, serial, new_host, new_port, at=now)

                self.layer.sessions.clear_session_for(cam.host)
                self._failures.pop(serial, None)
                self._not_before.pop(serial, None)
                self._verified_until[serial] = now + self.verified_window
                return HealOutcome(
                    kind=HealKind.HEALED,
                    serial=serial,
                    old_address=f"{cam.host}:{cam.https_port}",
                    new_address=f"{new_host}:{new_port}",
                    claimants=1,
                )

            if len(matches) > 1:
                logger.warning("%d devices claim serial %s; no change", len(matches), serial)
                return HealOutcome(
                    kind=HealKind.AMBIGUOUS,
                    serial=serial,
                    old_address=f"{cam.host}:{cam.https_port}",
                    claimants=len(matches),
                )

            # No matches found: record failure and schedule exponential backoff
            self._schedule_retry(serial)
            return HealOutcome(
                kind=HealKind.NOT_FOUND,
                serial=serial,
                old_address=f"{cam.host}:{cam.https_port}",
                next_attempt_at=self._not_before.get(serial),
            )
        finally:
            self._in_flight.discard(serial)

    def attach(self, events: CameraEventBus) -> Callable[[], None]:
        """Subscribe to mismatch and unreachable events on CameraEventBus."""

        def handle_event(event: Any) -> None:
            if isinstance(event, CameraIdMismatchEvent):
                t = asyncio.create_task(
                    self.heal(
                        event.expected_id,
                        HealTrigger.ID_MISMATCH,
                        reported_host=event.host,
                        reported_port=event.port,
                    )
                )
                self._tasks.add(t)
                t.add_done_callback(self._tasks.discard)
            elif isinstance(event, CameraUnreachableEvent):
                t = asyncio.create_task(
                    self.heal(
                        event.expected_id,
                        HealTrigger.UNREACHABLE,
                        reported_host=event.host,
                        reported_port=event.port,
                    )
                )
                self._tasks.add(t)
                t.add_done_callback(self._tasks.discard)

        return events.subscribe(handle_event)

    async def aclose(self) -> None:
        """Cancel and await all in-flight scheduled healing tasks."""
        if self._tasks:
            for t in list(self._tasks):
                t.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()


def make_healer(rt: Runtime, layer: CameraLayer, settings: NvrSettings) -> AddressHealer:
    """Construct production AddressHealer with WS-Discovery and blank serial probe."""
    disc_client = WsDiscoveryClient(
        port=settings.discovery_port,
        multicast_group=settings.discovery_multicast_group,
        unicast_hosts=settings.discovery_unicast_hosts,
        clock=rt.clock,
    )

    async def discover(thorough: bool) -> list[DiscoveredDevice]:
        if thorough:
            return await disc_client.scan_unicast()
        return await disc_client.scan_multicast()

    async def read_serial(host: str, port: int) -> str | None:
        conn = CameraConnection.blank(host, port)
        client = OnvifDeviceClient(conn, layer.http, layer.clock)
        res = await client.get_serial_number(timeout=4.0)
        if isinstance(res, Success) and res.value:
            return res.value.strip()
        return None

    return AddressHealer(
        rt,
        layer,
        discover=discover,
        read_serial=read_serial,
        clock=rt.clock,
    )
