"""Directory and file paths for VizenLink NVR."""

import os
from pathlib import Path

from vizenlink_nvr.config import NvrSettings


def ensure_data_dir(settings: NvrSettings) -> Path:
    """Ensure data directory exists with restricted permissions on POSIX."""
    p = settings.data_dir
    p.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(p, 0o700)
    return p


def db_path(settings: NvrSettings) -> Path:
    """Return path to SQLite database."""
    return settings.data_dir / "nvr.db"


def secrets_dir(settings: NvrSettings) -> Path:
    """Return path to secrets storage directory."""
    return settings.data_dir / "secrets"


def mediamtx_dir(settings: NvrSettings) -> Path:
    """Return path to mediamtx working directory."""
    return settings.data_dir / "mediamtx"
