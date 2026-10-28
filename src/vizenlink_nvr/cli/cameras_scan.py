"""Camera discovery scan command."""

import asyncio
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from vizenlink_nvr.cli.cameras import cameras_app
from vizenlink_nvr.cli.options import DataDirOpt, JsonOpt
from vizenlink_nvr.cli.output import emit, err_console
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.services.scan import run_scan


@cameras_app.command("scan")
def scan_command(
    thorough: bool = typer.Option(
        False,
        "--thorough",
        help="Run unicast subnet sweep in addition to multicast.",
    ),
    timeout: float | None = typer.Option(
        None,
        "--timeout",
        help="Timeout in seconds for probe operations.",
    ),
    json_mode: JsonOpt = False,
    data_dir: DataDirOpt = None,
) -> None:
    """Scan local network for VizenLink and NuraEye cameras."""
    err_console.print("Scanning...")
    settings = load_settings(data_dir=data_dir)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            report = pool.submit(
                asyncio.run,
                run_scan(settings, thorough=thorough, timeout=timeout),
            ).result()
    else:
        report = asyncio.run(run_scan(settings, thorough=thorough, timeout=timeout))

    payload = [c.model_dump(mode="json") for c in report.cameras]

    def _render_human(_: Any) -> None:
        table = Table(title="Discovered Cameras", show_header=True)
        table.add_column("Model")
        table.add_column("Name")
        table.add_column("IP")
        table.add_column("Port")
        table.add_column("MAC")

        for cam in report.cameras:
            table.add_row(cam.model, cam.name, cam.host, str(cam.port), cam.mac)

        console = Console()
        console.print(table)

        if not report.cameras:
            err_console.print(
                "No cameras found.\n"
                "Hint: If cameras are on Wi-Fi or macOS, check Local Network permissions "
                "or multicast blocking. Try '--thorough' or 'nvr cameras add --host <ip>'."
            )

    emit(payload, json_mode=json_mode, render_human=_render_human)


__all__ = ["cameras_app"]
