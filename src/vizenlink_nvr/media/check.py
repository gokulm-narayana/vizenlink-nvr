"""Live MediaMTX probe executor verifying strict default-deny and loopback binding."""

from __future__ import annotations

import asyncio
import base64
import socket
from typing import TYPE_CHECKING

import httpx
from pydantic import BaseModel

if TYPE_CHECKING:
    from vizenlink_nvr.media.config import MediaMtxPorts

REFUSED_PORTS = (1935, 1936, 8890, 8892, 8893, 8322, 9998, 9999)


class ProbeResult(BaseModel):
    """Result of an individual protocol or endpoint probe."""

    name: str
    expected: str
    actual: str
    ok: bool


DUMMY_SDP = (
    "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=Test\r\nt=0 0\r\nm=video 0 RTP/AVP 96\r\na=rtpmap:96 H264/90000\r\n"
)


def listener_lines_ok(log_lines: list[str]) -> ProbeResult:
    """Verify all started listeners bind strictly to 127.0.0.1 and no unused protocols start."""
    bad_lines: list[str] = []
    listener_count = 0

    for line in log_lines:
        if "started with listener" in line:
            listener_count += 1
            if "127.0.0.1" not in line:
                bad_lines.append(f"Non-loopback listener: {line}")
        for forbidden in ("[RTMP]", "[SRT]", "[MoQ]"):
            if forbidden.lower() in line.lower() and "started with listener" in line:
                bad_lines.append(f"Forbidden listener started: {line}")

    if listener_count == 0:
        return ProbeResult(
            name="listener_lines",
            expected="listeners on 127.0.0.1",
            actual="no listener lines found",
            ok=False,
        )

    if bad_lines:
        return ProbeResult(
            name="listener_lines",
            expected="all listeners on 127.0.0.1 and no rtmp/srt/moq",
            actual="; ".join(bad_lines),
            ok=False,
        )

    return ProbeResult(
        name="listener_lines",
        expected="all listeners on 127.0.0.1 and no rtmp/srt/moq",
        actual=f"{listener_count} loopback listeners verified",
        ok=True,
    )


def _rtsp_probe(
    host: str,
    port: int,
    method: str,
    path: str,
    body: str = "",
    auth: tuple[str, str] | None = None,
) -> str:
    """Send raw RTSP request and return status line."""
    try:
        s = socket.create_connection((host, port), timeout=5.0)
    except Exception as exc:
        return f"ERROR: connect: {exc}"

    try:
        url = f"rtsp://{host}:{port}{path}"
        req = f"{method} {url} RTSP/1.0\r\nCSeq: 1\r\n"
        if auth:
            token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
            req += f"Authorization: Basic {token}\r\n"
        if body:
            req += f"Content-Type: application/sdp\r\nContent-Length: {len(body)}\r\n"
        req += "\r\n" + body
        s.sendall(req.encode("ascii"))
        res = s.recv(4096)
        line = res.split(b"\r\n")[0].decode("latin1", errors="replace")
        return line
    except Exception as exc:
        return f"ERROR: recv: {exc}"
    finally:
        s.close()


def _check_port_refused(host: str, port: int) -> bool:
    """Verify that a TCP port refuses connections."""
    try:
        s = socket.create_connection((host, port), timeout=0.5)
        s.close()
        return False
    except (ConnectionRefusedError, TimeoutError, OSError):
        return True
    except Exception:
        return True


async def run_probes(
    ports: MediaMtxPorts,
    control_password: str,
    *,
    host: str = "127.0.0.1",
) -> list[ProbeResult]:
    """Execute live rejection probes against running MediaMTX instance."""
    results: list[ProbeResult] = []

    # 1. RTSP ANNOUNCE anonymous -> 401
    status_line = await asyncio.to_thread(_rtsp_probe, host, ports.rtsp, "ANNOUNCE", "/cam/test", DUMMY_SDP)
    ok = "401" in status_line
    results.append(
        ProbeResult(
            name="rtsp_announce_anonymous",
            expected="401",
            actual=status_line,
            ok=ok,
        )
    )

    # 2. RTSP DESCRIBE anonymous -> 401
    status_line = await asyncio.to_thread(_rtsp_probe, host, ports.rtsp, "DESCRIBE", "/cam/test")
    ok = "401" in status_line
    results.append(
        ProbeResult(
            name="rtsp_describe_anonymous",
            expected="401",
            actual=status_line,
            ok=ok,
        )
    )

    # 3. API-only user RTSP ANNOUNCE refused -> 401
    status_line = await asyncio.to_thread(
        _rtsp_probe,
        host,
        ports.rtsp,
        "ANNOUNCE",
        "/cam/test",
        DUMMY_SDP,
        auth=("nvr-control", control_password),
    )
    ok = "401" in status_line
    results.append(
        ProbeResult(
            name="rtsp_announce_api_only_user",
            expected="401",
            actual=status_line,
            ok=ok,
        )
    )

    # HTTP client probes
    async with httpx.AsyncClient(timeout=5.0) as client:
        # 4. HLS index.m3u8 anonymous -> 401 (follows 302 redirect)
        try:
            resp = await client.get(
                f"http://{host}:{ports.hls}/cam/test/index.m3u8",
                follow_redirects=True,
            )
            act = str(resp.status_code)
        except Exception as exc:
            act = f"ERROR: {exc}"
        results.append(
            ProbeResult(
                name="hls_anonymous",
                expected="401",
                actual=act,
                ok=act == "401",
            )
        )

        # 5. HLS read by API-only user refused -> 401
        try:
            resp = await client.get(
                f"http://{host}:{ports.hls}/cam/test/index.m3u8",
                auth=("nvr-control", control_password),
                follow_redirects=True,
            )
            act = str(resp.status_code)
        except Exception as exc:
            act = f"ERROR: {type(exc).__name__}: {exc}"
        results.append(
            ProbeResult(
                name="hls_api_only_user",
                expected="401",
                actual=act,
                ok=act == "401",
            )
        )

        # 6. WHEP anonymous -> 401
        try:
            resp = await client.post(
                f"http://{host}:{ports.webrtc}/cam/test/whep",
                headers={"Content-Type": "application/sdp"},
                content=DUMMY_SDP,
            )
            act = str(resp.status_code)
        except Exception as exc:
            act = f"ERROR: {type(exc).__name__}: {exc}"
        results.append(
            ProbeResult(
                name="whep_anonymous",
                expected="401",
                actual=act,
                ok=act == "401",
            )
        )

        # 7. WHIP anonymous -> 401
        try:
            resp = await client.post(
                f"http://{host}:{ports.webrtc}/cam/test/whip",
                headers={"Content-Type": "application/sdp"},
                content=DUMMY_SDP,
            )
            act = str(resp.status_code)
        except Exception as exc:
            act = f"ERROR: {type(exc).__name__}: {exc}"
        results.append(
            ProbeResult(
                name="whip_anonymous",
                expected="401",
                actual=act,
                ok=act == "401",
            )
        )

        # 8. Playback /list anonymous -> 401
        try:
            resp = await client.get(f"http://{host}:{ports.playback}/list?path=cam/test")
            act = str(resp.status_code)
        except Exception as exc:
            act = f"ERROR: {type(exc).__name__}: {exc}"
        results.append(
            ProbeResult(
                name="playback_list_anonymous",
                expected="401",
                actual=act,
                ok=act == "401",
            )
        )

        # 9. Playback /get anonymous -> 401
        try:
            resp = await client.get(f"http://{host}:{ports.playback}/get?path=cam/test&start=0&duration=1")
            act = str(resp.status_code)
        except Exception as exc:
            act = f"ERROR: {type(exc).__name__}: {exc}"
        results.append(
            ProbeResult(
                name="playback_get_anonymous",
                expected="401",
                actual=act,
                ok=act == "401",
            )
        )

        # 10. API anonymous -> 401
        try:
            resp = await client.get(f"http://{host}:{ports.api}/v3/paths/list")
            act = str(resp.status_code)
        except Exception as exc:
            act = f"ERROR: {exc}"
        results.append(
            ProbeResult(
                name="api_anonymous",
                expected="401",
                actual=act,
                ok=act == "401",
            )
        )

        # 11. API wrong credentials -> 401
        try:
            resp = await client.get(
                f"http://{host}:{ports.api}/v3/paths/list",
                auth=("nvr-control", "wrong-password"),
            )
            act = str(resp.status_code)
        except Exception as exc:
            act = f"ERROR: {exc}"
        results.append(
            ProbeResult(
                name="api_wrong_credentials",
                expected="401",
                actual=act,
                ok=act == "401",
            )
        )

        # 12. API control credentials -> 200
        try:
            resp = await client.get(
                f"http://{host}:{ports.api}/v3/paths/list",
                auth=("nvr-control", control_password),
            )
            act = str(resp.status_code)
        except Exception as exc:
            act = f"ERROR: {exc}"
        results.append(
            ProbeResult(
                name="api_control_credentials",
                expected="200",
                actual=act,
                ok=act == "200",
            )
        )

    # 13. Refused ports
    for p in REFUSED_PORTS:
        refused = await asyncio.to_thread(_check_port_refused, host, p)
        results.append(
            ProbeResult(
                name=f"refused_port_{p}",
                expected="connection_refused",
                actual="connection_refused" if refused else "connected",
                ok=refused,
            )
        )

    return results
