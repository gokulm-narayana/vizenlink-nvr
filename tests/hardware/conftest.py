"""Pytest fixtures and configuration for real-camera hardware suite (D-20, D-24)."""

import contextlib
import os
import sys
from collections.abc import Generator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

# Ensure repository root is on sys.path for test imports
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tests.hardware.support.report import HwReport  # noqa: E402
from vizenlink_nvr.camera.connection import CameraConnection  # noqa: E402
from vizenlink_nvr.camera.http import CameraHttp, camera_ssl_context  # noqa: E402
from vizenlink_nvr.camera.onvif.device import OnvifDeviceClient  # noqa: E402
from vizenlink_nvr.timeutil import SystemClock  # noqa: E402


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Ensure all tests in tests/hardware are marked with 'hardware'."""
    hw_mark = pytest.mark.hardware
    for item in items:
        if str(item.fspath).find("tests/hardware") != -1 or "tests/hardware" in str(item.path):
            if "hardware" not in item.keywords:
                item.add_marker(hw_mark)


@dataclass
class HwConfig:
    host: str
    port: int
    username: str
    password: str

    @property
    def base_url(self) -> str:
        return f"https://{self.host}:{self.port}"


@dataclass
class CameraSnapshot:
    serial: str = ""
    name: str = ""
    location: str = ""
    accounts: list[str] = field(default_factory=list)
    mutation_occurred: bool = False


@pytest.fixture
def hw_env() -> HwConfig:
    """Fixture providing hardware camera configuration.

    Guaranteed to skip immediately without any network calls if NVR_HW_RUN_AUTHORIZED != 1
    or if NVR_HW_HOST is not set.
    """
    if os.environ.get("NVR_HW_RUN_AUTHORIZED") != "1":
        pytest.skip("Hardware execution requires NVR_HW_RUN_AUTHORIZED=1 (checkpoint approval)")
    host = os.environ.get("NVR_HW_HOST")
    if not host:
        pytest.skip("NVR_HW_HOST not set")
    password = os.environ.get("NVR_HW_PASSWORD")
    if not password:
        pytest.skip("NVR_HW_PASSWORD not set")

    port_raw = os.environ.get("NVR_HW_PORT", "443")
    try:
        port = int(port_raw)
    except ValueError:
        port = 443

    username = os.environ.get("NVR_HW_USER", "admin")
    return HwConfig(host=host, port=port, username=username, password=password)


@pytest.fixture
def hw_write(hw_env: HwConfig) -> HwConfig:
    """Gate for tests that modify hardware camera configuration."""
    if os.environ.get("NVR_HW_ALLOW_WRITE") != "1":
        pytest.skip("Hardware write tests require NVR_HW_ALLOW_WRITE=1")
    return hw_env


@pytest.fixture
def hw_reset(hw_env: HwConfig) -> HwConfig:
    """Gate for destructive tests that soft-reset the hardware camera."""
    if os.environ.get("NVR_HW_ALLOW_RESET") != "1":
        pytest.skip("Hardware reset tests require NVR_HW_ALLOW_RESET=1")
    return hw_env


@pytest.fixture(scope="session")
def hw_report() -> Generator[HwReport, None, None]:
    """Session fixture managing the hardware verification markdown report."""
    report = HwReport()
    yield report
    if os.environ.get("NVR_HW_RUN_AUTHORIZED") == "1":
        report.write()


@pytest.fixture(scope="session")
async def hw_camera_snapshot(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[CameraSnapshot, None, None]:
    """Snapshots hardware camera identity at session start, restores on session end if mutated."""
    snapshot = CameraSnapshot()

    # If run is not authorized or host not configured, do not connect
    if os.environ.get("NVR_HW_RUN_AUTHORIZED") != "1" or not os.environ.get("NVR_HW_HOST"):
        yield snapshot
        return

    host = os.environ["NVR_HW_HOST"]
    password = os.environ.get("NVR_HW_PASSWORD", "")
    port = int(os.environ.get("NVR_HW_PORT", "443"))
    username = os.environ.get("NVR_HW_USER", "admin")

    conn = CameraConnection(
        host=host,
        port=port,
        username=username,
        password=password,
    )
    http = CameraHttp(ssl_context=camera_ssl_context(None))
    clock = SystemClock()

    with contextlib.suppress(Exception):
        dev_client = OnvifDeviceClient(conn, http, clock)
        info = await dev_client.get_device_information()
        if info.is_success():
            snapshot.serial = info.unwrap().serial_number

        scopes = await dev_client.get_scopes()
        if scopes.is_success():
            for sc in scopes.unwrap():
                if sc.startswith("onvif://www.onvif.org/name/"):
                    snapshot.name = sc.removeprefix("onvif://www.onvif.org/name/")
                elif sc.startswith("onvif://www.onvif.org/location/"):
                    snapshot.location = sc.removeprefix("onvif://www.onvif.org/location/")

    yield snapshot

    # Teardown: restore name/location ONLY if mutations occurred
    if snapshot.mutation_occurred and (snapshot.name or snapshot.location):
        with contextlib.suppress(Exception):
            restore_scopes: list[str] = []
            if snapshot.name:
                restore_scopes.append(f"onvif://www.onvif.org/name/{snapshot.name}")
            if snapshot.location:
                restore_scopes.append(f"onvif://www.onvif.org/location/{snapshot.location}")
            await dev_client.set_scopes(restore_scopes)
