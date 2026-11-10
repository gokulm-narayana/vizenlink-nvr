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
from vizenlink_nvr.cli.backup_cmd import backup_app
from vizenlink_nvr.cli.cameras import cameras_app
from vizenlink_nvr.cli.mediamtx_cmd import mediamtx_app
from vizenlink_nvr.cli.options import DataDirOpt, JsonOpt
from vizenlink_nvr.cli.output import emit
from vizenlink_nvr.cli.recording import recording_app
from vizenlink_nvr.cli.service_cmd import service_app
from vizenlink_nvr.cli.settings_cmd import settings_app
from vizenlink_nvr.cli.storage import storage_app
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.services.runtime import open_runtime
from vizenlink_nvr.services.status import StatusReport, get_status

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="VizenLink NVR Admin CLI",
)

app.add_typer(cameras_app, name="cameras")
app.add_typer(settings_app, name="settings")
app.add_typer(mediamtx_app, name="mediamtx")
app.add_typer(storage_app, name="storage")
app.add_typer(recording_app, name="recording")
app.add_typer(service_app, name="service")
app.add_typer(backup_app, name="backup")


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


@app.command(name="run")
def run_cmd(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Bind host address"),  # noqa: S104
    port: int = typer.Option(8000, "--port", "-p", help="Bind port number"),
    data_dir: DataDirOpt = None,
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development"),
    no_mdns: bool = typer.Option(False, "--no-mdns", help="Disable mDNS LAN discovery advertiser"),
) -> None:
    """Run VizenLink NVR web application and REST API server."""
    import logging

    import uvicorn
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from vizenlink_nvr.api.app import create_app
    from vizenlink_nvr.db.engine import create_engine_for, upgrade_to_head
    from vizenlink_nvr.network.mdns import NvrMdnsAdvertiser
    from vizenlink_nvr.paths import db_path, ensure_data_dir

    settings = load_settings(data_dir=data_dir)
    ensure_data_dir(settings)
    db_p = db_path(settings)
    upgrade_to_head(db_p)
    engine = create_engine_for(db_p)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    server_app = create_app(session_factory=session_factory)

    mdns = None
    if not no_mdns:
        try:
            mdns = NvrMdnsAdvertiser(nvr_id="vizenlink-nvr", port=port)
            mdns.start()
        except Exception as exc:
            logging.getLogger(__name__).warning("mDNS advertisement failed to start: %s", exc)

    try:
        print("\n========================================================")
        print(f"🚀 VizenLink NVR VMS Running at: http://{host}:{port}")
        print(f"📁 Data Directory: {settings.data_dir}")
        print(f"📖 REST API Docs: http://{host}:{port}/docs")
        print(f"🖥️  Web UI: http://{host}:{port}/")
        print("========================================================\n")
        uvicorn.run(server_app, host=host, port=port, reload=reload)
    finally:
        if mdns is not None:
            mdns.stop()
