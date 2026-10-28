"""Camera layer container coordinating HTTP transport, event bus, clocks, and sessions."""

from dataclasses import dataclass, field
from typing import Self

from vizenlink_nvr.camera.events import CameraEventBus
from vizenlink_nvr.camera.http import SILENT_AFTER, CameraHttp
from vizenlink_nvr.camera.nuraeye.sessions import NuraeyeSessionCache
from vizenlink_nvr.timeutil import Clock, SystemClock


@dataclass
class CameraLayer:
    """Composite facade managing camera HTTP client, bus, clock, and session cache."""

    http: CameraHttp
    events: CameraEventBus
    clock: Clock
    sessions: NuraeyeSessionCache = field(default_factory=lambda: NuraeyeSessionCache(SystemClock()))

    @classmethod
    def create(
        cls,
        clock: Clock | None = None,
        *,
        silent_after: float = SILENT_AFTER,
    ) -> Self:
        """Create a new CameraLayer with default or provided clock."""
        events = CameraEventBus()
        http = CameraHttp(events, silent_after=silent_after)
        clk = clock if clock is not None else SystemClock()
        sessions = NuraeyeSessionCache(clk)
        return cls(http=http, events=events, clock=clk, sessions=sessions)

    async def aclose(self) -> None:
        """Close underlying HTTP clients."""
        await self.http.aclose()
