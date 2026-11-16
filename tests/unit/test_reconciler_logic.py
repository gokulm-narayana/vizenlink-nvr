"""Unit tests for declarative MediaMTX reconciler diff logic and desired paths computation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.db.engine import create_engine_for
from vizenlink_nvr.db.models import Base, Camera, CameraStream
from vizenlink_nvr.media.reconciler import (
    MediaMtxReconciler,
    PathConfiguration,
    _needs_patch,
    compute_desired_paths,
)
from vizenlink_nvr.services.settings import CLIP_MINUTES_KEY, put_setting
from vizenlink_nvr.timeutil import utc_now


def test_needs_patch_logic() -> None:
    """_needs_patch returns True only when significant fields differ."""
    base_cur = {
        "source": "rtsp://192.168.1.10:554/live",
        "sourceOnDemand": False,
        "record": True,
        "recordFormat": "fmp4",
        "recordPartDuration": "1s",
        "recordSegmentDuration": "60s",
        "recordDeleteAfter": "0s",
        "recordPath": "/rec/%path/%Y-%m-%d-%f",
        "runOnRecordSegmentComplete": "nvr recording hook-segment-complete",
        "sourceFingerprint": "",
    }
    desired = dict(base_cur)

    # Identical: no patch needed
    assert _needs_patch(base_cur, desired) is False

    # Record toggle: patch needed
    assert _needs_patch(base_cur, {**desired, "record": False}) is True

    # Source URL change: patch needed
    assert _needs_patch(base_cur, {**desired, "source": "rtsp://192.168.1.11:554/live"}) is True

    # Record path change: patch needed
    assert _needs_patch(base_cur, {**desired, "recordPath": "/new/%path/%Y-%m-%d-%f"}) is True


@pytest.mark.asyncio
async def test_compute_desired_paths(tmp_path: Path) -> None:
    """compute_desired_paths builds main and sub PathConfiguration objects for active cameras."""
    db_file = tmp_path / "test_reconciler_db.db"
    engine = create_engine_for(db_file)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    now = utc_now()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        cam_active = Camera(
            serial="VZL-CAM-001",
            host="192.168.1.50",
            https_port=443,
            mac="AA:BB:CC:DD:EE:01",
            name="Front Gate",
            state="active",
            added_at=now,
            host_updated_at=now,
            tls_fingerprint_sha256="fp_front",
        )
        cam_inactive = Camera(
            serial="VZL-CAM-002",
            host="192.168.1.51",
            https_port=443,
            mac="AA:BB:CC:DD:EE:02",
            name="Old Cam",
            state="unreachable",
            added_at=now,
            host_updated_at=now,
            tls_fingerprint_sha256="fp_old",
        )
        session.add_all([cam_active, cam_inactive])

        main_stream = CameraStream(
            serial="VZL-CAM-001",
            role="main",
            profile_token="prof1",
            profile_name="MainProfile",
            venc_token="venc1",
            codec="H264",
            width=1920,
            height=1080,
            transport="tcp",
            scheme="rtsps",
            port=443,
            path="/live/main",
            source="nuraeye",
            sub_is_main=False,
            probed_at=now,
            tls_fingerprint_sha256="fp_main_rtsps",
        )
        sub_stream = CameraStream(
            serial="VZL-CAM-001",
            role="sub",
            profile_token="prof2",
            profile_name="SubProfile",
            venc_token="venc2",
            codec="H264",
            width=640,
            height=360,
            transport="tcp",
            scheme="rtsps",
            port=443,
            path="/live/sub",
            source="nuraeye",
            sub_is_main=False,
            probed_at=now,
        )
        session.add_all([main_stream, sub_stream])
        await session.commit()

        # Compute desired paths with volume_ok=True
        storage_root = tmp_path / "rec"
        desired = await compute_desired_paths(session, storage_root, volume_ok=True, now=now)

        # Inactive camera excluded
        assert "cam/vzl-cam-002/main" not in desired

        # Active camera has main and sub
        assert "cam/vzl-cam-001/main" in desired
        assert "cam/vzl-cam-001/sub" in desired

        main_cfg = desired["cam/vzl-cam-001/main"]
        assert main_cfg.source == "rtsps://192.168.1.50:443/live/main"
        assert main_cfg.source_on_demand is False
        assert main_cfg.record is False  # No RecordingSettings row yet, defaults to False
        # The RTSPS port's own pin, never the camera's HTTPS pin ("fp_front"):
        # VizenLink cameras use a different certificate for video.
        assert main_cfg.source_fingerprint == "fp_main_rtsps"

        sub_cfg = desired["cam/vzl-cam-001/sub"]
        assert sub_cfg.source == "rtsps://192.168.1.50:443/live/sub"
        assert sub_cfg.source_on_demand is True
        assert sub_cfg.record is False

        # Clip length: 1 minute unless the recorder-wide setting says otherwise.
        assert main_cfg.record_segment_duration == "60s"
        await put_setting(session, CLIP_MINUTES_KEY, 30)
        await session.commit()
        longer = await compute_desired_paths(session, storage_root, volume_ok=True, now=now)
        assert longer["cam/vzl-cam-001/main"].record_segment_duration == "1800s"
        assert longer["cam/vzl-cam-001/main"].to_api_dict()["recordSegmentDuration"] == "1800s"

        # When volume_ok=False, record is forced False
        desired_unhealthy = await compute_desired_paths(session, storage_root, volume_ok=False, now=now)
        assert desired_unhealthy["cam/vzl-cam-001/main"].record is False

    await engine.dispose()


@pytest.mark.asyncio
async def test_reconciler_diff_actions() -> None:
    """MediaMtxReconciler identifies added, patched, deleted, and unchanged paths."""
    mock_client = AsyncMock()

    # Initial state in MediaMTX:
    # - all_others (built-in, unmanaged)
    # - cam/existing/main (unchanged)
    # - cam/tomodify/main (needs patch)
    # - cam/deleted/main (unwanted, should delete)
    existing_items = [
        {"name": "all_others", "record": False},
        {
            "name": "cam/existing/main",
            "source": "rtsp://10.0.0.1/live",
            "sourceOnDemand": False,
            "record": True,
            "recordFormat": "fmp4",
            "recordPartDuration": "1s",
            "recordSegmentDuration": "60s",
            "recordDeleteAfter": "0s",
            "runOnRecordSegmentComplete": "nvr recording hook-segment-complete",
            "recordPath": "/rec/%path/%Y-%m-%d-%f",
            "sourceFingerprint": "",
        },
        {
            "name": "cam/tomodify/main",
            "source": "rtsp://10.0.0.2/live",
            "sourceOnDemand": False,
            "record": False,  # Was False, now should be True
            "recordFormat": "fmp4",
            "recordPartDuration": "1s",
            "recordSegmentDuration": "60s",
            "recordDeleteAfter": "0s",
            "runOnRecordSegmentComplete": "nvr recording hook-segment-complete",
        },
        {"name": "cam/deleted/main", "source": "rtsp://10.0.0.3/live"},
    ]

    list_resp = MagicMock()
    list_resp.json.return_value = {"items": existing_items}
    list_resp.raise_for_status = MagicMock()
    mock_client.get.return_value = list_resp

    post_resp = MagicMock()
    post_resp.raise_for_status = MagicMock()
    mock_client.post.return_value = post_resp

    patch_resp = MagicMock()
    patch_resp.raise_for_status = MagicMock()
    mock_client.patch.return_value = patch_resp

    del_resp = MagicMock()
    del_resp.raise_for_status = MagicMock()
    mock_client.delete.return_value = del_resp

    desired = {
        "cam/existing/main": PathConfiguration(
            name="cam/existing/main",
            source="rtsp://10.0.0.1/live",
            source_on_demand=False,
            record=True,
            record_path="/rec/%path/%Y-%m-%d-%f",
        ),
        "cam/tomodify/main": PathConfiguration(
            name="cam/tomodify/main",
            source="rtsp://10.0.0.2/live",
            source_on_demand=False,
            record=True,  # Patched
        ),
        "cam/new/main": PathConfiguration(
            name="cam/new/main",
            source="rtsp://10.0.0.4/live",
            source_on_demand=False,
            record=True,  # Added
        ),
    }

    reconciler = MediaMtxReconciler(
        client=mock_client,
        api_base="http://127.0.0.1:9997",
        control_auth=("nvr-control", "secret"),
    )

    result = await reconciler.reconcile(desired)

    assert result.added == ["cam/new/main"]
    assert result.patched == ["cam/tomodify/main"]
    assert result.deleted == ["cam/deleted/main"]
    assert result.unchanged == ["cam/existing/main"]

    mock_client.post.assert_awaited_once()
    mock_client.patch.assert_awaited_once()
    mock_client.delete.assert_awaited_once()
