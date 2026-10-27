"""Contract tests for typed camera results and failure categories."""

from dataclasses import FrozenInstanceError
from datetime import timedelta

import pytest

from vizenlink_nvr.camera.result import (
    CameraResult,
    Failure,
    FailureKind,
    Success,
    Timeout,
    parse_retry_after,
)


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
    # From body
    assert parse_retry_after({"retry_after_seconds": 60}, "") == timedelta(seconds=60)
    assert parse_retry_after({"retry_after_seconds": "45"}, "") == timedelta(seconds=45)

    # From error string
    assert parse_retry_after(None, "Account locked; retry in 30 s") == timedelta(seconds=30)
    assert parse_retry_after({}, "Too many attempts, please retry in 120s") == timedelta(seconds=120)

    # Missing
    assert parse_retry_after(None, "Generic error") is None
    assert parse_retry_after({}, "") is None
