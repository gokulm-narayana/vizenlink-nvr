"""Pytest shared fixtures for VizenLink NVR."""

from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vizenlink_nvr.config import NvrSettings, load_settings
from vizenlink_nvr.timeutil import UTC, FakeClock

pytest_plugins = ["fake_camera.pytest_plugin"]


@pytest.fixture(autouse=True)
def setup_nvr_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Set isolated environment variables for NVR tests so the real system is never touched."""
    test_data_dir = tmp_path / "data"
    test_data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("NVR_SECRETS_BACKEND", "file")
    monkeypatch.setenv("NVR_DATA_DIR", str(test_data_dir))
    return test_data_dir


@pytest.fixture
def data_dir(setup_nvr_env: Path) -> Path:
    """Return isolated data directory path."""
    return setup_nvr_env


@pytest.fixture
def settings(data_dir: Path) -> NvrSettings:
    """Return NvrSettings pointing to the isolated data directory."""
    return load_settings(data_dir)


@pytest.fixture
def fake_clock() -> FakeClock:
    """Return FakeClock initialized to 2026-01-01T00:00:00Z."""
    return FakeClock(datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC))


@pytest.fixture
def cli() -> CliRunner:
    """Return isolated Typer CLI runner."""
    return CliRunner()
