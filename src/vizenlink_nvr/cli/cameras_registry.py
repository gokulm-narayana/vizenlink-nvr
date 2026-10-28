"""Camera registry inspection CLI commands (list, show)."""

import asyncio
from typing import Annotated
from zoneinfo import ZoneInfo

import typer
from rich.console import Console
from rich.table import Table

from vizenlink_nvr.cli.cameras import cameras_app
from vizenlink_nvr.cli.exitcodes import ExitCode
from vizenlink_nvr.cli.options import DataDirOpt, JsonOpt
from vizenlink_nvr.cli.output import emit, fail
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.services.registry import CameraView, get_camera, list_cameras
from vizenlink_nvr.services.runtime import open_runtime
from vizenlink_nvr.services.settings import get_site_timezone
from vizenlink_nvr.timeutil import format_local


def _render_cameras_list(cameras: list[CameraView]) -> None:
    """Render table of registered cameras."""
    console = Console()
    table = Table(title="Registered Cameras", show_header=True)
    table.add_column("Serial", style="cyan", no_wrap=True)
    table.add_column("Name", style="green")
    table.add_column("Location", style="yellow")
    table.add_column("Model", style="blue")
    table.add_column("IP", style="magenta")
    table.add_column("State", style="bold")

    for c in cameras:
        state_color = "green" if c.state == "active" else "red"
        table.add_row(
            c.serial,
            c.name or "-",
            c.location or "-",
            c.model or "-",
            f"{c.host}:{c.https_port}",
            f"[{state_color}]{c.state}[/{state_color}]",
        )
    console.print(table)


def _render_camera_show(cam: CameraView, site_tz: str) -> None:
    """Render detailed view of a camera with localized timestamps."""
    console = Console()
    tz = ZoneInfo(site_tz)

    table = Table(title=f"Camera {cam.serial}", show_header=True)
    table.add_column("Property", style="cyan", no_wrap=True)
    table.add_column("Value", style="magenta")

    table.add_row("Serial", cam.serial)
    table.add_row("Host", f"{cam.host}:{cam.https_port}")
    table.add_row("MAC", cam.mac or "-")
    table.add_row("Name", cam.name or "-")
    table.add_row("Location", cam.location or "-")
    table.add_row("Group", cam.group_tag or "-")
    table.add_row("Manufacturer", cam.manufacturer or "-")
    table.add_row("Model", cam.model or "-")
    table.add_row("Firmware Version", cam.firmware_version or "-")
    table.add_row("Hardware ID", cam.hardware_id or "-")
    table.add_row("TLS Pin", cam.tls_fingerprint_sha256)
    table.add_row("State", cam.state)
    table.add_row("Added At", format_local(cam.added_at, tz))
    table.add_row("Host Updated At", format_local(cam.host_updated_at, tz))
    synced_str = format_local(cam.identity_synced_at, tz) if cam.identity_synced_at else "-"
    table.add_row("Identity Synced At", synced_str)
    table.add_row("Last Error", cam.last_error or "-")

    stream_desc = "\n".join(
        f"- {s.role.upper()}: {s.codec} {s.width}x{s.height} ({s.source}) -> {s.scheme}://{cam.host}:{s.port}{s.path}"
        for s in cam.streams
    )
    table.add_row("Streams", stream_desc or "None")

    console.print(table)


@cameras_app.command(name="list")
def list_registered_cameras(
    json_mode: JsonOpt = False,
    data_dir: DataDirOpt = None,
) -> None:
    """List all registered cameras."""
    settings = load_settings(data_dir=data_dir)

    async def _fetch() -> list[CameraView]:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                return await list_cameras(session)

    cameras = asyncio.run(_fetch())
    if json_mode:
        emit([c.model_dump(mode="json") for c in cameras], json_mode=True)
    else:
        emit(cameras, json_mode=False, render_human=_render_cameras_list)


@cameras_app.command(name="show")
def show_camera(
    serial: Annotated[str, typer.Option("--serial", "-s", help="Camera serial number.")],
    json_mode: JsonOpt = False,
    data_dir: DataDirOpt = None,
) -> None:
    """Show detailed information and streams for a registered camera."""
    settings = load_settings(data_dir=data_dir)

    async def _fetch() -> tuple[CameraView | None, str]:
        async with open_runtime(settings) as rt:
            site_tz = await get_site_timezone(rt)
            async with rt.sessions() as session:
                cam = await get_camera(session, serial)
                return cam, site_tz

    camera, site_tz = asyncio.run(_fetch())
    if camera is None:
        fail(
            ExitCode.NOT_FOUND,
            f"Camera {serial} not found",
            json_mode=json_mode,
        )

    emit(
        camera,
        json_mode=json_mode,
        render_human=lambda c: _render_camera_show(c, site_tz),
    )
