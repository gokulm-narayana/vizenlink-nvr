"""Unit tests for camera password validation rules (ONB-04)."""

import pytest
from pydantic import SecretStr

from vizenlink_nvr.services.passwords import (
    PasswordRuleError,
    validate_new_camera_password,
)


@pytest.mark.behavior("ONB-04")
def test_password_length_boundaries() -> None:
    """Accept exactly 8 and 32 characters; reject 7 and 33 characters."""
    # Boundary: exactly 8 characters
    validate_new_camera_password(SecretStr("12345678"))
    validate_new_camera_password("12345678")

    # Boundary: exactly 32 characters
    validate_new_camera_password(SecretStr("a" * 32))
    validate_new_camera_password("a" * 32)

    # 7 characters rejected
    with pytest.raises(PasswordRuleError, match="Use 8 to 32 characters."):
        validate_new_camera_password(SecretStr("1234567"))

    with pytest.raises(PasswordRuleError, match="Use 8 to 32 characters."):
        validate_new_camera_password("1234567")

    # 33 characters rejected
    with pytest.raises(PasswordRuleError, match="Use 8 to 32 characters."):
        validate_new_camera_password(SecretStr("a" * 33))

    with pytest.raises(PasswordRuleError, match="Use 8 to 32 characters."):
        validate_new_camera_password("a" * 33)


@pytest.mark.behavior("ONB-04")
def test_reject_factory_password_in_any_case() -> None:
    """Reject 'password' case-insensitively with exact message."""
    variants = ["password", "PASSWORD", "PassWord", "pAssWORD", "PassWORD"]
    for variant in variants:
        with pytest.raises(PasswordRuleError, match="Choose a password other than the factory password."):
            validate_new_camera_password(SecretStr(variant))
        with pytest.raises(PasswordRuleError, match="Choose a password other than the factory password."):
            validate_new_camera_password(variant)


@pytest.mark.behavior("ONB-04")
def test_valid_passwords_accepted() -> None:
    """Accept valid compliant passwords."""
    valid_passwords = [
        "N3w-Camera-Pass",
        "SecureP@ssw0rd!",
        "correct-horse-battery",
    ]
    for pw in valid_passwords:
        validate_new_camera_password(SecretStr(pw))
        validate_new_camera_password(pw)
