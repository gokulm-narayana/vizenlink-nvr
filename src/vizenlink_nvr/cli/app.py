"""VizenLink NVR CLI root application."""

import asyncio
import logging

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
from vizenlink_nvr.config import NvrSettings, load_settings
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


def _mdns_identity(settings: NvrSettings) -> tuple[str, str]:
    """Read recorder name from DB if present and derive a DNS-safe nvr_id."""
    import json
    import re
    import socket
    import sqlite3

    from vizenlink_nvr.paths import db_path

    name = "VizenLink-NVR"
    db_file = db_path(settings)
    if db_file.exists():
        try:
            with sqlite3.connect(f"file:{db_file}?mode=ro", uri=True, timeout=1.0) as conn:
                row = conn.execute("SELECT value FROM app_setting WHERE key = 'recorder_name'").fetchone()
            if row and row[0]:
                parsed = json.loads(row[0])
                if isinstance(parsed, str) and parsed.strip():
                    name = parsed.strip()
        except Exception as exc:
            logging.getLogger(__name__).debug("Could not read recorder_name from DB for mDNS: %s", exc)

    raw_host = socket.gethostname().split(".")[0].lower()
    sanitized = re.sub(r"[^a-z0-9-]+", "-", raw_host).strip("-")
    nvr_id = sanitized or "vizenlink-nvr"
    return nvr_id, name


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

    from vizenlink_nvr.api.app import create_app
    from vizenlink_nvr.log import configure_logging
    from vizenlink_nvr.network.mdns import NvrMdnsAdvertiser

    # Recorder, MediaMTX and camera errors are only visible if app logging is configured;
    # the handler also redacts credentials.
    configure_logging()
    settings = load_settings(data_dir=data_dir)
    lan_access = not host.startswith("127.") and host not in ("localhost", "::1")
    server_app = create_app(
        settings=settings,
        recorder_port=port,
        recorder_lan_access=lan_access,
    )

    mdns = None
    if not no_mdns and lan_access:
        try:
            nvr_id, mdns_name = _mdns_identity(settings)
            mdns = NvrMdnsAdvertiser(nvr_id=nvr_id, name=mdns_name, port=port)
            mdns.start()
        except Exception as exc:
            logging.getLogger(__name__).warning("mDNS advertisement failed to start: %s", exc)
            mdns = None

    server_app.state.mdns = mdns

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
