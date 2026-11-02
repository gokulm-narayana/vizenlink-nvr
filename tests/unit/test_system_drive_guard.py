"""Unit tests for system drive detection and protection guard across operating systems."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from vizenlink_nvr.services.storage import is_system_drive


def test_is_system_drive_posix_root(tmp_path: Path) -> None:
    """On POSIX systems, root path or default home dir is detected as system drive."""
    if os.name != "posix":
        return

    # Root filesystem "/" is the system drive
    assert is_system_drive(Path("/")) is True

    # Subdirectories on root partition match root st_dev
    root_dev = os.stat("/").st_dev
    if os.stat(tmp_path).st_dev == root_dev:
        assert is_system_drive(tmp_path) is True


def test_is_system_drive_posix_different_mount(monkeypatch: pytest.MonkeyPatch) -> None:
    """When target path has different st_dev from root, is_system_drive returns False."""
    stat_root = MagicMock()
    stat_root.st_dev = 100

    stat_mount = MagicMock()
    stat_mount.st_dev = 200

    def mock_stat(p: str | Path) -> os.stat_result:
        resolved = str(Path(p).resolve())
        if resolved == "/":
            return stat_root  # type: ignore[return-value]
        return stat_mount  # type: ignore[return-value]

    monkeypatch.setattr(os, "stat", mock_stat)
    monkeypatch.setattr(os, "name", "posix")

    assert is_system_drive(Path("/mnt/external_drive")) is False


def test_is_system_drive_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """On Windows, drive letter matches SystemDrive environment variable."""
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setenv("SystemDrive", "C:")

    # Mock Path.resolve() drive property
    path_c = MagicMock(spec=Path)
    path_c.resolve.return_value.drive = "C:"

    path_d = MagicMock(spec=Path)
    path_d.resolve.return_value.drive = "D:"

    assert is_system_drive(path_c) is True
    assert is_system_drive(path_d) is False
