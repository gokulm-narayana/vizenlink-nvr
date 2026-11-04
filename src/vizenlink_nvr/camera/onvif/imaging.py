"""ONVIF Imaging service client and models for camera image settings (SET-03, SET-08)."""

from __future__ import annotations

from dataclasses import dataclass

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.http import CameraHttp
from vizenlink_nvr.camera.onvif.soap import find_text, parse_xml, post_soap, xml_escape
from vizenlink_nvr.camera.result import CameraResult, Failure, FailureKind, Success, Timeout
from vizenlink_nvr.timeutil import Clock

IMAGING_SERVICE_PATH = "/onvif/imaging_service"


@dataclass(frozen=True)
class ImagingSettings:
    """Current imaging and ISP parameters on the camera."""

    brightness: float | None = None
    color_saturation: float | None = None
    contrast: float | None = None
    sharpness: float | None = None
    ir_cut_filter: str | None = None  # "ON", "OFF", "AUTO"
    wdr_mode: str | None = None  # "ON", "OFF"
    wdr_level: float | None = None


@dataclass(frozen=True)
class ImagingOptions:
    """Supported ranges and capability flags for camera imaging parameters."""

    brightness_range: tuple[float, float] = (0.0, 100.0)
    color_saturation_range: tuple[float, float] = (0.0, 100.0)
    contrast_range: tuple[float, float] = (0.0, 100.0)
    sharpness_range: tuple[float, float] = (0.0, 100.0)
    ir_cut_filter_modes: tuple[str, ...] = ("AUTO", "ON", "OFF")
    wdr_supported: bool = False
    wdr_level_range: tuple[float, float] = (0.0, 100.0)


class OnvifImagingClient:
    """Client for ONVIF Imaging service (GetImagingSettings, SetImagingSettings, GetOptions)."""

    def __init__(
        self,
        conn: CameraConnection,
        http: CameraHttp,
        clock: Clock,
        endpoint_path: str = IMAGING_SERVICE_PATH,
    ) -> None:
        self.conn = conn
        self.http = http
        self.clock = clock
        self.endpoint_path = endpoint_path

    async def get_imaging_settings(
        self,
        video_source_token: str = "VideoSource_1",  # noqa: S107
        timeout: float = 8.0,
    ) -> CameraResult[ImagingSettings]:
        """Fetch current imaging parameters via ONVIF GetImagingSettings."""
        body = (
            '<timg:GetImagingSettings xmlns:timg="http://www.onvif.org/ver20/imaging/wsdl">'
            f"<timg:VideoSourceToken>{xml_escape(video_source_token)}</timg:VideoSourceToken>"
            "</timg:GetImagingSettings>"
        )
        res = await post_soap(
            self.http,
            self.conn,
            self.endpoint_path,
            body,
            clock=self.clock,
            timeout=timeout,
        )
        if isinstance(res, (Failure, Timeout)):
            return res

        try:
            root = parse_xml(res.value)
            b_str = find_text(root, "Brightness")
            s_str = find_text(root, "ColorSaturation")
            c_str = find_text(root, "Contrast")
            sh_str = find_text(root, "Sharpness")
            irc_str = find_text(root, "IrCutFilter")
            wdr_m = find_text(root, "Mode")
            wdr_l = find_text(root, "Level")

            return Success(
                ImagingSettings(
                    brightness=float(b_str) if b_str is not None else None,
                    color_saturation=float(s_str) if s_str is not None else None,
                    contrast=float(c_str) if c_str is not None else None,
                    sharpness=float(sh_str) if sh_str is not None else None,
                    ir_cut_filter=irc_str,
                    wdr_mode=wdr_m,
                    wdr_level=float(wdr_l) if wdr_l is not None else None,
                )
            )
        except Exception as exc:
            return Failure(
                kind=FailureKind.BAD_RESPONSE,
                reason=f"Failed to parse GetImagingSettings response: {exc}",
            )

    async def get_imaging_options(
        self,
        video_source_token: str = "VideoSource_1",  # noqa: S107
        timeout: float = 8.0,
    ) -> CameraResult[ImagingOptions]:
        """Fetch imaging parameter limits and capability flags via ONVIF GetOptions."""
        body = (
            '<timg:GetOptions xmlns:timg="http://www.onvif.org/ver20/imaging/wsdl">'
            f"<timg:VideoSourceToken>{xml_escape(video_source_token)}</timg:VideoSourceToken>"
            "</timg:GetOptions>"
        )
        res = await post_soap(
            self.http,
            self.conn,
            self.endpoint_path,
            body,
            clock=self.clock,
            timeout=timeout,
        )
        if isinstance(res, (Failure, Timeout)):
            return res

        try:
            root = parse_xml(res.value)

            def parse_range(tag_name: str, default: tuple[float, float]) -> tuple[float, float]:
                for el in root.iter():
                    if el.tag.split("}")[-1] == tag_name:
                        b_min = find_text(el, "Min")
                        b_max = find_text(el, "Max")
                        if b_min is not None and b_max is not None:
                            return (float(b_min), float(b_max))
                return default

            brightness_range = parse_range("Brightness", (0.0, 100.0))
            saturation_range = parse_range("ColorSaturation", (0.0, 100.0))
            contrast_range = parse_range("Contrast", (0.0, 100.0))
            sharpness_range = parse_range("Sharpness", (0.0, 100.0))

            ir_modes: list[str] = []
            wdr_supported = False
            wdr_level_range = (0.0, 100.0)

            for el in root.iter():
                local = el.tag.split("}")[-1]
                if local == "IrCutFilterModes":
                    if el.text:
                        ir_modes.append(el.text.strip())
                elif local == "WideDynamicRange":
                    wdr_supported = True
                    w_min = find_text(el, "Min")
                    w_max = find_text(el, "Max")
                    if w_min and w_max:
                        wdr_level_range = (float(w_min), float(w_max))

            if not ir_modes:
                ir_modes = ["AUTO", "ON", "OFF"]

            return Success(
                ImagingOptions(
                    brightness_range=brightness_range,
                    color_saturation_range=saturation_range,
                    contrast_range=contrast_range,
                    sharpness_range=sharpness_range,
                    ir_cut_filter_modes=tuple(ir_modes),
                    wdr_supported=wdr_supported,
                    wdr_level_range=wdr_level_range,
                )
            )
        except Exception as exc:
            return Failure(
                kind=FailureKind.BAD_RESPONSE,
                reason=f"Failed to parse GetOptions response: {exc}",
            )

    async def set_imaging_settings(
        self,
        video_source_token: str,
        settings: ImagingSettings,
        force_persistence: bool = True,
        timeout: float = 8.0,
    ) -> CameraResult[bool]:
        """Update imaging parameters via ONVIF SetImagingSettings."""
        elements: list[str] = []
        if settings.brightness is not None:
            elements.append(f"<tt:Brightness>{settings.brightness}</tt:Brightness>")
        if settings.color_saturation is not None:
            elements.append(f"<tt:ColorSaturation>{settings.color_saturation}</tt:ColorSaturation>")
        if settings.contrast is not None:
            elements.append(f"<tt:Contrast>{settings.contrast}</tt:Contrast>")
        if settings.sharpness is not None:
            elements.append(f"<tt:Sharpness>{settings.sharpness}</tt:Sharpness>")
        if settings.ir_cut_filter is not None:
            elements.append(f"<tt:IrCutFilter>{xml_escape(settings.ir_cut_filter)}</tt:IrCutFilter>")
        if settings.wdr_mode is not None:
            wdr_inner = f"<tt:Mode>{xml_escape(settings.wdr_mode)}</tt:Mode>"
            if settings.wdr_level is not None:
                wdr_inner += f"<tt:Level>{settings.wdr_level}</tt:Level>"
            elements.append(f"<tt:WideDynamicRange>{wdr_inner}</tt:WideDynamicRange>")

        inner_xml = "".join(elements)
        persist_str = "true" if force_persistence else "false"

        body = (
            '<timg:SetImagingSettings xmlns:timg="http://www.onvif.org/ver20/imaging/wsdl" '
            'xmlns:tt="http://www.onvif.org/ver10/schema">'
            f"<timg:VideoSourceToken>{xml_escape(video_source_token)}</timg:VideoSourceToken>"
            f"<timg:ImagingSettings>{inner_xml}</timg:ImagingSettings>"
            f"<timg:ForcePersistence>{persist_str}</timg:ForcePersistence>"
            "</timg:SetImagingSettings>"
        )

        res = await post_soap(
            self.http,
            self.conn,
            self.endpoint_path,
            body,
            clock=self.clock,
            timeout=timeout,
        )
        if isinstance(res, (Failure, Timeout)):
            return res
        return Success(True)
