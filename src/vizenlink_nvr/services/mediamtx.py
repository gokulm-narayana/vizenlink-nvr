"""MediaMTX service check and inspection operations."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from vizenlink_nvr.media.binary import binary_version, resolve_binary, validate_config
from vizenlink_nvr.media.config import (
    MediaMtxPorts,
    build_config,
    hash_control_password,
    write_config,
)
from vizenlink_nvr.paths import mediamtx_dir

if TYPE_CHECKING:
    from vizenlink_nvr.services.runtime import Runtime


class ProbeResult(BaseModel):
    """Result of an individual protocol or endpoint probe."""

    name: str
    expected: str
    actual: str
    ok: bool


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
    used_ports = ports or MediaMtxPorts()
    random_pw = secrets.token_urlsafe(24)
    pw_hash = hash_control_password(random_pw)
    cfg = build_config(used_ports, pw_hash)

    cfg_dir = mediamtx_dir(rt.settings)
    cfg_path = cfg_dir / "mediamtx.yml"
    write_config(cfg_path, cfg)

    binary = resolve_binary(rt.settings)
    version = binary_version(binary)

    validate_ok, validate_output = validate_config(binary, cfg_path)

    probes_list: list[ProbeResult] | None = None
    all_ok = validate_ok

    if probe:
        # Deferred import so 01-09 works without 01-10 modules present
        from vizenlink_nvr.media.check import run_probes  # type: ignore[import-untyped]
        from vizenlink_nvr.media.process import MediaMtxProcess  # type: ignore[import-untyped]

        async with MediaMtxProcess(binary, cfg_path):
            probes_list = await run_probes(used_ports, random_pw)
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
