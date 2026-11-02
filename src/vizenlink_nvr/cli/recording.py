"""CLI recording subcommands."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Annotated, Any

import httpx
import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from vizenlink_nvr.cli.exitcodes import ExitCode
from vizenlink_nvr.cli.options import DataDirOpt, JsonOpt
from vizenlink_nvr.cli.output import emit, fail
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.db.models import Camera, RecordingSettings
from vizenlink_nvr.media.config import CONTROL_USER
from vizenlink_nvr.media.reconciler import (
    MediaMtxReconciler,
    ReconcileResult,
    compute_desired_paths,
    get_control_password,
)
from vizenlink_nvr.secrets.vault import open_vault
from vizenlink_nvr.services.indexer import record_segment_from_hook
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
from vizenlink_nvr.services.settings import get_site_timezone
from vizenlink_nvr.services.storage import StorageHealthState, get_storage_config
from vizenlink_nvr.services.watchdog import check_camera_gaps

recording_app = typer.Typer(
    no_args_is_help=True,
    help="Recording configuration and status.",
)
logger = logging.getLogger(__name__)


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


@recording_app.command(name="reconcile")
def reconcile(
    json_mode: JsonOpt = False,
    data_dir: DataDirOpt = None,
) -> None:
    """Synchronize camera recording paths from database into MediaMTX."""
    settings = load_settings(data_dir=data_dir)
    api_url = os.environ.get("NVR_MEDIAMTX_API_URL", "http://127.0.0.1:9997")
    control_pw = get_control_password(settings)
    auth = (CONTROL_USER, control_pw)

    async def _run() -> ReconcileResult:
        async with open_runtime(settings) as rt:
            site_tz = await get_site_timezone(rt)
            vault = None
            try:
                vault = await open_vault(rt)
            except Exception as exc:
                logger.debug("Vault deferred or unavailable: %s", exc)

            async with rt.sessions() as session:
                storage_cfg = await get_storage_config(
                    session,
                    default_path=settings.data_dir / "recordings",
                )
                volume_ok = storage_cfg.health_state == StorageHealthState.OK

                desired = await compute_desired_paths(
                    session,
                    storage_path=storage_cfg.storage_path,
                    volume_ok=volume_ok,
                    tz_name=site_tz,
                    vault=vault,
                )

                async with httpx.AsyncClient() as client:
                    reconciler = MediaMtxReconciler(client, api_url, auth)
                    return await reconciler.reconcile(desired)

    try:
        result = asyncio.run(_run())
    except Exception as exc:
        fail(
            ExitCode.MEDIAMTX_CHECK_FAILED,
            f"Failed to reconcile MediaMTX paths: {exc}",
            json_mode=json_mode,
        )

    payload = {
        "added": result.added,
        "patched": result.patched,
        "deleted": result.deleted,
        "unchanged": result.unchanged,
        "total_managed": len(result.added) + len(result.patched) + len(result.unchanged),
    }

    def _render_human(data: dict[str, Any]) -> None:
        table = Table(title="MediaMTX Path Reconciliation", show_header=True)
        table.add_column("Action", style="cyan")
        table.add_column("Count", style="magenta")
        table.add_column("Paths", style="white")

        table.add_row("Added", str(len(data["added"])), ", ".join(data["added"]) or "-")
        table.add_row("Patched", str(len(data["patched"])), ", ".join(data["patched"]) or "-")
        table.add_row("Deleted", str(len(data["deleted"])), ", ".join(data["deleted"]) or "-")
        table.add_row("Unchanged", str(len(data["unchanged"])), ", ".join(data["unchanged"]) or "-")
        Console().print(table)

    emit(payload, json_mode=json_mode, render_human=_render_human)


@recording_app.command(name="hook-segment-complete", hidden=True)
def hook_segment_complete(
    data_dir: DataDirOpt = None,
) -> None:
    """Internal hook executed by MediaMTX when a recording segment completes."""
    env = dict(os.environ)
    settings = load_settings(data_dir=data_dir)

    async def _run() -> None:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                await record_segment_from_hook(session, env)

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.error("Error processing hook-segment-complete: %s", exc)


@recording_app.command(name="status")
def recording_status(
    json_mode: JsonOpt = False,
    data_dir: DataDirOpt = None,
) -> None:
    """Show per-camera recording state, mode, current segment age, and health badges."""
    settings = load_settings(data_dir=data_dir)

    async def _run() -> dict[str, Any]:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                health_map = await check_camera_gaps(session)
                cam_res = await session.execute(
                    select(Camera).options(selectinload(Camera.recording_settings))
                )
                cameras = {c.serial: c for c in cam_res.scalars().all()}

                out: list[dict[str, Any]] = []
                for serial, h in sorted(health_map.items()):
                    cam = cameras.get(serial)
                    mode = cam.recording_settings.mode if (cam and cam.recording_settings) else "continuous"
                    out.append({
                        "camera_serial": serial,
                        "name": cam.name if cam else None,
                        "online_state": h.online_state.value,
                        "recording_state": h.recording_state.value,
                        "mode": mode,
                        "last_segment_at": h.last_segment_at.isoformat() if h.last_segment_at else None,
                        "segment_age_seconds": h.segment_age_seconds,
                        "gap_alarm": h.gap_alarm,
                        "details": h.details,
                    })
                return {"cameras": out}

    data = asyncio.run(_run())

    def _render_human(report: dict[str, Any]) -> None:
        table = Table(title="Camera Recording & Health Status", show_header=True)
        table.add_column("Serial", style="cyan", no_wrap=True)
        table.add_column("Name", style="green")
        table.add_column("Online", style="bold")
        table.add_column("Recording", style="bold")
        table.add_column("Mode", style="white")
        table.add_column("Last Segment Age", style="magenta")
        table.add_column("Gap Alarm", style="bold")

        for item in report.get("cameras", []):
            online = item["online_state"]
            on_style = "green" if online == "online" else "red"
            on_badge = f"[{on_style}]{online.upper()}[/{on_style}]"

            rec = item["recording_state"]
            if rec == "recording":
                rec_badge = "[green]RECORDING[/green]"
            elif rec == "disabled":
                rec_badge = "[yellow]DISABLED[/yellow]"
            else:
                rec_badge = "[red]NOT RECORDING[/red]"

            age_str = (
                f"{item['segment_age_seconds']}s ago"
                if item.get("segment_age_seconds") is not None
                else "-"
            )
            alarm_badge = (
                "[bold red]ALARM[/bold red]" if item.get("gap_alarm") else "[green]OK[/green]"
            )

            table.add_row(
                item["camera_serial"],
                item["name"] or "-",
                on_badge,
                rec_badge,
                item["mode"],
                age_str,
                alarm_badge,
            )

        Console().print(table)

    emit(data, json_mode=json_mode, render_human=_render_human)

