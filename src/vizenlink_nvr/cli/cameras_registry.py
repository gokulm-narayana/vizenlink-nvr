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
from vizenlink_nvr.cli.outcomes import blocked_message
from vizenlink_nvr.cli.output import emit, err_console, fail
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.services.manage import ManageKind, RenameRequest, run_rename
from vizenlink_nvr.services.registry import CameraView, get_camera, list_cameras
from vizenlink_nvr.services.reprobe import ReprobeKind, run_reprobe
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


@cameras_app.command(name="rename")
def rename_camera_cmd(
    serial: Annotated[str, typer.Option("--serial", "-s", help="Camera serial number.")],
    name: Annotated[
        str | None,
        typer.Option("--name", "-n", help="New camera display name."),
    ] = None,
    location: Annotated[
        str | None,
        typer.Option("--location", "-l", help="New camera physical location."),
    ] = None,
    group: Annotated[
        str | None,
        typer.Option("--group", "-g", help="New camera group tag."),
    ] = None,
    json_mode: JsonOpt = False,
    data_dir: DataDirOpt = None,
) -> None:
    """Update camera display name, physical location, or group tag."""
    settings = load_settings(data_dir=data_dir)
    req = RenameRequest(serial=serial, name=name, location=location, group=group)
    outcome = asyncio.run(run_rename(settings, req))

    if outcome.kind == ManageKind.OK and outcome.camera is not None:

        async def _get_tz() -> str:
            async with open_runtime(settings) as rt:
                return await get_site_timezone(rt)

        site_tz = asyncio.run(_get_tz())
        emit(
            outcome.camera,
            json_mode=json_mode,
            render_human=lambda c: _render_camera_show(c, site_tz),
        )
        return

    # Map failures to exit codes and messages
    code_map: dict[ManageKind, tuple[ExitCode, str]] = {
        ManageKind.NOT_FOUND: (ExitCode.NOT_FOUND, f"Camera {serial} not found in registry."),
        ManageKind.INVALID_INPUT: (ExitCode.INVALID_INPUT, outcome.detail or "Invalid input."),
        ManageKind.AUTH_FAILED: (
            ExitCode.AUTH_FAILED,
            "Camera authentication failed; password must be updated.",
        ),
        ManageKind.TLS_CHANGED: (
            ExitCode.TLS_CHANGED,
            outcome.detail
            or (
                f"The camera's certificate has changed since it was added. "
                f"If you replaced or updated this camera, run: "
                f"nvr cameras reprobe {serial} --accept-new-certificate"
            ),
        ),
        ManageKind.FORBIDDEN: (ExitCode.FORBIDDEN, "Access forbidden by camera."),
        ManageKind.BLOCKED: (ExitCode.BLOCKED, blocked_message(outcome.retry_after_seconds)),
        ManageKind.WRONG_CREDENTIALS: (ExitCode.WRONG_CREDENTIALS, "Incorrect username or password."),
        ManageKind.UNREACHABLE: (
            ExitCode.UNREACHABLE,
            "Could not reach the camera — check the connection and try again.",
        ),
    }
    code, msg = code_map.get(
        outcome.kind,
        (ExitCode.GENERIC_FAILURE, outcome.detail or "Failed to rename camera."),
    )
    fail(code, msg, json_mode=json_mode)


@cameras_app.command(name="reprobe")
def reprobe_camera_cmd(
    serial: Annotated[str, typer.Option("--serial", "-s", help="Camera serial number.")],
    accept_new_certificate: Annotated[
        bool,
        typer.Option("--accept-new-certificate", help="Accept new TLS certificate fingerprint."),
    ] = False,
    json_mode: JsonOpt = False,
    data_dir: DataDirOpt = None,
) -> None:
    """Reprobe and heal a registered camera after DHCP re-IP or network changes."""
    settings = load_settings(data_dir=data_dir)
    report = asyncio.run(run_reprobe(settings, serial, accept_new_certificate=accept_new_certificate))

    if json_mode:
        emit(report, json_mode=True)
        if report.kind in (ReprobeKind.OK, ReprobeKind.HEALED):
            return
        if report.kind == ReprobeKind.TLS_CHANGED:
            raise typer.Exit(code=int(ExitCode.TLS_CHANGED))
        if report.kind == ReprobeKind.AUTH_FAILED:
            raise typer.Exit(code=int(ExitCode.AUTH_FAILED))
        if report.kind == ReprobeKind.FORBIDDEN:
            raise typer.Exit(code=int(ExitCode.FORBIDDEN))
        if report.kind == ReprobeKind.NOT_FOUND_SERIAL:
            raise typer.Exit(code=int(ExitCode.NOT_FOUND))
        if report.kind in (ReprobeKind.UNREACHABLE, ReprobeKind.NOT_FOUND):
            raise typer.Exit(code=int(ExitCode.UNREACHABLE))
        if report.kind == ReprobeKind.AMBIGUOUS:
            raise typer.Exit(code=int(ExitCode.GENERIC_FAILURE))
        raise typer.Exit(code=1)

    # Human mode
    for w in report.warnings:
        err_console.print(f"[yellow]Warning:[/] {w}")

    if report.kind == ReprobeKind.TLS_CHANGED:
        fail(
            ExitCode.TLS_CHANGED,
            (
                "The camera's certificate has changed since it was added. "
                "If you replaced or updated this camera, run: "
                f"nvr cameras reprobe {serial} --accept-new-certificate"
            ),
            json_mode=False,
        )

    if report.kind == ReprobeKind.AUTH_FAILED:
        fail(
            ExitCode.AUTH_FAILED,
            "Camera authentication failed; password must be updated.",
            json_mode=False,
        )

    if report.kind == ReprobeKind.FORBIDDEN:
        fail(
            ExitCode.FORBIDDEN,
            "Access forbidden by camera.",
            json_mode=False,
        )

    if report.kind == ReprobeKind.OK:
        print(f"Camera {report.serial} is at {report.address}")
        if report.refreshed:
            print("Capabilities and streams refreshed.")
        return

    if report.kind == ReprobeKind.HEALED:
        old_addr = report.heal.old_address if report.heal else "unknown"
        print(f"Address updated from {old_addr} to {report.address}")
        if report.refreshed:
            print("Capabilities and streams refreshed.")
        return

    if report.kind == ReprobeKind.AMBIGUOUS:
        claimants = report.heal.claimants if report.heal else 2
        fail(
            ExitCode.GENERIC_FAILURE,
            f"{claimants} devices claim serial {report.serial}; nothing was changed.",
            json_mode=False,
        )

    if report.kind in (ReprobeKind.NOT_FOUND, ReprobeKind.UNREACHABLE):
        fail(
            ExitCode.UNREACHABLE,
            f"Could not find camera {report.serial} on the network.",
            json_mode=False,
        )

    if report.kind == ReprobeKind.NOT_FOUND_SERIAL:
        fail(
            ExitCode.NOT_FOUND,
            f"Camera {report.serial} not found in registry.",
            json_mode=False,
        )
