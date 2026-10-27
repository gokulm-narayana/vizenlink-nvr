"""Camera management subcommands."""

import typer

cameras_app = typer.Typer(
    no_args_is_help=True,
    help="Camera discovery, onboarding, and management.",
)


@cameras_app.callback()
def cameras_callback() -> None:
    """Manage cameras."""
