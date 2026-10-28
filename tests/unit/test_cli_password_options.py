"""Unit tests asserting CLI options enforce no-password-arguments and flag-only parameters (D-16)."""

from typing import Any

import typer.main
from typer.core import TyperOption
from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app


def _walk_commands(group_or_cmd: Any) -> list[Any]:
    """Recursively collect all leaf click/typer Commands."""
    cmds: list[Any] = []
    if hasattr(group_or_cmd, "commands"):
        for sub_cmd in group_or_cmd.commands.values():
            cmds.extend(_walk_commands(sub_cmd))
    else:
        cmds.append(group_or_cmd)
    return cmds


def test_no_positional_arguments_and_no_password_flag_except_stdin() -> None:
    """Assert all CLI commands use TyperOption and no password flags except --password-stdin (D-16)."""
    click_root = typer.main.get_command(app)
    leaf_commands = _walk_commands(click_root)

    assert len(leaf_commands) > 0, "No CLI commands discovered"

    for cmd in leaf_commands:
        for param in cmd.params:
            # 1. No positional Argument allowed anywhere (all non-password inputs are flags)
            assert isinstance(param, TyperOption), (
                f"Command '{cmd.name}' has positional argument '{param.name}'; expected TyperOption (D-16)"
            )

            # 2. No parameter containing 'password' except '--password-stdin'
            param_names = [param.name] + list(param.opts) + list(param.secondary_opts)
            for p_name in param_names:
                if "password" in p_name.lower():
                    clean_name = p_name.lstrip("-")
                    assert clean_name in (
                        "password_stdin",
                        "password-stdin",
                    ), (
                        f"Command '{cmd.name}' has prohibited password parameter '{p_name}'; "
                        "only '--password-stdin' allowed (D-16)"
                    )


def test_positional_arguments_rejected_at_runtime() -> None:
    """Assert passing positional arguments to commands is rejected with non-zero exit."""
    runner = CliRunner()

    # cameras show positional serial
    res_show = runner.invoke(app, ["cameras", "show", "VZL-CAM-0001"])
    assert res_show.exit_code != 0
    assert "Got unexpected extra argument" in res_show.output or "Error" in res_show.output

    # cameras rename positional serial
    res_rename = runner.invoke(app, ["cameras", "rename", "VZL-CAM-0001"])
    assert res_rename.exit_code != 0

    # settings set-timezone positional zone
    res_tz = runner.invoke(app, ["settings", "set-timezone", "America/New_York"])
    assert res_tz.exit_code != 0
