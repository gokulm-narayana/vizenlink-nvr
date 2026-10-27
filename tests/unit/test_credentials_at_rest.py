"""Unit tests for credential sealing, AAD binding, at-rest database confidentiality, and key sources."""

import base64
import os
import sys
import time
from pathlib import Path

import keyring
import keyring.errors
import pytest
from keyring.backend import KeyringBackend
from pydantic import SecretStr
from sqlalchemy import text

from vizenlink_nvr.config import NvrSettings, load_settings
from vizenlink_nvr.paths import secrets_dir
from vizenlink_nvr.secrets.keysource import (
    KeyringKeySource,
    resolve_key_source,
)
from vizenlink_nvr.secrets.permissions import ensure_private_file
from vizenlink_nvr.secrets.vault import (
    CredentialsUnreadable,
    Vault,
    check_canary,
    open_vault,
)
from vizenlink_nvr.services.runtime import open_runtime


class InMemoryKeyring(KeyringBackend):
    """In-memory keyring backend for isolated testing."""

    priority = 1

    def __init__(self) -> None:
        self.storage: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.storage.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.storage[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.storage.pop((service, username), None)


class FailingKeyring(KeyringBackend):
    """Keyring backend raising KeyringError on access."""

    priority = 1

    def get_password(self, service: str, username: str) -> str | None:
        raise keyring.errors.KeyringError("OS keystore unavailable")

    def set_password(self, service: str, username: str, password: str) -> None:
        raise keyring.errors.KeyringError("OS keystore unavailable")

    def delete_password(self, service: str, username: str) -> None:
        raise keyring.errors.KeyringError("OS keystore unavailable")


class SlowKeyring(KeyringBackend):
    """Keyring backend that sleeps to simulate timeout."""

    priority = 1

    def get_password(self, service: str, username: str) -> str | None:
        time.sleep(0.5)
        return None

    def set_password(self, service: str, username: str, password: str) -> None:
        time.sleep(0.5)

    def delete_password(self, service: str, username: str) -> None:
        pass


def test_vault_roundtrip_and_aad_binding() -> None:
    """Verify seal/open roundtrip, different nonces, and AAD binding."""
    key = os.urandom(32)
    vault = Vault(key=key, key_id="file:1234", source="file")

    pwd = SecretStr("CorrectHorseBatteryStaple")
    sealed1 = vault.seal(serial="VZL-1", username="admin", password=pwd)
    sealed2 = vault.seal(serial="VZL-1", username="admin", password=pwd)

    # Distinct nonces and ciphertexts
    assert sealed1.nonce != sealed2.nonce
    assert sealed1.ciphertext != sealed2.ciphertext

    # Valid roundtrip
    opened = vault.open(serial="VZL-1", username="admin", sealed=sealed1)
    assert opened.get_secret_value() == "CorrectHorseBatteryStaple"

    # AAD tampering: wrong serial
    with pytest.raises(CredentialsUnreadable):
        vault.open(serial="VZL-WRONG", username="admin", sealed=sealed1)

    # AAD tampering: wrong username
    with pytest.raises(CredentialsUnreadable):
        vault.open(serial="VZL-1", username="operator", sealed=sealed1)


def test_vault_edge_passwords() -> None:
    """Empty string and 32-character passwords roundtrip cleanly."""
    key = os.urandom(32)
    vault = Vault(key=key, key_id="file:1234", source="file")

    # Empty string
    sealed_empty = vault.seal("VZL-1", "user", SecretStr(""))
    assert vault.open("VZL-1", "user", sealed_empty).get_secret_value() == ""

    # 32 characters
    long_pass = "A" * 32
    sealed_long = vault.seal("VZL-1", "user", SecretStr(long_pass))
    assert vault.open("VZL-1", "user", sealed_long).get_secret_value() == long_pass


async def test_credentials_never_plain_in_sqlite(data_dir: Path) -> None:
    """Raw bytes of nvr.db, nvr.db-wal, and nvr.db-shm never contain plaintext passwords."""
    settings = load_settings(data_dir)
    sentinel = "Sentinel-Pa55word!"

    async with open_runtime(settings) as rt:
        vault = await open_vault(rt)
        sealed = vault.seal(serial="VZL-TEST", username="admin", password=SecretStr(sentinel))

        # Store encrypted ciphertext and metadata into SQLite
        async with rt.sessions() as session:
            await session.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS test_creds "
                    "(id INTEGER PRIMARY KEY, ct BLOB, nonce BLOB, key_id TEXT)"
                )
            )
            await session.execute(
                text("INSERT INTO test_creds (ct, nonce, key_id) VALUES (:ct, :nonce, :key_id)"),
                {"ct": sealed.ciphertext, "nonce": sealed.nonce, "key_id": sealed.key_id},
            )
            await session.commit()

    # Inspect all database files
    sentinel_bytes = sentinel.encode("utf-8")
    for fname in ["nvr.db", "nvr.db-wal", "nvr.db-shm"]:
        p = data_dir / fname
        if p.exists():
            content = p.read_bytes()
            assert sentinel_bytes not in content, f"Plaintext credential found in {fname}!"


async def test_insecure_key_file_permissions(data_dir: Path) -> None:
    """chmod 0o644 on key file raises InsecureKeyFile on POSIX."""
    if os.name != "posix":
        pytest.skip("POSIX permissions test only")

    settings = load_settings(data_dir)
    async with open_runtime(settings) as rt:
        key_file = secrets_dir(settings) / "data.key"
        assert key_file.exists()

        # Insecure permissions
        os.chmod(key_file, 0o644)
        status = await check_canary(rt)
        assert status.status == "insecure_key_file"

        # Restore
        os.chmod(key_file, 0o600)
        status2 = await check_canary(rt)
        assert status2.status == "ok"


async def test_keyring_source_lifecycle(monkeypatch) -> None:
    """NVR_SECRETS_BACKEND=keyring stores base64 key under vizenlink-nvr / data-key."""
    mem_keyring = InMemoryKeyring()
    orig = keyring.get_keyring()
    keyring.set_keyring(mem_keyring)
    try:
        ks = KeyringKeySource()
        key = await ks.load(create=True)
        assert key is not None
        assert len(key) == 32

        stored = mem_keyring.get_password("vizenlink-nvr", "data-key")
        assert stored is not None
        assert base64.b64decode(stored) == key
    finally:
        keyring.set_keyring(orig)


async def test_auto_fallback_to_file(data_dir: Path, monkeypatch) -> None:
    """Auto mode falls back to FileKeySource on FailingKeyring."""
    orig = keyring.get_keyring()
    keyring.set_keyring(FailingKeyring())
    try:
        settings = NvrSettings(data_dir=data_dir, secrets_backend="auto")
        ks = resolve_key_source(settings)
        key = await ks.load(create=True)
        assert key is not None
        assert len(key) == 32
        assert ks.name == "file"
        assert (secrets_dir(settings) / "data.key").exists()
    finally:
        keyring.set_keyring(orig)


async def test_keyring_timeout_fallback(data_dir: Path) -> None:
    """Keyring call exceeding timeout falls back to file in auto, reports unavailable in explicit."""
    orig = keyring.get_keyring()
    keyring.set_keyring(SlowKeyring())
    try:
        # In auto mode with 0.1s timeout -> falls back in under 1 second
        t0 = time.monotonic()
        auto_ks = resolve_key_source(NvrSettings(data_dir=data_dir, secrets_backend="auto"))
        # Force low timeout
        if hasattr(auto_ks, "primary"):
            auto_ks.primary.timeout = 0.1
        key = await auto_ks.load(create=True)
        assert key is not None
        assert auto_ks.name == "file"
        assert time.monotonic() - t0 < 2.0

        # In explicit keyring mode -> unavailable
        explicit_ks = KeyringKeySource(timeout=0.1)
        with pytest.raises((TimeoutError, Exception)):
            await explicit_ks.load(create=False)
    finally:
        keyring.set_keyring(orig)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows ACL test")
def test_windows_private_file_acl(tmp_path: Path) -> None:
    """On Windows, ensure_private_file restricts ACL to current user."""
    test_file = tmp_path / "data.key"
    test_file.write_bytes(os.urandom(32))
    ensure_private_file(test_file)

    import getpass
    import subprocess

    res = subprocess.run(  # noqa: S603
        ["icacls", str(test_file)],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    )
    user = getpass.getuser()
    assert user in res.stdout
