"""Integration tests exercising MediaMTX REST control API over loopback."""

from __future__ import annotations

import secrets
import socket
from pathlib import Path

import httpx
import pytest

from vizenlink_nvr.config import load_settings
from vizenlink_nvr.media.binary import resolve_binary
from vizenlink_nvr.media.config import (
    MediaMtxPorts,
    build_config,
    hash_control_password,
    write_config,
)
from vizenlink_nvr.media.process import MediaMtxProcess
from vizenlink_nvr.media.reconciler import MediaMtxReconciler, PathConfiguration

pytestmark = [pytest.mark.mediamtx, pytest.mark.timeout(60)]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.mark.asyncio
async def test_reconciler_api_live_sync(tmp_path: Path) -> None:
    """MediaMtxReconciler adds, patches, deletes, and reports unchanged paths against live MediaMTX."""
    api_port = _free_port()
    ports = MediaMtxPorts(
        api=api_port,
        playback=_free_port(),
        rtsp=_free_port(),
        hls=_free_port(),
        webrtc=_free_port(),
        webrtc_udp=_free_port(),
    )
    control_pw = secrets.token_urlsafe(24)
    cfg = build_config(ports, hash_control_password(control_pw), auth_method="internal")
    cfg_path = tmp_path / "mediamtx.yml"
    write_config(cfg_path, cfg)

    settings = load_settings(data_dir=tmp_path)
    binary = resolve_binary(settings)

    rec_root = tmp_path / "recordings"

    path1 = PathConfiguration(
        name="cam/cam1/main",
        source="rtsp://127.0.0.1:8554/cam1",
        source_on_demand=False,
        record=True,
        record_format="fmp4",
        record_part_duration="1s",
        record_segment_duration="60s",
        record_delete_after="0s",
        record_path=str(rec_root / "%path/%Y/%m/%d/%Y-%m-%dT%H-%M-%SZ-%f"),
        run_on_record_segment_complete="nvr recording hook-segment-complete",
    )

    path2 = PathConfiguration(
        name="cam/cam2/main",
        source="rtsp://127.0.0.1:8554/cam2",
        source_on_demand=False,
        record=False,
        record_format="fmp4",
        record_part_duration="1s",
        record_segment_duration="60s",
        record_delete_after="0s",
        record_path=str(rec_root / "%path/%Y/%m/%d/%Y-%m-%dT%H-%M-%SZ-%f"),
        run_on_record_segment_complete="nvr recording hook-segment-complete",
    )

    proc = MediaMtxProcess(binary, cfg_path)
    proc.start()

    try:
        api_base = f"http://127.0.0.1:{api_port}"
        auth = ("nvr-control", control_pw)

        async with httpx.AsyncClient() as client:
            reconciler = MediaMtxReconciler(client, api_base, auth)

            # 1. Initial reconciliation: add both paths
            res1 = await reconciler.reconcile({"cam/cam1/main": path1, "cam/cam2/main": path2})
            assert set(res1.added) == {"cam/cam1/main", "cam/cam2/main"}
            assert res1.patched == []
            assert res1.deleted == []

            # Verify path1 in MediaMTX
            p1_info = (await client.get(f"{api_base}/v3/config/paths/get/cam/cam1/main", auth=auth)).json()
            assert p1_info["record"] is True
            assert p1_info["recordFormat"] == "fmp4"
            assert p1_info["recordSegmentDuration"] == "1m0s"

            # 2. Idempotent re-run: 0 added, 0 patched, 0 deleted, 2 unchanged
            res2 = await reconciler.reconcile({"cam/cam1/main": path1, "cam/cam2/main": path2})
            assert res2.added == []
            assert res2.patched == []
            assert res2.deleted == []
            assert set(res2.unchanged) == {"cam/cam1/main", "cam/cam2/main"}

            # 3. Modify path1: toggle record to False
            path1_off = PathConfiguration(
                name="cam/cam1/main",
                source=path1.source,
                source_on_demand=path1.source_on_demand,
                record=False,  # Toggled off
                record_format=path1.record_format,
                record_part_duration=path1.record_part_duration,
                record_segment_duration=path1.record_segment_duration,
                record_delete_after=path1.record_delete_after,
                record_path=path1.record_path,
                run_on_record_segment_complete=path1.run_on_record_segment_complete,
            )
            res3 = await reconciler.reconcile({"cam/cam1/main": path1_off, "cam/cam2/main": path2})
            assert res3.patched == ["cam/cam1/main"]
            assert res3.unchanged == ["cam/cam2/main"]

            # Verify update applied in MediaMTX
            p1_updated = (await client.get(f"{api_base}/v3/config/paths/get/cam/cam1/main", auth=auth)).json()
            assert p1_updated["record"] is False

            # 4. Remove path2: delete from MediaMTX
            res4 = await reconciler.reconcile({"cam/cam1/main": path1_off})
            assert res4.deleted == ["cam/cam2/main"]
            assert res4.unchanged == ["cam/cam1/main"]

            # Verify path2 deleted
            p2_del = await client.get(f"{api_base}/v3/config/paths/get/cam/cam2/main", auth=auth)
            assert p2_del.status_code == 404
    finally:
        proc.stop()
