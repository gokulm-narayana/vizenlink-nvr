"""Unit tests for camera stream selection, natural ordering, and resolution (CAM-07, D-23, PRF-03)."""

import logging
from typing import Any
from unittest.mock import AsyncMock

import pytest

from vizenlink_nvr.camera.nuraeye.client import NuraeyeClient
from vizenlink_nvr.camera.nuraeye.live_stream_uri import LiveStreamUri
from vizenlink_nvr.camera.onvif.media2 import MediaProfile, OnvifMedia2Client
from vizenlink_nvr.camera.result import Failure, FailureKind, Success
from vizenlink_nvr.services.streams import natural_token_key, resolve_streams, select_streams


@pytest.mark.behavior("PRF-03")
def test_natural_token_key() -> None:
    """Natural token sorting places Profile_2 before Profile_10."""
    tokens = ["Profile_10", "Profile_2", "Profile_1", "Profile_20"]
    sorted_tokens = sorted(tokens, key=natural_token_key)
    assert sorted_tokens == ["Profile_1", "Profile_2", "Profile_10", "Profile_20"]


@pytest.mark.behavior("PRF-03")
def test_select_streams_drops_profile_3_and_empty_sizes() -> None:
    """Profile_3 and zero/negative resolution profiles are dropped."""
    profiles = [
        MediaProfile("Profile_3", "Small", "venc3", 1280, 720, "H265"),
        MediaProfile("Profile_Invalid", "Zero", "venc_zero", 0, 0, "H264"),
        MediaProfile("Profile_1", "Main", "venc1", 2560, 1440, "H265"),
        MediaProfile("Profile_2", "Sub", "venc2", 1280, 720, "H265"),
    ]
    selection = select_streams(profiles)
    assert selection is not None
    assert selection.main.token == "Profile_1"
    assert selection.sub.token == "Profile_2"
    assert selection.sub_is_main is False


@pytest.mark.behavior("PRF-03")
def test_select_streams_three_profiles_profile_3_largest() -> None:
    """When Profile_3 is the largest profile, it is ignored and Profile_1 / Profile_2 are selected."""
    profiles = [
        MediaProfile("Profile_3", "HugeMobile", "venc3", 3840, 2160, "H265"),
        MediaProfile("Profile_1", "Main", "venc1", 2560, 1440, "H265"),
        MediaProfile("Profile_2", "Sub", "venc2", 1280, 720, "H265"),
    ]
    selection = select_streams(profiles)
    assert selection is not None
    assert selection.main.token == "Profile_1"
    assert selection.sub.token == "Profile_2"
    assert selection.sub_is_main is False


@pytest.mark.behavior("PRF-03")
def test_select_streams_equal_resolution_natural_order() -> None:
    """Profiles with equal resolution are sorted by natural token order."""
    profiles = [
        MediaProfile("Profile_10", "Stream10", "venc10", 1920, 1080, "H265"),
        MediaProfile("Profile_2", "Stream2", "venc2", 1920, 1080, "H265"),
    ]
    selection = select_streams(profiles)
    assert selection is not None
    assert selection.main.token == "Profile_2"
    assert selection.sub.token == "Profile_10"


@pytest.mark.behavior("PRF-03")
def test_select_streams_single_profile() -> None:
    """Single profile sets sub = main and sub_is_main = True."""
    profiles = [
        MediaProfile("Profile_1", "Main", "venc1", 1920, 1080, "H264"),
    ]
    selection = select_streams(profiles)
    assert selection is not None
    assert selection.main.token == "Profile_1"
    assert selection.sub.token == "Profile_1"
    assert selection.sub_is_main is True


@pytest.mark.behavior("PRF-03")
def test_select_streams_no_usable() -> None:
    """No eligible profiles returns None."""
    assert select_streams([]) is None
    assert select_streams([MediaProfile("Profile_3", "Small", "venc3", 1280, 720, "H265")]) is None
    assert select_streams([MediaProfile("Profile_1", "Invalid", "venc1", 0, 1080, "H264")]) is None


@pytest.mark.behavior("PRF-03")
async def test_resolve_streams_rtsp_and_webrtc_fallback(caplog: pytest.LogCaptureFixture) -> None:
    """WebRTC transport falls back to ONVIF Media2 GetStreamUri; H.265 logs warning."""
    profiles = [
        MediaProfile("Profile_1", "MainStream", "venc1", 2560, 1440, "H265"),
        MediaProfile("Profile_2", "SubStream", "venc2", 1280, 720, "H264"),
    ]
    media2 = AsyncMock(spec=OnvifMedia2Client)
    media2.get_profiles.return_value = Success(profiles)
    media2.get_stream_uri.return_value = Success("rtsps://127.0.0.1:554/onvif_high")

    nuraeye = AsyncMock(spec=NuraeyeClient)

    async def mock_get_live_uri(token: str, timeout: float = 8.0) -> Any:
        if token == "Profile_1":
            return Success(
                LiveStreamUri(
                    transport="webrtc",
                    port=8554,
                    url="webrtc://127.0.0.1:8554/webrtc",
                    scheme="webrtc",
                    path="/webrtc",
                )
            )
        return Success(
            LiveStreamUri(
                transport="rtsp",
                port=554,
                url="rtsps://127.0.0.1:554/nura_sub",
                scheme="rtsps",
                path="/nura_sub",
            )
        )

    nuraeye.get_live_stream_uri.side_effect = mock_get_live_uri

    with caplog.at_level(logging.WARNING):
        records = await resolve_streams(nuraeye, media2)

    assert isinstance(records, list)
    assert len(records) == 2

    main_rec = records[0]
    assert main_rec.role == "main"
    assert main_rec.source == "onvif_fallback"
    assert main_rec.path == "/onvif_high"
    assert main_rec.transport == "rtsp"
    assert main_rec.sub_is_main is False

    sub_rec = records[1]
    assert sub_rec.role == "sub"
    assert sub_rec.source == "nuraeye"
    assert sub_rec.path == "/nura_sub"
    assert sub_rec.transport == "rtsp"
    assert sub_rec.sub_is_main is False

    # Verify H.265 warning logged
    assert any("H.265" in rec.message or "H265" in rec.message for rec in caplog.records)


async def test_resolve_streams_profiles_failure() -> None:
    """Media2 get_profiles failure propagates."""
    media2 = AsyncMock(spec=OnvifMedia2Client)
    media2.get_profiles.return_value = Failure(
        kind=FailureKind.BAD_RESPONSE,
        reason="Profiles failed",
    )
    nuraeye = AsyncMock(spec=NuraeyeClient)

    res = await resolve_streams(nuraeye, media2)
    assert isinstance(res, Failure)
    assert res.reason == "Profiles failed"
