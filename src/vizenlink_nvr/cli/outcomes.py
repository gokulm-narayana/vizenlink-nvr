"""CLI presentation and exit mapping for onboarding outcomes."""

from typing import TYPE_CHECKING

from vizenlink_nvr.cli.exitcodes import ExitCode

if TYPE_CHECKING:
    from vizenlink_nvr.services.onboarding import AddOutcome


def blocked_message(retry_after_seconds: int | None) -> str:
    """Format user-facing lockout message."""
    if retry_after_seconds is None:
        return "This camera is locked after too many failed sign-ins. Try again in a few minutes."
    if retry_after_seconds <= 60:
        return "This camera is locked after too many failed sign-ins. Try again in about a minute."
    mins = (retry_after_seconds + 59) // 60
    return f"This camera is locked after too many failed sign-ins. Try again in about {mins} minutes."


def present(outcome: "AddOutcome") -> tuple[ExitCode, str]:
    """Map AddOutcome to CLI ExitCode and human-readable message."""
    from vizenlink_nvr.services.onboarding import AddOutcomeKind

    kind = outcome.kind

    if kind == AddOutcomeKind.OK:
        return ExitCode.OK, f"Added camera {outcome.serial}."

    if kind == AddOutcomeKind.ADDRESS_UPDATED:
        addr = ""
        if outcome.camera is not None:
            addr = f"{outcome.camera.host}:{outcome.camera.https_port}"
        msg = (
            f"Camera {outcome.serial} is already registered; address updated to {addr}."
            if addr
            else f"Camera {outcome.serial} is already registered; address updated."
        )
        return ExitCode.OK, msg

    if kind == AddOutcomeKind.ALREADY_REGISTERED:
        return ExitCode.ALREADY_REGISTERED, f"Camera {outcome.serial} is already registered."

    if kind == AddOutcomeKind.UNREACHABLE:
        return ExitCode.UNREACHABLE, "Could not reach the camera — check the connection and try again."

    if kind == AddOutcomeKind.WRONG_CREDENTIALS:
        return ExitCode.WRONG_CREDENTIALS, "Incorrect username or password."

    if kind == AddOutcomeKind.UNSUPPORTED_DEVICE:
        return (
            ExitCode.UNSUPPORTED_DEVICE,
            "This device is not a VizenLink camera, or its firmware is not supported.",
        )

    if kind == AddOutcomeKind.NEEDS_NEW_PASSWORD:
        return (
            ExitCode.NEEDS_NEW_PASSWORD,
            "Camera requires a new password before it can be added.",
        )

    if kind == AddOutcomeKind.BLOCKED:
        return ExitCode.BLOCKED, blocked_message(outcome.retry_after_seconds)

    if kind == AddOutcomeKind.NO_SERIAL:
        return (
            ExitCode.NO_SERIAL,
            "This camera did not report a serial number and cannot be added.",
        )

    if kind == AddOutcomeKind.STREAMS_UNAVAILABLE:
        return ExitCode.STREAMS_UNAVAILABLE, "Could not read the camera's video streams. Try again."

    if kind == AddOutcomeKind.FORBIDDEN:
        return ExitCode.FORBIDDEN, "Access forbidden by camera."

    if kind == AddOutcomeKind.TLS_CHANGED:
        return ExitCode.TLS_CHANGED, "Camera TLS certificate changed."

    if kind == AddOutcomeKind.INVALID_INPUT:
        return ExitCode.INVALID_INPUT, outcome.detail or "Invalid input."

    return ExitCode.GENERIC_FAILURE, outcome.detail or "Onboarding failed."
