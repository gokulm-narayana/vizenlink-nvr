"""Alert severity for camera events (Phase 10, old VMS parity).

Severity is derived from the event type rather than stored, so it can be tuned
without a migration and stays identical for the web UI and the mobile app.
"""

from __future__ import annotations

from typing import Literal

Severity = Literal["critical", "warning", "info"]

_SEVERITY: dict[str, Severity] = {
    "tamper": "critical",
    "digital_input": "critical",
    "line_crossing": "warning",
    "person": "warning",
    "vehicle": "info",
    "motion": "info",
    "generic": "info",
}


def severity_for(event_type: str) -> Severity:
    return _SEVERITY.get(event_type, "info")


def event_types_for(severity: Severity) -> list[str]:
    return [t for t, s in _SEVERITY.items() if s == severity]
