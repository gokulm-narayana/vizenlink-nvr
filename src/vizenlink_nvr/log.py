"""Logging configuration and credential redaction filter."""

import logging
import re
import sys
from typing import Any

# Patterns to scrub credentials from log messages
REDACT_PATTERNS = [
    (re.compile(r"Authorization:\s*\S+(\s+\S+)?", re.IGNORECASE), "Authorization: [REDACTED]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE), "Bearer [REDACTED]"),
    (
        re.compile(r"(password|password_digest)\s*[=:]\s*\S+", re.IGNORECASE),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(r'"(password|password_digest|new_password)"\s*:\s*"[^"]*"', re.IGNORECASE),
        r'"\1": "[REDACTED]"',
    ),
]


def redact_text(text: str) -> str:
    """Apply all redaction rules to input text."""
    for pattern, repl in REDACT_PATTERNS:
        text = pattern.sub(repl, text)
    return text


class RedactingFilter(logging.Filter):
    """Logging filter stripping credentials, tokens, and digests from record messages and arguments."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                new_dict: dict[str, Any] = {}
                for k, v in record.args.items():
                    new_dict[k] = redact_text(v) if isinstance(v, str) else v
                record.args = new_dict
            elif isinstance(record.args, tuple):
                new_tuple: list[Any] = []
                for item in record.args:
                    if isinstance(item, str):
                        new_tuple.append(redact_text(item))
                    elif isinstance(item, dict):
                        new_dict = {}
                        for k, v in item.items():
                            new_dict[k] = redact_text(v) if isinstance(v, str) else v
                        new_tuple.append(new_dict)
                    else:
                        new_tuple.append(item)
                record.args = tuple(new_tuple)

        return True


def configure_logging(level: str = "INFO") -> None:
    """Configure root logger with stderr handler and credential redacting filter."""
    root = logging.getLogger()
    root.setLevel(level.upper())

    # Avoid duplicate handlers
    for h in root.handlers[:]:
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    handler.addFilter(RedactingFilter())
    root.addHandler(handler)
