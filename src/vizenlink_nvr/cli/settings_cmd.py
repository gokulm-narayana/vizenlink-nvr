"""CLI settings subcommands."""

import asyncio
from typing import Annotated

import typer

from vizenlink_nvr.cli.exitcodes import ExitCode
from vizenlink_nvr.cli.options import DataDirOpt, JsonOpt
from vizenlink_nvr.cli.output import emit, fail
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.services.runtime import open_runtime
from vizenlink_nvr.services.settings import set_site_timezone
from vizenlink_nvr.timeutil import InvalidTimezone, validate_zone

settings_app = typer.Typer(
    no_args_is_help=True,
    help="Configure NVR system settings.",
)


@settings_app.callback()
def settings_callback() -> None:
    """Manage NVR settings."""


@settings_app.command(name="set-timezone")
def set_timezone(
    zone: Annotated[
        str,
        typer.Option(
            "--zone",
            help="IANA timezone name, e.g., Europe/London.",
        ),
    ],
    json_mode: JsonOpt = False,
    data_dir: DataDirOpt = None,
) -> None:
    """Set the NVR site timezone."""
    try:
        validate_zone(zone)
    except InvalidTimezone:
        fail(
            ExitCode.INVALID_INPUT,
            f"Unknown time zone: {zone}. Use an IANA name such as Europe/London.",
            json_mode=json_mode,
        )

    settings = load_settings(data_dir=data_dir)

    async def _run() -> str:
        async with open_runtime(settings) as rt:
            return await set_site_timezone(rt, zone)

    saved_zone = asyncio.run(_run())
    emit(
        {"site_timezone": saved_zone},
        json_mode=json_mode,
        render_human=lambda res: print(f"Site timezone set to {res['site_timezone']}"),
    )
