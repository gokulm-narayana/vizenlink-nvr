"""Camera event subscription supervisor with resilient auto-resubscribe (EVT-01, EVT-06)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vizenlink_nvr.db.models import EventSubscription
from vizenlink_nvr.events.source import EventSource, RawCameraEvent
from vizenlink_nvr.timeutil import utc_now

logger = logging.getLogger(__name__)

INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 60.0
RENEW_INTERVAL_SECONDS = 30.0


EventCallback = Callable[[RawCameraEvent], Coroutine[Any, Any, None]]


class EventSubscriptionSupervisor:
    """Manages active event subscriptions across cameras, handling renewal and auto-reconnect."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        event_callback: EventCallback | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.event_callback = event_callback
        self._sources: dict[str, EventSource] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False

    def register_camera_source(self, camera_serial: str, source: EventSource) -> None:
        """Register an event source for a camera."""
        self._sources[camera_serial] = source

    def unregister_camera_source(self, camera_serial: str) -> None:
        """Unregister a camera event source and stop its task."""
        self._sources.pop(camera_serial, None)
        task = self._tasks.pop(camera_serial, None)
        if task:
            task.cancel()

    async def start(self) -> None:
        """Start subscription tasks for all registered sources."""
        self._running = True
        for serial, source in list(self._sources.items()):
            if serial not in self._tasks:
                self._tasks[serial] = asyncio.create_task(
                    self._camera_subscription_loop(serial, source)
                )

    async def stop(self) -> None:
        """Cancel all running subscription tasks and cleanly unsubscribe."""
        self._running = False
        for _serial, task in list(self._tasks.items()):
            task.cancel()
        self._tasks.clear()

        # Cleanly unsubscribe from sources
        for _serial, source in self._sources.items():
            try:
                await source.unsubscribe()
            except Exception as exc:
                logger.debug("Unsubscribe on stop failed: %s", exc)

    async def _update_subscription_state(
        self,
        camera_serial: str,
        state: str,
        subscription_url: str | None = None,
        last_event_at: datetime | None = None,
        last_renewed_at: datetime | None = None,
        error_reason: str | None = None,
        clock_drift_seconds: float | None = None,
    ) -> None:
        """Persist subscription state in the database."""
        now = utc_now()
        async with self.session_factory() as session:
            sub = await session.get(EventSubscription, camera_serial)
            if sub is None:
                sub = EventSubscription(
                    camera_serial=camera_serial,
                    state=state,
                    subscription_url=subscription_url,
                    last_event_at=last_event_at,
                    last_renewed_at=last_renewed_at,
                    error_reason=error_reason,
                    clock_drift_seconds=clock_drift_seconds,
                    updated_at=now,
                )
                session.add(sub)
            else:
                sub.state = state
                if subscription_url is not None:
                    sub.subscription_url = subscription_url
                if last_event_at is not None:
                    sub.last_event_at = last_event_at
                if last_renewed_at is not None:
                    sub.last_renewed_at = last_renewed_at
                sub.error_reason = error_reason
                if clock_drift_seconds is not None:
                    sub.clock_drift_seconds = clock_drift_seconds
                sub.updated_at = now
            await session.commit()

    async def _camera_subscription_loop(self, camera_serial: str, source: EventSource) -> None:
        """Resilient polling and renewal loop for a single camera."""
        backoff = INITIAL_BACKOFF_SECONDS
        last_renew = utc_now()

        while self._running:
            # 1. Establish subscription
            try:
                await self._update_subscription_state(camera_serial, state="subscribing")
                sub_url = await source.subscribe()
                await self._update_subscription_state(
                    camera_serial,
                    state="active",
                    subscription_url=sub_url,
                    last_renewed_at=utc_now(),
                    error_reason=None,
                )
                backoff = INITIAL_BACKOFF_SECONDS
                last_renew = utc_now()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(
                    "Subscription failed on %s: %s; retrying in %.1fs",
                    camera_serial,
                    exc,
                    backoff,
                )
                await self._update_subscription_state(
                    camera_serial,
                    state="reconnecting",
                    error_reason=str(exc),
                )
                try:
                    await asyncio.sleep(backoff)
                except asyncio.CancelledError:
                    break
                backoff = min(MAX_BACKOFF_SECONDS, backoff * 2.0)
                continue

            # 2. Polling loop
            while self._running:
                try:
                    events = await source.poll(timeout_seconds=5.0)
                    now = utc_now()
                    if events:
                        for evt in events:
                            await self._update_subscription_state(
                                camera_serial,
                                state="active",
                                last_event_at=evt.utc_time,
                                clock_drift_seconds=evt.clock_drift_seconds,
                            )
                            if self.event_callback:
                                await self.event_callback(evt)

                    # Periodically renew subscription
                    if (now - last_renew).total_seconds() >= RENEW_INTERVAL_SECONDS:
                        renew_ok = await source.renew(seconds=60)
                        if renew_ok:
                            last_renew = now
                            await self._update_subscription_state(
                                camera_serial,
                                state="active",
                                last_renewed_at=now,
                            )
                        else:
                            raise RuntimeError("Subscription renewal refused by camera")

                except asyncio.CancelledError:
                    return
                except Exception as exc:
                    logger.warning("Polling error on %s: %s; resubscribing", camera_serial, exc)
                    await self._update_subscription_state(
                        camera_serial,
                        state="reconnecting",
                        error_reason=str(exc),
                    )
                    break  # Break inner loop to resubscribe
