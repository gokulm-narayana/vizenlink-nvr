"""Filesystem permission enforcement for secrets directory and files."""

import getpass
import os
import subprocess
from pathlib import Path


class InsecureKeyFile(Exception):
    """Raised when key file has insecure permissions or invalid content."""


def ensure_private_dir(path: Path) -> None:
    """Ensure directory exists with restricted permissions (0700 on POSIX)."""
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(path, 0o700)


def ensure_private_file(path: Path) -> None:
    """Ensure file permissions are restricted to owner only (0600 on POSIX, ACL on Windows)."""
    if os.name == "posix":
        os.chmod(path, 0o600)
    elif os.name == "nt":
        user = getpass.getuser()
        subprocess.run(  # noqa: S603
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],  # noqa: S607
            shell=False,
            check=True,
            capture_output=True,
        )


def assert_private(path: Path) -> None:
    """Assert file has no group or other permissions on POSIX."""
    if os.name == "posix":
        st_mode = path.stat().st_mode
        if st_mode & 0o077 != 0:
            raise InsecureKeyFile(f"Insecure permissions on key file {path}: mode {oct(st_mode)}")
