"""NVR configuration."""

from pathlib import Path
from typing import Literal

import platformdirs
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class NvrSettings(BaseSettings):
    """Runtime settings for VizenLink NVR."""

    model_config = SettingsConfigDict(
        env_prefix="NVR_",
        extra="ignore",
    )

    data_dir: Path = Field(
        default_factory=lambda: Path(platformdirs.user_data_dir("vizenlink-nvr", appauthor=False))
    )
    secrets_backend: Literal["auto", "keyring", "file"] = "auto"
    mediamtx_bin: Path | None = None
    discovery_port: int = 3702
    discovery_multicast_group: str = "239.255.255.250"
    discovery_unicast_hosts: list[str] | None = None


def load_settings(data_dir: Path | None = None) -> NvrSettings:
    """Load settings with optional data_dir override."""
    if data_dir is not None:
        return NvrSettings(data_dir=Path(data_dir))
    return NvrSettings()
