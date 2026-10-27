# mirrors: mobile_app/packages/camera_api/lib/src/lan/nuraeye/rest_identity_discovery_client.dart@49ec7db1d149
"""NuraEye REST client for identity probe and device discovery."""

import asyncio
import hmac
from collections.abc import Callable
from typing import Any

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.http import CameraHttp
from vizenlink_nvr.camera.nuraeye.rest import RestError, RestOk, post_json
from vizenlink_nvr.camera.result import (
    CameraResult,
    Failure,
    FailureKind,
    Success,
    Timeout,
)
from vizenlink_nvr.camera.wsse import compute_digest, make_token
from vizenlink_nvr.timeutil import Clock


class NuraeyeClient:
    """NuraEye REST client for camera identity and device operations."""

    def __init__(
        self,
        conn: CameraConnection,
        http: CameraHttp,
        clock: Clock,
        *,
        sleep: Callable[[float], Any] = asyncio.sleep,
    ) -> None:
        self.conn = conn
        self.http = http
        self.clock = clock
        self.sleep = sleep

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
