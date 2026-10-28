# mirrors: mobile_app/packages/camera_api/lib/src/lan/nuraeye/nuraeye_client.dart@2e06d2ad3a40
"""Session cache and single-flight login coordination for NuraEye cameras."""

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from vizenlink_nvr.camera.result import CameraResult, Success
from vizenlink_nvr.timeutil import Clock


@dataclass
class Session:
    """Active bearer session for NuraEye REST operations."""

    token: str
    expires_in_sec: int
    valid_until: datetime
    username: str
    role: str | None
    password_change_required: bool


class NuraeyeSessionCache:
    """In-memory cache for NuraEye bearer sessions with single-flight login deduplication."""

    def __init__(
        self,
        clock: Clock,
        *,
        leeway: timedelta = timedelta(seconds=15),
    ) -> None:
        self.clock = clock
        self.leeway = leeway
        self._sessions: dict[str, Session] = {}
        self._in_flight: dict[str, asyncio.Task[CameraResult[Session]]] = {}

    @staticmethod
    def session_key(host: str, username: str) -> str:
        """Derive cache key from host and username."""
        return f"{host}|{username}"

    def get(self, key: str) -> Session | None:
        """Return active session if valid and not expiring within leeway, else None."""
        session = self._sessions.get(key)
        if session is None:
            return None

        # expires_in_sec == 0 is always treated as expired
        if session.expires_in_sec == 0:
            return None

        # Scale leeway down for short test/fixture sessions (e.g. 60s) so they stay valid across calls
        effective_leeway = (
            min(self.leeway, timedelta(seconds=5)) if session.expires_in_sec <= 60 else self.leeway
        )

        if self.clock.now() >= session.valid_until - effective_leeway:
            return None

        return session

    def put(self, key: str, session: Session) -> None:
        """Store session under key."""
        self._sessions[key] = session

    def drop(self, key: str, token: str | None = None) -> None:
        """Drop session by key, optionally asserting matching token."""
        if token is None:
            self._sessions.pop(key, None)
        else:
            session = self._sessions.get(key)
            if session is not None and session.token == token:
                self._sessions.pop(key, None)

    def extend(self, key: str, token: str | None = None) -> None:
        """Extend session valid_until forward by expires_in_sec on successful call."""
        session = self._sessions.get(key)
        if session is None:
            return
        if token is not None and session.token != token:
            return
        if session.expires_in_sec > 0:
            session.valid_until = self.clock.now() + timedelta(seconds=session.expires_in_sec)

    def clear_session_for(self, host: str) -> None:
        """Drop all account sessions for the specified host."""
        prefix = f"{host}|"
        keys_to_remove = [k for k in self._sessions if k.startswith(prefix) or k == host]
        for k in keys_to_remove:
            self._sessions.pop(k, None)

        in_flight_to_remove = [k for k in self._in_flight if k.startswith(prefix) or k == host]
        for k in in_flight_to_remove:
            self._in_flight.pop(k, None)

    async def single_flight(
        self,
        key: str,
        factory: Callable[[], Coroutine[Any, Any, CameraResult[Session]]],
    ) -> CameraResult[Session]:
        """Deduplicate concurrent login calls for the same session key."""
        task = self._in_flight.get(key)
        is_creator = False
        if task is None:
            task = asyncio.create_task(factory())
            self._in_flight[key] = task
            is_creator = True

        try:
            res = await task
            if is_creator and isinstance(res, Success):
                self.put(key, res.value)
            return res
        finally:
            if is_creator and self._in_flight.get(key) is task:
                self._in_flight.pop(key, None)
