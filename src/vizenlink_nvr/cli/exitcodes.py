"""CLI exit code enumeration."""

from enum import IntEnum


class ExitCode(IntEnum):
    """Exit codes returned by the NVR CLI."""

    OK = 0
    GENERIC_FAILURE = 1
    USAGE = 2
    UNREACHABLE = 10
    WRONG_CREDENTIALS = 11
    UNSUPPORTED_DEVICE = 12
    NEEDS_NEW_PASSWORD = 13
    BLOCKED = 14
    NO_SERIAL = 15
    STREAMS_UNAVAILABLE = 16
    ALREADY_REGISTERED = 17
    FORBIDDEN = 18
    TLS_CHANGED = 19
    INVALID_INPUT = 20
    CREDENTIALS_UNREADABLE = 21
    NOT_FOUND = 22
    AUTH_FAILED = 23
    MEDIAMTX_CHECK_FAILED = 30
