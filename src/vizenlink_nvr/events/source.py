"""Pluggable camera event source protocol and raw event representation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from vizenlink_nvr.services.events import ClockSyncState, EventType, canonicalize_event_topic


@dataclass(frozen=True)
class RawCameraEvent:
    """Raw parsed notification emitted by a camera event provider."""

    camera_serial: str
    topic: str
    utc_time: datetime | None
    data: dict[str, Any] = field(default_factory=dict)
    source_name: str = "onvif_pullpoint"
    clock_drift_seconds: float | None = None
    clock_sync_state: ClockSyncState = ClockSyncState.SYNCED

    @property
    def event_type(self) -> EventType:
        """Derive canonical EventType from topic string."""
        return canonicalize_event_topic(self.topic)


class EventSource(Protocol):
    """Abstract protocol for pluggable camera event providers."""

    async def subscribe(self) -> str:
        """Establish subscription and return subscription endpoint URL."""
        ...

    async def poll(self, timeout_seconds: float = 5.0) -> list[RawCameraEvent]:
        """Poll for new event notifications; return empty list on timeout."""
        ...

    async def renew(self, seconds: int = 60) -> bool:
        """Extend subscription termination time; return True if successful."""
        ...

    async def unsubscribe(self) -> None:
        """Cleanly terminate subscription with camera."""
        ...
