"""Report generator for real-camera hardware test runs (D-20)."""

import os
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class HwReport:
    """Collects and writes structured markdown reports of hardware test executions."""

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            reports_dir = Path(__file__).resolve().parents[1] / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            self.path = reports_dir / f"{ts}.md"
        else:
            self.path = path
            self.path.parent.mkdir(parents=True, exist_ok=True)

        self._records: dict[str, dict[str, Any]] = defaultdict(dict)
        self._outcomes: dict[str, tuple[str, str]] = {}

    def record(self, hw_id: str, key: str, value: Any) -> None:
        """Record a measured value for a hardware check."""
        self._records[hw_id][key] = value

    def outcome(self, hw_id: str, status: str, note: str = "") -> None:
        """Record the outcome (PASSED, SKIPPED, FAILED) of a hardware check."""
        self._outcomes[hw_id] = (status, note)

    def write(self) -> None:
        """Write the markdown report to disk, asserting no passwords appear."""
        pw = os.environ.get("NVR_HW_PASSWORD")

        lines = [
            "# Real Camera Hardware Verification Report",
            "",
            f"**Generated:** {datetime.now(UTC).isoformat()}",
            "",
            "## Summary of Results",
            "",
            "| Test ID | Status | Notes |",
            "|---------|--------|-------|",
        ]

        all_ids = sorted(set(self._outcomes.keys()) | set(self._records.keys()))
        for hw_id in all_ids:
            status, note = self._outcomes.get(hw_id, ("RECORDED", ""))
            lines.append(f"| {hw_id} | {status} | {note} |")

        lines.extend(["", "## Detailed Measurements", ""])

        for hw_id in all_ids:
            data = self._records.get(hw_id)
            if not data:
                continue
            lines.append(f"### {hw_id}")
            for k, v in data.items():
                lines.append(f"- **{k}:** `{v}`")
            lines.append("")

        content = "\n".join(lines) + "\n"

        if pw:
            assert pw not in content, "Hardware report contains cleartext NVR_HW_PASSWORD!"

        self.path.write_text(content, encoding="utf-8")
