"""Domain models, state machine, and grid layout calculations for Live Multiview (LIVE-01 to LIVE-06)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, TypeVar

T = TypeVar("T")


class TileState(StrEnum):
    """Truthful tile operational state (LIVE-04)."""

    CONNECTING = "connecting"
    LIVE = "live"
    STALLED = "stalled"
    OFFLINE = "offline"
    ERROR = "error"


class ViewMode(StrEnum):
    """UI view complexity mode (AUTH-06)."""

    SIMPLE = "simple"
    ADVANCED = "advanced"


ADVANCED_METRIC_KEYS = {
    "reserve_bytes",
    "db_ok",
    "mediamtx_ok",
    "details",
    "mountpoint",
    "hardware_id",
    "tls_fingerprint_sha256",
    "raw_capabilities",
}


def filter_dashboard_metrics(metrics: dict[str, Any], mode: ViewMode | str) -> dict[str, Any]:
    """Filter dashboard telemetry based on user view mode (AUTH-06).

    Simple view hides low-level technical and diagnostic fields.
    Advanced view exposes full system diagnostics.
    """
    mode_str = str(mode).strip().lower()
    if mode_str == ViewMode.ADVANCED.value:
        return dict(metrics)

    # Simple mode: filter out advanced keys
    filtered = {k: v for k, v in metrics.items() if k not in ADVANCED_METRIC_KEYS}
    return filtered


class TileStateMachine:
    """State machine governing video stream connection and stall detection.

    Prohibition: Never present a frozen video frame or dead stream as live (LIVE-04).
    """

    def __init__(self, stall_timeout_seconds: float = 5.0, max_retries: int = 3) -> None:
        self.state: TileState = TileState.CONNECTING
        self.stall_timeout: float = stall_timeout_seconds
        self.max_retries: int = max_retries
        self.retry_count: int = 0
        self.last_frame_timestamp: float = 0.0

    @property
    def is_live(self) -> bool:
        """Only returns True when video frames are actively playing without stalls."""
        return self.state == TileState.LIVE

    def on_connect_started(self) -> None:
        """Connection negotiation initiated."""
        self.state = TileState.CONNECTING

    def on_first_frame(self, current_time: float) -> None:
        """First video frame decoded or normal playback resumed."""
        self.state = TileState.LIVE
        self.retry_count = 0
        self.last_frame_timestamp = current_time

    def on_frame_progress(self, current_time: float) -> None:
        """Video playback clock advancing normally."""
        self.state = TileState.LIVE
        self.last_frame_timestamp = current_time

    def check_staleness(self, current_time: float) -> TileState:
        """Check for frozen stream. If frame hasn't advanced for > stall_timeout, leave LIVE."""
        if self.state == TileState.LIVE:
            if current_time - self.last_frame_timestamp >= self.stall_timeout:
                self.state = TileState.STALLED
        return self.state

    def on_disconnect_or_error(self, fatal: bool = False) -> None:
        """Stream transport failure or peer disconnection."""
        if fatal:
            self.state = TileState.ERROR
            return

        self.retry_count += 1
        if self.retry_count > self.max_retries:
            self.state = TileState.OFFLINE
        else:
            self.state = TileState.CONNECTING


class GridLayoutCalculator:
    """Computes grid dimensions, tile capacities, and pagination slices (LIVE-02)."""

    VALID_DIMENSIONS = (1, 2, 3, 4)

    @classmethod
    def get_tiles_per_page(cls, dimension: int) -> int:
        """Return number of tiles in an NxN grid (1x1=1, 2x2=4, 3x3=9, 4x4=16)."""
        if dimension not in cls.VALID_DIMENSIONS:
            raise ValueError(f"Invalid grid dimension '{dimension}'. Must be one of {cls.VALID_DIMENSIONS}")
        return dimension * dimension

    @classmethod
    def get_total_pages(cls, total_items: int, dimension: int) -> int:
        """Calculate total number of pages for given item count and grid dimension."""
        if total_items <= 0:
            return 1
        per_page = cls.get_tiles_per_page(dimension)
        return (total_items + per_page - 1) // per_page

    @classmethod
    def paginate(cls, items: list[T], dimension: int, page_index: int) -> list[T]:
        """Slice items for a specific 0-based page index."""
        per_page = cls.get_tiles_per_page(dimension)
        start = page_index * per_page
        end = start + per_page
        return items[start:end]


@dataclass
class TileControlsModel:
    """Tile overlay controls and automatic sub/main stream switching (LIVE-03, LIVE-05)."""

    camera_serial: str
    camera_name: str
    is_muted: bool = True
    is_recording: bool = False
    is_maximized: bool = False
    active_stream: str = "sub"  # LIVE-03: Sub-stream by default
    state: TileState = TileState.CONNECTING

    def toggle_maximize(self) -> str:
        """Toggle maximize state and auto-switch stream (LIVE-03).
        
        Sub-stream in multiview grid; main-stream when enlarged or maximized.
        """
        self.is_maximized = not self.is_maximized
        self.active_stream = "main" if self.is_maximized else "sub"
        return self.active_stream

    def toggle_mute(self) -> bool:
        """Toggle audio mute state."""
        self.is_muted = not self.is_muted
        return self.is_muted

    def can_snapshot(self) -> bool:
        """Snapshot is only valid when stream is actively live."""
        return self.state == TileState.LIVE


@dataclass
class GridLayoutConfig:
    """Serializable layout state for local persistence (LIVE-06)."""

    dimension: int = 2
    page: int = 0
    slot_assignments: dict[int, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize configuration to JSON-compatible dict."""
        return {
            "dimension": self.dimension,
            "page": self.page,
            "slot_assignments": {str(k): v for k, v in self.slot_assignments.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GridLayoutConfig:
        """Deserialize and validate layout configuration."""
        dim = data.get("dimension", 2)
        if dim not in GridLayoutCalculator.VALID_DIMENSIONS:
            dim = 2
        page = max(0, int(data.get("page", 0)))
        raw_slots = data.get("slot_assignments", {})
        slots: dict[int, str] = {}
        if isinstance(raw_slots, dict):
            for k, v in raw_slots.items():
                try:
                    slots[int(k)] = str(v)
                except (ValueError, TypeError):
                    continue
        return cls(dimension=dim, page=page, slot_assignments=slots)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> GridLayoutConfig:
        try:
            data = json.loads(raw)
            return cls.from_dict(data)
        except Exception:
            return cls()
