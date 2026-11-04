"""MediaMTX service check and inspection operations."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from vizenlink_nvr.media.binary import binary_version, resolve_binary, validate_config
from vizenlink_nvr.media.check import ProbeResult, listener_lines_ok, run_probes
from vizenlink_nvr.media.config import (
    MediaMtxPorts,
    build_config,
    hash_control_password,
    write_config,
)
from vizenlink_nvr.media.process import MediaMtxProcess
from vizenlink_nvr.paths import mediamtx_dir

if TYPE_CHECKING:
    from vizenlink_nvr.services.runtime import Runtime


class MediaMtxCheckReport(BaseModel):
    """Aggregated report of MediaMTX binary, configuration, and probe checks."""

    config_path: Path
    binary_path: Path
    binary_version: str
    validate_ok: bool
    validate_output: str
    probes: list[ProbeResult] | None = None
    ok: bool


async def run_check(
    rt: Runtime,
    *,
    probe: bool = False,
    ports: MediaMtxPorts | None = None,
) -> MediaMtxCheckReport:
    """Generate configuration, validate against binary, and optionally run network probes."""
    import os

    if ports is not None:
        used_ports = ports
    elif os.environ.get("NVR_MEDIAMTX_TEST_PORTS"):
        parts = [int(p) for p in os.environ["NVR_MEDIAMTX_TEST_PORTS"].split(",")]
        used_ports = MediaMtxPorts(*parts)
    else:
        used_ports = MediaMtxPorts()

    random_pw = secrets.token_urlsafe(24)
    pw_hash = hash_control_password(random_pw)
    cfg = build_config(used_ports, pw_hash, auth_method="internal")

    cfg_dir = mediamtx_dir(rt.settings)
    cfg_path = cfg_dir / "mediamtx.yml"
    write_config(cfg_path, cfg)

    binary = resolve_binary(rt.settings)
    version = binary_version(binary)

    validate_ok, validate_output = validate_config(binary, cfg_path)

    probes_list: list[ProbeResult] | None = None
    all_ok = validate_ok

    if probe:
        async with MediaMtxProcess(binary, cfg_path) as proc:
            probes_list = await run_probes(used_ports, random_pw)
            listener_probe = listener_lines_ok(proc.log_lines)
            probes_list.append(listener_probe)
            if any(not p.ok for p in probes_list):
                all_ok = False

    return MediaMtxCheckReport(
        config_path=cfg_path,
        binary_path=binary,
        binary_version=version,
        validate_ok=validate_ok,
        validate_output=validate_output,
        probes=probes_list,
        ok=all_ok,
    )
