"""Contract tests for WS-Security UsernameToken digest generation and nonces."""

from datetime import datetime

import pytest

from vizenlink_nvr.camera.wsse import (
    compute_digest,
    created_from,
    make_token,
    new_nonce_b64,
)
from vizenlink_nvr.timeutil import UTC, FakeClock


@pytest.mark.behavior("WSSE-01")
def test_wsse_known_test_vector() -> None:
    """Verify exact WSSE digest matching known answer vector from camera_api."""
    nonce = "AAAAAAAAAAAAAAAAAAAAAA=="
    created = "2026-01-01T00:00:00.000Z"
    password = "test-password"

    digest = compute_digest(password, nonce_b64=nonce, created=created)
    assert digest == "F3ldVt6HHuN3/vvi4vYtwEH8+w8="


@pytest.mark.behavior("WSSE-02")
def test_wsse_created_format_and_nonce_uniqueness() -> None:
    """Verify created_from always ends in .000Z and nonces are unique."""
    ts1 = datetime(2026, 10, 27, 15, 30, 45, tzinfo=UTC)
    assert created_from(ts1) == "2026-10-27T15:30:45.000Z"

    # Even with microsecond input, wire format forces .000Z per camera_api
    ts2 = datetime(2026, 10, 27, 15, 30, 45, 999999, tzinfo=UTC)
    assert created_from(ts2) == "2026-10-27T15:30:45.000Z"

    clock = FakeClock(ts1)
    t1 = make_token("pwd", clock)
    t2 = make_token("pwd", clock)
    assert t1.created.endswith(".000Z")
    assert t2.created.endswith(".000Z")
    assert t1.nonce_b64 != t2.nonce_b64


def test_wsse_make_token_injected_clock() -> None:
    """Verify make_token binds time from the provided Clock."""
    fixed_time = datetime(2026, 7, 4, 12, 0, 0, tzinfo=UTC)
    clock = FakeClock(fixed_time)

    token = make_token("my-secret", clock)
    assert token.created == "2026-07-04T12:00:00.000Z"
    assert len(token.nonce_b64) > 0
    assert len(token.digest) > 0

    recomputed = compute_digest("my-secret", nonce_b64=token.nonce_b64, created=token.created)
    assert token.digest == recomputed


def test_wsse_nonces_random_and_distinct() -> None:
    """Verify generated nonces are unique and base64 encoded 16 bytes."""
    nonces = {new_nonce_b64() for _ in range(100)}
    assert len(nonces) == 100
