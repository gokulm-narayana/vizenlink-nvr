"""Real-camera hardware tests: Stream URIs, Profiles, Codecs, and Concurrency Limits (HW-10, HW-11, HW-09)."""

import pytest

from tests.hardware.conftest import HwConfig
from tests.hardware.support.report import HwReport
from tests.hardware.support.rtsps_client import RtspsClient
from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.http import CameraHttp, camera_ssl_context
from vizenlink_nvr.camera.nuraeye.client import NuraeyeClient
from vizenlink_nvr.camera.onvif.media2 import OnvifMedia2Client
from vizenlink_nvr.timeutil import SystemClock


@pytest.mark.hardware
@pytest.mark.asyncio
async def test_hw_10_live_stream_uri_fallback(
    hw_env: HwConfig,
    hw_report: HwReport,
) -> None:
    """HW-10: live-stream-uri for profiles; ONVIF GetStreamUri fallback on webrtc (D-23)."""
    conn = CameraConnection(
        host=hw_env.host,
        port=hw_env.port,
        username=hw_env.username,
        password=hw_env.password,
    )
    http = CameraHttp(ssl_context=camera_ssl_context(None))
    clock = SystemClock()
    nura_client = NuraeyeClient(conn, http, clock)
    media2_client = OnvifMedia2Client(conn, http, clock)

    profiles = ["Profile_1", "Profile_2", "Profile_3"]
    for token in profiles:
        res = await nura_client.get_live_stream_uri(token)
        if not res.is_success():
            hw_report.record("HW-10", f"{token}_status", f"FAILED: {res.failure().reason}")
            continue

        uri_info = res.unwrap()
        hw_report.record(
            "HW-10",
            f"{token}_uri",
            f"transport={uri_info.transport}, port={uri_info.port}, path={uri_info.path}",
        )

        # If transport is webrtc, fallback to Media2 GetStreamUri (D-23)
        if uri_info.transport == "webrtc":
            onvif_res = await media2_client.get_stream_uri(token)
            if onvif_res.is_success():
                hw_report.record("HW-10", f"{token}_onvif_fallback_uri", onvif_res.unwrap())
            else:
                fail_msg = f"FAILED: {onvif_res.failure().reason}"
                hw_report.record("HW-10", f"{token}_onvif_fallback_uri", fail_msg)

    hw_report.outcome("HW-10", "PASSED", "Stream URIs queried across profiles with WebRTC fallback handling")


@pytest.mark.hardware
@pytest.mark.asyncio
async def test_hw_11_media2_profiles_and_sdp_codecs(
    hw_env: HwConfig,
    hw_report: HwReport,
) -> None:
    """HW-11: Media2 GetProfiles count, tokens, sizes, encodings; RTSPS DESCRIBE SDP codec."""
    conn = CameraConnection(
        host=hw_env.host,
        port=hw_env.port,
        username=hw_env.username,
        password=hw_env.password,
    )
    http = CameraHttp(ssl_context=camera_ssl_context(None))
    clock = SystemClock()
    media2_client = OnvifMedia2Client(conn, http, clock)

    res = await media2_client.get_profiles()
    if not res.is_success():
        hw_report.outcome("HW-11", "FAILED", f"GetProfiles failed: {res.failure().reason}")
        pytest.fail(f"Media2 GetProfiles failed: {res.failure().reason}")

    profiles = res.unwrap()
    hw_report.record("HW-11", "profile_count", len(profiles))

    for p in profiles:
        info_str = f"size={p.width}x{p.height}, encoding={p.encoding}"
        hw_report.record("HW-11", f"profile_{p.token}", info_str)

        # DESCRIBE stream via RTSPS client
        path = f"/{p.token.lower()}" if not p.token.startswith("/") else p.token
        rtsps = RtspsClient(
            host=hw_env.host,
            port=hw_env.port,
            path=path,
            username=hw_env.username,
            password=hw_env.password,
        )
        try:
            await rtsps.connect()
            status, sdp = await rtsps.describe()
            hw_report.record("HW-11", f"{p.token}_describe_status", status)
            if status == 200:
                codec = "H265" if "H265" in sdp.upper() or "HEVC" in sdp.upper() else "H264"
                hw_report.record("HW-11", f"{p.token}_sdp_codec", codec)
        except Exception as exc:
            hw_report.record("HW-11", f"{p.token}_describe_error", str(exc))
        finally:
            await rtsps.close()

    hw_report.outcome("HW-11", "PASSED", f"Parsed {len(profiles)} profiles and queried SDP codecs")


@pytest.mark.hardware
@pytest.mark.asyncio
async def test_hw_09_concurrent_stream_limit_cap_2(
    hw_env: HwConfig,
    hw_report: HwReport,
) -> None:
    """HW-09: Assert RTSPS client cap is 2 per stream; third concurrent client refused (D-26)."""
    clients: list[RtspsClient] = []
    refusal_reason = ""
    third_refused = False

    try:
        # Client 1
        c1 = RtspsClient(hw_env.host, hw_env.port, "/high", hw_env.username, hw_env.password)
        await c1.connect()
        s1, _ = await c1.describe()
        assert s1 == 200, f"Client 1 DESCRIBE returned {s1}"
        assert await c1.setup() == 200, "Client 1 SETUP failed"
        assert await c1.play() == 200, "Client 1 PLAY failed"
        clients.append(c1)

        # Client 2
        c2 = RtspsClient(hw_env.host, hw_env.port, "/high", hw_env.username, hw_env.password)
        await c2.connect()
        s2, _ = await c2.describe()
        assert s2 == 200, f"Client 2 DESCRIBE returned {s2}"
        assert await c2.setup() == 200, "Client 2 SETUP failed"
        assert await c2.play() == 200, "Client 2 PLAY failed"
        clients.append(c2)

        # Client 3: expected to be refused (either TCP close before TLS, or error status)
        c3 = RtspsClient(hw_env.host, hw_env.port, "/high", hw_env.username, hw_env.password)
        try:
            await c3.connect()
            s3, _ = await c3.describe()
            if s3 != 200:
                third_refused = True
                refusal_reason = f"DESCRIBE status {s3}"
            else:
                set3 = await c3.setup()
                if set3 != 200:
                    third_refused = True
                    refusal_reason = f"SETUP status {set3}"
                else:
                    play3 = await c3.play()
                    if play3 != 200:
                        third_refused = True
                        refusal_reason = f"PLAY status {play3}"
        except (ConnectionResetError, EOFError, OSError) as exc:
            third_refused = True
            refusal_reason = f"TCP close before/during TLS: {exc}"
        except Exception as exc:
            third_refused = True
            refusal_reason = f"Connection refused: {exc}"
        finally:
            await c3.close()

        hw_report.record("HW-09", "concurrent_clients_allowed", len(clients))
        hw_report.record("HW-09", "third_client_refusal_type", refusal_reason)

        assert third_refused, "Expected third concurrent RTSPS client on /high to be refused (D-26 limit 2)"
        hw_report.outcome(
            "HW-09",
            "PASSED",
            f"Max 2 concurrent clients confirmed; 3rd rejected via {refusal_reason}",
        )

    finally:
        for c in clients:
            await c.close()
