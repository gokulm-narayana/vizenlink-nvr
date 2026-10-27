"""Loopback TLS HTTP/1.1 server and request tracer for fake camera."""

import asyncio
import json
import logging
import os
import re
import ssl
import tempfile
from dataclasses import dataclass
from typing import Literal

from fake_camera.certs import generate_self_signed_cert
from fake_camera.faults import (
    Delay,
    Drop,
    FaultPlan,
    Malformed,
    Silence,
    SoapFault,
    Status,
)
from fake_camera.routes import find_route
from fake_camera.state import CameraState

logger = logging.getLogger(__name__)


def _create_server_ssl_context(cert_pem: bytes, key_pem: bytes) -> ssl.SSLContext:
    """Create SSL context loaded with ephemeral in-memory certificate."""
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    cert_fd, cert_path = tempfile.mkstemp(prefix="vzl_cert_", suffix=".pem")
    key_fd, key_path = tempfile.mkstemp(prefix="vzl_key_", suffix=".pem")
    try:
        with os.fdopen(cert_fd, "wb") as f:
            f.write(cert_pem)
        with os.fdopen(key_fd, "wb") as f:
            f.write(key_pem)
        ssl_ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
    finally:
        if os.path.exists(cert_path):
            os.unlink(cert_path)
        if os.path.exists(key_path):
            os.unlink(key_path)
    return ssl_ctx


@dataclass
class RecordedRequest:
    """Request recorded by the fake camera simulator."""

    method: str
    path: str
    raw_header_names: list[bytes]
    headers: list[tuple[bytes, bytes]]
    body: bytes
    credential_use: Literal["none", "blank", "stored", "other"]
    soap_action: str | None = None


class FakeCamera:
    """Simulated camera server running over TLS on 127.0.0.1."""

    def __init__(
        self,
        state: CameraState | None = None,
        faults: FaultPlan | None = None,
    ) -> None:
        self.state = state or CameraState()
        self.faults = faults or FaultPlan()
        self.requests: list[RecordedRequest] = []
        self._server: asyncio.Server | None = None
        self.host = "127.0.0.1"
        self.port = 0
        self.cert_sha256 = ""
        self._cert_pem = b""
        self._key_pem = b""

    def requests_with_credentials(self) -> list[RecordedRequest]:
        """Return requests where credentials were transmitted."""
        return [r for r in self.requests if r.credential_use != "none"]

    async def start(self) -> None:
        """Start the fake camera TLS server on an ephemeral loopback port."""
        cert_pem, key_pem, fingerprint = generate_self_signed_cert()
        self.cert_sha256 = fingerprint
        self._cert_pem = cert_pem
        self._key_pem = key_pem

        ssl_ctx = _create_server_ssl_context(cert_pem, key_pem)
        self._server = await asyncio.start_server(
            self._handle_client,
            host=self.host,
            port=0,
            ssl=ssl_ctx,
        )
        self.port = self._server.sockets[0].getsockname()[1]

    async def close(self) -> None:
        """Stop the fake camera server."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle incoming TLS HTTP/1.1 client connection."""
        try:
            while True:
                # Read headers
                header_data = bytearray()
                while b"\r\n\r\n" not in header_data and b"\n\n" not in header_data:
                    chunk = await reader.read(4096)
                    if not chunk:
                        break
                    header_data.extend(chunk)

                if not header_data:
                    break

                if b"\r\n\r\n" in header_data:
                    delim = b"\r\n\r\n"
                elif b"\n\n" in header_data:
                    delim = b"\n\n"
                else:
                    break

                headers_part, leftover = header_data.split(delim, 1)
                lines = headers_part.splitlines()
                if not lines:
                    break

                request_line = lines[0].decode("latin1")
                parts = request_line.split()
                if not parts:
                    break
                method = parts[0]
                path = parts[1] if len(parts) > 1 else "/"

                raw_header_names: list[bytes] = []
                headers: list[tuple[bytes, bytes]] = []
                content_length = 0
                soap_action: str | None = None

                for line in lines[1:]:
                    if not line:
                        continue
                    if b":" in line:
                        name, val = line.split(b":", 1)
                        name_stripped = name.strip()
                        val_stripped = val.strip()
                        raw_header_names.append(name_stripped)
                        headers.append((name_stripped, val_stripped))
                        if name_stripped.lower() == b"content-length":
                            try:
                                content_length = int(val_stripped.decode("latin1"))
                            except ValueError:
                                content_length = 0
                        elif name_stripped.lower() == b"soapaction":
                            soap_action = val_stripped.decode("latin1").strip("\"'")

                # Read body
                body = bytearray(leftover)
                bytes_needed = content_length - len(body)
                while bytes_needed > 0:
                    chunk = await reader.read(min(bytes_needed, 65536))
                    if not chunk:
                        break
                    body.extend(chunk)
                    bytes_needed -= len(chunk)
                body_bytes = bytes(body)

                # Classify credential use
                cred_use: Literal["none", "blank", "stored", "other"] = "none"
                for h_name, h_val in headers:
                    if h_name.lower() == b"authorization":
                        auth_val = h_val.decode("latin1").strip()
                        if auth_val.lower().startswith("bearer "):
                            token = auth_val[7:].strip()
                            if not token:
                                cred_use = "blank"
                            elif token in self.state.sessions:
                                cred_use = "stored"
                            else:
                                cred_use = "other"
                        elif auth_val.lower().startswith("basic "):
                            import base64

                            try:
                                decoded = base64.b64decode(auth_val[6:].strip()).decode("utf-8")
                                user, pwd = decoded.split(":", 1)
                                if not pwd:
                                    cred_use = "blank"
                                elif (
                                    user in self.state.accounts and self.state.accounts[user].password == pwd
                                ):
                                    cred_use = "stored"
                                else:
                                    cred_use = "other"
                            except Exception:
                                cred_use = "other"

                if cred_use == "none" and b"UsernameToken" in body_bytes:
                    match_user = re.search(rb"<[a-zA-Z0-9_:]*Username[^>]*>([^<]*)</", body_bytes)
                    user = match_user.group(1).decode("utf-8") if match_user else ""
                    if not user:
                        cred_use = "blank"
                    elif user in self.state.accounts:
                        cred_use = "stored"
                    else:
                        cred_use = "other"

                recorded = RecordedRequest(
                    method=method,
                    path=path,
                    raw_header_names=raw_header_names,
                    headers=headers,
                    body=body_bytes,
                    credential_use=cred_use,
                    soap_action=soap_action,
                )
                self.requests.append(recorded)

                # Camera ID verification
                if not self.state.check_camera_id(headers):
                    resp_bytes = b"Misdirected Request"
                    resp_lines = [
                        b"HTTP/1.1 421 Misdirected Request",
                        b"Content-Type: text/plain",
                        f"Content-Length: {len(resp_bytes)}".encode("latin1"),
                        b"Connection: keep-alive",
                        b"",
                        resp_bytes,
                    ]
                    writer.write(b"\r\n".join(resp_lines))
                    await writer.drain()
                    continue

                # Fault processing
                route_key = f"{method} {path}"
                fault = self.faults.pop_fault(route_key)
                if fault is not None:
                    if isinstance(fault, Delay):
                        await asyncio.sleep(fault.seconds)
                    elif isinstance(fault, Silence):
                        await asyncio.sleep(fault.seconds)
                    elif isinstance(fault, Drop):
                        writer.close()
                        await writer.wait_closed()
                        return
                    elif isinstance(fault, Malformed):
                        writer.write(
                            b"HTTP/1.1 200 OK\r\n"
                            b"Content-Type: application/json\r\n"
                            b"Content-Length: 15\r\n"
                            b"Connection: close\r\n\r\n"
                            b"{invalid json:"
                        )
                        await writer.drain()
                        return
                    elif isinstance(fault, Status):
                        if fault.json_body is not None:
                            body_out = json.dumps(fault.json_body).encode("utf-8")
                            status_text = "OK" if fault.code == 200 else "Error"
                            resp_lines = [
                                f"HTTP/1.1 {fault.code} {status_text}".encode("latin1"),
                                b"Content-Type: application/json",
                                f"Content-Length: {len(body_out)}".encode("latin1"),
                                b"Connection: keep-alive",
                                b"",
                                body_out,
                            ]
                        else:
                            resp_lines = [
                                f"HTTP/1.1 {fault.code} Status".encode("latin1"),
                                b"Content-Length: 0",
                                b"Connection: keep-alive",
                                b"",
                                b"",
                            ]
                        writer.write(b"\r\n".join(resp_lines))
                        await writer.drain()
                        continue
                    elif isinstance(fault, SoapFault):
                        soap_body = (
                            f'<?xml version="1.0" encoding="utf-8"?>\n'
                            f'<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">\n'
                            f"  <soap:Body>\n"
                            f"    <soap:Fault>\n"
                            f"      <soap:Code><soap:Value>soap:Receiver</soap:Value>"
                            f"<soap:Subcode><soap:Value>{fault.subcode}</soap:Value></soap:Subcode></soap:Code>\n"
                            f'      <soap:Reason><soap:Text xml:lang="en">'
                            f"{fault.reason}</soap:Text></soap:Reason>\n"
                            f"    </soap:Fault>\n"
                            f"  </soap:Body>\n"
                            f"</soap:Envelope>"
                        ).encode()
                        resp_lines = [
                            f"HTTP/1.1 {fault.http_status} Fault".encode("latin1"),
                            b"Content-Type: application/soap+xml; charset=utf-8",
                            f"Content-Length: {len(soap_body)}".encode("latin1"),
                            b"Connection: keep-alive",
                            b"",
                            soap_body,
                        ]
                        writer.write(b"\r\n".join(resp_lines))
                        await writer.drain()
                        continue

                # Route dispatch
                handler = find_route(method, path, soap_action)
                if handler is not None:
                    res = handler(self.state, body_bytes, headers)
                    if asyncio.iscoroutine(res):
                        status_code, resp_payload = await res
                    else:
                        status_code, resp_payload = res

                    if isinstance(resp_payload, dict):
                        resp_bytes = json.dumps(resp_payload).encode("utf-8")
                        content_type = b"application/json"
                    elif isinstance(resp_payload, str):
                        resp_bytes = resp_payload.encode("utf-8")
                        content_type = b"text/plain"
                    elif isinstance(resp_payload, bytes):
                        resp_bytes = resp_payload
                        content_type = b"application/octet-stream"
                    else:
                        resp_bytes = b""
                        content_type = b"text/plain"

                    status_map = {
                        200: "OK",
                        400: "Bad Request",
                        401: "Unauthorized",
                        404: "Not Found",
                        421: "Misdirected Request",
                        500: "Internal Server Error",
                    }
                    st_text = status_map.get(status_code, "Status")
                    resp_lines = [
                        f"HTTP/1.1 {status_code} {st_text}".encode("latin1"),
                        b"Content-Type: " + content_type,
                        f"Content-Length: {len(resp_bytes)}".encode("latin1"),
                        b"Connection: keep-alive",
                        b"",
                        resp_bytes,
                    ]
                    writer.write(b"\r\n".join(resp_lines))
                    await writer.drain()
                else:
                    err_body = json.dumps({"error_code": 404, "error_msg": "Not Found", "output": {}}).encode(
                        "utf-8"
                    )
                    resp_lines = [
                        b"HTTP/1.1 404 Not Found",
                        b"Content-Type: application/json",
                        f"Content-Length: {len(err_body)}".encode("latin1"),
                        b"Connection: keep-alive",
                        b"",
                        err_body,
                    ]
                    writer.write(b"\r\n".join(resp_lines))
                    await writer.drain()

        except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                logger.debug("Exception closing writer in fake camera", exc_info=True)
