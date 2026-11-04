"""Cross-platform host power management and sleep inhibitor (FND-06)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from types import TracebackType
from typing import Any

from vizenlink_nvr.service.installer import TargetOS, detect_os

logger = logging.getLogger(__name__)

# Windows SetThreadExecutionState flags
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002
ES_AWAYMODE_REQUIRED = 0x00000040
ES_CONTINUOUS = 0x80000000


class PowerManager:
    """Inhibits operating system idle sleep and standby during active recording."""

    def __init__(self, target_os: TargetOS | None = None) -> None:
        self.target_os: TargetOS = target_os or detect_os()
        self._process: subprocess.Popen[Any] | None = None
        self._is_inhibited: bool = False

    @property
    def is_inhibited(self) -> bool:
        """Return True if host sleep is currently inhibited."""
        return self._is_inhibited

    def inhibit_sleep(self, reason: str = "Active camera recording") -> bool:
        """Inhibit system idle sleep across macOS, Linux, or Windows."""
        if self._is_inhibited:
            return True

        try:
            if self.target_os == "darwin":
                # caffeinate -d (display) -i (idle) -s (system sleep) -w <pid>
                caff_bin = shutil.which("caffeinate")
                if caff_bin:
                    self._process = subprocess.Popen(  # noqa: S603
                        [caff_bin, "-d", "-i", "-s", "-w", str(os.getpid())],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    self._is_inhibited = True
                    logger.info("macOS sleep inhibited via caffeinate (pid=%s)", self._process.pid)
                    return True
                logger.warning("caffeinate binary not found on macOS; sleep inhibitor unavailable")
                return False

            if self.target_os == "linux":
                inhibit_bin = shutil.which("systemd-inhibit")
                if inhibit_bin:
                    self._process = subprocess.Popen(  # noqa: S603
                        [
                            inhibit_bin,
                            "--what=idle:sleep",
                            f"--why={reason}",
                            "--mode=block",
                            "sleep",
                            "infinity",
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    self._is_inhibited = True
                    logger.info(
                        "Linux sleep inhibited via systemd-inhibit (pid=%s)",
                        self._process.pid,
                    )
                    return True
                logger.warning("systemd-inhibit not available; falling back to uninhibited operation")
                return False

            if self.target_os == "windows":
                import ctypes

                flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
                ret = ctypes.windll.kernel32.SetThreadExecutionState(flags)  # type: ignore[attr-defined]
                self._is_inhibited = bool(ret != 0)
                logger.info("Windows SetThreadExecutionState called (result=%s)", ret)
                return self._is_inhibited

        except Exception as exc:
            logger.error("Failed to inhibit sleep on %s: %s", self.target_os, exc)
            self._is_inhibited = False
            return False

        return False

    def release_sleep(self) -> None:
        """Release sleep inhibitor lock and terminate supervision child process."""
        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=2.0)
            except Exception:
                try:
                    self._process.kill()
                except Exception:  # noqa: S110
                    pass
            finally:
                self._process = None

        if self.target_os == "windows" and self._is_inhibited:
            try:
                import ctypes

                ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)  # type: ignore[attr-defined]
            except Exception as exc:
                logger.warning("Failed to reset Windows SetThreadExecutionState: %s", exc)

        self._is_inhibited = False
        logger.debug("Sleep inhibitor released on %s", self.target_os)

    def __enter__(self) -> PowerManager:
        self.inhibit_sleep()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.release_sleep()

    async def __aenter__(self) -> PowerManager:
        self.inhibit_sleep()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.release_sleep()

    def __del__(self) -> None:
        self.release_sleep()
