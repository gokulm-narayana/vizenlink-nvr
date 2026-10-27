"""Camera layer container coordinating HTTP transport, event bus, and clocks."""

from dataclasses import dataclass
from typing import Self

from vizenlink_nvr.camera.events import CameraEventBus
from vizenlink_nvr.camera.http import SILENT_AFTER, CameraHttp
from vizenlink_nvr.timeutil import Clock, SystemClock


@dataclass
class CameraLayer:
    """Composite facade managing camera HTTP client, bus, and clock."""

    http: CameraHttp
    events: CameraEventBus
    clock: Clock

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
        return cls(http=http, events=events, clock=clk)

    async def aclose(self) -> None:
        """Close underlying HTTP clients."""
        await self.http.aclose()
