"""Sliding window brute-force lockout rate limiter."""

from __future__ import annotations

import threading
import time


class RateLimiter:
    """In-memory sliding window rate limiter for brute-force protection.
    
    Tracks failed attempts per identifier (username or IP).
    If max_attempts are reached within window_seconds, the identifier is locked out
    for lockout_seconds.
    """

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: float = 900.0,
        lockout_seconds: float = 900.0,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self._lock = threading.Lock()
        # identifier -> list of failure timestamps (monotonic float)
        self._failures: dict[str, list[float]] = {}
        # identifier -> lockout expiry timestamp (monotonic float)
        self._lockouts: dict[str, float] = {}

    def is_locked(self, identifier: str) -> bool:
        """Check if identifier is currently locked out."""
        with self._lock:
            now = time.monotonic()
            lockout_until = self._lockouts.get(identifier)
            if lockout_until is not None:
                if now < lockout_until:
                    return True
                # Lockout expired
                del self._lockouts[identifier]
                self._failures.pop(identifier, None)
            return False

    def remaining_lockout_seconds(self, identifier: str) -> int:
        """Return remaining lockout duration in integer seconds, or 0 if not locked."""
        with self._lock:
            now = time.monotonic()
            lockout_until = self._lockouts.get(identifier)
            if lockout_until is not None:
                remaining = int(lockout_until - now)
                return max(0, remaining)
            return 0

    def record_failure(self, identifier: str) -> bool:
        """Record a failed attempt. Returns True if this failure triggered a lockout."""
        with self._lock:
            now = time.monotonic()
            # If already locked, keep existing lockout
            if self._lockouts.get(identifier, 0) > now:
                return True

            attempts = self._failures.get(identifier, [])
            # Prune attempts outside sliding window
            cutoff = now - self.window_seconds
            attempts = [t for t in attempts if t > cutoff]
            attempts.append(now)
            self._failures[identifier] = attempts

            if len(attempts) >= self.max_attempts:
                self._lockouts[identifier] = now + self.lockout_seconds
                return True
            return False

    def reset(self, identifier: str) -> None:
        """Clear failed attempts and lockouts for identifier upon successful login."""
        with self._lock:
            self._failures.pop(identifier, None)
            self._lockouts.pop(identifier, None)


# Global default rate limiter instance for auth endpoints
login_rate_limiter = RateLimiter(
    max_attempts=5,
    window_seconds=900.0,
    lockout_seconds=900.0,
)
