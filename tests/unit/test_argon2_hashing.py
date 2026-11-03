"""Unit tests for Argon2id password hashing and verification."""

import pytest

from vizenlink_nvr.services.auth_hasher import (
    check_needs_rehash,
    hash_password,
    verify_password,
)


def test_hash_password_format_and_salt() -> None:
    """Verify Argon2id hash format and randomized per-call salt."""
    pw = "superSecretPassword123!"
    h1 = hash_password(pw)
    h2 = hash_password(pw)

    assert h1.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert h2.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    # Different salts must yield different hash strings
    assert h1 != h2


def test_verify_password_success_and_failure() -> None:
    """Verify correct password matches and wrong password fails."""
    pw = "CorrectHorseBatteryStaple"
    h = hash_password(pw)

    assert verify_password(h, pw) is True
    assert verify_password(h, "WrongPassword") is False
    assert verify_password(h, pw.lower()) is False
    assert verify_password(h, pw + " ") is False


def test_verify_password_tampered_or_invalid() -> None:
    """Verify that tampered or malformed hash strings return False safely without raising."""
    assert verify_password("not-a-valid-hash", "password") is False
    assert verify_password("", "password") is False
    assert verify_password("$argon2id$v=19$m=65536,t=3,p=4$fake$fake", "password") is False
    assert verify_password("$argon2id$v=19$m=65536,t=3,p=4$1234$5678", "") is False


def test_hash_password_empty_rejected() -> None:
    """Empty passwords must be rejected with ValueError."""
    with pytest.raises(ValueError, match="Password cannot be empty"):
        hash_password("")


def test_check_needs_rehash() -> None:
    """A fresh hash produced with current parameters does not need rehash."""
    h = hash_password("validPassword456")
    assert check_needs_rehash(h) is False
    assert check_needs_rehash("invalid-hash") is True
