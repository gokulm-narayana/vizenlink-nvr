"""CLI prompt helpers for secret input and password collection."""

import sys

import typer
from pydantic import SecretStr


class PasswordMismatch(Exception):
    """Raised when password confirmation does not match the new password."""


def read_secret(prompt: str, *, stdin_mode: bool) -> SecretStr:
    """Read a sensitive secret value without echoing to stdout.

    In stdin mode, reads a single line from standard input.
    In interactive mode, prompts on stderr with input masked.
    """
    if stdin_mode:
        line = sys.stdin.readline()
        if not line:
            raise ValueError("Unexpected EOF reading password from stdin")
        return SecretStr(line.rstrip("\r\n"))

    entered = typer.prompt(prompt, hide_input=True, err=True)
    return SecretStr(entered)


class CliPasswordProvider:
    """Password provider reading secrets interactively or via stdin."""

    def __init__(self, stdin_mode: bool = False) -> None:
        self.stdin_mode = stdin_mode

    async def current_password(self) -> SecretStr:
        """Prompt user for existing camera password."""
        return read_secret("Camera password: ", stdin_mode=self.stdin_mode)

    async def new_password(self) -> SecretStr:
        """Prompt user for new camera password with confirmation."""
        p1 = read_secret("New camera password: ", stdin_mode=self.stdin_mode)
        p2 = read_secret("Confirm new camera password: ", stdin_mode=self.stdin_mode)
        if p1.get_secret_value() != p2.get_secret_value():
            raise PasswordMismatch("Passwords do not match")
        return p1
