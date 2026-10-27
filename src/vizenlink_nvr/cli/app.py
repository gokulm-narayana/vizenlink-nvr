"""VizenLink NVR CLI root application."""

import asyncio

import typer
from rich.table import Table

# Side-effect imports for command registration on cameras_app
from vizenlink_nvr.cli import (  # noqa: F401
    cameras_onboard,
    cameras_registry,
    cameras_scan,
)
from vizenlink_nvr.cli.cameras import cameras_app
from vizenlink_nvr.cli.options import DataDirOpt, JsonOpt
from vizenlink_nvr.cli.output import emit
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.services.runtime import open_runtime
from vizenlink_nvr.services.status import StatusReport, get_status

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="VizenLink NVR Admin CLI",
)

app.add_typer(cameras_app, name="cameras")


def _render_status_human(report: StatusReport) -> None:
    table = Table(title="VizenLink NVR Status", show_header=True)
    table.add_column("Property", style="cyan", no_wrap=True)
    table.add_column("Value", style="magenta")

    table.add_row("Data Directory", report.data_dir)
    table.add_row("Database OK", "[green]True[/green]" if report.db_ok else "[red]False[/red]")
    table.add_row("Schema Revision", str(report.schema_revision))
    table.add_row("Schema Head", report.schema_head)
    table.add_row("Site Timezone", report.site_timezone)

    from rich.console import Console

    console = Console()
    console.print(table)


@app.command()
def status(
    json_mode: JsonOpt = False,
    data_dir: DataDirOpt = None,
) -> None:
    """Show NVR status, database connection, and schema revision."""
    settings = load_settings(data_dir=data_dir)

    async def _run() -> StatusReport:
        async with open_runtime(settings) as rt:
            return await get_status(rt)

    report = asyncio.run(_run())
    emit(report, json_mode=json_mode, render_human=_render_status_human)
