"""CLI recording subcommands."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from vizenlink_nvr.cli.exitcodes import ExitCode
from vizenlink_nvr.cli.options import DataDirOpt, JsonOpt
from vizenlink_nvr.cli.output import emit, fail
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.db.models import RecordingSettings
from vizenlink_nvr.services.recording_settings import (
    AudioNotSupportedError,
    CameraNotFoundError,
    RecordingMode,
    set_recording_audio,
    set_recording_mode,
    set_recording_retention,
    set_recording_schedule,
)
from vizenlink_nvr.services.runtime import open_runtime
from vizenlink_nvr.services.schedule import WeeklySchedule

recording_app = typer.Typer(
    no_args_is_help=True,
    help="Recording configuration and status.",
)


@recording_app.callback()
def recording_callback() -> None:
    """Manage camera recording settings and modes."""


def _recording_settings_to_dict(settings: RecordingSettings) -> dict[str, Any]:
    return {
        "camera_serial": settings.camera_serial,
        "mode": settings.mode,
        "audio_enabled": settings.audio_enabled,
        "retention_days": settings.retention_days,
        "retention_max_gb": settings.retention_max_gb,
        "schedule_json": settings.schedule_json,
        "updated_at": settings.updated_at.isoformat() if settings.updated_at else None,
    }


def _render_settings_human(res: dict[str, Any]) -> None:
    table = Table(title=f"Recording Settings — {res['camera_serial']}", show_header=True)
    table.add_column("Property", style="cyan", no_wrap=True)
    table.add_column("Value", style="magenta")

    table.add_row("Camera Serial", res["camera_serial"])
    table.add_row("Recording Mode", f"[bold green]{res['mode']}[/bold green]")
    table.add_row(
        "Audio Enabled",
        "[green]True[/green]" if res["audio_enabled"] else "[yellow]False[/yellow]",
    )
    days_str = str(res["retention_days"]) if res["retention_days"] else "Unlimited"
    gb_str = str(res["retention_max_gb"]) if res["retention_max_gb"] else "Unlimited"
    table.add_row("Retention Days", days_str)
    table.add_row("Retention Max GB", gb_str)

    Console().print(table)


@recording_app.command(name="set-mode")
def set_mode(
    serial: Annotated[
        str,
        typer.Option(
            "--serial",
            help="Unique camera serial number.",
        ),
    ],
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            help="Recording mode: continuous, scheduled, event, or off.",
        ),
    ],
    json_mode: JsonOpt = False,
    data_dir: DataDirOpt = None,
) -> None:
    """Set the recording mode for a camera."""
    mode_clean = mode.strip().lower()
    valid_modes = {m.value for m in RecordingMode}
    if mode_clean not in valid_modes:
        fail(
            ExitCode.INVALID_INPUT,
            f"Invalid recording mode '{mode}'. Choose from: {sorted(valid_modes)}",
            json_mode=json_mode,
        )

    settings = load_settings(data_dir=data_dir)

    async def _run() -> RecordingSettings:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                return await set_recording_mode(session, serial, mode_clean)

    try:
        rec_settings = asyncio.run(_run())
    except CameraNotFoundError as exc:
        fail(ExitCode.NOT_FOUND, str(exc), json_mode=json_mode)
    except Exception as exc:
        fail(ExitCode.GENERIC_FAILURE, str(exc), json_mode=json_mode)

    emit(
        _recording_settings_to_dict(rec_settings),
        json_mode=json_mode,
        render_human=_render_settings_human,
    )


@recording_app.command(name="set-schedule")
def set_schedule(
    serial: Annotated[
        str,
        typer.Option(
            "--serial",
            help="Unique camera serial number.",
        ),
    ],
    schedule: Annotated[
        str,
        typer.Option(
            "--schedule",
            help="Schedule preset (e.g. business_hours, weekdays, weekends, always) or JSON string.",
        ),
    ],
    json_mode: JsonOpt = False,
    data_dir: DataDirOpt = None,
) -> None:
    """Set the weekly recording schedule for a camera."""
    try:
        WeeklySchedule.from_spec(schedule)
    except Exception as exc:
        fail(ExitCode.INVALID_INPUT, f"Invalid schedule specification: {exc}", json_mode=json_mode)

    settings = load_settings(data_dir=data_dir)

    async def _run() -> RecordingSettings:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                return await set_recording_schedule(session, serial, schedule)

    try:
        rec_settings = asyncio.run(_run())
    except CameraNotFoundError as exc:
        fail(ExitCode.NOT_FOUND, str(exc), json_mode=json_mode)
    except Exception as exc:
        fail(ExitCode.GENERIC_FAILURE, str(exc), json_mode=json_mode)

    emit(
        _recording_settings_to_dict(rec_settings),
        json_mode=json_mode,
        render_human=_render_settings_human,
    )


@recording_app.command(name="set-audio")
def set_audio(
    serial: Annotated[
        str,
        typer.Option(
            "--serial",
            help="Unique camera serial number.",
        ),
    ],
    enabled: Annotated[
        bool,
        typer.Option(
            "--enabled/--disabled",
            help="Enable or disable audio recording track.",
        ),
    ],
    json_mode: JsonOpt = False,
    data_dir: DataDirOpt = None,
) -> None:
    """Toggle audio recording track for a camera."""
    settings = load_settings(data_dir=data_dir)

    async def _run() -> RecordingSettings:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                return await set_recording_audio(session, serial, enabled=enabled)

    try:
        rec_settings = asyncio.run(_run())
    except CameraNotFoundError as exc:
        fail(ExitCode.NOT_FOUND, str(exc), json_mode=json_mode)
    except AudioNotSupportedError as exc:
        fail(ExitCode.INVALID_INPUT, str(exc), json_mode=json_mode)
    except Exception as exc:
        fail(ExitCode.GENERIC_FAILURE, str(exc), json_mode=json_mode)

    emit(
        _recording_settings_to_dict(rec_settings),
        json_mode=json_mode,
        render_human=_render_settings_human,
    )


@recording_app.command(name="set-retention")
def set_retention(
    serial: Annotated[
        str,
        typer.Option(
            "--serial",
            help="Unique camera serial number.",
        ),
    ],
    days: Annotated[
        int | None,
        typer.Option(
            "--days",
            help="Maximum retention duration in days (positive integer).",
        ),
    ] = None,
    max_gb: Annotated[
        int | None,
        typer.Option(
            "--max-gb",
            help="Maximum disk space cap for camera in gigabytes (positive integer).",
        ),
    ] = None,
    json_mode: JsonOpt = False,
    data_dir: DataDirOpt = None,
) -> None:
    """Configure retention duration and storage cap for a camera."""
    if days is not None and days <= 0:
        fail(ExitCode.INVALID_INPUT, "--days must be a positive integer", json_mode=json_mode)
    if max_gb is not None and max_gb <= 0:
        fail(ExitCode.INVALID_INPUT, "--max-gb must be a positive integer", json_mode=json_mode)

    settings = load_settings(data_dir=data_dir)

    async def _run() -> RecordingSettings:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                return await set_recording_retention(session, serial, days=days, max_gb=max_gb)

    try:
        rec_settings = asyncio.run(_run())
    except CameraNotFoundError as exc:
        fail(ExitCode.NOT_FOUND, str(exc), json_mode=json_mode)
    except Exception as exc:
        fail(ExitCode.GENERIC_FAILURE, str(exc), json_mode=json_mode)

    emit(
        _recording_settings_to_dict(rec_settings),
        json_mode=json_mode,
        render_human=_render_settings_human,
    )
