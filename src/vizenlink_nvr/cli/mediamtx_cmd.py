"""CLI commands for MediaMTX management and validation."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from vizenlink_nvr.cli.exitcodes import ExitCode
from vizenlink_nvr.cli.options import DataDirOpt, JsonOpt
from vizenlink_nvr.cli.output import emit, fail
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.services.mediamtx import MediaMtxCheckReport, run_check
from vizenlink_nvr.services.runtime import open_runtime

mediamtx_app = typer.Typer(
    no_args_is_help=True,
    help="MediaMTX binary and configuration inspection.",
)


@mediamtx_app.callback()
def mediamtx_callback() -> None:
    """Manage MediaMTX integration."""


@mediamtx_app.command(name="check")
def check(
    probe: Annotated[
        bool,
        typer.Option(
            "--probe",
            help="Run network probes against live instance.",
        ),
    ] = False,
    json_mode: JsonOpt = False,
    data_dir: DataDirOpt = None,
) -> None:
    """Generate configuration, validate against binary, and optionally run probes."""
    settings = load_settings(data_dir=data_dir)

    async def _run() -> MediaMtxCheckReport:
        async with open_runtime(settings) as rt:
            return await run_check(rt, probe=probe)

    try:
        report = asyncio.run(_run())
    except Exception as exc:
        fail(
            ExitCode.MEDIAMTX_CHECK_FAILED,
            f"MediaMTX check error: {exc}",
            json_mode=json_mode,
        )

    def _render_human(r: MediaMtxCheckReport) -> None:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="MediaMTX Check Report", show_header=True)
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="magenta")

        table.add_row("Binary Path", str(r.binary_path))
        table.add_row("Binary Version", r.binary_version)
        table.add_row("Config Path", str(r.config_path))
        table.add_row("Validation OK", "[green]True[/green]" if r.validate_ok else "[red]False[/red]")
        table.add_row("Overall OK", "[green]True[/green]" if r.ok else "[red]False[/red]")
        if r.validate_output:
            table.add_row("Validation Output", r.validate_output)

        console.print(table)

    emit(report, json_mode=json_mode, render_human=_render_human)

    if not report.ok:
        raise typer.Exit(code=int(ExitCode.MEDIAMTX_CHECK_FAILED))
