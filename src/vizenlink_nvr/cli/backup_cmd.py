"""CLI commands for database backup, restore, and snapshot inspection (FND-06)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from vizenlink_nvr.cli.options import DataDirOpt, JsonOpt
from vizenlink_nvr.cli.output import emit
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.paths import db_path
from vizenlink_nvr.services.backup import create_backup, list_backups, restore_backup

backup_app = typer.Typer(
    no_args_is_help=True,
    help="Manage NVR database backups, manifests, and restoration.",
)


@backup_app.command(name="create")
def backup_create_cmd(
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--out",
            "-o",
            help="Directory to save backup snapshot. Defaults to <data_dir>/backups.",
        ),
    ] = None,
    data_dir: DataDirOpt = None,
    json_mode: JsonOpt = False,
) -> None:
    """Create an atomic SQLite online backup snapshot and manifest."""
    settings = load_settings(data_dir=data_dir)
    database_file = db_path(settings)

    if not database_file.exists():
        typer.echo(f"Database file does not exist: {database_file}", err=True)
        raise typer.Exit(code=1)

    backup_file, meta = create_backup(database_file, output_dir=output_dir)
    human = (
        f"Backup created: {backup_file.name}\n"
        f"Path: {backup_file}\n"
        f"Size: {meta['size_bytes']} bytes\n"
        f"SHA-256: {meta['sha256']}\n"
        f"Schema Revision: {meta.get('schema_revision')}"
    )
    emit(meta, json_mode=json_mode, render_human=lambda _: print(human))


@backup_app.command(name="restore")
def backup_restore_cmd(
    backup_file: Annotated[
        Path,
        typer.Option(
            "--file",
            "-f",
            help="Path to the backup SQLite database file to restore.",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Bypass interactive confirmation prompt.",
        ),
    ] = False,
    data_dir: DataDirOpt = None,
    json_mode: JsonOpt = False,
) -> None:
    """Safely restore a database from a verified backup snapshot."""
    settings = load_settings(data_dir=data_dir)
    target_database = db_path(settings)

    if not force and not json_mode:
        confirm = typer.confirm(
            f"Are you sure you want to restore {backup_file.name} over {target_database}? "
            "A rollback copy will be saved."
        )
        if not confirm:
            typer.echo("Restore cancelled.")
            raise typer.Exit(code=0)

    try:
        report = restore_backup(backup_file, target_database)
    except Exception as exc:
        typer.echo(f"Restore failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    human = (
        f"Successfully restored database to: {target_database}\n"
        f"Source: {backup_file}\n"
        f"Rollback file: {report.get('rollback_created')}\n"
        f"Integrity check: PASS"
    )
    emit(report, json_mode=json_mode, render_human=lambda _: print(human))


@backup_app.command(name="list")
def backup_list_cmd(
    backup_dir: Annotated[
        Path | None,
        typer.Option(
            "--dir",
            "-d",
            help="Directory where backups are stored. Defaults to <data_dir>/backups.",
        ),
    ] = None,
    data_dir: DataDirOpt = None,
    json_mode: JsonOpt = False,
) -> None:
    """List available database backups."""
    settings = load_settings(data_dir=data_dir)
    target_dir = backup_dir or (settings.data_dir / "backups")
    backups = list_backups(target_dir)

    result = {"backups": backups, "count": len(backups), "directory": str(target_dir)}

    def _render(data: dict) -> None:  # type: ignore[type-arg]
        if not data["backups"]:
            print(f"No backups found in {data['directory']}.")
            return
        print(f"Found {data['count']} backup(s) in {data['directory']}:\n")
        for b in data["backups"]:
            print(f"• {b['filename']} ({b['size_bytes']} bytes)")
            print(f"  Created: {b.get('created_at')}")
            print(f"  Revision: {b.get('schema_revision')}")
            print(f"  SHA-256: {b.get('sha256')}\n")

    emit(result, json_mode=json_mode, render_human=_render)

