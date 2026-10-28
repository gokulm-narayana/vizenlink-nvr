"""Password validation rules and constants for camera credentials."""

from pydantic import SecretStr

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 32
FACTORY_PASSWORD_LOWER = "password"  # noqa: S105


class PasswordRuleError(ValueError):
    """Raised when a candidate camera password violates length or content rules."""


def validate_new_camera_password(pw: SecretStr | str) -> None:
    """Validate that a new camera password meets length and content requirements.

    Raises PasswordRuleError with exact user-facing messages on rule violations.
    """
    raw = pw.get_secret_value() if isinstance(pw, SecretStr) else str(pw)
    if len(raw) < MIN_PASSWORD_LENGTH or len(raw) > MAX_PASSWORD_LENGTH:
        raise PasswordRuleError("Use 8 to 32 characters.")
    if raw.lower() == FACTORY_PASSWORD_LOWER:
        raise PasswordRuleError("Choose a password other than the factory password.")
