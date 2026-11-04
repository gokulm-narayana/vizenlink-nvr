"""CLI service packaging and installation commands (FND-06)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from vizenlink_nvr.cli.options import JsonOpt
from vizenlink_nvr.cli.output import emit
from vizenlink_nvr.service.installer import ServiceManager, TargetOS, detect_os

service_app = typer.Typer(
    no_args_is_help=True,
    help="Manage NVR boot-time service installation and configuration generation.",
)


@service_app.command(name="generate")
def generate_service_cmd(
    target_os: Annotated[
        str | None,
        typer.Option(
            "--os",
            help="Target OS: linux, darwin (macOS), or windows.",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Optional file path to write service definition.",
        ),
    ] = None,
    json_mode: JsonOpt = False,
) -> None:
    """Generate system service configuration for Linux, macOS, or Windows."""
    chosen_os: TargetOS = (target_os.lower() if target_os else detect_os())  # type: ignore[assignment]
    mgr = ServiceManager(target_os=chosen_os)
    content = mgr.get_service_content()
    filename = mgr.get_service_filename()

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        result = {
            "status": "written",
            "target_os": chosen_os,
            "filename": filename,
            "path": str(output.resolve()),
        }
        human = f"Service definition for {chosen_os} written to {output}"
    else:
        result = {
            "status": "generated",
            "target_os": chosen_os,
            "filename": filename,
            "content": content,
        }
        human = content

    emit(result, json_mode=json_mode, render_human=lambda _: print(human))


@service_app.command(name="status")
def service_status_cmd(
    target_os: Annotated[
        str | None,
        typer.Option(
            "--os",
            help="Target OS: linux, darwin (macOS), or windows.",
        ),
    ] = None,
    json_mode: JsonOpt = False,
) -> None:
    """Display system service registration status."""
    chosen_os: TargetOS = (target_os.lower() if target_os else detect_os())  # type: ignore[assignment]
    mgr = ServiceManager(target_os=chosen_os)
    status_info = mgr.get_service_status()

    human = (
        f"OS: {status_info['target_os']}\n"
        f"Service Filename: {status_info['filename']}\n"
        f"Standard Location: {status_info['standard_path']}\n"
        f"Installed: {'Yes' if status_info['installed'] else 'No'}"
    )
    emit(status_info, json_mode=json_mode, render_human=lambda _: print(human))
