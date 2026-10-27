# mirrors: mobile_app/packages/camera_api/lib/src/lan/nuraeye/rest_result.dart@5f873ea471c1
# mirrors: mobile_app/packages/camera_api/lib/src/lan/nuraeye/nuraeye_rest_client.dart@c6af6ee3efb7
"""NuraEye REST envelope handling, unwrap, and JSON helpers."""

import json
from dataclasses import dataclass
from typing import Any

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.http import CameraHttp, HttpResponse
from vizenlink_nvr.camera.result import Failure, FailureKind, Timeout


@dataclass(frozen=True)
class RestOk:
    """Successful REST envelope containing output mapping."""

    status: int
    output: dict[str, Any]


@dataclass(frozen=True)
class RestError:
    """Unsuccessful REST envelope carrying camera error code and message."""

    status: int
    error_code: int | None
    error_msg: str
    body: dict[str, Any] | None = None


def unwrap(resp: HttpResponse) -> RestOk | RestError | Failure:
    """Unwrap standard NuraEye REST envelope {error_code, error_msg, output}."""
    try:
        data = json.loads(resp.body.decode("utf-8"))
    except Exception:
        return Failure(
            kind=FailureKind.BAD_RESPONSE,
            reason=f"HTTP {resp.status}: Malformed response body",
            http_status=resp.status,
        )

    if not isinstance(data, dict):
        return Failure(
            kind=FailureKind.BAD_RESPONSE,
            reason=f"HTTP {resp.status}: Malformed response body",
            http_status=resp.status,
        )

    if 200 <= resp.status < 300:
        # If camera returns error_code in a 200 status
        if "error_code" in data and data.get("error_code") not in (0, None):
            return RestError(
                status=resp.status,
                error_code=data.get("error_code"),
                error_msg=str(data.get("error_msg", "")),
                body=data,
            )
        output = data.get("output", data)
        return RestOk(status=resp.status, output=output if isinstance(output, dict) else {})

    # Non-2xx
    err_code = data.get("error_code")
    err_msg = str(data.get("error_msg", f"HTTP {resp.status}"))
    return RestError(
        status=resp.status,
        error_code=err_code,
        error_msg=err_msg,
        body=data,
    )


async def post_json(
    http: CameraHttp,
    conn: CameraConnection,
    path: str,
    payload: Any,
    *,
    bearer: str | None = None,
    timeout: float,
) -> RestOk | RestError | Failure | Timeout:
    """POST JSON payload to NuraEye REST endpoint."""
    headers = [("Content-Type", "application/json")]
    if bearer:
        headers.append(("Authorization", f"Bearer {bearer}"))

    body = json.dumps(payload).encode("utf-8")
    resp = await http.send(conn, "POST", path, body=body, headers=headers, timeout=timeout)
    if isinstance(resp, (Failure, Timeout)):
        return resp
    return unwrap(resp)


async def get_json(
    http: CameraHttp,
    conn: CameraConnection,
    path: str,
    *,
    bearer: str | None = None,
    timeout: float,
) -> RestOk | RestError | Failure | Timeout:
    """GET JSON from NuraEye REST endpoint."""
    headers: list[tuple[str, str]] = []
    if bearer:
        headers.append(("Authorization", f"Bearer {bearer}"))

    resp = await http.send(conn, "GET", path, headers=headers, timeout=timeout)
    if isinstance(resp, (Failure, Timeout)):
        return resp
    return unwrap(resp)
