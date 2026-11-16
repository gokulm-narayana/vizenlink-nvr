"""Camera SDK parity checks for codec-specific options, overlays, masks and authenticated dispatch."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.nuraeye.client import NuraeyeClient
from vizenlink_nvr.camera.nuraeye.rest import RestError, RestOk
from vizenlink_nvr.camera.nuraeye.sessions import NuraeyeSessionCache, Session
from vizenlink_nvr.camera.onvif.masks import OnvifMaskClient
from vizenlink_nvr.camera.onvif.media2 import OnvifMedia2Client, OsdConfig
from vizenlink_nvr.camera.result import Failure, Success
from vizenlink_nvr.timeutil import SystemClock


def media_client(cls=OnvifMedia2Client):
    conn = CameraConnection("192.168.1.10", 443, "admin", SecretStr("secret"), serial="CAM-1")
    client = cls(conn, AsyncMock(), SystemClock())
    client._endpoint_path = "/onvif/media2_service"
    return client


@pytest.mark.asyncio
async def test_codec_options_keep_per_codec_resolutions_profiles_rates_and_cbr():
    client = media_client()
    options = '<Options xmlns="urn:test" GovLengthRange="1 50" FrameRatesSupported="5 10 25" ProfilesSupported="Main" ConstantBitRateSupported="true"><Encoding>H265</Encoding><QualityRange><Min>1</Min><Max>100</Max></QualityRange><BitrateRange><Min>256</Min><Max>8192</Max></BitrateRange><ResolutionsAvailable><Width>2560</Width><Height>1440</Height></ResolutionsAvailable></Options>'  # noqa: E501 - exact camera XML fixture
    other = (
        options.replace("H265", "H264")
        .replace("2560", "1920")
        .replace("1440", "1080")
        .replace('ProfilesSupported="Main"', 'ProfilesSupported="Baseline High"')
        .replace('ConstantBitRateSupported="true"', 'ConstantBitRateSupported="false"')
    )
    with patch(
        "vizenlink_nvr.camera.onvif.media2.post_soap",
        new=AsyncMock(return_value=Success(f"<Response>{options}{other}</Response>")),
    ):
        result = await client.get_video_encoder_configuration_options("Encoder_1")
    assert isinstance(result, Success)
    h265, h264 = result.value.codec_options
    assert h265["resolutions"][0].width == 2560 and h264["resolutions"][0].width == 1920
    assert h264["encoder_profiles"] == ("Baseline", "High")
    assert h265["frame_rates"] == (5.0, 10.0, 25.0)
    assert h265["supports_cbr"] is True and h264["supports_cbr"] is False


@pytest.mark.asyncio
async def test_missing_encoder_config_cannot_turn_into_invented_settings():
    client = media_client()
    with patch(
        "vizenlink_nvr.camera.onvif.media2.post_soap", new=AsyncMock(return_value=Success("<Response/>"))
    ):
        assert isinstance(await client.get_video_encoder_configuration("missing"), Failure)
        assert isinstance(await client.get_video_encoder_configuration_options("missing"), Failure)


@pytest.mark.asyncio
async def test_encoder_uses_media2_attributes_and_preserves_constant_bitrate():
    client = media_client()
    xml = '<Response xmlns:tt="urn:test"><Configurations token="Encoder_1" GovLength="45" Profile="High"><tt:Name>Main stream</tt:Name><tt:Encoding>H264</tt:Encoding><tt:Resolution><tt:Width>1920</tt:Width><tt:Height>1080</tt:Height></tt:Resolution><tt:Quality>75</tt:Quality><tt:RateControl ConstantBitRate="true"><tt:FrameRateLimit>25</tt:FrameRateLimit><tt:BitrateLimit>4096</tt:BitrateLimit></tt:RateControl></Configurations></Response>'  # noqa: E501 - exact camera XML fixture
    with patch(
        "vizenlink_nvr.camera.onvif.media2.post_soap", new=AsyncMock(return_value=Success(xml))
    ) as post:
        result = await client.get_video_encoder_configuration("Encoder_1")
        assert isinstance(result, Success)
        assert (result.value.gov_length, result.value.profile, result.value.cbr) == (45, "High", True)
        await client.set_video_encoder_configuration("Encoder_1", result.value)
        wire = post.call_args.args[3]
        assert 'GovLength="45" Profile="High"' in wire
        assert '<tt:RateControl ConstantBitRate="true">' in wire
        assert "<tt:GovLength>" not in wire


@pytest.mark.asyncio
async def test_osd_custom_position_color_and_formats_round_trip():
    client = media_client()
    xml = '<Response xmlns:tt="urn:test"><OSDs token="Actual_OSD"><tt:VideoSourceConfigurationToken>VideoSourceCfg_1</tt:VideoSourceConfigurationToken><tt:Type>Text</tt:Type><tt:Position><tt:Type>Custom</tt:Type><tt:Pos x="-0.4" y="0.8"/></tt:Position><tt:TextString><tt:Type>DateAndTime</tt:Type><tt:FontSize>12</tt:FontSize><tt:FontColor><tt:Color X="1" Y="0.5" Z="0" Colorspace="http://www.onvif.org/ver10/colorspace/RGB"/></tt:FontColor><tt:DateFormat>dd/MM/yyyy</tt:DateFormat><tt:TimeFormat>hh:mm:ss tt</tt:TimeFormat></tt:TextString></OSDs></Response>'  # noqa: E501 - exact camera XML fixture
    with patch(
        "vizenlink_nvr.camera.onvif.media2.post_soap", new=AsyncMock(return_value=Success(xml))
    ) as post:
        result = await client.get_osds()
        assert isinstance(result, Success)
        assert "<tr2:ConfigurationToken>VideoSourceCfg_1</tr2:ConfigurationToken>" in post.call_args.args[3]
        item = result.value[0]
        assert (item.osd_type, item.position, item.position_x, item.position_y) == (
            "DateAndTime",
            "Custom",
            -0.4,
            0.8,
        )
        await client.set_osd(item)
        wire = post.call_args.args[3]
        assert '<tt:Pos x="-0.4" y="0.8"/>' in wire
        assert '<tt:Color X="1.0" Y="0.5" Z="0.0"' in wire
        assert "<tt:DateFormat>dd/MM/yyyy</tt:DateFormat>" in wire
        post.return_value = Success("<Response><OSDToken>Camera-created-42</OSDToken></Response>")
        assert (
            await client.create_osd(OsdConfig("", "VideoSourceCfg_1", "Plain", "UpperLeft", "A&B"))
        ).value == "Camera-created-42"
        assert "A&amp;B" in post.call_args.args[3]
        post.return_value = Success("<Response/>")
        assert isinstance(await client.create_osd(item), Failure)


@pytest.mark.asyncio
async def test_mask_protocol_uses_real_options_token_and_normalized_polygon():
    client = media_client(OnvifMaskClient)
    options = '<Response xmlns:tt="urn:test"><Options RectangleOnly="true" SingleColorOnly="true"><tt:MaxMasks>4</tt:MaxMasks><tt:MaxPoints>4</tt:MaxPoints><tt:Types>Color</tt:Types><tt:Color><tt:ColorList X="0" Y="0" Z="0" Colorspace="RGB"/></tt:Color></Options></Response>'  # noqa: E501 - exact camera XML fixture
    with patch(
        "vizenlink_nvr.camera.onvif.masks.post_soap", new=AsyncMock(return_value=Success(options))
    ) as post:
        result = await client.options()
        assert isinstance(result, Success)
        assert result.value["types"] == ["Color"] and result.value["max_masks"] == 4
        post.return_value = Success("<Response><Token>Mask_42</Token></Response>")
        result = await client.save(
            [{"x": -1, "y": 1}, {"x": 0, "y": 1}, {"x": 0, "y": 0}, {"x": -1, "y": 0}],
            "Color",
            True,
            color=result.value["colors"][0],
        )
        assert result.value == {"token": "Mask_42"}
        assert '<tt:Point x="-1" y="1"/>' in post.call_args.args[3]
        assert "<tr2:Enabled>true</tr2:Enabled>" in post.call_args.args[3]
        post.return_value = Success("not xml")
        assert isinstance(await client.masks(), Failure)


@pytest.mark.asyncio
async def test_general_settings_dispatch_refreshes_a_rejected_session_once():
    media = media_client()
    clock = media.clock
    client = NuraeyeClient(media.conn, media.http, clock)
    now = clock.now()
    session = Session("old", 1800, now + timedelta(minutes=30), "admin", "admin", False)
    key = NuraeyeSessionCache.session_key(media.conn.host, "admin")
    client.sessions.put(key, session)
    new_session = Session("new", 1800, now + timedelta(minutes=30), "admin", "admin", False)
    client._do_login = AsyncMock(return_value=Success(new_session))
    client._send_authed = AsyncMock(
        side_effect=[RestError(401, 401, "expired"), RestOk(200, {"mode": "Full"})]
    )
    result = await client.request("POST", "/nuraeye/privacy-mode", {"mode": "Full"})
    assert isinstance(result, Success)
    assert client._do_login.await_count == 1 and client._send_authed.await_count == 2
    assert client._send_authed.call_args.args[2] == "new"
