"""Argon2id password hashing and verification service."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Standard OWASP recommended Argon2id parameters:
# time_cost = 3 iterations
# memory_cost = 65536 KiB (64 MiB)
# parallelism = 4 threads
# hash_len = 32 bytes
# salt_len = 16 bytes
_PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id with randomized salt."""
    if not password:
        raise ValueError("Password cannot be empty")
    return _PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Verify a plaintext password against an Argon2id hash.
    
    Returns True if the password matches, False if mismatch or invalid hash.
    Does not leak plaintext or raise on mismatched password.
    """
    if not password_hash or not password:
        return False
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def check_needs_rehash(password_hash: str) -> bool:
    """Check whether a hash needs to be recomputed due to updated parameters."""
    try:
        return _PASSWORD_HASHER.check_needs_rehash(password_hash)
    except Exception:
        return True
