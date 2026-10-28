"""Camera onboarding CLI command (nvr cameras add)."""

import asyncio
import json
import sys
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from vizenlink_nvr.cli.cameras import cameras_app
from vizenlink_nvr.cli.options import DataDirOpt, JsonOpt
from vizenlink_nvr.cli.outcomes import present
from vizenlink_nvr.cli.output import emit, err_console, fail
from vizenlink_nvr.cli.prompts import CliPasswordProvider
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.services.onboarding import AddOutcomeKind, AddRequest, run_add
from vizenlink_nvr.services.registry import CameraView


def _render_camera_added(camera: CameraView) -> None:
    """Render human table of newly onboarded camera."""
    console = Console()
    table = Table(title=f"Added Camera {camera.serial}", show_header=True)
    table.add_column("Property", style="cyan", no_wrap=True)
    table.add_column("Value", style="magenta")

    table.add_row("Serial", camera.serial)
    table.add_row("Host", f"{camera.host}:{camera.https_port}")
    table.add_row("MAC", camera.mac or "-")
    table.add_row("Name", camera.name or "-")
    table.add_row("Location", camera.location or "-")
    table.add_row("Model", camera.model or "-")
    table.add_row("Firmware", camera.firmware_version or "-")
    table.add_row("State", f"[green]{camera.state}[/green]")

    stream_desc = ", ".join(f"{s.role}: {s.codec} {s.width}x{s.height} ({s.source})" for s in camera.streams)
    table.add_row("Streams", stream_desc or "None")

    console.print(table)


@cameras_app.command(name="add")
def add_camera(
    host: Annotated[str, typer.Option("--host", "-h", help="Camera IP address or hostname.")],
    port: Annotated[int, typer.Option("--port", "-p", help="Camera HTTPS port.")] = 443,
    password_stdin: Annotated[
        bool,
        typer.Option("--password-stdin", help="Read password from standard input."),
    ] = False,
    allow_public: Annotated[
        bool,
        typer.Option("--allow-public", help="Allow public IP addresses."),
    ] = False,
    name: Annotated[
        str | None,
        typer.Option("--name", "-n", help="Camera display name."),
    ] = None,
    location: Annotated[
        str | None,
        typer.Option("--location", "-l", help="Camera physical location."),
    ] = None,
    group: Annotated[
        str | None,
        typer.Option("--group", "-g", help="Camera group tag."),
    ] = None,
    json_mode: JsonOpt = False,
    data_dir: DataDirOpt = None,
) -> None:
    """Add and onboard a camera into the NVR registry."""
    settings = load_settings(data_dir=data_dir)
    req = AddRequest(
        host=host,
        port=port,
        allow_public=allow_public,
        name=name,
        location=location,
        group=group,
    )
    passwords = CliPasswordProvider(stdin_mode=password_stdin)

    outcome = asyncio.run(run_add(settings, req, passwords))

    if outcome.kind == AddOutcomeKind.OK:
        if json_mode:
            payload = outcome.camera.model_dump(mode="json") if outcome.camera else {}
            if outcome.notice is not None:
                payload["notice"] = outcome.notice
            emit(payload, json_mode=True)
            return

        def render_human(cam: CameraView | None) -> None:
            if cam:
                _render_camera_added(cam)
            if outcome.notice:
                print(outcome.notice)

        emit(outcome.camera, json_mode=False, render_human=render_human)
        return

    if outcome.kind == AddOutcomeKind.ADDRESS_UPDATED:
        _, msg = present(outcome)
        emit(outcome.camera, json_mode=json_mode, render_human=lambda _: print(msg))
        return

    code, msg = present(outcome)
    if json_mode:
        payload = {
            "kind": outcome.kind.value,
            "message": msg,
            "error": msg,
            "code": int(code),
        }
        if outcome.detail:
            payload["detail"] = outcome.detail
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        sys.stdout.flush()
        err_console.print(f"Error: {msg}")
        if outcome.detail and outcome.detail.startswith("The camera"):
            err_console.print(outcome.detail)
        raise typer.Exit(code=int(code))

    if outcome.detail and outcome.detail.startswith("The camera"):
        err_console.print(outcome.detail)
    fail(code, msg, json_mode=False)
