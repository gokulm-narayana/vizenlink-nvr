"""CLI storage subcommands."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from vizenlink_nvr.cli.exitcodes import ExitCode
from vizenlink_nvr.cli.options import DataDirOpt, JsonOpt
from vizenlink_nvr.cli.output import emit, fail
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.services.runtime import open_runtime
from vizenlink_nvr.services.storage import (
    StorageConfig,
    StorageHealthState,
    evaluate_storage_health,
    get_storage_config,
    set_storage_path,
)

storage_app = typer.Typer(
    no_args_is_help=True,
    help="Storage configuration and status.",
)


@storage_app.callback()
def storage_callback() -> None:
    """Manage NVR recording storage."""


def _format_bytes(num_bytes: int | float) -> str:
    """Format bytes into human-readable string."""
    val = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(val) < 1024.0:
            return f"{val:.1f} {unit}"
        val /= 1024.0
    return f"{val:.1f} PB"


def _storage_config_to_dict(config: StorageConfig) -> dict[str, Any]:
    telemetry_dict = None
    if config.telemetry is not None:
        telemetry_dict = {
            "total_bytes": config.telemetry.total_bytes,
            "used_bytes": config.telemetry.used_bytes,
            "free_bytes": config.telemetry.free_bytes,
            "reserve_bytes": config.telemetry.reserve_bytes,
        }

    return {
        "storage_path": str(config.storage_path),
        "allow_system_disk": config.allow_system_disk,
        "reserve_bytes": config.reserve_bytes,
        "health_state": config.health_state.value,
        "health_reason": config.health_reason,
        "total_bytes": config.telemetry.total_bytes if config.telemetry else None,
        "used_bytes": config.telemetry.used_bytes if config.telemetry else None,
        "free_bytes": config.telemetry.free_bytes if config.telemetry else None,
        "telemetry": telemetry_dict,
        "estimated_retention_days": config.estimated_retention_days,
    }


def _render_storage_status_human(report: dict[str, Any]) -> None:
    table = Table(title="VizenLink NVR Storage Status", show_header=True)
    table.add_column("Property", style="cyan", no_wrap=True)
    table.add_column("Value", style="magenta")

    table.add_row("Storage Path", str(report.get("storage_path")))
    table.add_row(
        "System Disk Allowed",
        "[green]True[/green]" if report.get("allow_system_disk") else "[yellow]False[/yellow]",
    )

    health = report.get("health_state", "unknown")
    health_style = "green" if health == "ok" else "bold red"
    table.add_row("Health State", f"[{health_style}]{health}[/{health_style}]")
    if report.get("health_reason"):
        table.add_row("Health Reason", str(report.get("health_reason")))

    telemetry = report.get("telemetry")
    if telemetry:
        table.add_row("Total Space", _format_bytes(telemetry["total_bytes"]))
        table.add_row("Used Space", _format_bytes(telemetry["used_bytes"]))
        table.add_row("Free Space", _format_bytes(telemetry["free_bytes"]))
        table.add_row("Reserve Buffer", _format_bytes(telemetry["reserve_bytes"]))
    else:
        table.add_row("Telemetry", "[yellow]Unavailable[/yellow]")

    est_days = report.get("estimated_retention_days")
    table.add_row("Estimated Retention", f"{est_days} days" if est_days is not None else "Unknown")

    console = Console()
    console.print(table)


@storage_app.command(name="status")
def status(
    json_mode: JsonOpt = False,
    data_dir: DataDirOpt = None,
) -> None:
    """Show recording storage configuration, health, and disk telemetry."""
    settings = load_settings(data_dir=data_dir)
    default_rec_path = settings.data_dir / "recordings"

    async def _run() -> StorageConfig:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                return await get_storage_config(session, default_path=default_rec_path)

    config = asyncio.run(_run())
    emit(
        _storage_config_to_dict(config),
        json_mode=json_mode,
        render_human=_render_storage_status_human,
    )


@storage_app.command(name="set-path")
def set_path(
    path: Annotated[
        Path,
        typer.Option(
            "--path",
            help="Directory path for recording storage volume.",
        ),
    ],
    allow_system_disk: Annotated[
        bool,
        typer.Option(
            "--allow-system-disk",
            help="Allow recording on system root drive/partition.",
        ),
    ] = False,
    json_mode: JsonOpt = False,
    data_dir: DataDirOpt = None,
) -> None:
    """Configure the recording storage destination path."""
    settings = load_settings(data_dir=data_dir)
    resolved = path.resolve()

    health_state, health_reason = evaluate_storage_health(
        resolved,
        allow_system_disk=allow_system_disk,
    )

    if health_state == StorageHealthState.SYSTEM_DISK_REFUSED:
        msg = (
            f"Storage path '{resolved}' is on the system root partition. "
            "Specify --allow-system-disk to override."
        )
        fail(
            ExitCode.INVALID_INPUT,
            msg,
            json_mode=json_mode,
        )

    if health_state in (StorageHealthState.UNMOUNTED, StorageHealthState.READ_ONLY):
        fail(
            ExitCode.GENERIC_FAILURE,
            f"Storage path '{resolved}' is unhealthy: {health_reason}",
            json_mode=json_mode,
        )

    async def _run() -> StorageConfig:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                return await set_storage_path(
                    session,
                    target_path=resolved,
                    allow_system_disk=allow_system_disk,
                )

    config = asyncio.run(_run())
    emit(
        _storage_config_to_dict(config),
        json_mode=json_mode,
        render_human=lambda res: Console().print(
            f"[bold green]Storage path updated:[/] {res['storage_path']}"
        ),
    )
