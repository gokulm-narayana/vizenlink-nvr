"""Unit tests for sliding window rate limiter."""

import time

from vizenlink_nvr.services.rate_limiter import RateLimiter


def test_rate_limiter_lockout_trigger() -> None:
    """Verify that reaching max_attempts triggers a lockout."""
    limiter = RateLimiter(max_attempts=5, window_seconds=60.0, lockout_seconds=60.0)
    user_id = "test_user_1"

    assert not limiter.is_locked(user_id)
    assert limiter.remaining_lockout_seconds(user_id) == 0

    # 4 failures: not locked
    for _ in range(4):
        locked = limiter.record_failure(user_id)
        assert not locked
        assert not limiter.is_locked(user_id)

    # 5th failure: locked
    locked = limiter.record_failure(user_id)
    assert locked
    assert limiter.is_locked(user_id)
    assert limiter.remaining_lockout_seconds(user_id) > 0


def test_rate_limiter_reset_on_success() -> None:
    """Verify that successful login resets failures and lockouts."""
    limiter = RateLimiter(max_attempts=3, window_seconds=60.0, lockout_seconds=60.0)
    user_id = "test_user_2"

    limiter.record_failure(user_id)
    limiter.record_failure(user_id)
    assert not limiter.is_locked(user_id)

    # Reset
    limiter.reset(user_id)

    # Now needs 3 more failures to lock
    limiter.record_failure(user_id)
    limiter.record_failure(user_id)
    assert not limiter.is_locked(user_id)
    limiter.record_failure(user_id)
    assert limiter.is_locked(user_id)

    # Reset while locked
    limiter.reset(user_id)
    assert not limiter.is_locked(user_id)


def test_rate_limiter_window_and_lockout_expiry() -> None:
    """Verify that failed attempts expire outside the window and lockouts expire."""
    # Fast window and lockout for testing
    limiter = RateLimiter(max_attempts=2, window_seconds=0.1, lockout_seconds=0.15)
    user_id = "test_user_3"

    # Attempt 1
    limiter.record_failure(user_id)
    # Wait for window to expire
    time.sleep(0.12)
    # Attempt 2 (attempt 1 should have expired)
    locked = limiter.record_failure(user_id)
    assert not locked
    assert not limiter.is_locked(user_id)

    # Fast 2nd failure inside window -> locks
    locked = limiter.record_failure(user_id)
    assert locked
    assert limiter.is_locked(user_id)

    # Wait for lockout to expire
    time.sleep(0.18)
    assert not limiter.is_locked(user_id)
