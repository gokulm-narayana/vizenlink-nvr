"""Secrets and credential encryption package."""

from vizenlink_nvr.secrets.keysource import (
    FileKeySource,
    KeyringKeySource,
    KeySource,
    key_id_for,
    resolve_key_source,
)
from vizenlink_nvr.secrets.permissions import (
    InsecureKeyFile,
    assert_private,
    ensure_private_dir,
    ensure_private_file,
)
from vizenlink_nvr.secrets.vault import (
    CanaryStatus,
    CredentialsUnreadable,
    SealedSecret,
    Vault,
    check_canary,
    initialise_vault,
    open_vault,
)

__all__ = [
    "CanaryStatus",
    "CredentialsUnreadable",
    "FileKeySource",
    "InsecureKeyFile",
    "KeySource",
    "KeyringKeySource",
    "SealedSecret",
    "Vault",
    "assert_private",
    "check_canary",
    "ensure_private_dir",
    "ensure_private_file",
    "initialise_vault",
    "key_id_for",
    "open_vault",
    "resolve_key_source",
]
