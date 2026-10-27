from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import SecretStr

from vizenlink_nvr.paths import secrets_dir
from vizenlink_nvr.secrets.keysource import (
    FileKeySource,
    KeyringKeySource,
    KeySource,
    key_id_for,
    resolve_key_source,
)
from vizenlink_nvr.secrets.permissions import InsecureKeyFile
from vizenlink_nvr.services.settings import get_setting, put_setting

if TYPE_CHECKING:
    from vizenlink_nvr.services.runtime import Runtime

CANARY_KEY = "secrets_canary"
AAD_PREFIX = b"vizenlink-nvr/cred/v1|"
CANARY_TEXT = b"vizenlink-nvr canary v1"


class CredentialsUnreadable(Exception):
    """Raised when credentials cannot be decrypted or key source is in an unreadable state."""


@dataclass(frozen=True)
class SealedSecret:
    """Encrypted credential payload with nonce and key metadata."""

    ciphertext: bytes
    nonce: bytes
    key_id: str
    enc_version: int = 1


class Vault:
    """Symmetric AEAD credential vault."""

    def __init__(self, key: bytes, key_id: str, source: str) -> None:
        self.key = key
        self.key_id = key_id
        self.source = source

    def seal(self, serial: str, username: str, password: SecretStr) -> SealedSecret:
        """Encrypt password bound to serial and username as AAD."""
        nonce = os.urandom(12)
        aad = AAD_PREFIX + serial.encode("utf-8") + b"|" + username.encode("utf-8")
        aesgcm = AESGCM(self.key)
        ct = aesgcm.encrypt(nonce, password.get_secret_value().encode("utf-8"), aad)
        return SealedSecret(ciphertext=ct, nonce=nonce, key_id=self.key_id)

    def open(self, serial: str, username: str, sealed: SealedSecret) -> SecretStr:
        """Decrypt password verifying AAD binding to serial and username."""
        aad = AAD_PREFIX + serial.encode("utf-8") + b"|" + username.encode("utf-8")
        aesgcm = AESGCM(self.key)
        try:
            pt = aesgcm.decrypt(sealed.nonce, sealed.ciphertext, aad)
            return SecretStr(pt.decode("utf-8"))
        except InvalidTag as exc:
            raise CredentialsUnreadable("credentials unreadable") from exc


@dataclass(frozen=True)
class CanaryStatus:
    """Health check assessment of the credential vault and canary key source."""

    status: Literal["ok", "mismatch", "missing_key", "insecure_key_file", "unavailable", "not_initialised"]
    key_source: str | None = None
    key_id: str | None = None
    detail: str | None = None


async def check_canary(rt: Runtime) -> CanaryStatus:
    """Check stored canary against key source without modifying existing records."""
    raw_canary = await get_setting(rt, CANARY_KEY)
    if not raw_canary:
        return CanaryStatus(status="not_initialised")

    if isinstance(raw_canary, dict):
        data = raw_canary
    elif isinstance(raw_canary, str):
        try:
            data = json.loads(raw_canary)
        except Exception as exc:
            return CanaryStatus(
                status="mismatch",
                detail=f"corrupt canary JSON: {exc}",
            )
    else:
        return CanaryStatus(status="not_initialised")

    key_source_name = data.get("key_source")
    expected_key_id = data.get("key_id")
    nonce_b64 = data.get("nonce_b64", "")
    ct_b64 = data.get("ct_b64", "")

    # D-29 Rule: Explicit configuration contradicting recorded source reports mismatch
    backend_configured = rt.settings.secrets_backend.lower()
    if backend_configured != "auto" and backend_configured != key_source_name:
        return CanaryStatus(
            status="mismatch",
            key_source=key_source_name,
            key_id=expected_key_id,
            detail="explicit configuration contradicts recorded key source",
        )

    # Load the exact recorded key source with create=False
    ks: KeySource
    if key_source_name == "file":
        ks = FileKeySource(secrets_dir(rt.settings) / "data.key")
    elif key_source_name == "keyring":
        ks = KeyringKeySource()
    else:
        return CanaryStatus(
            status="mismatch",
            key_source=key_source_name,
            key_id=expected_key_id,
            detail=f"unknown recorded key source {key_source_name}",
        )

    try:
        key = await ks.load(create=False)
    except InsecureKeyFile as exc:
        return CanaryStatus(
            status="insecure_key_file",
            key_source=key_source_name,
            key_id=expected_key_id,
            detail=str(exc),
        )
    except Exception as exc:
        return CanaryStatus(
            status="unavailable",
            key_source=key_source_name,
            key_id=expected_key_id,
            detail=str(exc),
        )

    if key is None:
        return CanaryStatus(
            status="missing_key",
            key_source=key_source_name,
            key_id=expected_key_id,
            detail="key material absent",
        )

    actual_key_id = key_id_for(key, key_source_name)
    if actual_key_id != expected_key_id:
        return CanaryStatus(
            status="mismatch",
            key_source=key_source_name,
            key_id=expected_key_id,
            detail="credentials unreadable (key source mismatch)",
        )

    try:
        nonce = base64.b64decode(nonce_b64.encode("ascii"))
        ct = base64.b64decode(ct_b64.encode("ascii"))
        pt = AESGCM(key).decrypt(nonce, ct, AAD_PREFIX + b"canary")
        if pt != CANARY_TEXT:
            return CanaryStatus(
                status="mismatch",
                key_source=key_source_name,
                key_id=expected_key_id,
                detail="credentials unreadable (key source mismatch)",
            )
    except Exception:
        return CanaryStatus(
            status="mismatch",
            key_source=key_source_name,
            key_id=expected_key_id,
            detail="credentials unreadable (key source mismatch)",
        )

    return CanaryStatus(
        status="ok",
        key_source=key_source_name,
        key_id=expected_key_id,
    )


async def initialise_vault(rt: Runtime) -> CanaryStatus:
    """Initialize vault canary on fresh database, or return current status."""
    existing = await get_setting(rt, CANARY_KEY)
    if existing is not None:
        return await check_canary(rt)

    ks = resolve_key_source(rt.settings)
    try:
        key = await ks.load(create=True)
    except InsecureKeyFile as exc:
        return CanaryStatus(status="insecure_key_file", key_source=ks.name, detail=str(exc))
    except Exception as exc:
        return CanaryStatus(status="unavailable", key_source=ks.name, detail=str(exc))

    if key is None:
        return CanaryStatus(status="missing_key", key_source=ks.name)

    key_id = key_id_for(key, ks.name)
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, CANARY_TEXT, AAD_PREFIX + b"canary")
    payload = {
        "key_source": ks.name,
        "key_id": key_id,
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ct_b64": base64.b64encode(ct).decode("ascii"),
    }
    async with rt.sessions() as session:
        await put_setting(session, CANARY_KEY, payload, rt.clock.now())
        await session.commit()

    return CanaryStatus(status="ok", key_source=ks.name, key_id=key_id)


async def open_vault(rt: Runtime) -> Vault:
    """Open operational vault, raising CredentialsUnreadable unless canary check passes."""
    status = await check_canary(rt)
    if status.status != "ok":
        raise CredentialsUnreadable(f"Vault unavailable: {status.status} ({status.detail})")

    source_name = status.key_source or "file"
    ks: KeySource
    if source_name == "file":
        ks = FileKeySource(secrets_dir(rt.settings) / "data.key")
    else:
        ks = KeyringKeySource()

    key = await ks.load(create=False)
    if key is None:
        raise CredentialsUnreadable("Data key missing")

    return Vault(key=key, key_id=status.key_id or "", source=source_name)
