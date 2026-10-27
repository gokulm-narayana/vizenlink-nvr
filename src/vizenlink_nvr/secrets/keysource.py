"""Key source abstractions and implementations for data encryption keys.

Documented usage:
Service installs should use the 'file' key source (D-29).
Both CLI and service must resolve the same data encryption key.
"""

import asyncio
import base64
import hashlib
import logging
import os
from pathlib import Path
from typing import Protocol

import keyring
from keyring.backends import fail, null

from vizenlink_nvr.config import NvrSettings
from vizenlink_nvr.paths import secrets_dir
from vizenlink_nvr.secrets.permissions import (
    InsecureKeyFile,
    assert_private,
    ensure_private_dir,
    ensure_private_file,
)

logger = logging.getLogger(__name__)


def key_id_for(key: bytes, source: str) -> str:
    """Compute deterministic key identifier for source and raw key material."""
    digest = hashlib.sha256(key).hexdigest()[:16]
    return f"{source}:{digest}"


class KeySource(Protocol):
    """Protocol for loading or creating data encryption key material."""

    name: str

    async def load(self, create: bool) -> bytes | None:
        """Load 32-byte data encryption key, creating if absent and create=True."""
        ...


class FileKeySource:
    """File-backed data encryption key source."""

    name = "file"

    def __init__(self, path: Path) -> None:
        self.path = path

    async def load(self, create: bool) -> bytes | None:
        """Load key from filesystem with strict permissions."""
        if not self.path.exists():
            if not create:
                return None
            ensure_private_dir(self.path.parent)
            key = os.urandom(32)
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(key)
            finally:
                ensure_private_file(self.path)
            return key

        assert_private(self.path)
        data = self.path.read_bytes()
        if len(data) != 32:
            raise InsecureKeyFile(f"key file corrupt: expected 32 bytes, got {len(data)}")
        return data


class KeyringKeySource:
    """OS keystore data encryption key source via python keyring."""

    name = "keyring"

    def __init__(
        self,
        service: str = "vizenlink-nvr",
        username: str = "data-key",
        timeout: float = 5.0,
    ) -> None:
        self.service = service
        self.username = username
        self.timeout = timeout

    async def load(self, create: bool) -> bytes | None:
        """Load or generate key from OS keystore within timeout."""

        def _get() -> str | None:
            return keyring.get_password(self.service, self.username)

        raw = await asyncio.wait_for(asyncio.to_thread(_get), timeout=self.timeout)
        if raw is None:
            if not create:
                return None
            key = os.urandom(32)
            b64_val = base64.b64encode(key).decode("ascii")

            def _set() -> None:
                keyring.set_password(self.service, self.username, b64_val)

            await asyncio.wait_for(asyncio.to_thread(_set), timeout=self.timeout)
            return key

        try:
            key_bytes = base64.b64decode(raw.encode("ascii"))
        except Exception as exc:
            raise InsecureKeyFile(f"corrupt keyring key: {exc}") from exc

        if len(key_bytes) != 32:
            raise InsecureKeyFile(f"key file corrupt: expected 32 bytes, got {len(key_bytes)}")
        return key_bytes


class AutoFallbackKeySource:
    """Key source attempting keyring first with fallback to file on error or timeout."""

    name = "keyring"

    def __init__(self, primary: KeyringKeySource, fallback: FileKeySource) -> None:
        self.primary = primary
        self.fallback = fallback

    async def load(self, create: bool) -> bytes | None:
        """Attempt primary keyring load, falling back to file on error or timeout."""
        try:
            key = await self.primary.load(create=create)
            if key is not None:
                return key
        except (keyring.errors.KeyringError, TimeoutError, Exception) as exc:
            logger.debug("Keyring unavailable in auto mode, falling back to file: %s", exc)

        self.name = "file"
        return await self.fallback.load(create=create)


def resolve_key_source(settings: NvrSettings) -> KeySource:
    """Resolve key source for a NEW vault according to configuration."""
    backend = settings.secrets_backend.lower()
    file_path = secrets_dir(settings) / "data.key"

    if backend == "file":
        return FileKeySource(file_path)

    if backend == "keyring":
        return KeyringKeySource()

    if backend == "auto":
        kb = keyring.get_keyring()
        if isinstance(kb, (fail.Keyring, null.Keyring)):
            return FileKeySource(file_path)
        return AutoFallbackKeySource(
            primary=KeyringKeySource(timeout=5.0),
            fallback=FileKeySource(file_path),
        )

    return FileKeySource(file_path)
