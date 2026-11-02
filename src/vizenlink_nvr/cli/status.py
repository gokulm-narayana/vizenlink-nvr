"""CLI status utilities and recorder health rendering (HLTH-06)."""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

from vizenlink_nvr.config import NvrSettings
from vizenlink_nvr.media.process import live_processes
from vizenlink_nvr.services.health import RecorderHealthService, RecorderStatus
from vizenlink_nvr.services.runtime import open_runtime
from vizenlink_nvr.services.storage import get_storage_config
from vizenlink_nvr.services.watchdog import check_camera_gaps

if TYPE_CHECKING:
    pass


def check_mediamtx_alive(api_port: int = 9997) -> bool:
    """Check if MediaMTX process is running or its API port is open."""
    if len(live_processes()) > 0:
        return True
    try:
        with socket.create_connection(("127.0.0.1", api_port), timeout=0.2):
            return True
    except Exception:
        return False


async def evaluate_system_recorder_health(
    settings: NvrSettings,
    mediamtx_alive: bool | None = None,
) -> RecorderStatus:
    """Evaluate overall recorder health: healthy, degraded, or critical (HLTH-06)."""
    if mediamtx_alive is None:
        mediamtx_alive = check_mediamtx_alive()

    async with open_runtime(settings) as rt:
        async with rt.sessions() as session:
            default_path = settings.data_dir / "recordings"
            storage_config = await get_storage_config(session, default_path=default_path)
            gaps = await check_camera_gaps(session)
            gap_count = sum(1 for h in gaps.values() if h.gap_alarm)

            return await RecorderHealthService.get_recorder_status(
                session=session,
                media_status=mediamtx_alive,
                storage_status=storage_config,
                gap_count=gap_count,
            )


def render_recorder_status_table(status: RecorderStatus) -> None:
    """Render Rich table displaying overall recorder health."""
    table = Table(title="VizenLink Recorder Health", show_header=True)
    table.add_column("Subsystem", style="cyan")
    table.add_column("Status", style="magenta")

    stat_str = status.status.value.upper()
    stat_style = (
        "green"
        if stat_str == "HEALTHY"
        else ("yellow" if stat_str == "DEGRADED" else "bold red")
    )
    table.add_row("Overall Recorder Status", f"[{stat_style}]{stat_str}[/{stat_style}]")
    table.add_row("Database", "[green]OK[/green]" if status.db_ok else "[red]FAILED[/red]")
    table.add_row("MediaMTX Process", "[green]RUNNING[/green]" if status.mediamtx_ok else "[red]DOWN[/red]")
    table.add_row("Recording Storage", "[green]OK[/green]" if status.storage_ok else "[red]DEGRADED[/red]")
    table.add_row("Active Gap Alarms", str(status.details.get("gap_count", 0)))

    Console().print(table)
