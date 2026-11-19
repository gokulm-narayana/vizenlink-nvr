"""Recorder runtime: starts and supervises everything that makes the NVR record.

`nvr run` used to start only the web server. This supervisor runs inside the web
app's lifespan (one Uvicorn worker) and owns:

- the MediaMTX process (config written from the DB, restarted if it exits),
- path reconciliation (DB -> MediaMTX, incl. recording schedules and storage health),
- camera outage tracking from MediaMTX stream state,
- the segment index fallback scan (the segment-complete hook is the primary path),
- the retention janitor (the only component that deletes footage),
- ONVIF PullPoint event subscriptions.

Every loop logs and keeps going on errors: one failing camera or a full disk must
never stop recording for the others.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shlex
import subprocess
import sys
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select

from vizenlink_nvr.camera.events import CameraEventBus
from vizenlink_nvr.camera.http import CameraHttp, fetch_certificate_sha256
from vizenlink_nvr.db.models import Camera, CameraStream
from vizenlink_nvr.events.onvif_pullpoint import OnvifPullPointSource
from vizenlink_nvr.events.source import RawCameraEvent
from vizenlink_nvr.events.supervisor import EventSubscriptionSupervisor
from vizenlink_nvr.media.binary import resolve_binary
from vizenlink_nvr.media.config import (
    CONTROL_USER,
    MediaMtxPorts,
    build_config,
    camera_path_name,
    hash_control_password,
    write_config,
)
from vizenlink_nvr.media.process import MediaMtxProcess
from vizenlink_nvr.media.reconciler import (
    MediaMtxReconciler,
    PathConfiguration,
    compute_desired_paths,
    get_control_password,
)
from vizenlink_nvr.paths import mediamtx_dir
from vizenlink_nvr.services.events import ClockSyncState, EventRecord, insert_event
from vizenlink_nvr.services.indexer import scan_and_reconcile
from vizenlink_nvr.services.janitor import enforce_camera_retention, enforce_disk_low_water_mark
from vizenlink_nvr.services.outage_tracker import OutageTracker
from vizenlink_nvr.services.recording_settings import get_or_create_recording_settings
from vizenlink_nvr.services.registry import load_connection
from vizenlink_nvr.services.runtime import Runtime
from vizenlink_nvr.services.settings import read_site_timezone
from vizenlink_nvr.services.storage import StorageConfig, StorageHealthState, get_storage_config
from vizenlink_nvr.timeutil import utc_now

logger = logging.getLogger(__name__)

RECORDER_CONFIG_NAME = "mediamtx-recorder.yml"  # `nvr mediamtx check` owns mediamtx.yml
MAX_EVENT_DRIFT_SECONDS = 5.0  # EVT-07


def segment_hook_command(data_dir: Path) -> str:
    """Command MediaMTX runs when a segment completes.

    Uses this interpreter (or the frozen executable) and the recorder's data dir, so the
    hook works under systemd/launchd/WinSW where `nvr` is not on PATH and the default
    data dir differs. MediaMTX splits the command shell-style without invoking a shell.
    """
    if getattr(sys, "frozen", False):
        argv = [sys.executable]
    else:
        argv = [sys.executable, "-m", "vizenlink_nvr"]
    argv += ["recording", "hook-segment-complete", "--data-dir", str(data_dir)]
    if sys.platform == "win32":
        return subprocess.list2cmdline(argv)
    return shlex.join(argv)


def lan_ipv4_addresses() -> list[str]:
    """Non-loopback IPv4 addresses, advertised as WebRTC ICE candidates for LAN browsers."""
    try:
        import ifaddr
    except ImportError:  # pragma: no cover - dependency is declared
        return []
    found: list[str] = []
    for adapter in ifaddr.get_adapters():
        for ip in adapter.ips:
            if isinstance(ip.ip, str) and not ip.ip.startswith(("127.", "169.254.")) and ip.ip not in found:
                found.append(ip.ip)
    return found


def build_recorder_config(
    ports: MediaMtxPorts, control_password: str, nvr_port: int, lan_access: bool
) -> dict[str, Any]:
    cfg = build_config(ports, hash_control_password(control_password), nvr_port=nvr_port)
    if lan_access:
        # WebRTC signalling stays on loopback behind the authenticated /cam proxy; the
        # WebRTC media UDP and TCP ICE sockets listen on the LAN so LAN clients receive video.
        cfg["webrtcLocalUDPAddress"] = f":{ports.webrtc_udp}"
        cfg["webrtcLocalTCPAddress"] = f":{ports.webrtc_udp}"
        cfg["webrtcAdditionalHosts"] = lan_ipv4_addresses()
    return cfg


def restamp_event_time(event: RawCameraEvent, now: datetime) -> tuple[datetime, ClockSyncState]:
    """EVT-07: use NVR time when the camera clock is unknown or drifting."""
    drift = event.clock_drift_seconds
    if (
        event.utc_time is None
        or event.clock_sync_state != ClockSyncState.SYNCED
        or (drift is not None and abs(drift) > MAX_EVENT_DRIFT_SECONDS)
    ):
        state = event.clock_sync_state
        if state == ClockSyncState.SYNCED:
            state = ClockSyncState.DRIFT_DETECTED if event.utc_time is not None else ClockSyncState.UNCERTAIN
        return now, state
    return event.utc_time, ClockSyncState.SYNCED


class RecorderSupervisor:
    """Owns MediaMTX and the recorder background loops for the life of the web app."""

    def __init__(
        self,
        rt: Runtime,
        *,
        nvr_port: int,
        lan_access: bool,
        ports: MediaMtxPorts | None = None,
        mdns: Any | None = None,
        reconcile_interval: float = 30.0,
        janitor_interval: float = 300.0,
        index_interval: float = 1800.0,
        offline_grace_seconds: float = 60.0,
    ) -> None:
        self.rt = rt
        self.nvr_port = nvr_port
        self.lan_access = lan_access
        self.ports = ports or MediaMtxPorts()
        self.mdns = mdns
        self._last_lan_ips: list[str] | None = None
        self.reconcile_interval = reconcile_interval
        self.janitor_interval = janitor_interval
        self.index_interval = index_interval
        self.offline_grace_seconds = offline_grace_seconds

        self.api_base = f"http://127.0.0.1:{self.ports.api}"
        self.control_password = get_control_password(rt.settings)
        self.auth = (CONTROL_USER, self.control_password)
        self.hook_command = segment_hook_command(rt.settings.data_dir)

        self.process: MediaMtxProcess | None = None
        self.adopted_external = False
        self.mediamtx_error: str | None = None
        self._client: httpx.AsyncClient | None = None
        self._tasks: list[asyncio.Task[None]] = []
        self._stopping = False

        self._camera_http = CameraHttp(CameraEventBus())
        self._events = EventSubscriptionSupervisor(
            rt.sessions,
            event_callback=self._on_camera_event,
            min_poll_interval=3.0,
        )
        self._event_cameras: set[str] = set()
        self._not_ready_since: dict[str, datetime] = {}
        self._offline: set[str] = set()
        self._seen: set[str] = set()
        self._event_failures: set[str] = set()

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        self._client = httpx.AsyncClient(timeout=10.0, trust_env=False)
        self._tasks = [
            asyncio.create_task(self._loop("mediamtx", self._ensure_mediamtx, 5.0), name="recorder-mediamtx"),
            asyncio.create_task(
                self._loop("reconcile", self._reconcile_once, self.reconcile_interval),
                name="recorder-reconcile",
            ),
            asyncio.create_task(
                self._loop("index", self._index_once, self.index_interval), name="recorder-index"
            ),
            asyncio.create_task(
                self._loop("janitor", self._janitor_once, self.janitor_interval), name="recorder-janitor"
            ),
        ]
        logger.info("Recorder started (MediaMTX API %s)", self.api_base)

    async def stop(self) -> None:
        self._stopping = True
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._tasks.clear()
        with contextlib.suppress(Exception):
            await self._events.stop()
        if self.process is not None:
            await asyncio.to_thread(self.process.stop)
            self.process = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        await self._camera_http.aclose()
        logger.info("Recorder stopped")

    async def _loop(self, name: str, body: Callable[[], Awaitable[None]], interval: float) -> None:
        while not self._stopping:
            try:
                await body()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Recorder %s pass failed; retrying in %.0fs", name, interval)
            await asyncio.sleep(interval)

    # ------------------------------------------------------------------ MediaMTX

    async def _mediamtx_answering(self) -> dict[str, Any] | None:
        if self._client is None:
            return None
        try:
            res = await self._client.get(f"{self.api_base}/v3/config/global/get", auth=self.auth)
        except httpx.HTTPError:
            return None
        if res.status_code != 200:
            return {}
        try:
            data = res.json()
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    async def _ensure_mediamtx(self) -> None:
        if self.process is not None and self.process.popen is not None and self.process.popen.poll() is None:
            return
        if self.process is not None:
            code = self.process.popen.returncode if self.process.popen else None
            tail = "\n".join(self.process.log_lines[-10:])
            logger.error("MediaMTX exited (code %s); restarting. Last output:\n%s", code, tail)
            self.process = None

        running = await self._mediamtx_answering()
        if running is not None:
            expected_auth = build_config(self.ports, "", nvr_port=self.nvr_port)["authHTTPAddress"]
            if running.get("authHTTPAddress") == expected_auth:
                # Our own MediaMTX survived a core restart (FND-01): keep recording, re-sync.
                if not self.adopted_external:
                    logger.info("Adopted running MediaMTX on %s", self.api_base)
                self.adopted_external = True
                self.mediamtx_error = None
                await self._sync_webrtc_lan_config()
                return
            self.adopted_external = False
            self.mediamtx_error = (
                f"Port {self.ports.api} is used by another program (not this recorder's MediaMTX). "
                "Stop it so the recorder can start."
            )
            logger.error(self.mediamtx_error)
            return
        self.adopted_external = False

        binary = resolve_binary(self.rt.settings)
        cfg_path = mediamtx_dir(self.rt.settings) / RECORDER_CONFIG_NAME
        cfg = build_recorder_config(self.ports, self.control_password, self.nvr_port, self.lan_access)
        write_config(cfg_path, cfg)
        proc = MediaMtxProcess(binary, cfg_path)
        try:
            await asyncio.to_thread(proc.start)
        except Exception as exc:
            self.mediamtx_error = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
            raise
        self.process = proc
        self.mediamtx_error = None
        if self.lan_access:
            self._last_lan_ips = list(cfg.get("webrtcAdditionalHosts", []))
        logger.info("MediaMTX started (pid %s)", proc.popen.pid if proc.popen else "?")
        await self._sync_webrtc_lan_config()
        await self._reconcile_once()

    async def _sync_webrtc_lan_config(self) -> None:
        """Keep MediaMTX WebRTC UDP/TCP listeners and ICE hosts aligned with current LAN IPs."""
        if not self.lan_access or self._client is None:
            return
        current_ips = lan_ipv4_addresses()
        changed = self._last_lan_ips is None or current_ips != self._last_lan_ips
        if not changed:
            return
        payload = {
            "webrtcLocalUDPAddress": f":{self.ports.webrtc_udp}",
            "webrtcLocalTCPAddress": f":{self.ports.webrtc_udp}",
            "webrtcAdditionalHosts": current_ips,
        }
        try:
            res = await self._client.patch(
                f"{self.api_base}/v3/config/global/patch",
                auth=self.auth,
                json=payload,
            )
            if 200 <= res.status_code < 300:
                logger.info("Synced MediaMTX WebRTC LAN config: hosts=%s", current_ips)
                self._last_lan_ips = list(current_ips)
            else:
                logger.warning(
                    "Failed to patch MediaMTX WebRTC LAN config (%s): %s",
                    res.status_code,
                    res.text[:200],
                )
        except httpx.HTTPError as exc:
            logger.warning("Failed to patch MediaMTX WebRTC LAN config: %s", exc)
        if self.mdns is not None:
            await asyncio.to_thread(self.mdns.refresh_ip)

    # ------------------------------------------------------------------ reconcile + health

    async def _storage(self, session: Any) -> StorageConfig:
        return await get_storage_config(session, default_path=self.rt.settings.data_dir / "recordings")

    async def _reconcile_once(self) -> None:
        if self._client is None or await self._mediamtx_answering() is None:
            return
        await self._sync_webrtc_lan_config()
        async with self.rt.sessions() as session:
            active = select(Camera.serial).where(Camera.state == "active")
            serials = list((await session.scalars(active)).all())
            for serial in serials:
                # A camera added by any path records continuously until the user says otherwise.
                await get_or_create_recording_settings(session, serial)
            await self._pin_stream_certificates(session)
            storage = await self._storage(session)
            tz_name = await read_site_timezone(session)
            volume_ok = storage.health_state == StorageHealthState.OK
            if volume_ok:
                storage.storage_path.mkdir(parents=True, exist_ok=True)
            desired = await compute_desired_paths(
                session,
                storage_path=storage.storage_path,
                volume_ok=volume_ok,
                tz_name=tz_name,
                vault=self.rt.vault,
            )
        desired = {
            name: replace(cfg, run_on_record_segment_complete=self.hook_command)
            if cfg.run_on_record_segment_complete
            else cfg
            for name, cfg in desired.items()
        }
        result = await MediaMtxReconciler(self._client, self.api_base, self.auth).reconcile(desired)
        if not result.is_clean:
            logger.info(
                "MediaMTX paths: added=%s patched=%s deleted=%s", result.added, result.patched, result.deleted
            )
        await self._track_outages(serials)
        await self._sync_event_sources(serials)

    async def _pin_stream_certificates(self, session: Any) -> None:
        """Pin each RTSPS stream to the certificate its own port presents.

        The camera's RTSPS ports use a different certificate than HTTPS, so the
        onboarding pin cannot be reused. Trust on first use (as onboarding does),
        then the pin is kept: a changed certificate stops the stream instead of
        silently trusting a new one.
        """
        rows = (
            await session.execute(
                select(CameraStream, Camera.host)
                .join(Camera, Camera.serial == CameraStream.serial)
                .where(
                    Camera.state == "active",
                    CameraStream.scheme == "rtsps",
                    CameraStream.tls_fingerprint_sha256.is_(None),
                )
            )
        ).all()
        pinned: dict[tuple[str, int], str] = {}
        for stream, host in rows:
            key = (host, stream.port)
            if key not in pinned:
                fingerprint = await fetch_certificate_sha256(host, stream.port, timeout=5.0)
                if not isinstance(fingerprint, str):
                    logger.warning(
                        "Could not read the video certificate of %s (%s:%s): %s",
                        stream.serial, host, stream.port, fingerprint.reason,
                    )
                    continue
                pinned[key] = fingerprint
                logger.info("Pinned video certificate for %s %s stream", stream.serial, stream.role)
            stream.tls_fingerprint_sha256 = pinned[key]
        if pinned:
            await session.commit()

    async def _path_ready(self) -> dict[str, bool]:
        if self._client is None:
            return {}
        res = await self._client.get(f"{self.api_base}/v3/paths/list", auth=self.auth)
        res.raise_for_status()
        ready: dict[str, bool] = {}
        for item in res.json().get("items", []):
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                # v1.21 reports `online: true` for any configured path; only `available`
                # (or the older `ready`) means video is actually arriving from the camera.
                ready[item["name"]] = bool(item.get("available", item.get("ready", False)))
        return ready

    async def _track_outages(self, serials: list[str]) -> None:
        ready = await self._path_ready()
        now = utc_now()
        async with self.rt.sessions() as session:
            for serial in serials:
                if ready.get(camera_path_name(serial, "main"), False):
                    self._not_ready_since.pop(serial, None)
                    if serial in self._offline or serial not in self._seen:
                        await OutageTracker.record_online(session, serial, at=now)
                        self._offline.discard(serial)
                    self._seen.add(serial)
                    continue
                since = self._not_ready_since.setdefault(serial, now)
                waited = (now - since).total_seconds()
                if serial not in self._offline and waited >= self.offline_grace_seconds:
                    await OutageTracker.record_offline(
                        session, serial, reason="Camera video stream unavailable", at=since
                    )
                    self._offline.add(serial)
                self._seen.add(serial)
        for gone in set(self._not_ready_since) - set(serials):
            self._not_ready_since.pop(gone, None)
            self._offline.discard(gone)

    # ------------------------------------------------------------------ events

    async def _sync_event_sources(self, serials: list[str]) -> None:
        if self.rt.vault is None:
            return
        wanted = set(serials)
        for serial in self._event_cameras - wanted:
            self._events.unregister_camera_source(serial)
        self._event_cameras &= wanted
        added = False
        async with self.rt.sessions() as session:
            for serial in wanted - self._event_cameras:
                try:
                    conn = await load_connection(session, self.rt.vault, serial)
                except Exception as exc:
                    if serial not in self._event_failures:
                        logger.warning("Events not started for %s: %s", serial, exc)
                        self._event_failures.add(serial)
                    continue
                self._event_failures.discard(serial)
                source = OnvifPullPointSource(
                    serial,
                    conn,
                    http=self._camera_http,
                    clock=self.rt.clock,
                    event_service_path="/onvif/events_service",
                )
                self._events.register_camera_source(serial, source)
                self._event_cameras.add(serial)
                added = True
        if added:
            await self._events.start()

    async def _on_camera_event(self, event: RawCameraEvent) -> None:
        start, clock_state = restamp_event_time(event, utc_now())
        async with self.rt.sessions() as session:
            await insert_event(
                session,
                EventRecord(
                    camera_serial=event.camera_serial,
                    event_type=event.event_type,
                    start_time=start,
                    source=event.source_name,
                    clock_sync_state=clock_state,
                    raw_topic=event.topic,
                    details=event.data or None,
                ),
            )

    # ------------------------------------------------------------------ index + retention

    async def _index_once(self) -> None:
        async with self.rt.sessions() as session:
            storage = await self._storage(session)
            report = await scan_and_reconcile(session, storage.storage_path)
        if report.adopted or report.missing_marked or report.truncated_marked:
            logger.info(
                "Segment index: adopted=%d missing=%d truncated=%d",
                report.adopted,
                report.missing_marked,
                report.truncated_marked,
            )

    async def _janitor_once(self) -> None:
        async with self.rt.sessions() as session:
            serials = list((await session.scalars(select(Camera.serial))).all())
            for serial in serials:
                try:
                    report = await enforce_camera_retention(session, serial)
                    if report.deleted_files:
                        logger.info("Retention removed %d segments for %s", len(report.deleted_files), serial)
                except Exception:
                    logger.exception("Retention failed for %s", serial)
            storage = await self._storage(session)
            await enforce_disk_low_water_mark(
                session, storage.storage_path, reserve_bytes=storage.reserve_bytes
            )

    # ------------------------------------------------------------------ status

    def status(self) -> dict[str, Any]:
        running = self.adopted_external or (
            self.process is not None and self.process.popen is not None and self.process.popen.poll() is None
        )
        return {"mediamtx_running": running, "mediamtx_error": None if running else self.mediamtx_error}


__all__ = ["RecorderSupervisor", "PathConfiguration", "segment_hook_command", "restamp_event_time"]
