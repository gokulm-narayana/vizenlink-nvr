# mirrors: mobile_app/packages/camera_api/lib/src/lan/nuraeye/rest_identity_discovery_client.dart@49ec7db1d149
# mirrors: mobile_app/packages/camera_api/lib/src/lan/nuraeye/nuraeye_client.dart@2e06d2ad3a40
"""NuraEye REST client for identity probe, device discovery, session login, and capabilities."""

import asyncio
import hmac
from collections.abc import Callable
from datetime import timedelta
from typing import Any, Literal

from pydantic import SecretStr

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.http import CameraHttp
from vizenlink_nvr.camera.nuraeye.capabilities import Capabilities, parse_capabilities
from vizenlink_nvr.camera.nuraeye.models import LoginInfo
from vizenlink_nvr.camera.nuraeye.rest import (
    RestError,
    RestOk,
    failure_from_rest,
    get_json,
    post_json,
)
from vizenlink_nvr.camera.nuraeye.sessions import NuraeyeSessionCache, Session
from vizenlink_nvr.camera.result import (
    CameraResult,
    Failure,
    FailureKind,
    Success,
    Timeout,
)
from vizenlink_nvr.camera.wsse import compute_digest, make_token
from vizenlink_nvr.timeutil import Clock

DEFAULT_EXPIRES_IN_SEC = 1800
EXPIRY_LEEWAY = timedelta(seconds=15)
CLIENT_LABEL_MAX = 32


class NuraeyeClient:
    """NuraEye REST client for camera identity, sessions, and device operations."""

    def __init__(
        self,
        conn: CameraConnection,
        http: CameraHttp,
        clock: Clock,
        sessions: NuraeyeSessionCache | None = None,
        *,
        sleep: Callable[[float], Any] = asyncio.sleep,
        client_label: str = "VizenLink NVR",
    ) -> None:
        self.conn = conn
        self.http = http
        self.clock = clock
        self.sessions = sessions if sessions is not None else NuraeyeSessionCache(clock)
        self.sleep = sleep
        self.client_label = client_label[:CLIENT_LABEL_MAX]

    async def are_you_nuraeye_device(self, timeout: float = 3.0) -> CameraResult[bool]:
        """Probe /nuraeye/identity to verify if target is a genuine VizenLink/NuraEye camera."""
        token = make_token("are-you-onchip-nuraeye", self.clock)
        payload = {
            "nonce": token.nonce_b64,
            "created": token.created,
            "digest": token.digest,
        }

        res = await post_json(
            self.http,
            self.conn,
            "/nuraeye/identity",
            payload,
            timeout=timeout,
        )

        if isinstance(res, Timeout):
            return res
        if isinstance(res, Failure):
            return res
        if isinstance(res, RestError):
            return Failure(kind=FailureKind.GENERIC, reason=res.error_msg)

        if isinstance(res, RestOk):
            reply = res.output.get("reply")
            if not reply:
                return Failure(kind=FailureKind.GENERIC, reason="missing reply digest in response")

            expected = compute_digest(
                "yes-i-am-onchip-nuraeye",
                nonce_b64=token.nonce_b64,
                created=token.created,
            )
            matches = hmac.compare_digest(str(reply), expected)
            return Success(matches)

        return Failure(kind=FailureKind.GENERIC, reason="Unexpected response format")

    async def are_you_nuraeye_device_with_retry(
        self,
        attempts: int = 3,
        attempt_timeout: float = 8.0,
        retry_delay: float = 1.0,
    ) -> CameraResult[bool]:
        """Retry probe up to 3 times (8s each, 1s apart), stopping at first genuine reply (IDN-03)."""
        last: CameraResult[bool] = Timeout()
        for attempt in range(attempts):
            last = await self.are_you_nuraeye_device(timeout=attempt_timeout)
            if isinstance(last, Success) and last.value is True:
                return last
            if attempt < attempts - 1:
                await self.sleep(retry_delay)
        return last

    async def _do_login(self, timeout: float = 8.0) -> CameraResult[Session]:
        """Perform raw POST /nuraeye/session/login and construct Session."""
        raw_pw = (
            self.conn.password.get_secret_value()
            if isinstance(self.conn.password, SecretStr)
            else str(self.conn.password)
        )
        token = make_token(raw_pw, self.clock)
        payload = {
            "auth_credentials": {
                "username": self.conn.username,
                "password_digest": token.digest,
                "digest": token.digest,
                "nonce": token.nonce_b64,
                "created": token.created,
            },
            "client_label": self.client_label,
        }

        res = await post_json(
            self.http,
            self.conn,
            "/nuraeye/session/login",
            payload,
            timeout=timeout,
        )

        if isinstance(res, (Timeout, Failure)):
            return res
        if isinstance(res, RestError):
            return failure_from_rest(res)
        if isinstance(res, RestOk):
            raw_token = res.output.get("token")
            if not raw_token:
                return Failure(
                    kind=FailureKind.GENERIC,
                    reason="session/login succeeded but returned no token",
                    http_status=res.status,
                )

            expires_in_sec = res.output.get("expires_in_sec")
            if not isinstance(expires_in_sec, int):
                expires_in_sec = DEFAULT_EXPIRES_IN_SEC

            valid_until = self.clock.now() + timedelta(seconds=expires_in_sec)
            role = res.output.get("role")
            pwd_change_req = bool(res.output.get("password_change_required", False))

            session = Session(
                token=str(raw_token),
                expires_in_sec=expires_in_sec,
                valid_until=valid_until,
                username=self.conn.username,
                role=str(role) if role is not None else None,
                password_change_required=pwd_change_req,
            )
            return Success(session)

        return Failure(kind=FailureKind.GENERIC, reason="Unexpected response format")

    async def login(self, timeout: float = 8.0) -> CameraResult[LoginInfo]:
        """Send login request via single_flight and return LoginInfo without token (D-14)."""
        key = NuraeyeSessionCache.session_key(self.conn.host, self.conn.username)
        res = await self.sessions.single_flight(key, lambda: self._do_login(timeout=timeout))
        if isinstance(res, (Failure, Timeout)):
            return res

        session = res.value
        return Success(
            LoginInfo(
                username=session.username,
                role=session.role,
                password_change_required=session.password_change_required,
                expires_in_sec=session.expires_in_sec,
            )
        )

    async def _send_authed(
        self,
        method: Literal["GET", "POST"],
        path: str,
        token: str,
        payload: Any,
        timeout: float,
    ) -> RestOk | RestError | Failure | Timeout:
        """Send authenticated HTTP request with bearer token."""
        if method == "GET":
            return await get_json(self.http, self.conn, path, bearer=token, timeout=timeout)
        return await post_json(
            self.http,
            self.conn,
            path,
            payload,
            bearer=token,
            timeout=timeout,
        )

    async def _authed(
        self,
        method: Literal["GET", "POST"],
        path: str,
        payload: Any = None,
        timeout: float = 8.0,
    ) -> CameraResult[dict[str, Any]]:
        """Dispatch authenticated call with transparent login, caching, and retry on 401."""
        key = NuraeyeSessionCache.session_key(self.conn.host, self.conn.username)
        session = self.sessions.get(key)
        if session is None:
            login_res = await self.sessions.single_flight(
                key,
                lambda: self._do_login(timeout=timeout),
            )
            if isinstance(login_res, (Failure, Timeout)):
                return login_res
            session = login_res.value

        res = await self._send_authed(method, path, session.token, payload, timeout)

        # 401 triggers single retry after clearing token (SES-04, D-09)
        if isinstance(res, RestError) and res.status == 401:
            self.sessions.drop(key, session.token)
            login_res = await self.sessions.single_flight(
                key,
                lambda: self._do_login(timeout=timeout),
            )
            if isinstance(login_res, (Failure, Timeout)):
                return login_res
            session = login_res.value
            res = await self._send_authed(method, path, session.token, payload, timeout)

        if isinstance(res, (Timeout, Failure)):
            return res
        if isinstance(res, RestError):
            return failure_from_rest(res)
        if isinstance(res, RestOk):
            self.sessions.extend(key, session.token)
            return Success(res.output)

        return Failure(kind=FailureKind.GENERIC, reason="Unexpected response format")

    async def get_capabilities(
        self,
        timeout: float = 8.0,
        *,
        strict: bool = False,
    ) -> CameraResult[Capabilities]:
        """Fetch and parse /nuraeye/capabilities under authenticated session."""
        res = await self._authed("GET", "/nuraeye/capabilities", timeout=timeout)
        if isinstance(res, (Failure, Timeout)):
            return res

        parsed = parse_capabilities(res.value, strict=strict)
        if isinstance(parsed, Failure):
            return parsed
        return Success(parsed)
