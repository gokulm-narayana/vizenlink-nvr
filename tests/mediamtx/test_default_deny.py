"""Live MediaMTX tests proving strict default-deny and negative-control failure detection."""

from __future__ import annotations

import importlib.util
import secrets
import socket
from pathlib import Path

import pytest

from vizenlink_nvr.config import load_settings
from vizenlink_nvr.media.binary import resolve_binary
from vizenlink_nvr.media.check import listener_lines_ok, run_probes
from vizenlink_nvr.media.config import (
    MediaMtxPorts,
    build_config,
    hash_control_password,
    write_config,
)
from vizenlink_nvr.media.process import MediaMtxProcess, live_processes

_permissive_path = Path(__file__).parent / "permissive.py"
_spec = importlib.util.spec_from_file_location("permissive", _permissive_path)
assert _spec and _spec.loader
_permissive = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_permissive)
build_permissive_config = _permissive.build_permissive_config

pytestmark = [pytest.mark.mediamtx, pytest.mark.timeout(120)]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _random_ports() -> MediaMtxPorts:
    return MediaMtxPorts(
        api=_free_port(),
        playback=_free_port(),
        rtsp=_free_port(),
        hls=_free_port(),
        webrtc=_free_port(),
        webrtc_udp=_free_port(),
    )


@pytest.mark.asyncio
async def test_live_default_deny_probes(tmp_path: Path) -> None:
    """All live rejection probes against default-deny configuration pass with exact statuses."""
    ports = _random_ports()
    control_pw = secrets.token_urlsafe(24)
    pw_hash = hash_control_password(control_pw)

    cfg = build_config(ports, pw_hash)
    cfg_path = tmp_path / "mediamtx.yml"
    write_config(cfg_path, cfg)

    settings = load_settings(data_dir=tmp_path)
    binary = resolve_binary(settings)

    async with MediaMtxProcess(binary, cfg_path) as proc:
        probes = await run_probes(ports, control_pw)
        log_res = listener_lines_ok(proc.log_lines)
        probes.append(log_res)

        # Assert every probe passed
        failed = [f"{p.name} (exp: {p.expected}, act: {p.actual})" for p in probes if not p.ok]
        assert not failed, f"Probes failed: {failed}"

    # Clean process shutdown
    assert len(live_processes()) == 0


@pytest.mark.asyncio
async def test_negative_control_fails_probes(tmp_path: Path) -> None:
    """Negative-control permissive configuration causes probes to fail (proving tests are sensitive)."""
    ports = _random_ports()
    cfg = build_permissive_config(ports)
    cfg_path = tmp_path / "permissive.yml"
    write_config(cfg_path, cfg)

    settings = load_settings(data_dir=tmp_path)
    binary = resolve_binary(settings)

    async with MediaMtxProcess(binary, cfg_path):
        probes = await run_probes(ports, "dummy-password")

        # Map probes by name
        results = {p.name: p for p in probes}

        # ANNOUNCE must succeed (200 OK) under permissive, thus failing the default-deny probe (expected 401)
        announce_probe = results["rtsp_announce_anonymous"]
        assert announce_probe.ok is False, "Permissive ANNOUNCE should fail 401 check"
        assert "200" in announce_probe.actual

        # Anonymous API must succeed (200 OK) under permissive, failing the 401 check
        api_probe = results["api_anonymous"]
        assert api_probe.ok is False, "Permissive API should fail 401 check"
        assert api_probe.actual == "200"

    assert len(live_processes()) == 0
