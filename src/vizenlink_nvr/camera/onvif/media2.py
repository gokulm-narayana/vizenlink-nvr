# mirrors: mobile_app/packages/camera_api/lib/src/lan/onvif/onvif_video_encoder_client.dart@2e06d2ad3a40
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
