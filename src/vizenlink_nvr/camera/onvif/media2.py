# mirrors: mobile_app/packages/camera_api/lib/src/lan/onvif/onvif_video_encoder_client.dart@af62024e35e1
"""ONVIF Media2 service client and models for profiles and stream URIs."""

from dataclasses import dataclass
from urllib.parse import urlsplit

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.http import CameraHttp
from vizenlink_nvr.camera.onvif.device import OnvifDeviceClient
from vizenlink_nvr.camera.onvif.soap import find_text, parse_xml, post_soap, xml_escape
from vizenlink_nvr.camera.result import CameraResult, Failure, FailureKind, Success, Timeout
from vizenlink_nvr.timeutil import Clock

MEDIA2_NAMESPACE = "http://www.onvif.org/ver20/media/wsdl"


@dataclass(frozen=True)
class MediaProfile:
    """ONVIF Media2 profile configuration."""

    token: str
    name: str
    venc_token: str
    width: int
    height: int
    encoding: str


@dataclass(frozen=True)
class VideoResolution:
    """Video frame width and height."""

    width: int
    height: int


@dataclass(frozen=True)
class VideoEncoderConfiguration:
    """Video stream compression, resolution, and bitrate configuration."""

    token: str
    name: str
    encoding: str  # "H264" or "H265"
    width: int
    height: int
    quality: float
    frame_rate_limit: float
    bitrate_limit_kbps: int
    gov_length: int = 30
    profile: str = "Main"


@dataclass(frozen=True)
class VideoEncoderConfigurationOptions:
    """Allowed values and capability limits for a video encoder configuration."""

    token: str
    encodings: tuple[str, ...]
    resolutions: tuple[VideoResolution, ...]
    quality_range: tuple[float, float]
    frame_rate_range: tuple[float, float]
    bitrate_range_kbps: tuple[int, int]
    gov_length_range: tuple[int, int] = (1, 120)


@dataclass(frozen=True)
class OsdConfig:
    """On-Screen Display overlay configuration."""

    token: str
    video_source_token: str
    osd_type: str  # "DateAndTime" or "Plain"
    position: str  # "UpperLeft", "UpperRight", "BottomLeft", "BottomRight"
    plain_text: str | None = None
    date_format: str = "YYYY/MM/DD"
    time_format: str = "HH:mm:ss"


class OnvifMedia2Client:
    """Client for ONVIF Media2 service (GetProfiles, GetStreamUri)."""

    def __init__(
        self,
        conn: CameraConnection,
        http: CameraHttp,
        clock: Clock,
    ) -> None:
        self.conn = conn
        self.http = http
        self.clock = clock
        self._endpoint_path: str | None = None

    async def resolve_endpoint(
        self,
        timeout: float = 8.0,
    ) -> CameraResult[str]:
        """Resolve the Media2 endpoint path via GetServices (DEV-07, PRF-02)."""
        if self._endpoint_path is not None:
            return Success(self._endpoint_path)

        device_client = OnvifDeviceClient(self.conn, self.http, self.clock)
        services_res = await device_client.get_services(timeout=timeout)
        if isinstance(services_res, (Failure, Timeout)):
            return services_res

        for service in services_res.value:
            if service.namespace == MEDIA2_NAMESPACE:
                path = urlsplit(service.xaddr).path
                self._endpoint_path = path
                return Success(path)

        return Failure(
            kind=FailureKind.BAD_RESPONSE,
            reason="Media2 service not offered by this camera",
        )

    async def get_profiles(
        self,
        timeout: float = 8.0,
    ) -> CameraResult[list[MediaProfile]]:
        """Fetch configured Media2 profiles (PRF-01, CAM-07)."""
        ep_res = await self.resolve_endpoint(timeout=timeout)
        if isinstance(ep_res, (Failure, Timeout)):
            return ep_res

        body = f'<tr2:GetProfiles xmlns:tr2="{MEDIA2_NAMESPACE}"/>'
        res = await post_soap(
            self.http,
            self.conn,
            ep_res.value,
            body,
            clock=self.clock,
            timeout=timeout,
        )
        if isinstance(res, (Failure, Timeout)):
            return res

        try:
            root = parse_xml(res.value)
            profiles: list[MediaProfile] = []
            for el in root.iter():
                local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
                if local == "Profiles":
                    token = el.get("token")
                    if not token:
                        continue
                    name = find_text(el, "Name") or token

                    # Find VideoEncoder element
                    venc_el = None
                    for child in el.iter():
                        c_local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                        if c_local == "VideoEncoder":
                            venc_el = child
                            break
                    if venc_el is None:
                        continue

                    venc_token = venc_el.get("token")
                    if not venc_token:
                        continue

                    width_str = find_text(venc_el, "Width")
                    height_str = find_text(venc_el, "Height")
                    if not width_str or not height_str:
                        continue
                    try:
                        width = int(width_str)
                        height = int(height_str)
                    except ValueError:
                        continue

                    encoding = (
                        venc_el.get("encoding")
                        or venc_el.get("Encoding")
                        or find_text(venc_el, "Encoding")
                        or "H265"
                    )

                    profiles.append(
                        MediaProfile(
                            token=token,
                            name=name,
                            venc_token=venc_token,
                            width=width,
                            height=height,
                            encoding=encoding,
                        )
                    )

            if not profiles:
                return Failure(
                    kind=FailureKind.BAD_RESPONSE,
                    reason="GetProfiles response has no usable Profiles",
                )
            return Success(profiles)
        except Exception as exc:
            return Failure(
                kind=FailureKind.BAD_RESPONSE,
                reason=f"Failed to parse GetProfiles response: {exc}",
            )

    async def get_stream_uri(
        self,
        profile_token: str,
        timeout: float = 8.0,
    ) -> CameraResult[str]:
        """Fetch stream URI for given profile via GetStreamUri (D-23)."""
        ep_res = await self.resolve_endpoint(timeout=timeout)
        if isinstance(ep_res, (Failure, Timeout)):
            return ep_res

        body = (
            f'<tr2:GetStreamUri xmlns:tr2="{MEDIA2_NAMESPACE}">'
            "<tr2:Protocol>RTSP</tr2:Protocol>"
            f"<tr2:ProfileToken>{xml_escape(profile_token)}</tr2:ProfileToken>"
            "</tr2:GetStreamUri>"
        )
        res = await post_soap(
            self.http,
            self.conn,
            ep_res.value,
            body,
            clock=self.clock,
            timeout=timeout,
        )
        if isinstance(res, (Failure, Timeout)):
            return res

        try:
            root = parse_xml(res.value)
            uri = find_text(root, "Uri")
            if not uri:
                return Failure(
                    kind=FailureKind.BAD_RESPONSE,
                    reason="GetStreamUri response missing Uri",
                )
            return Success(uri.strip())
        except Exception as exc:
            return Failure(
                kind=FailureKind.BAD_RESPONSE,
                reason=f"Failed to parse GetStreamUri response: {exc}",
            )

    async def get_video_encoder_configuration(
        self,
        token: str,
        timeout: float = 8.0,
    ) -> CameraResult[VideoEncoderConfiguration]:
        """Query video encoder settings for token via Media2 GetVideoEncoderConfigurations."""
        ep_res = await self.resolve_endpoint(timeout=timeout)
        if isinstance(ep_res, (Failure, Timeout)):
            return ep_res

        body = (
            f'<tr2:GetVideoEncoderConfigurations xmlns:tr2="{MEDIA2_NAMESPACE}">'
            f"<tr2:ConfigurationToken>{xml_escape(token)}</tr2:ConfigurationToken>"
            "</tr2:GetVideoEncoderConfigurations>"
        )
        res = await post_soap(
            self.http,
            self.conn,
            ep_res.value,
            body,
            clock=self.clock,
            timeout=timeout,
        )
        if isinstance(res, (Failure, Timeout)):
            return res

        try:
            root = parse_xml(res.value)
            venc = None
            for el in root.iter():
                if el.tag.split("}")[-1] == "Configurations":
                    venc = el
                    break
            if venc is None:
                venc = root

            name = venc.get("Name") or venc.get("token") or token
            encoding = find_text(venc, "Encoding") or "H265"
            width_str = find_text(venc, "Width") or "1920"
            height_str = find_text(venc, "Height") or "1080"
            quality_str = find_text(venc, "Quality") or "50"
            fps_str = find_text(venc, "FrameRateLimit") or "25"
            bitrate_str = find_text(venc, "BitrateLimit") or "2048"
            gov_str = find_text(venc, "GovLength") or "30"
            profile = find_text(venc, "Profile") or "Main"

            return Success(
                VideoEncoderConfiguration(
                    token=token,
                    name=name,
                    encoding=encoding,
                    width=int(width_str),
                    height=int(height_str),
                    quality=float(quality_str),
                    frame_rate_limit=float(fps_str),
                    bitrate_limit_kbps=int(bitrate_str),
                    gov_length=int(gov_str),
                    profile=profile,
                )
            )
        except Exception as exc:
            return Failure(
                kind=FailureKind.BAD_RESPONSE,
                reason=f"Failed to parse GetVideoEncoderConfigurations: {exc}",
            )

    async def get_video_encoder_configuration_options(
        self,
        token: str,
        timeout: float = 8.0,
    ) -> CameraResult[VideoEncoderConfigurationOptions]:
        """Query allowed values and capability limits for video encoder configuration."""
        ep_res = await self.resolve_endpoint(timeout=timeout)
        if isinstance(ep_res, (Failure, Timeout)):
            return ep_res

        body = (
            f'<tr2:GetVideoEncoderConfigurationOptions xmlns:tr2="{MEDIA2_NAMESPACE}">'
            f"<tr2:ConfigurationToken>{xml_escape(token)}</tr2:ConfigurationToken>"
            "</tr2:GetVideoEncoderConfigurationOptions>"
        )
        res = await post_soap(
            self.http,
            self.conn,
            ep_res.value,
            body,
            clock=self.clock,
            timeout=timeout,
        )
        if isinstance(res, (Failure, Timeout)):
            return res

        try:
            root = parse_xml(res.value)
            encodings: list[str] = []
            resolutions: list[VideoResolution] = []

            for el in root.iter():
                local = el.tag.split("}")[-1]
                if local == "Encoding":
                    if el.text and el.text.strip():
                        encodings.append(el.text.strip())
                elif local in ("ResolutionsAvailable", "Resolution"):
                    w = find_text(el, "Width")
                    h = find_text(el, "Height")
                    if w and h:
                        resolutions.append(VideoResolution(width=int(w), height=int(h)))

            if not encodings:
                encodings = ["H264", "H265"]
            if not resolutions:
                resolutions = [VideoResolution(1920, 1080), VideoResolution(1280, 720)]

            def parse_bounds(tag: str, default: tuple[float, float]) -> tuple[float, float]:
                for el in root.iter():
                    if el.tag.split("}")[-1] == tag:
                        mn = find_text(el, "Min")
                        mx = find_text(el, "Max")
                        if mn and mx:
                            return (float(mn), float(mx))
                return default

            q_range = parse_bounds("QualityRange", (0.0, 100.0))
            fps_range = parse_bounds("FrameRateRange", (1.0, 30.0))
            br_range_f = parse_bounds("BitrateRange", (256.0, 8192.0))
            br_range = (int(br_range_f[0]), int(br_range_f[1]))
            gov_range_f = parse_bounds("GovLengthRange", (1.0, 120.0))
            gov_range = (int(gov_range_f[0]), int(gov_range_f[1]))

            return Success(
                VideoEncoderConfigurationOptions(
                    token=token,
                    encodings=tuple(encodings),
                    resolutions=tuple(resolutions),
                    quality_range=q_range,
                    frame_rate_range=fps_range,
                    bitrate_range_kbps=br_range,
                    gov_length_range=gov_range,
                )
            )
        except Exception as exc:
            return Failure(
                kind=FailureKind.BAD_RESPONSE,
                reason=f"Failed to parse GetVideoEncoderConfigurationOptions: {exc}",
            )

    async def set_video_encoder_configuration(
        self,
        token: str,
        config: VideoEncoderConfiguration,
        timeout: float = 8.0,
    ) -> CameraResult[bool]:
        """Update video encoder configuration via SetVideoEncoderConfiguration."""
        ep_res = await self.resolve_endpoint(timeout=timeout)
        if isinstance(ep_res, (Failure, Timeout)):
            return ep_res

        body = (
            f'<tr2:SetVideoEncoderConfiguration xmlns:tr2="{MEDIA2_NAMESPACE}" '
            'xmlns:tt="http://www.onvif.org/ver10/schema">'
            f'<tr2:Configuration token="{xml_escape(token)}">'
            f"<tt:Name>{xml_escape(config.name)}</tt:Name>"
            f"<tt:Encoding>{xml_escape(config.encoding)}</tt:Encoding>"
            f"<tt:Resolution><tt:Width>{config.width}</tt:Width><tt:Height>{config.height}</tt:Height></tt:Resolution>"
            f"<tt:Quality>{config.quality}</tt:Quality>"
            f"<tt:RateControl><tt:FrameRateLimit>{config.frame_rate_limit}</tt:FrameRateLimit><tt:BitrateLimit>{config.bitrate_limit_kbps}</tt:BitrateLimit></tt:RateControl>"
            f"<tt:GovLength>{config.gov_length}</tt:GovLength>"
            f"<tt:Profile>{xml_escape(config.profile)}</tt:Profile>"
            "</tr2:Configuration>"
            "</tr2:SetVideoEncoderConfiguration>"
        )
        res = await post_soap(
            self.http,
            self.conn,
            ep_res.value,
            body,
            clock=self.clock,
            timeout=timeout,
        )
        if isinstance(res, (Failure, Timeout)):
            return res
        return Success(True)

    async def get_osds(
        self,
        timeout: float = 8.0,
    ) -> CameraResult[list[OsdConfig]]:
        """Fetch OSD configurations via Media2 GetOSDs."""
        ep_res = await self.resolve_endpoint(timeout=timeout)
        if isinstance(ep_res, (Failure, Timeout)):
            return ep_res

        body = f'<tr2:GetOSDs xmlns:tr2="{MEDIA2_NAMESPACE}"/>'
        res = await post_soap(
            self.http,
            self.conn,
            ep_res.value,
            body,
            clock=self.clock,
            timeout=timeout,
        )
        if isinstance(res, (Failure, Timeout)):
            return res

        try:
            root = parse_xml(res.value)
            osds: list[OsdConfig] = []
            for el in root.iter():
                if el.tag.split("}")[-1] == "OSDs":
                    token = el.get("token") or "OSD_1"
                    src_token = find_text(el, "VideoSourceConfigurationToken") or "VideoSource_1"
                    osd_type = find_text(el, "Type") or "DateAndTime"
                    pos = find_text(el, "Position") or "UpperLeft"
                    plain_text = find_text(el, "PlainText")

                    osds.append(
                        OsdConfig(
                            token=token,
                            video_source_token=src_token,
                            osd_type=osd_type,
                            position=pos,
                            plain_text=plain_text,
                        )
                    )
            return Success(osds)
        except Exception as exc:
            return Failure(
                kind=FailureKind.BAD_RESPONSE,
                reason=f"Failed to parse GetOSDs response: {exc}",
            )

    async def set_osd(
        self,
        osd: OsdConfig,
        timeout: float = 8.0,
    ) -> CameraResult[bool]:
        """Update OSD configuration via Media2 SetOSD."""
        ep_res = await self.resolve_endpoint(timeout=timeout)
        if isinstance(ep_res, (Failure, Timeout)):
            return ep_res

        if osd.osd_type == "Plain":
            plain_xml = f"<tt:PlainText>{xml_escape(osd.plain_text or '')}</tt:PlainText>"
        else:
            plain_xml = (
                f"<tt:DateFormat>{xml_escape(osd.date_format)}</tt:DateFormat>"
                f"<tt:TimeFormat>{xml_escape(osd.time_format)}</tt:TimeFormat>"
            )

        body = (
            f'<tr2:SetOSD xmlns:tr2="{MEDIA2_NAMESPACE}" xmlns:tt="http://www.onvif.org/ver10/schema">'
            f'<tr2:OSD token="{xml_escape(osd.token)}">'
            f"<tt:VideoSourceConfigurationToken>{xml_escape(osd.video_source_token)}</tt:VideoSourceConfigurationToken>"
            f"<tt:Type>{xml_escape(osd.osd_type)}</tt:Type>"
            f"<tt:Position><tt:Type>{xml_escape(osd.position)}</tt:Type></tt:Position>"
            f"<tt:TextString>{plain_xml}</tt:TextString>"
            "</tr2:OSD>"
            "</tr2:SetOSD>"
        )
        res = await post_soap(
            self.http,
            self.conn,
            ep_res.value,
            body,
            clock=self.clock,
            timeout=timeout,
        )
        if isinstance(res, (Failure, Timeout)):
            return res
        return Success(True)
