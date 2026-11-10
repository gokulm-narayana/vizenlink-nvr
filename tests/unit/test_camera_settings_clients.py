"""Unit tests for ONVIF and NuraEye camera settings clients (Plan 06-01).

Tests:
- OnvifDeviceClient: system_reboot, set_system_factory_default, set_system_date_and_time
- OnvifImagingClient: get_imaging_settings, get_imaging_options, set_imaging_settings
- OnvifMedia2Client: encoder configs & options, OSD query & update
- NuraeyeSettingsClient: night vision, mirror/flip, anti-flicker, timezones
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.http import CameraHttp
from vizenlink_nvr.camera.nuraeye.rest import RestError, RestOk
from vizenlink_nvr.camera.nuraeye.settings import (
    FALLBACK_TIMEZONES,
    NightVisionStatus,
    NuraeyeSettingsClient,
)
from vizenlink_nvr.camera.onvif.device import OnvifDeviceClient
from vizenlink_nvr.camera.onvif.imaging import (
    ImagingOptions,
    ImagingSettings,
    OnvifImagingClient,
)
from vizenlink_nvr.camera.onvif.media2 import (
    OsdConfig,
    VideoEncoderConfiguration,
    VideoEncoderConfigurationOptions,
    VideoResolution,
)
from vizenlink_nvr.camera.result import Failure, Success
from vizenlink_nvr.timeutil import SystemClock


@pytest.fixture
def fake_conn() -> CameraConnection:
    return CameraConnection(
        host="192.168.1.100",
        port=80,
        username="admin",
        password=SecretStr("TestPass123"),
        serial="CAM-SETTINGS-TEST",
    )


@pytest.fixture
def fake_http() -> CameraHttp:
    return AsyncMock(spec=CameraHttp)


# -----------------------------------------------------------------------------
# OnvifDeviceClient Settings Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_onvif_device_system_reboot(fake_conn: CameraConnection, fake_http: CameraHttp) -> None:
    clock = SystemClock()
    client = OnvifDeviceClient(fake_conn, fake_http, clock)

    xml_response = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
        "<s:Body>"
        '<tds:SystemRebootResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl">'
        "<tds:Message>Rebooting in 2 seconds</tds:Message>"
        "</tds:SystemRebootResponse>"
        "</s:Body>"
        "</s:Envelope>"
    )

    with patch("vizenlink_nvr.camera.onvif.device.post_soap", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Success(xml_response)
        res = await client.system_reboot()
        assert isinstance(res, Success)
        assert res.value == "Rebooting in 2 seconds"
        mock_post.assert_awaited_once()


@pytest.mark.asyncio
async def test_onvif_device_factory_default(fake_conn: CameraConnection, fake_http: CameraHttp) -> None:
    clock = SystemClock()
    client = OnvifDeviceClient(fake_conn, fake_http, clock)

    with patch("vizenlink_nvr.camera.onvif.device.post_soap", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Success("<tds:SetSystemFactoryDefaultResponse/>")

        # Soft reset
        res_soft = await client.set_system_factory_default(mode="Soft")
        assert isinstance(res_soft, Success)
        assert res_soft.value is True
        call_soft_xml = mock_post.call_args_list[0][0][3]
        assert "<tds:FactoryDefault>Soft</tds:FactoryDefault>" in call_soft_xml

        # Hard reset
        res_hard = await client.set_system_factory_default(mode="Hard")
        assert isinstance(res_hard, Success)
        assert res_hard.value is True
        call_hard_xml = mock_post.call_args_list[1][0][3]
        assert "<tds:FactoryDefault>Hard</tds:FactoryDefault>" in call_hard_xml


@pytest.mark.asyncio
async def test_onvif_device_set_date_and_time(fake_conn: CameraConnection, fake_http: CameraHttp) -> None:
    clock = SystemClock()
    client = OnvifDeviceClient(fake_conn, fake_http, clock)

    with patch("vizenlink_nvr.camera.onvif.device.post_soap", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Success("<tds:SetSystemDateAndTimeResponse/>")
        res = await client.set_system_date_and_time("America/Los_Angeles")
        assert isinstance(res, Success)
        assert res.value is True
        call_xml = mock_post.call_args[0][3]
        assert "America/Los_Angeles" in call_xml
        assert "<tds:DateTimeType>NTP</tds:DateTimeType>" in call_xml


# -----------------------------------------------------------------------------
# OnvifImagingClient Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_onvif_imaging_get_settings(fake_conn: CameraConnection, fake_http: CameraHttp) -> None:
    clock = SystemClock()
    client = OnvifImagingClient(fake_conn, fake_http, clock)

    xml_response = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
        "<s:Body>"
        '<timg:GetImagingSettingsResponse xmlns:timg="http://www.onvif.org/ver20/imaging/wsdl" '
        'xmlns:tt="http://www.onvif.org/ver10/schema">'
        "<timg:ImagingSettings>"
        "<tt:Brightness>60.0</tt:Brightness>"
        "<tt:ColorSaturation>55.0</tt:ColorSaturation>"
        "<tt:Contrast>50.0</tt:Contrast>"
        "<tt:Sharpness>45.0</tt:Sharpness>"
        "<tt:IrCutFilter>AUTO</tt:IrCutFilter>"
        "<tt:WideDynamicRange>"
        "<tt:Mode>ON</tt:Mode>"
        "<tt:Level>20.0</tt:Level>"
        "</tt:WideDynamicRange>"
        "</timg:ImagingSettings>"
        "</timg:GetImagingSettingsResponse>"
        "</s:Body>"
        "</s:Envelope>"
    )

    with patch("vizenlink_nvr.camera.onvif.imaging.post_soap", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Success(xml_response)
        res = await client.get_imaging_settings("VideoSource_1")
        assert isinstance(res, Success)
        settings = res.value
        assert settings.brightness == 60.0
        assert settings.color_saturation == 55.0
        assert settings.contrast == 50.0
        assert settings.sharpness == 45.0
        assert settings.ir_cut_filter == "AUTO"
        assert settings.wdr_mode == "ON"
        assert settings.wdr_level == 20.0


@pytest.mark.asyncio
async def test_onvif_imaging_get_options(fake_conn: CameraConnection, fake_http: CameraHttp) -> None:
    clock = SystemClock()
    client = OnvifImagingClient(fake_conn, fake_http, clock)

    xml_response = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
        "<s:Body>"
        '<timg:GetOptionsResponse xmlns:timg="http://www.onvif.org/ver20/imaging/wsdl" '
        'xmlns:tt="http://www.onvif.org/ver10/schema">'
        "<timg:ImagingOptions>"
        "<tt:Brightness><tt:Min>0</tt:Min><tt:Max>100</tt:Max></tt:Brightness>"
        "<tt:ColorSaturation><tt:Min>0</tt:Min><tt:Max>100</tt:Max></tt:ColorSaturation>"
        "<tt:Contrast><tt:Min>10</tt:Min><tt:Max>90</tt:Max></tt:Contrast>"
        "<tt:Sharpness><tt:Min>0</tt:Min><tt:Max>50</tt:Max></tt:Sharpness>"
        "<tt:IrCutFilterModes>AUTO</tt:IrCutFilterModes>"
        "<tt:IrCutFilterModes>ON</tt:IrCutFilterModes>"
        "<tt:IrCutFilterModes>OFF</tt:IrCutFilterModes>"
        "<tt:WideDynamicRange>"
        "<tt:Mode>OFF</tt:Mode>"
        "<tt:Level><tt:Min>0</tt:Min><tt:Max>100</tt:Max></tt:Level>"
        "</tt:WideDynamicRange>"
        "</timg:ImagingOptions>"
        "</timg:GetOptionsResponse>"
        "</s:Body>"
        "</s:Envelope>"
    )

    with patch("vizenlink_nvr.camera.onvif.imaging.post_soap", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Success(xml_response)
        res = await client.get_imaging_options("VideoSource_1")
        assert isinstance(res, Success)
        opts: ImagingOptions = res.value
        assert opts.brightness_range == (0.0, 100.0)
        assert opts.contrast_range == (10.0, 90.0)
        assert opts.sharpness_range == (0.0, 50.0)
        assert opts.ir_cut_filter_modes == ("AUTO", "ON", "OFF")
        assert opts.wdr_supported is True
        assert opts.wdr_level_range == (0.0, 100.0)


@pytest.mark.asyncio
async def test_onvif_imaging_set_settings(fake_conn: CameraConnection, fake_http: CameraHttp) -> None:
    clock = SystemClock()
    client = OnvifImagingClient(fake_conn, fake_http, clock)

    with patch("vizenlink_nvr.camera.onvif.imaging.post_soap", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Success("<timg:SetImagingSettingsResponse/>")
        settings = ImagingSettings(
            brightness=72.0,
            contrast=48.0,
            ir_cut_filter="AUTO",
            wdr_mode="ON",
            wdr_level=15.0,
        )
        res = await client.set_imaging_settings("VideoSource_1", settings)
        assert isinstance(res, Success)
        assert res.value is True

        call_xml = mock_post.call_args[0][3]
        assert "<tt:Brightness>72.0</tt:Brightness>" in call_xml
        assert "<tt:Contrast>48.0</tt:Contrast>" in call_xml
        assert "<tt:IrCutFilter>AUTO</tt:IrCutFilter>" in call_xml
        assert "<tt:Mode>ON</tt:Mode>" in call_xml
        assert "<tt:Level>15.0</tt:Level>" in call_xml
        assert "<timg:ForcePersistence>true</timg:ForcePersistence>" in call_xml


# -----------------------------------------------------------------------------
# OnvifMedia2Client Settings Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_onvif_media2_encoder_config(fake_conn: CameraConnection, fake_http: CameraHttp) -> None:
    from vizenlink_nvr.camera.onvif.media2 import OnvifMedia2Client

    clock = SystemClock()
    client = OnvifMedia2Client(fake_conn, fake_http, clock)
    client._endpoint_path = "/onvif/media2_service"

    xml_config = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
        "<s:Body>"
        '<tr2:GetVideoEncoderConfigurationsResponse xmlns:tr2="http://www.onvif.org/ver20/media/wsdl" '
        'xmlns:tt="http://www.onvif.org/ver10/schema">'
        '<tr2:Configurations token="VEC_Main" Name="MainStream">'
        "<tt:Encoding>H265</tt:Encoding>"
        "<tt:Resolution><tt:Width>2560</tt:Width><tt:Height>1440</tt:Height></tt:Resolution>"
        "<tt:Quality>60</tt:Quality>"
        "<tt:RateControl><tt:FrameRateLimit>30</tt:FrameRateLimit><tt:BitrateLimit>4096</tt:BitrateLimit></tt:RateControl>"
        "<tt:GovLength>60</tt:GovLength>"
        "<tt:Profile>Main</tt:Profile>"
        "</tr2:Configurations>"
        "</tr2:GetVideoEncoderConfigurationsResponse>"
        "</s:Body>"
        "</s:Envelope>"
    )

    with patch("vizenlink_nvr.camera.onvif.media2.post_soap", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Success(xml_config)
        res = await client.get_video_encoder_configuration("VEC_Main")
        assert isinstance(res, Success)
        cfg: VideoEncoderConfiguration = res.value
        assert cfg.token == "VEC_Main"
        assert cfg.name == "MainStream"
        assert cfg.encoding == "H265"
        assert cfg.width == 2560
        assert cfg.height == 1440
        assert cfg.quality == 60.0
        assert cfg.frame_rate_limit == 30.0
        assert cfg.bitrate_limit_kbps == 4096
        assert cfg.gov_length == 60


@pytest.mark.asyncio
async def test_onvif_media2_encoder_options(fake_conn: CameraConnection, fake_http: CameraHttp) -> None:
    from vizenlink_nvr.camera.onvif.media2 import OnvifMedia2Client

    clock = SystemClock()
    client = OnvifMedia2Client(fake_conn, fake_http, clock)
    client._endpoint_path = "/onvif/media2_service"

    xml_options = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
        "<s:Body>"
        '<tr2:GetVideoEncoderConfigurationOptionsResponse xmlns:tr2="http://www.onvif.org/ver20/media/wsdl" '
        'xmlns:tt="http://www.onvif.org/ver10/schema">'
        "<tr2:Options>"
        "<tt:Encoding>H264</tt:Encoding>"
        "<tt:Encoding>H265</tt:Encoding>"
        "<tt:QualityRange><tt:Min>1</tt:Min><tt:Max>100</tt:Max></tt:QualityRange>"
        "<tt:ResolutionsAvailable><tt:Width>2560</tt:Width><tt:Height>1440</tt:Height></tt:ResolutionsAvailable>"
        "<tt:ResolutionsAvailable><tt:Width>1920</tt:Width><tt:Height>1080</tt:Height></tt:ResolutionsAvailable>"
        "<tt:FrameRateRange><tt:Min>5</tt:Min><tt:Max>30</tt:Max></tt:FrameRateRange>"
        "<tt:BitrateRange><tt:Min>512</tt:Min><tt:Max>8192</tt:Max></tt:BitrateRange>"
        "<tt:GovLengthRange><tt:Min>10</tt:Min><tt:Max>120</tt:Max></tt:GovLengthRange>"
        "</tr2:Options>"
        "</tr2:GetVideoEncoderConfigurationOptionsResponse>"
        "</s:Body>"
        "</s:Envelope>"
    )

    with patch("vizenlink_nvr.camera.onvif.media2.post_soap", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Success(xml_options)
        res = await client.get_video_encoder_configuration_options("VEC_Main")
        assert isinstance(res, Success)
        opts: VideoEncoderConfigurationOptions = res.value
        assert "H264" in opts.encodings and "H265" in opts.encodings
        assert VideoResolution(2560, 1440) in opts.resolutions
        assert VideoResolution(1920, 1080) in opts.resolutions
        assert opts.frame_rate_range == (5.0, 30.0)
        assert opts.bitrate_range_kbps == (512, 8192)


@pytest.mark.asyncio
async def test_onvif_media2_set_encoder_config(fake_conn: CameraConnection, fake_http: CameraHttp) -> None:
    from vizenlink_nvr.camera.onvif.media2 import OnvifMedia2Client

    clock = SystemClock()
    client = OnvifMedia2Client(fake_conn, fake_http, clock)
    client._endpoint_path = "/onvif/media2_service"

    with patch("vizenlink_nvr.camera.onvif.media2.post_soap", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Success("<tr2:SetVideoEncoderConfigurationResponse/>")
        cfg = VideoEncoderConfiguration(
            token="VEC_Main",
            name="MainStream",
            encoding="H265",
            width=2560,
            height=1440,
            quality=50.0,
            frame_rate_limit=25.0,
            bitrate_limit_kbps=4096,
            gov_length=50,
        )
        res = await client.set_video_encoder_configuration("VEC_Main", cfg)
        assert isinstance(res, Success)
        assert res.value is True

        call_xml = mock_post.call_args[0][3]
        assert "<tt:Width>2560</tt:Width>" in call_xml
        assert "<tt:Height>1440</tt:Height>" in call_xml
        assert "<tt:BitrateLimit>4096</tt:BitrateLimit>" in call_xml


@pytest.mark.asyncio
async def test_onvif_media2_osd_get_and_set(fake_conn: CameraConnection, fake_http: CameraHttp) -> None:
    from vizenlink_nvr.camera.onvif.media2 import OnvifMedia2Client

    clock = SystemClock()
    client = OnvifMedia2Client(fake_conn, fake_http, clock)
    client._endpoint_path = "/onvif/media2_service"

    xml_osds = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
        "<s:Body>"
        '<tr2:GetOSDsResponse xmlns:tr2="http://www.onvif.org/ver20/media/wsdl" '
        'xmlns:tt="http://www.onvif.org/ver10/schema">'
        '<tr2:OSDs token="OSD_1">'
        "<tt:VideoSourceConfigurationToken>VideoSource_1</tt:VideoSourceConfigurationToken>"
        "<tt:Type>DateAndTime</tt:Type>"
        "<tt:Position><tt:Type>UpperLeft</tt:Type></tt:Position>"
        "</tr2:OSDs>"
        '<tr2:OSDs token="OSD_2">'
        "<tt:VideoSourceConfigurationToken>VideoSource_1</tt:VideoSourceConfigurationToken>"
        "<tt:Type>Plain</tt:Type>"
        "<tt:Position><tt:Type>BottomRight</tt:Type></tt:Position>"
        "<tt:TextString><tt:PlainText>Entrance Cam</tt:PlainText></tt:TextString>"
        "</tr2:OSDs>"
        "</tr2:GetOSDsResponse>"
        "</s:Body>"
        "</s:Envelope>"
    )

    with patch("vizenlink_nvr.camera.onvif.media2.post_soap", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Success(xml_osds)
        res = await client.get_osds()
        assert isinstance(res, Success)
        osds = res.value
        assert len(osds) == 2
        assert osds[0].token == "OSD_1"
        assert osds[0].osd_type == "DateAndTime"
        assert osds[1].token == "OSD_2"
        assert osds[1].plain_text == "Entrance Cam"

    with patch("vizenlink_nvr.camera.onvif.media2.post_soap", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Success("<tr2:SetOSDResponse/>")
        updated_osd = OsdConfig(
            token="OSD_2",
            video_source_token="VideoSource_1",
            osd_type="Plain",
            position="BottomLeft",
            plain_text="Backyard Cam",
        )
        set_res = await client.set_osd(updated_osd)
        assert isinstance(set_res, Success)
        assert set_res.value is True

        call_xml = mock_post.call_args[0][3]
        assert "<tt:PlainText>Backyard Cam</tt:PlainText>" in call_xml
        assert "<tt:Type>BottomLeft</tt:Type>" in call_xml


# -----------------------------------------------------------------------------
# NuraeyeSettingsClient Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nuraeye_night_vision(fake_conn: CameraConnection, fake_http: CameraHttp) -> None:
    clock = SystemClock()
    client = NuraeyeSettingsClient(fake_conn, fake_http, clock)

    with patch("vizenlink_nvr.camera.nuraeye.settings.get_json", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = RestOk(
            status=200,
            output={"type": "smart", "color_capable": True, "smart_capable": True},
        )
        res = await client.get_night_vision_type()
        assert isinstance(res, Success)
        nv: NightVisionStatus = res.value
        assert nv.current_type == "smart"
        assert nv.color_capable is True
        assert nv.smart_capable is True

    with patch("vizenlink_nvr.camera.nuraeye.settings.post_json", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = RestOk(status=200, output={"result": "ok"})
        set_res = await client.set_night_vision_type("color")
        assert isinstance(set_res, Success)
        assert set_res.value is True
        assert mock_post.call_args[0][3] == {"type": "color"}

    # Invalid type rejection
    bad_res = await client.set_night_vision_type("ultraviolet")
    assert isinstance(bad_res, Failure)
    assert "Invalid night vision type" in bad_res.reason


@pytest.mark.asyncio
async def test_nuraeye_mirror_flip(fake_conn: CameraConnection, fake_http: CameraHttp) -> None:
    clock = SystemClock()
    client = NuraeyeSettingsClient(fake_conn, fake_http, clock)

    with patch("vizenlink_nvr.camera.nuraeye.settings.get_json", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = RestOk(status=200, output={"mode": "mirror"})
        res = await client.get_mirror_flip()
        assert isinstance(res, Success)
        assert res.value == "mirror"

    with patch("vizenlink_nvr.camera.nuraeye.settings.post_json", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = RestOk(status=200, output={"result": "ok"})
        set_res = await client.set_mirror_flip("both")
        assert isinstance(set_res, Success)
        assert set_res.value is True
        assert mock_post.call_args[0][3] == {"mode": "both"}

    # Invalid mode rejection
    bad_res = await client.set_mirror_flip("upside_down")
    assert isinstance(bad_res, Failure)
    assert "Invalid mirror/flip mode" in bad_res.reason


@pytest.mark.asyncio
async def test_nuraeye_anti_flicker(fake_conn: CameraConnection, fake_http: CameraHttp) -> None:
    clock = SystemClock()
    client = NuraeyeSettingsClient(fake_conn, fake_http, clock)

    with patch("vizenlink_nvr.camera.nuraeye.settings.get_json", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = RestOk(status=200, output={"mode": "50Hz"})
        res = await client.get_anti_flicker()
        assert isinstance(res, Success)
        assert res.value == "50Hz"

    with patch("vizenlink_nvr.camera.nuraeye.settings.post_json", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = RestOk(status=200, output={"result": "ok"})
        set_res = await client.set_anti_flicker("60hz")
        assert isinstance(set_res, Success)
        assert set_res.value is True
        assert mock_post.call_args[0][3] == {"mode": "60Hz"}

    # Invalid mode rejection
    bad_res = await client.set_anti_flicker("120Hz")
    assert isinstance(bad_res, Failure)
    assert "Invalid anti-flicker mode" in bad_res.reason


@pytest.mark.asyncio
async def test_nuraeye_timezones_catalog(fake_conn: CameraConnection, fake_http: CameraHttp) -> None:
    clock = SystemClock()
    client = NuraeyeSettingsClient(fake_conn, fake_http, clock)

    # 1. Successful camera catalog fetch
    with patch("vizenlink_nvr.camera.nuraeye.settings.get_json", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = RestOk(
            status=200,
            output={"timezones": [{"code": "UTC", "label": "UTC"}]},
        )
        res = await client.get_supported_timezones()
        assert isinstance(res, Success)
        assert res.value == [{"code": "UTC", "label": "UTC"}]

    # 2. Fallback when endpoint returns error
    with patch("vizenlink_nvr.camera.nuraeye.settings.get_json", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = RestError(status=404, error_code=404, error_msg="Not Found")
        res_fb = await client.get_supported_timezones()
        assert isinstance(res_fb, Success)
        assert res_fb.value == FALLBACK_TIMEZONES


# -----------------------------------------------------------------------------
# Phase 10: exposure / gain / white balance (camera_api onvif_imaging_client.dart)
# -----------------------------------------------------------------------------

_SOAP = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body>'
    '<timg:{op}Response xmlns:timg="http://www.onvif.org/ver20/imaging/wsdl" '
    'xmlns:tt="http://www.onvif.org/ver10/schema">{body}</timg:{op}Response>'
    "</s:Body></s:Envelope>"
)


@pytest.mark.asyncio
async def test_imaging_exposure_white_balance_parse_without_mixing_modes(
    fake_conn: CameraConnection, fake_http: CameraHttp
) -> None:
    client = OnvifImagingClient(fake_conn, fake_http, SystemClock())
    # Exposure comes BEFORE WideDynamicRange: the old parser took the first <Mode> as WDR mode.
    body = (
        "<timg:ImagingSettings>"
        "<tt:Exposure><tt:Mode>MANUAL</tt:Mode><tt:ExposureTime>20000</tt:ExposureTime><tt:Gain>12</tt:Gain></tt:Exposure>"
        "<tt:WideDynamicRange><tt:Mode>OFF</tt:Mode><tt:Level>0</tt:Level></tt:WideDynamicRange>"
        "<tt:WhiteBalance><tt:Mode>AUTO</tt:Mode></tt:WhiteBalance>"
        "</timg:ImagingSettings>"
    )
    with patch("vizenlink_nvr.camera.onvif.imaging.post_soap", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Success(_SOAP.format(op="GetImagingSettings", body=body))
        res = await client.get_imaging_settings("VideoSource_1")
    assert isinstance(res, Success)
    s = res.value
    assert s.wdr_mode == "OFF"
    assert (s.exposure_mode, s.exposure_time, s.exposure_gain) == ("MANUAL", 20000.0, 12.0)
    assert s.white_balance_mode == "AUTO"
    assert s.brightness is None or isinstance(s.brightness, float)


@pytest.mark.asyncio
async def test_imaging_options_exposure_white_balance(
    fake_conn: CameraConnection, fake_http: CameraHttp
) -> None:
    client = OnvifImagingClient(fake_conn, fake_http, SystemClock())
    body = (
        "<timg:ImagingOptions>"
        "<tt:Exposure><tt:Mode>AUTO</tt:Mode><tt:Mode>MANUAL</tt:Mode>"
        "<tt:ExposureTime><tt:Min>10</tt:Min><tt:Max>40000</tt:Max></tt:ExposureTime>"
        "<tt:Gain><tt:Min>0</tt:Min><tt:Max>100</tt:Max></tt:Gain></tt:Exposure>"
        "<tt:WhiteBalance><tt:Mode>AUTO</tt:Mode><tt:Mode>MANUAL</tt:Mode></tt:WhiteBalance>"
        "</timg:ImagingOptions>"
    )
    with patch("vizenlink_nvr.camera.onvif.imaging.post_soap", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Success(_SOAP.format(op="GetOptions", body=body))
        res = await client.get_imaging_options("VideoSource_1")
    assert isinstance(res, Success)
    o = res.value
    assert o.exposure_modes == ("AUTO", "MANUAL")
    assert o.exposure_time_range == (10.0, 40000.0)
    assert o.exposure_gain_range == (0.0, 100.0)
    assert o.white_balance_modes == ("AUTO", "MANUAL")


@pytest.mark.asyncio
async def test_imaging_options_absent_exposure_is_empty(
    fake_conn: CameraConnection, fake_http: CameraHttp
) -> None:
    client = OnvifImagingClient(fake_conn, fake_http, SystemClock())
    with patch("vizenlink_nvr.camera.onvif.imaging.post_soap", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Success(_SOAP.format(op="GetOptions", body="<timg:ImagingOptions/>"))
        res = await client.get_imaging_options("VideoSource_1")
    assert isinstance(res, Success)
    assert res.value.exposure_modes == () and res.value.exposure_time_range is None
    assert res.value.white_balance_modes == ()


@pytest.mark.asyncio
async def test_imaging_set_exposure_white_balance_xml(
    fake_conn: CameraConnection, fake_http: CameraHttp
) -> None:
    client = OnvifImagingClient(fake_conn, fake_http, SystemClock())
    with patch("vizenlink_nvr.camera.onvif.imaging.post_soap", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Success("<ok/>")
        await client.set_imaging_settings(
            "VideoSource_1",
            ImagingSettings(
                exposure_mode="MANUAL", exposure_time=20000.0, exposure_gain=12.0, white_balance_mode="AUTO"
            ),
        )
        body = mock_post.call_args.args[3]
    # Same element order and shape as the Dart client.
    assert (
        "<tt:Exposure><tt:Mode>MANUAL</tt:Mode><tt:ExposureTime>20000.0</tt:ExposureTime>"
        "<tt:Gain>12.0</tt:Gain></tt:Exposure>"
    ) in body
    assert "<tt:WhiteBalance><tt:Mode>AUTO</tt:Mode></tt:WhiteBalance>" in body
    assert "<timg:ForcePersistence>true</timg:ForcePersistence>" in body
