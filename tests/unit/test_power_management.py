"""Unit tests for host power management and sleep inhibition (FND-06)."""

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from vizenlink_nvr.service.power import (
    ES_AWAYMODE_REQUIRED,
    ES_CONTINUOUS,
    ES_SYSTEM_REQUIRED,
    PowerManager,
)


def test_power_manager_darwin() -> None:
    pm = PowerManager(target_os="darwin")
    assert not pm.is_inhibited

    fake_proc = MagicMock(spec=subprocess.Popen)
    fake_proc.pid = 99999

    with (
        patch("shutil.which", return_value="/usr/bin/caffeinate"),
        patch("subprocess.Popen", return_value=fake_proc) as mock_popen,
    ):
        ok = pm.inhibit_sleep("Testing")
        assert ok is True
        assert pm.is_inhibited is True
        mock_popen.assert_called_once()
        cmd_args = mock_popen.call_args[0][0]
        assert "caffeinate" in cmd_args[0]
        assert "-s" in cmd_args

        # Calling again while active should be idempotent
        ok2 = pm.inhibit_sleep("Again")
        assert ok2 is True
        assert mock_popen.call_count == 1

        pm.release_sleep()
        assert not pm.is_inhibited
        fake_proc.terminate.assert_called_once()


def test_power_manager_linux() -> None:
    pm = PowerManager(target_os="linux")
    fake_proc = MagicMock(spec=subprocess.Popen)
    fake_proc.pid = 88888

    with (
        patch("shutil.which", return_value="/usr/bin/systemd-inhibit"),
        patch("subprocess.Popen", return_value=fake_proc) as mock_popen,
    ):
        ok = pm.inhibit_sleep("Continuous video recording")
        assert ok is True
        assert pm.is_inhibited is True
        mock_popen.assert_called_once()
        cmd_args = mock_popen.call_args[0][0]
        assert "systemd-inhibit" in cmd_args[0]
        assert "--what=idle:sleep" in cmd_args

        pm.release_sleep()
        assert not pm.is_inhibited
        fake_proc.terminate.assert_called_once()


def test_power_manager_windows() -> None:
    pm = PowerManager(target_os="windows")
    fake_kernel32 = MagicMock()
    fake_kernel32.SetThreadExecutionState.return_value = 1

    mock_windll = MagicMock()
    mock_windll.kernel32 = fake_kernel32

    with patch.dict(sys.modules, {"ctypes": MagicMock(windll=mock_windll)}):
        ok = pm.inhibit_sleep("Active recording")
        assert ok is True
        assert pm.is_inhibited is True

        expected_flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
        fake_kernel32.SetThreadExecutionState.assert_called_with(expected_flags)

        pm.release_sleep()
        assert not pm.is_inhibited
        fake_kernel32.SetThreadExecutionState.assert_called_with(ES_CONTINUOUS)


def test_power_manager_sync_context_manager() -> None:
    pm = PowerManager(target_os="darwin")
    fake_proc = MagicMock()
    fake_proc.pid = 99999

    with (
        patch("shutil.which", return_value="/usr/bin/caffeinate"),
        patch("subprocess.Popen", return_value=fake_proc),
    ):
        with pm as active_pm:
            assert active_pm.is_inhibited is True

        assert not pm.is_inhibited
        fake_proc.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_power_manager_async_context_manager() -> None:
    pm = PowerManager(target_os="darwin")
    fake_proc = MagicMock()
    fake_proc.pid = 99999

    with (
        patch("shutil.which", return_value="/usr/bin/caffeinate"),
        patch("subprocess.Popen", return_value=fake_proc),
    ):
        async with pm as active_pm:
            assert active_pm.is_inhibited is True

        assert not pm.is_inhibited
        fake_proc.terminate.assert_called_once()


def test_power_manager_missing_binary() -> None:
    pm = PowerManager(target_os="linux")
    with patch("shutil.which", return_value=None):
        ok = pm.inhibit_sleep()
        assert ok is False
        assert not pm.is_inhibited
