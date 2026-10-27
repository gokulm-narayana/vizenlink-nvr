"""Contract tests for typed camera results and failure categories."""

from dataclasses import FrozenInstanceError
from datetime import timedelta

import pytest
from fake_camera.faults import Delay, Drop
from fake_camera.server import FakeCamera

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.events import CameraEventBus
from vizenlink_nvr.camera.http import CameraHttp, HttpResponse
from vizenlink_nvr.camera.nuraeye.rest import RestError, RestOk, unwrap
from vizenlink_nvr.camera.result import (
    CameraResult,
    Failure,
    FailureKind,
    Success,
    Timeout,
    parse_retry_after,
)


@pytest.mark.behavior("RES-01")
def test_frozen_result_types() -> None:
    """Verify Success, Failure, and Timeout are frozen immutable types."""
    succ = Success(value=42)
    assert succ.value == 42
    with pytest.raises(FrozenInstanceError):
        succ.value = 100  # type: ignore[misc]

    fail = Failure(kind=FailureKind.UNAUTHORIZED, reason="Bad password", http_status=401)
    assert fail.kind == FailureKind.UNAUTHORIZED
    assert fail.http_status == 401
    with pytest.raises(FrozenInstanceError):
        fail.reason = "other"  # type: ignore[misc]

    tout = Timeout()
    assert tout.reason == "timeout"
    with pytest.raises(FrozenInstanceError):
        tout.reason = "other"  # type: ignore[misc]


@pytest.mark.behavior("RES-02")
def test_failure_reuse_preserves_metadata() -> None:
    """A Failure re-used as another call's result keeps kind, retry_after and http_status."""
    original = Failure(
        kind=FailureKind.BLOCKED,
        reason="Account locked",
        http_status=429,
        retry_after=timedelta(seconds=15),
        fault_subcode="Lockout",
    )

    def relay_result(res: CameraResult[str]) -> CameraResult[str]:
        if isinstance(res, Failure):
            return res
        return Success("ok")

    relayed = relay_result(original)
    assert isinstance(relayed, Failure)
    assert relayed.kind == FailureKind.BLOCKED
    assert relayed.http_status == 429
    assert relayed.retry_after == timedelta(seconds=15)
    assert relayed.fault_subcode == "Lockout"


@pytest.mark.behavior("RES-06")
async def test_delay_and_drop_fault_mapping(
    fake_camera: pytest.FixtureRequest,
) -> None:
    """Delay beyond timeout returns Timeout instance, never Failure; Drop() returns Failure(UNREACHABLE)."""
    cam: FakeCamera = await fake_camera(serial="VZL-1")
    conn = CameraConnection(host=cam.host, port=cam.port, serial="VZL-1", tls_pin_sha256=cam.cert_sha256)
    bus = CameraEventBus()
    http = CameraHttp(bus)
    try:
        # Delay beyond timeout -> Timeout
        cam.faults.add("GET /timeout", Delay(1.0))
        res_timeout = await http.send(conn, "GET", "/timeout", timeout=0.1)
        assert isinstance(res_timeout, Timeout)
        assert not isinstance(res_timeout, Failure)

        # Drop -> Failure(UNREACHABLE)
        cam.faults.add("GET /drop", Drop())
        res_drop = await http.send(conn, "GET", "/drop", timeout=1.0)
        assert isinstance(res_drop, Failure)
        assert res_drop.kind == FailureKind.UNREACHABLE
    finally:
        await http.aclose()


@pytest.mark.behavior("RES-07")
def test_unwrap_rest_envelopes() -> None:
    """Malformed body -> Failure(BAD_RESPONSE); list output -> dict; 421 -> RestError."""
    # Malformed body -> Failure(BAD_RESPONSE, "HTTP 200: Malformed response body")
    malformed_resp = HttpResponse(status=200, headers=[], body=b"not json")
    unwrapped = unwrap(malformed_resp)
    assert isinstance(unwrapped, Failure)
    assert unwrapped.kind == FailureKind.BAD_RESPONSE
    assert unwrapped.reason == "HTTP 200: Malformed response body"

    # 2xx with output list -> RestOk(output={})
    list_output_resp = HttpResponse(
        status=200,
        headers=[],
        body=b'{"error_code": 0, "error_msg": "OK", "output": [1, 2, 3]}',
    )
    unwrapped2 = unwrap(list_output_resp)
    assert isinstance(unwrapped2, RestOk)
    assert unwrapped2.output == {}

    # 421 body without output -> RestError
    err_421_resp = HttpResponse(
        status=421,
        headers=[],
        body=b'{"error_code": 421, "error_msg": "Camera ID mismatch"}',
    )
    unwrapped3 = unwrap(err_421_resp)
    assert isinstance(unwrapped3, RestError)
    assert unwrapped3.status == 421
    assert unwrapped3.error_code == 421
    assert unwrapped3.error_msg == "Camera ID mismatch"


def test_pattern_matching_and_unions() -> None:
    """Verify pattern matching discriminates between CameraResult subtypes."""

    def describe(res: CameraResult[str]) -> str:
        match res:
            case Success(value=v):
                return f"OK: {v}"
            case Failure(kind=FailureKind.FORBIDDEN):
                return "FORBIDDEN"
            case Failure(reason=r):
                return f"FAIL: {r}"
            case Timeout():
                return "TIMEOUT"

    assert describe(Success("stream")) == "OK: stream"
    assert describe(Failure(kind=FailureKind.FORBIDDEN, reason="Deny")) == "FORBIDDEN"
    assert describe(Failure(kind=FailureKind.UNREACHABLE, reason="No route")) == "FAIL: No route"
    assert describe(Timeout()) == "TIMEOUT"


def test_failure_kinds_enum() -> None:
    """Verify all required FailureKind members are present."""
    expected = {
        "generic",
        "unauthorized",
        "forbidden",
        "blocked",
        "password_change_required",
        "credentials_missing",
        "id_mismatch",
        "unreachable",
        "bad_response",
        "tls_changed",
    }
    actual = {k.value for k in FailureKind}
    assert expected == actual


def test_parse_retry_after() -> None:
    """Verify lockout delay parsing from body mapping and message strings."""
    assert parse_retry_after({"retry_after_seconds": 60}, "") == timedelta(seconds=60)
    assert parse_retry_after({"retry_after_seconds": "45"}, "") == timedelta(seconds=45)
    assert parse_retry_after(None, "Account locked; retry in 30 s") == timedelta(seconds=30)
    assert parse_retry_after({}, "Too many attempts, please retry in 120s") == timedelta(seconds=120)
    assert parse_retry_after(None, "Generic error") is None
    assert parse_retry_after({}, "") is None
