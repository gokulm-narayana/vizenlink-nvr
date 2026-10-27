"""CLI output formatting, stdout/stderr separation, and exit utilities."""

import json
import sys
from collections.abc import Callable
from typing import Any, NoReturn

from pydantic import BaseModel
from rich.console import Console

from vizenlink_nvr.cli.exitcodes import ExitCode

# err_console prints exclusively to stderr for progress, prompts, and errors
err_console = Console(stderr=True)


def emit(
    result: Any,
    *,
    json_mode: bool,
    render_human: Callable[[Any], None] | None = None,
) -> None:
    """Emit command result to stdout. Clean JSON if json_mode, else human renderer."""
    if json_mode:
        payload: Any
        if isinstance(result, BaseModel):
            payload = result.model_dump(mode="json")
        elif isinstance(result, (dict, list, int, float, str, bool)) or result is None:
            payload = result
        else:
            payload = str(result)
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        sys.stdout.flush()
    else:
        if render_human is not None:
            render_human(result)
        elif isinstance(result, BaseModel):
            sys.stdout.write(result.model_dump_json(indent=2) + "\n")
        else:
            sys.stdout.write(str(result) + "\n")
        sys.stdout.flush()


def fail(
    code: ExitCode,
    message: str,
    *,
    json_mode: bool,
    detail: dict[str, Any] | None = None,
) -> NoReturn:
    """Exit process with error code and format error appropriately."""
    if json_mode:
        payload: dict[str, Any] = {
            "error": message,
            "code": int(code),
        }
        if detail:
            payload["detail"] = detail
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        sys.stdout.flush()
    else:
        err_console.print(f"[bold red]Error:[/] {message}")
        if detail:
            err_console.print(f"[dim]{detail}[/]")
    sys.exit(int(code))
