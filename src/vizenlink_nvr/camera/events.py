# mirrors: mobile_app/packages/camera_api/lib/src/lan/camera_id_mismatch.dart@1e0f913e3a37
"""Camera network and mismatch event models and in-memory event bus."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CameraIdMismatchEvent:
    """Emitted when camera returns HTTP 421 due to mismatched serial identity."""

    host: str
    port: int
    expected_id: str


@dataclass(frozen=True)
class CameraUnreachableEvent:
    """Emitted when camera cannot be reached over the network."""

    host: str
    port: int
    expected_id: str


class CameraEventBus:
    """Per-instance in-memory bus for camera lifecycle and error events."""

    def __init__(self) -> None:
        self._subscribers: list[Callable[[Any], None]] = []

    def subscribe(self, callback: Callable[[Any], None]) -> Callable[[], None]:
        """Register subscriber callback and return unsubscription handle."""
        self._subscribers.append(callback)

        def unsubscribe() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return unsubscribe

    def publish(self, event: Any) -> None:
        """Publish event to all registered subscribers."""
        for cb in list(self._subscribers):
            try:
                cb(event)
            except Exception as exc:
                logger.debug("Subscriber raised exception: %s", exc)
