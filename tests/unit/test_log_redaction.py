"""Unit tests for log redaction filter stripping secrets from formatted messages and args."""

import logging

from vizenlink_nvr.log import RedactingFilter, configure_logging, redact_text


def test_redact_text_patterns() -> None:
    """Verify regex patterns correctly scrub tokens, passwords, and authorization headers."""
    # Authorization header
    raw_auth = "Header: Authorization: Bearer secret-token-1234"
    assert redact_text(raw_auth) == "Header: Authorization: [REDACTED]"
    assert redact_text("Authorization: Basic dXNlcjpwYXNz") == "Authorization: [REDACTED]"

    # Standalone Bearer
    assert redact_text("Token was Bearer eyJhbGciOiJIUzI1NiJ9.abc") == "Token was Bearer [REDACTED]"

    # Key-value password
    assert redact_text("Connecting with password=hunter2 now") == "Connecting with password=[REDACTED] now"
    raw_digest = "Computed password_digest=F3ldVt6HHuN3/vvi4vYtwEH8+w8="
    assert redact_text(raw_digest) == "Computed password_digest=[REDACTED]"

    # JSON password
    assert redact_text('payload: {"password": "secret_password"}') == 'payload: {"password": "[REDACTED]"}'
    assert redact_text('{"new_password": "new_secret_123"}') == '{"new_password": "[REDACTED]"}'
    assert redact_text('{"password_digest": "abc12345"}') == '{"password_digest": "[REDACTED]"}'


def test_redacting_filter_on_log_records() -> None:
    """Verify RedactingFilter cleans record.msg and record.args."""
    flt = RedactingFilter()

    # Formatted record
    rec1 = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Login with password=hunter2 failed",
        args=(),
        exc_info=None,
    )
    flt.filter(rec1)
    assert rec1.msg == "Login with password=[REDACTED] failed"

    # Positional args record
    rec2 = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="User %s supplied token %s",
        args=("admin", "Bearer eyJhbGciOiJIUzI1NiJ9.abc"),
        exc_info=None,
    )
    flt.filter(rec2)
    assert rec2.args == ("admin", "Bearer [REDACTED]")

    # Dict args record
    rec3 = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Details %(info)s",
        args=({"info": "password=secret"},),
        exc_info=None,
    )
    flt.filter(rec3)
    assert rec3.args == {"info": "password=[REDACTED]"}


def test_configure_logging_integration(capsys) -> None:
    """Verify configured root logger redacts output to stderr."""
    configure_logging("DEBUG")
    logger = logging.getLogger("test_integration")
    logger.info("Attempting login with password=hunter2")

    captured = capsys.readouterr()
    assert "hunter2" not in captured.err
    assert "password=[REDACTED]" in captured.err
