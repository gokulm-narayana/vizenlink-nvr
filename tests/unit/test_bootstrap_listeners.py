"""Guard tests asserting bootstrap imports and status never open socket listeners."""

import socket
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app


def test_import_and_status_no_socket_listeners(
    cli: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assert running CLI status never invokes socket.bind or socket.listen."""

    def forbidden_bind(self: socket.socket, *args: object, **kwargs: object) -> None:
        pytest.fail(f"Forbidden socket.bind called during status: {args} {kwargs}")

    def forbidden_listen(self: socket.socket, *args: object, **kwargs: object) -> None:
        pytest.fail(f"Forbidden socket.listen called during status: {args} {kwargs}")

    monkeypatch.setattr(socket.socket, "bind", forbidden_bind)
    monkeypatch.setattr(socket.socket, "listen", forbidden_listen)

    test_dir = tmp_path / "bootstrap_guard"
    result = cli.invoke(app, ["status", "--json", "--data-dir", str(test_dir)])
    assert result.exit_code == 0


def test_subprocess_clean_import_no_listeners(tmp_path: Path) -> None:
    """Run isolated subprocess verifying modules import and status runs without binding sockets."""
    script = """
import socket, sys
def forbidden(*args, **kwargs):
    sys.stderr.write("FORBIDDEN SOCKET CALL\\n")
    sys.exit(99)
socket.socket.bind = forbidden
socket.socket.listen = forbidden

from vizenlink_nvr.cli.app import app
from typer.testing import CliRunner
runner = CliRunner()
res = runner.invoke(app, ["status", "--json", "--data-dir", sys.argv[1]])
if res.exit_code != 0:
    sys.exit(res.exit_code)
"""
    test_dir = tmp_path / "subprocess_guard"
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script, str(test_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"Failed with {proc.returncode}:\n{proc.stderr}\n{proc.stdout}"
    assert "FORBIDDEN SOCKET CALL" not in proc.stderr
