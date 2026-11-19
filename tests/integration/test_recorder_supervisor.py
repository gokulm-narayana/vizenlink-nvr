"""The recorder supervisor that `nvr run` starts: reconcile, outages, events, MediaMTX."""

from __future__ import annotations

import json
import socket
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from vizenlink_nvr.config import load_settings
from vizenlink_nvr.db.models import Camera, CameraOutage, CameraStream, Event, RecordingSettings
from vizenlink_nvr.events.source import RawCameraEvent
from vizenlink_nvr.media.config import MediaMtxPorts
from vizenlink_nvr.services.events import ClockSyncState
from vizenlink_nvr.services.recorder import (
    RecorderSupervisor,
    build_recorder_config,
    restamp_event_time,
    segment_hook_command,
)
from vizenlink_nvr.services.runtime import open_runtime
from vizenlink_nvr.services.storage import set_storage_path
from vizenlink_nvr.timeutil import utc_now


async def _add_camera(rt: Any, serial: str = "VZL-CAM-001", scheme: str = "rtsp") -> None:
    now = utc_now()
    async with rt.sessions() as session:
        # Recording only starts on a storage folder the recorder accepts (set by the setup wizard).
        await set_storage_path(session, Path(rt.settings.data_dir) / "recordings", allow_system_disk=True)
        session.add(
            Camera(
                serial=serial,
                host="192.168.1.100",
                https_port=443,
                mac="AA:BB:CC:DD:EE:01",
                name="Front Gate",
                state="active",
                tls_fingerprint_sha256="fp",
                added_at=now,
                host_updated_at=now,
            )
        )
        session.add(
            CameraStream(
                serial=serial,
                role="main",
                profile_token="p1",
                profile_name="Main",
                venc_token="v1",
                codec="H264",
                width=1920,
                height=1080,
                transport="tcp",
                scheme=scheme,
                port=554,
                path="/live/main",
                source="nuraeye",
                sub_is_main=False,
                probed_at=now,
            )
        )
        await session.commit()


class FakeMediaMtx:
    """Minimal MediaMTX control API: config paths + runtime path readiness."""

    def __init__(self, data_dir: Path) -> None:
        self.paths: dict[str, dict[str, Any]] = {}
        self.ready: dict[str, bool] = {}
        self.data_dir = data_dir

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v3/config/global/get":
            return httpx.Response(200, json={"authHTTPAddress": "http://127.0.0.1:8000/api/v1/auth/mediamtx"})
        if path == "/v3/config/paths/list":
            return httpx.Response(200, json={"items": [{"name": n, **c} for n, c in self.paths.items()]})
        if path.startswith("/v3/config/paths/add/"):
            self.paths[path.removeprefix("/v3/config/paths/add/")] = json.loads(request.content)
            return httpx.Response(200)
        if path.startswith("/v3/config/paths/patch/"):
            self.paths[path.removeprefix("/v3/config/paths/patch/")].update(json.loads(request.content))
            return httpx.Response(200)
        if path.startswith("/v3/config/paths/delete/"):
            self.paths.pop(path.removeprefix("/v3/config/paths/delete/"), None)
            return httpx.Response(200)
        if path == "/v3/paths/list":
            return httpx.Response(
                200, json={"items": [{"name": n, "ready": self.ready.get(n, False)} for n in self.paths]}
            )
        return httpx.Response(404)


@pytest.mark.asyncio
async def test_reconcile_records_new_camera_by_default_and_tracks_outages(tmp_path: Path) -> None:
    settings = load_settings(data_dir=tmp_path / "data")
    async with open_runtime(settings) as rt:
        await _add_camera(rt)
        fake = FakeMediaMtx(settings.data_dir)
        sup = RecorderSupervisor(rt, nvr_port=8000, lan_access=False, offline_grace_seconds=0)
        sup._client = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
        try:
            await sup._reconcile_once()

            # A camera added without opening its recording page still records (default continuous).
            async with rt.sessions() as session:
                rec = (await session.scalars(select(RecordingSettings))).one()
                assert rec.mode == "continuous"
            main = fake.paths["cam/vzl-cam-001/main"]
            assert main["record"] is True
            assert main["recordDeleteAfter"] == "0s"
            # The hook runs this interpreter against this data dir, not `nvr` from PATH.
            assert main["runOnRecordSegmentComplete"] == segment_hook_command(settings.data_dir)
            assert str(settings.data_dir) in main["runOnRecordSegmentComplete"]

            # Stream not ready -> outage opened; ready again -> outage closed.
            async with rt.sessions() as session:
                outage = (await session.scalars(select(CameraOutage))).one()
                assert outage.ended_at is None
            fake.ready["cam/vzl-cam-001/main"] = True
            await sup._reconcile_once()
            async with rt.sessions() as session:
                outage = (await session.scalars(select(CameraOutage))).one()
                assert outage.ended_at is not None
        finally:
            await sup._client.aclose()
            await sup._camera_http.aclose()


@pytest.mark.asyncio
async def test_rtsps_source_is_pinned_to_the_video_port_certificate(tmp_path: Path, monkeypatch) -> None:
    """The camera's RTSPS port has its own certificate; pinning the HTTPS one blocked all video."""
    settings = load_settings(data_dir=tmp_path / "data")
    probes: list[tuple[str, int]] = []

    async def fake_fetch(host: str, port: int, timeout: float) -> str:
        probes.append((host, port))
        return "a" * 64

    monkeypatch.setattr("vizenlink_nvr.services.recorder.fetch_certificate_sha256", fake_fetch)
    async with open_runtime(settings) as rt:
        await _add_camera(rt, scheme="rtsps")
        fake = FakeMediaMtx(settings.data_dir)
        sup = RecorderSupervisor(rt, nvr_port=8000, lan_access=False)
        sup._client = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
        try:
            await sup._reconcile_once()
            await sup._reconcile_once()
            assert probes == [("192.168.1.100", 554)]  # pinned once, then kept
            assert fake.paths["cam/vzl-cam-001/main"]["sourceFingerprint"] == "a" * 64
            async with rt.sessions() as session:
                stream = (await session.scalars(select(CameraStream))).one()
                assert stream.tls_fingerprint_sha256 == "a" * 64
        finally:
            await sup._client.aclose()
            await sup._camera_http.aclose()


@pytest.mark.asyncio
async def test_unknown_mediamtx_on_api_port_is_not_adopted(tmp_path: Path) -> None:
    settings = load_settings(data_dir=tmp_path / "data")
    async with open_runtime(settings) as rt:
        sup = RecorderSupervisor(rt, nvr_port=8000, lan_access=False)
        sup._client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"authHTTPAddress": "http://elsewhere/auth"})
            )
        )
        try:
            await sup._ensure_mediamtx()
            assert sup.process is None
            assert sup.status()["mediamtx_running"] is False
            assert "another program" in (sup.status()["mediamtx_error"] or "")
        finally:
            await sup._client.aclose()
            await sup._camera_http.aclose()


@pytest.mark.asyncio
async def test_camera_events_are_stored_and_restamped_when_clock_drifts(tmp_path: Path) -> None:
    settings = load_settings(data_dir=tmp_path / "data")
    async with open_runtime(settings) as rt:
        await _add_camera(rt)
        sup = RecorderSupervisor(rt, nvr_port=8000, lan_access=False)
        camera_time = utc_now() - timedelta(minutes=10)
        await sup._on_camera_event(
            RawCameraEvent(
                camera_serial="VZL-CAM-001",
                topic="tns1:RuleEngine/CellMotionDetector/Motion",
                utc_time=camera_time,
                clock_drift_seconds=600.0,
            )
        )
        async with rt.sessions() as session:
            event = (await session.scalars(select(Event))).one()
        assert event.event_type == "motion"
        assert event.clock_sync_state == ClockSyncState.DRIFT_DETECTED.value
        assert abs((utc_now() - event.start_time.replace(tzinfo=camera_time.tzinfo)).total_seconds()) < 60
        await sup._camera_http.aclose()


def test_event_time_kept_when_camera_clock_is_synced() -> None:
    now = utc_now()
    camera_time = now - timedelta(seconds=2)
    event = RawCameraEvent("S", "Motion", camera_time, clock_drift_seconds=1.0)
    assert restamp_event_time(event, now) == (camera_time, ClockSyncState.SYNCED)
    missing = RawCameraEvent("S", "Motion", None)
    assert restamp_event_time(missing, now) == (now, ClockSyncState.UNCERTAIN)


def test_lan_access_opens_only_webrtc_media_socket() -> None:
    ports = MediaMtxPorts()
    local = build_recorder_config(ports, "pw", 8000, lan_access=False)
    lan = build_recorder_config(ports, "pw", 8000, lan_access=True)
    assert local["webrtcLocalUDPAddress"].startswith("127.0.0.1:")
    assert local["webrtcLocalTCPAddress"].startswith("127.0.0.1:")
    assert lan["webrtcLocalUDPAddress"] == f":{ports.webrtc_udp}"
    assert lan["webrtcLocalTCPAddress"] == f":{ports.webrtc_udp}"
    assert "127.0.0.1" not in lan["webrtcAdditionalHosts"]
    # Signalling, API, RTSP, HLS and playback stay loopback-only behind the authenticated NVR.
    for key in ("apiAddress", "webrtcAddress", "rtspAddress", "hlsAddress", "playbackAddress"):
        assert lan[key].startswith("127.0.0.1:")


@pytest.mark.asyncio
async def test_sync_webrtc_lan_config_patches_on_ip_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import MagicMock

    settings = load_settings(data_dir=tmp_path / "data")
    patches: list[dict[str, Any]] = []

    def mock_handler(req: httpx.Request) -> httpx.Response:
        if req.method == "PATCH" and req.url.path == "/v3/config/global/patch":
            patches.append(json.loads(req.content))
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404)

    current_ips = ["192.168.10.10"]
    monkeypatch.setattr("vizenlink_nvr.services.recorder.lan_ipv4_addresses", lambda: list(current_ips))
    mock_mdns = MagicMock()

    async with open_runtime(settings) as rt:
        sup = RecorderSupervisor(rt, nvr_port=8000, lan_access=True, mdns=mock_mdns)
        sup._client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler), trust_env=False)
        try:
            await sup._sync_webrtc_lan_config()
            assert len(patches) == 1
            assert patches[0]["webrtcLocalUDPAddress"] == f":{sup.ports.webrtc_udp}"
            assert patches[0]["webrtcLocalTCPAddress"] == f":{sup.ports.webrtc_udp}"
            assert patches[0]["webrtcAdditionalHosts"] == ["192.168.10.10"]
            mock_mdns.refresh_ip.assert_called_once()

            # Same IP list does not re-patch
            await sup._sync_webrtc_lan_config()
            assert len(patches) == 1

            # IP change triggers fresh patch and mDNS refresh
            current_ips[:] = ["192.168.10.25"]
            await sup._sync_webrtc_lan_config()
            assert len(patches) == 2
            assert patches[1]["webrtcAdditionalHosts"] == ["192.168.10.25"]
            assert mock_mdns.refresh_ip.call_count == 2
        finally:
            await sup._client.aclose()
            sup._client = None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _control_auth_webhook(control_password: str) -> ThreadingHTTPServer:
    """Stand-in for the NVR's /api/v1/auth/mediamtx: allows only the control user's API calls."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            ok = body.get("action") == "api" and body.get("password") == control_password
            self.send_response(200 if ok else 401)
            self.end_headers()

        def log_message(self, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.mark.mediamtx
@pytest.mark.timeout(60)
@pytest.mark.asyncio
async def test_recorder_starts_real_mediamtx_and_configures_camera(tmp_path: Path) -> None:
    """End to end with the pinned binary: `nvr run`'s recorder starts MediaMTX and adds the path."""
    settings = load_settings(data_dir=tmp_path / "data")
    ports = MediaMtxPorts(
        api=_free_port(),
        playback=_free_port(),
        rtsp=_free_port(),
        hls=_free_port(),
        webrtc=_free_port(),
        webrtc_udp=_free_port(),
    )
    async with open_runtime(settings) as rt:
        await _add_camera(rt)
        sup = RecorderSupervisor(rt, nvr_port=0, lan_access=False, ports=ports)
        webhook = _control_auth_webhook(sup.control_password)
        sup.nvr_port = webhook.server_address[1]
        sup._client = httpx.AsyncClient(timeout=10.0, trust_env=False)
        try:
            await sup._ensure_mediamtx()
            assert sup.status()["mediamtx_running"] is True
            res = await sup._client.get(f"{sup.api_base}/v3/config/paths/list", auth=sup.auth)
            names = {item["name"]: item for item in res.json()["items"]}
            assert names["cam/vzl-cam-001/main"]["record"] is True
        finally:
            if sup.process is not None:
                sup.process.stop()
            webhook.shutdown()
            await sup._client.aclose()
            await sup._camera_http.aclose()
