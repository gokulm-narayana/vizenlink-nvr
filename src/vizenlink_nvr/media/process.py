"""MediaMTX process supervision and lifecycle management."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("vizenlink_nvr.mediamtx")
_TIMESTAMP = re.compile(r"^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2} ")

_LIVE_PROCESSES: list[subprocess.Popen[str]] = []
_LOCK: threading.Lock | None = None


def _get_lock() -> threading.Lock:
    global _LOCK
    if _LOCK is None:
        _LOCK = threading.Lock()
    return _LOCK


def live_processes() -> list[subprocess.Popen[str]]:
    """Return list of active MediaMTX processes."""
    with _get_lock():
        active: list[subprocess.Popen[str]] = []
        for p in _LIVE_PROCESSES:
            if p.poll() is None:
                active.append(p)
        _LIVE_PROCESSES[:] = active
        return list(_LIVE_PROCESSES)


class MediaMtxProcess:
    """Supervised execution of MediaMTX binary with log streaming and cleanup."""

    def __init__(
        self,
        binary: Path,
        config_path: Path,
        ready_timeout: float = 15.0,
    ) -> None:
        self.binary = binary
        self.config_path = config_path
        self.ready_timeout = ready_timeout
        self.popen: subprocess.Popen[str] | None = None
        self.log_lines: list[str] = []
        self._last_forwarded: str | None = None
        self._ready_event = threading.Event()
        self._reader_thread: threading.Thread | None = None

    def _reader(self) -> None:
        if self.popen is None or self.popen.stdout is None:
            return
        for line in iter(self.popen.stdout.readline, ""):
            line_str = line.strip()
            if line_str:
                self.log_lines.append(line_str)
                del self.log_lines[:-500]  # bounded: MediaMTX runs for weeks
                self._forward(line_str)
                if "[API] started" in line_str or "[api] started" in line_str.lower():
                    self._ready_event.set()
        self.popen.stdout.close()

    def _forward(self, line: str) -> None:
        """Surface MediaMTX warnings/errors (e.g. a camera source failing) in the NVR log.

        A failing source retries every few seconds; repeat lines are logged once.
        """
        if " ERR " not in line and " WAR " not in line:
            return
        message = _TIMESTAMP.sub("", line)
        if message == self._last_forwarded:
            return
        self._last_forwarded = message
        (logger.error if " ERR " in line else logger.warning)("%s", message)

    def start(self) -> None:
        """Start process and wait for ready line."""
        self.popen = subprocess.Popen(  # noqa: S603
            [str(self.binary), str(self.config_path)],
            # Recording filenames end in Z and are indexed as UTC.
            env={**os.environ, "TZ": "UTC"},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        with _get_lock():
            _LIVE_PROCESSES.append(self.popen)

        self._reader_thread = threading.Thread(target=self._reader, daemon=True)
        self._reader_thread.start()

        start_time = time.monotonic()
        while time.monotonic() - start_time < self.ready_timeout:
            if self._ready_event.wait(timeout=0.2):
                return
            if self.popen.poll() is not None:
                output = "\n".join(self.log_lines)
                raise RuntimeError(
                    f"MediaMTX process exited unexpectedly with code {self.popen.returncode}:\n{output}"
                )

        self.stop()
        output = "\n".join(self.log_lines)
        raise TimeoutError(f"MediaMTX failed to become ready within {self.ready_timeout}s:\n{output}")

    def stop(self) -> None:
        """Terminate process and clean up."""
        if self.popen is None:
            return

        with _get_lock():
            if self.popen in _LIVE_PROCESSES:
                _LIVE_PROCESSES.remove(self.popen)

        if self.popen.poll() is None:
            self.popen.terminate()
            try:
                self.popen.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self.popen.kill()
                self.popen.wait(timeout=2.0)

        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)

    def __enter__(self) -> MediaMtxProcess:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()

    async def __aenter__(self) -> MediaMtxProcess:
        self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()
