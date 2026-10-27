"""Fault injection models and queue manager for fake camera simulator."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Status:
    """Respond with explicit HTTP status and optional JSON body."""

    code: int
    json_body: dict[str, Any] | None = None


@dataclass(frozen=True)
class Delay:
    """Delay response processing by specified seconds before handling."""

    seconds: float


@dataclass(frozen=True)
class Silence:
    """Delay sending the HTTP response status line by specified seconds."""

    seconds: float


@dataclass(frozen=True)
class Drop:
    """Close connection immediately without sending any data."""


@dataclass(frozen=True)
class Malformed:
    """Respond with malformed/unparseable body."""


@dataclass(frozen=True)
class SoapFault:
    """Respond with SOAP Fault XML payload."""

    subcode: str
    http_status: int = 500
    reason: str = "SOAP Fault"


@dataclass
class FaultPlan:
    """Queued faults by route key (e.g. 'POST /nuraeye/identity' or '*')."""

    _faults: dict[str, list[Any]] = field(default_factory=dict)

    def add(self, route_key: str, *faults: Any) -> None:
        """Enqueue faults FIFO for route_key."""
        if route_key not in self._faults:
            self._faults[route_key] = []
        self._faults[route_key].extend(faults)

    def pop_fault(self, route_key: str) -> Any | None:
        """Pop next fault for route_key or wildcard '*'."""
        if route_key in self._faults and self._faults[route_key]:
            return self._faults[route_key].pop(0)
        if "*" in self._faults and self._faults["*"]:
            return self._faults["*"].pop(0)
        return None
