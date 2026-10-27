"""State container for simulated camera device."""

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from vizenlink_nvr.camera.roles import CameraRole
from vizenlink_nvr.camera.wsse import compute_digest
from vizenlink_nvr.timeutil import Clock, SystemClock


@dataclass
class Account:
    """User account on the simulated camera."""

    password: str
    role: CameraRole


@dataclass
class ActiveSession:
    """Active bearer session for REST operations."""

    token: str
    username: str
    role: CameraRole
    last_active: datetime


@dataclass
class CameraState:
    """Complete in-memory state of a simulated camera."""

    serial: str = "VZL-CAM-000001"
    mac: str = "AA:BB:CC:DD:EE:01"
    manufacturer: str = "VizenLink"
    model: str = "VZ-Pro-1"
    firmware: str = "1.0.0"
    hardware_id: str = "HW-001"
    name: str = "Front Door"
    location: str = "Entrance"
    accounts: dict[str, Account] = field(
        default_factory=lambda: {"admin": Account("admin", CameraRole.ADMINISTRATOR)}
    )
    default_password_in_use: bool = True
    first_password_gate: bool = True
    camera_id_check: bool = True
    genuine: bool = True
    session_table_size: int = 10
    lockout_counters: dict[str, int] = field(default_factory=dict)
    lockout_expiry: dict[str, datetime] = field(default_factory=dict)
    login_attempts: dict[str, int] = field(default_factory=dict)
    sessions: dict[str, ActiveSession] = field(default_factory=dict)
    clock: Clock = field(default_factory=SystemClock)

    def record_attempt(self, username: str) -> None:
        """Record every login attempt for auditing."""
        self.login_attempts[username] = self.login_attempts.get(username, 0) + 1

    def record_failure(self, username: str) -> None:
        """Increment failure counter and enforce lockout after 5 failures."""
        cnt = self.lockout_counters.get(username, 0) + 1
        self.lockout_counters[username] = cnt
        if cnt >= 5:
            # 60s lockout
            self.lockout_expiry[username] = self.clock.now() + timedelta(seconds=60)

    def record_success(self, username: str) -> None:
        """Reset failure counter on successful login."""
        self.lockout_counters[username] = 0
        self.lockout_expiry.pop(username, None)

    def blocked_for(self, username: str) -> int | None:
        """Return remaining lockout seconds if currently locked out, else None."""
        if username in self.lockout_expiry:
            diff = (self.lockout_expiry[username] - self.clock.now()).total_seconds()
            if diff > 0:
                return int(diff)
            self.lockout_expiry.pop(username, None)
            self.lockout_counters[username] = 0
        return None

    def set_password(self, username: str, new_password: str) -> None:
        """Update account password, clearing first password gate if admin."""
        if new_password.lower() == "password":
            raise ValueError("password_not_allowed")

        if username in self.accounts:
            self.accounts[username].password = new_password
            if username == "admin":
                self.first_password_gate = False
                self.default_password_in_use = False

    def verify_rest_login(
        self,
        username: str,
        password: str,
    ) -> tuple[Account | None, Literal["none", "blank", "stored", "other"]]:
        """Verify REST login credentials, classifying credential use."""
        self.record_attempt(username)
        if not password:
            cred_use: Literal["none", "blank", "stored", "other"] = "blank"
        elif username in self.accounts and self.accounts[username].password == password:
            cred_use = "stored"
        else:
            cred_use = "other"

        if username not in self.accounts:
            self.record_failure(username)
            return None, cred_use

        acc = self.accounts[username]
        if acc.password != password:
            self.record_failure(username)
            return None, cred_use

        self.record_success(username)
        return acc, cred_use

    def issue_token(self, username: str, role: CameraRole) -> str:
        """Issue fresh bearer session token, maintaining LRU table size."""
        token = secrets.token_hex(16)
        if len(self.sessions) >= self.session_table_size:
            # Evict oldest
            oldest_key = min(self.sessions, key=lambda k: self.sessions[k].last_active)
            self.sessions.pop(oldest_key, None)

        self.sessions[token] = ActiveSession(
            token=token,
            username=username,
            role=role,
            last_active=self.clock.now(),
        )
        return token

    def authenticate_bearer(self, token: str) -> Account | None:
        """Authenticate bearer token and refresh last_active timestamp."""
        session = self.sessions.get(token)
        if not session:
            return None
        # Check idle expiry (e.g. 30 minutes)
        now = self.clock.now()
        if (now - session.last_active).total_seconds() > 1800:
            self.sessions.pop(token, None)
            return None

        session.last_active = now
        return self.accounts.get(session.username)

    def verify_wsse(
        self,
        username: str,
        nonce_b64: str,
        created: str,
        digest: str,
    ) -> tuple[Account | None, Literal["none", "blank", "stored", "other"]]:
        """Verify WS-UsernameToken digest."""
        self.record_attempt(username)
        if username not in self.accounts:
            self.record_failure(username)
            return None, "other"

        acc = self.accounts[username]
        expected_digest = compute_digest(acc.password, nonce_b64=nonce_b64, created=created)
        blank_digest = compute_digest("", nonce_b64=nonce_b64, created=created)

        if digest == blank_digest:
            cred_use: Literal["none", "blank", "stored", "other"] = "blank"
        elif digest == expected_digest:
            cred_use = "stored"
        else:
            cred_use = "other"

        if digest != expected_digest:
            self.record_failure(username)
            return None, cred_use

        self.record_success(username)
        return acc, cred_use

    def check_camera_id(self, headers: list[tuple[bytes, bytes]]) -> bool:
        """Verify X-VizenLink-Camera-Id header if present and enforced."""
        if not self.camera_id_check:
            return True

        for k, v in headers:
            if k.lower() == b"x-vizenlink-camera-id":
                val = v.decode("latin1").strip()
                if val and val != self.serial:
                    return False
        return True
