"""Reusable CLI options for Typer commands."""

from pathlib import Path
from typing import Annotated

import typer

JsonOpt = Annotated[
    bool,
    typer.Option(
        "--json",
        help="Emit output as clean JSON to stdout.",
    ),
]

DataDirOpt = Annotated[
    Path | None,
    typer.Option(
        "--data-dir",
        envvar="NVR_DATA_DIR",
        help="Path to NVR data directory.",
    ),
]
