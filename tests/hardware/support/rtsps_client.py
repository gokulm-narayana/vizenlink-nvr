"""RTSPS client implementing RFC 2617 Digest authentication for stream testing (D-26)."""

import asyncio
import contextlib
import hashlib
import re

from vizenlink_nvr.camera.http import camera_ssl_context


def _md5_hex(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()  # noqa: S324


class RtspsClient:
    """Minimal RTSP-over-TLS client supporting OPTIONS, DESCRIBE, SETUP, PLAY, and TEARDOWN."""

    def __init__(
        self,
        host: str,
        port: int,
        path: str,
        username: str = "",
        password: str = "",
        timeout: float = 10.0,
    ) -> None:
        self.host = host
        self.port = port
        self.path = path if path.startswith("/") else f"/{path}"
        self.username = username
        self.password = password
        self.timeout = timeout
        self.cseq = 1
        self.session_id: str | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._realm: str | None = None
        self._nonce: str | None = None

    @property
    def url(self) -> str:
        """Construct full RTSPS URL."""
        return f"rtsps://{self.host}:{self.port}{self.path}"

    async def connect(self) -> None:
        """Open TLS TCP connection to RTSPS server."""
        ssl_ctx = camera_ssl_context(None)
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port, ssl=ssl_ctx),
            timeout=self.timeout,
        )

    async def _send_raw(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
    ) -> tuple[int, dict[str, str], str]:
        """Send RTSP request and parse response status, headers, and body."""
        if self._writer is None or self._reader is None:
            raise RuntimeError("Client not connected")

        cseq_num = self.cseq
        self.cseq += 1

        req_lines = [
            f"{method} {url} RTSP/1.0",
            f"CSeq: {cseq_num}",
        ]
        if self.session_id:
            req_lines.append(f"Session: {self.session_id}")

        for k, v in headers.items():
            req_lines.append(f"{k}: {v}")

        req_lines.extend(["", ""])
        req_bytes = "\r\n".join(req_lines).encode("utf-8")

        self._writer.write(req_bytes)
        await self._writer.drain()

        # Read response status line
        status_line = await asyncio.wait_for(self._reader.readline(), timeout=self.timeout)
        status_parts = status_line.decode("latin1").strip().split(maxsplit=2)
        if len(status_parts) < 2:
            return 500, {}, ""

        try:
            status_code = int(status_parts[1])
        except ValueError:
            status_code = 500

        # Read response headers
        resp_headers: dict[str, str] = {}
        content_length = 0
        while True:
            line = await asyncio.wait_for(self._reader.readline(), timeout=self.timeout)
            decoded = line.decode("latin1").strip()
            if not decoded:
                break
            if ":" in decoded:
                h_name, h_val = decoded.split(":", 1)
                resp_headers[h_name.strip().lower()] = h_val.strip()
                if h_name.strip().lower() == "content-length":
                    content_length = int(h_val.strip())

        # Read body if any
        body_text = ""
        if content_length > 0:
            body_bytes = await asyncio.wait_for(
                self._reader.readexactly(content_length),
                timeout=self.timeout,
            )
            body_text = body_bytes.decode("utf-8", errors="replace")

        return status_code, resp_headers, body_text

    def _build_auth_header(self, method: str, url: str) -> str:
        """Compute RFC 2617 Digest response header."""
        realm = self._realm or "ONVIF"
        nonce = self._nonce or ""
        ha1 = _md5_hex(f"{self.username}:{realm}:{self.password}")
        ha2 = _md5_hex(f"{method}:{url}")
        resp = _md5_hex(f"{ha1}:{nonce}:{ha2}")
        auth_val = (
            f'Digest username="{self.username}", realm="{realm}", nonce="{nonce}", '
            f'uri="{url}", response="{resp}"'
        )
        return auth_val

    def _extract_auth_params(self, headers: dict[str, str]) -> None:
        """Extract realm and nonce from WWW-Authenticate header."""
        auth_hdr = headers.get("www-authenticate", "")
        if not auth_hdr:
            return
        m_realm = re.search(r'realm="([^"]+)"', auth_hdr)
        if m_realm:
            self._realm = m_realm.group(1)
        m_nonce = re.search(r'nonce="([^"]+)"', auth_hdr)
        if m_nonce:
            self._nonce = m_nonce.group(1)

    async def describe(self) -> tuple[int, str]:
        """Send DESCRIBE and return HTTP/RTSP status code and SDP body."""
        headers = {"Accept": "application/sdp"}
        status, resp_headers, body = await self._send_raw("DESCRIBE", self.url, headers)

        if status == 401 and self.username:
            self._extract_auth_params(resp_headers)
            auth = self._build_auth_header("DESCRIBE", self.url)
            headers["Authorization"] = auth
            status, resp_headers, body = await self._send_raw("DESCRIBE", self.url, headers)

        return status, body

    async def setup(self, track: str | None = None) -> int:
        """Send SETUP for specified track (default: url/track1) and store Session ID."""
        track_url = f"{self.url}/{track}" if track else f"{self.url}/track1"
        headers = {"Transport": "RTP/AVP/TCP;unicast;interleaved=0-1"}
        status, resp_headers, body = await self._send_raw("SETUP", track_url, headers)

        if status == 401 and self.username:
            self._extract_auth_params(resp_headers)
            auth = self._build_auth_header("SETUP", track_url)
            headers["Authorization"] = auth
            status, resp_headers, body = await self._send_raw("SETUP", track_url, headers)

        if "session" in resp_headers:
            self.session_id = resp_headers["session"].split(";")[0].strip()

        return status

    async def play(self) -> int:
        """Send PLAY for the established session."""
        headers = {"Range": "npt=0.000-"}
        status, resp_headers, body = await self._send_raw("PLAY", self.url, headers)

        if status == 401 and self.username:
            self._extract_auth_params(resp_headers)
            auth = self._build_auth_header("PLAY", self.url)
            headers["Authorization"] = auth
            status, resp_headers, body = await self._send_raw("PLAY", self.url, headers)

        return status

    async def close(self) -> None:
        """Teardown session and close TCP socket."""
        with contextlib.suppress(Exception):
            if self._writer is not None and self.session_id:
                headers: dict[str, str] = {}
                if self.username and self._nonce:
                    headers["Authorization"] = self._build_auth_header("TEARDOWN", self.url)
                await self._send_raw("TEARDOWN", self.url, headers)

        if self._writer is not None:
            self._writer.close()
            with contextlib.suppress(Exception):
                await self._writer.wait_closed()
            self._writer = None
            self._reader = None
