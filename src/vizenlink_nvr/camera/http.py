# mirrors: mobile_app/packages/camera_api/lib/src/lan/camera_id_mismatch.dart@1e0f913e3a37
# mirrors: mobile_app/packages/camera_api/lib/src/lan/insecure_camera_http_client.dart@ba12f28f9848
"""HTTP client for camera communication with certificate pinning and exact header case."""

import asyncio
import hashlib
import ssl
from dataclasses import dataclass

import httpx

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.events import (
    CameraEventBus,
    CameraIdMismatchEvent,
    CameraUnreachableEvent,
)
from vizenlink_nvr.camera.result import Failure, FailureKind, Timeout

CAMERA_ID_HEADER = "X-VizenLink-Camera-Id"
CAMERA_ID_MISMATCH_STATUS = 421
SILENT_AFTER = 8.0


def camera_ssl_context(pin_sha256_hex: str | None = None) -> ssl.SSLContext:
    """Create SSLContext accepting self-signed camera certs with optional pin check."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
    except ssl.SSLError:
        pass

    if pin_sha256_hex is not None:
        expected = pin_sha256_hex.lower().replace(":", "")

        class _PinSSLObject(ssl.SSLObject):
            def do_handshake(self) -> None:
                super().do_handshake()
                cert_bin = self.getpeercert(binary_form=True)
                if not cert_bin:
                    raise ssl.SSLCertVerificationError("No peer certificate presented")
                actual = hashlib.sha256(cert_bin).hexdigest()
                if actual != expected:
                    raise ssl.SSLCertVerificationError(f"TLS pin mismatch: expected {expected}, got {actual}")

        class _PinSSLSocket(ssl.SSLSocket):
            def do_handshake(self, block: bool = False) -> None:
                super().do_handshake(block=block)
                cert_bin = self.getpeercert(binary_form=True)
                if not cert_bin:
                    raise ssl.SSLCertVerificationError("No peer certificate presented")
                actual = hashlib.sha256(cert_bin).hexdigest()
                if actual != expected:
                    raise ssl.SSLCertVerificationError(f"TLS pin mismatch: expected {expected}, got {actual}")

        ctx.sslobject_class = _PinSSLObject
        ctx.sslsocket_class = _PinSSLSocket

    return ctx


async def fetch_certificate_sha256(
    host: str,
    port: int,
    timeout: float,
) -> str | Failure | Timeout:
    """Connect to host:port via TLS, retrieve certificate and return its SHA-256 fingerprint."""
    ctx = camera_ssl_context(None)
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ctx),
            timeout=timeout,
        )
        ssl_obj = writer.get_extra_info("ssl_object")
        cert_bin = ssl_obj.getpeercert(binary_form=True)
        writer.close()
        await writer.wait_closed()
        if not cert_bin:
            return Failure(FailureKind.UNREACHABLE, "No peer certificate presented")
        return hashlib.sha256(cert_bin).hexdigest()
    except TimeoutError:
        return Timeout(reason="Timed out fetching certificate")
    except Exception as exc:
        return Failure(FailureKind.UNREACHABLE, str(exc))


@dataclass(frozen=True)
class HttpResponse:
    """Raw HTTP response carrying status, headers, and body."""

    status: int
    headers: list[tuple[str, str]]
    body: bytes


class CameraHttp:
    """Async HTTP transport for camera communication."""

    def __init__(self, events: CameraEventBus, *, silent_after: float = SILENT_AFTER) -> None:
        self.events = events
        self.silent_after = silent_after
        self._clients: dict[tuple[str, int, str | None], httpx.AsyncClient] = {}
        self._semaphores: dict[tuple[str, int], asyncio.Semaphore] = {}

    def _get_semaphore(self, conn: CameraConnection) -> asyncio.Semaphore:
        key = (conn.host, conn.port)
        sem = self._semaphores.get(key)
        if sem is None:
            sem = asyncio.Semaphore(2)
            self._semaphores[key] = sem
        return sem

    def _get_client(self, conn: CameraConnection) -> httpx.AsyncClient:
        key = (conn.host, conn.port, conn.tls_pin_sha256)
        if key not in self._clients:
            ctx = camera_ssl_context(conn.tls_pin_sha256)
            self._clients[key] = httpx.AsyncClient(
                verify=ctx,
                http2=False,
                follow_redirects=False,
                trust_env=False,  # Camera requests go directly to the configured device.
            )
        return self._clients[key]

    async def send(
        self,
        conn: CameraConnection,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: list[tuple[str, str]] | None = None,
        timeout: float,
        max_bytes: int | None = None,
    ) -> HttpResponse | Failure | Timeout:
        """Send HTTP request to camera, preserving header case and handling events."""
        client = self._get_client(conn)
        url = f"{conn.base_url}{path}"

        header_list: list[tuple[str, str]] = list(headers) if headers else []
        has_id_header = any(k.lower() == CAMERA_ID_HEADER.lower() for k, _ in header_list)
        if not has_id_header and conn.serial:
            header_list.append((CAMERA_ID_HEADER, conn.serial))

        async with self._get_semaphore(conn):
            silence_task: asyncio.Task[None] | None = None
            if conn.serial:

                async def _silence_guard() -> None:
                    await asyncio.sleep(self.silent_after)
                    self.events.publish(
                        CameraUnreachableEvent(
                            host=conn.host,
                            port=conn.port,
                            expected_id=conn.serial or "",
                        )
                    )

                silence_task = asyncio.create_task(_silence_guard())

            try:
                req = client.build_request(
                    method,
                    url,
                    headers=header_list,
                    content=body,
                    timeout=timeout,
                )

                async with client.stream(
                    method=req.method,
                    url=req.url,
                    headers=req.headers,
                    content=req.content,
                    timeout=timeout,
                ) as stream_resp:
                    if silence_task is not None:
                        silence_task.cancel()
                    if max_bytes is None:
                        content = await stream_resp.aread()
                    else:
                        chunks = bytearray()
                        async for chunk in stream_resp.aiter_bytes():
                            chunks.extend(chunk)
                            if len(chunks) > max_bytes:
                                return Failure(
                                    FailureKind.BAD_RESPONSE,
                                    "Camera response exceeds the size limit",
                                )
                        content = bytes(chunks)
                    status = stream_resp.status_code

                    if status == CAMERA_ID_MISMATCH_STATUS:
                        if conn.serial:
                            self.events.publish(
                                CameraIdMismatchEvent(
                                    host=conn.host,
                                    port=conn.port,
                                    expected_id=conn.serial,
                                )
                            )
                        return Failure(
                            kind=FailureKind.ID_MISMATCH,
                            reason="HTTP 421: Camera ID mismatch",
                            http_status=CAMERA_ID_MISMATCH_STATUS,
                        )

                    raw_headers = [
                        (
                            k.decode("latin1") if isinstance(k, bytes) else k,
                            v.decode("latin1") if isinstance(v, bytes) else v,
                        )
                        for k, v in stream_resp.headers.raw
                    ]
                    return HttpResponse(status=status, headers=raw_headers, body=content)

            except httpx.TimeoutException as exc:
                return Timeout(reason=str(exc))
            except Exception as exc:
                curr: BaseException | None = exc
                is_tls_changed = False
                while curr is not None:
                    if isinstance(curr, ssl.SSLCertVerificationError) or "TLS pin mismatch" in str(curr):
                        is_tls_changed = True
                        break
                    curr = curr.__cause__ or curr.__context__

                if is_tls_changed:
                    return Failure(
                        kind=FailureKind.TLS_CHANGED,
                        reason="camera certificate changed since it was added",
                    )

                if conn.serial:
                    self.events.publish(
                        CameraUnreachableEvent(
                            host=conn.host,
                            port=conn.port,
                            expected_id=conn.serial,
                        )
                    )
                return Failure(kind=FailureKind.UNREACHABLE, reason=str(exc))
            finally:
                if silence_task is not None and not silence_task.done():
                    silence_task.cancel()

    async def aclose(self) -> None:
        """Close all cached HTTP clients."""
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()
