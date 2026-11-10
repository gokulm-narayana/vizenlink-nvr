# Ported from camera_api lib/src/lan/onvif/onvif_imaging_client.dart
# (exposure + white balance, FR-MOB-062; file not yet in the vendored contract set).
"""ONVIF Imaging service client and models for camera image settings (SET-03, SET-08)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
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
    exposure_mode: str | None = None  # "AUTO", "MANUAL"
    exposure_time: float | None = None
    exposure_gain: float | None = None
    white_balance_mode: str | None = None  # e.g. "AUTO", "MANUAL"


def _first(root: ET.Element | None, local_name: str) -> ET.Element | None:
    """First descendant element with the given local name (namespace-agnostic)."""
    if root is None:
        return None
    for el in root.iter():
        if el.tag.split("}")[-1] == local_name:
            return el
    return None


def _text_in(el: ET.Element | None, local_name: str) -> str | None:
    """find_text scoped to an element; None when absent (find_text returns '')."""
    return (find_text(el, local_name) or None) if el is not None else None


def _float_in(el: ET.Element | None, local_name: str) -> float | None:
    raw = _text_in(el, local_name)
    return float(raw) if raw else None


def _modes_in(el: ET.Element | None) -> tuple[str, ...]:
    if el is None:
        return ()
    return tuple(
        m.text.strip() for m in el.iter() if m.tag.split("}")[-1] == "Mode" and m.text and m.text.strip()
    )


def _range_in(el: ET.Element | None, local_name: str) -> tuple[float, float] | None:
    sub = _first(el, local_name)
    lo, hi = _float_in(sub, "Min"), _float_in(sub, "Max")
    return (lo, hi) if lo is not None and hi is not None else None


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
    # Empty / None when the camera does not report them (Dart: const [] / null).
    white_balance_modes: tuple[str, ...] = ()
    exposure_modes: tuple[str, ...] = ()
    exposure_time_range: tuple[float, float] | None = None
    exposure_gain_range: tuple[float, float] | None = None


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
            # Each Mode is read inside its own element (WDR, Exposure, WhiteBalance), as in Dart.
            # Before: WDR mode was "the first Mode anywhere", which could be the exposure mode.
            wdr_el = _first(root, "WideDynamicRange")
            wdr_m = _text_in(wdr_el, "Mode")
            wdr_l = _text_in(wdr_el, "Level")
            exp_el = _first(root, "Exposure")
            wb_el = _first(root, "WhiteBalance")

            return Success(
                ImagingSettings(
                    brightness=float(b_str) if b_str else None,
                    color_saturation=float(s_str) if s_str else None,
                    contrast=float(c_str) if c_str else None,
                    sharpness=float(sh_str) if sh_str else None,
                    ir_cut_filter=irc_str or None,
                    wdr_mode=wdr_m,
                    wdr_level=float(wdr_l) if wdr_l else None,
                    exposure_mode=_text_in(exp_el, "Mode"),
                    exposure_time=_float_in(exp_el, "ExposureTime"),
                    exposure_gain=_float_in(exp_el, "Gain"),
                    white_balance_mode=_text_in(wb_el, "Mode"),
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

            exp_opts = _first(root, "Exposure")
            wb_opts = _first(root, "WhiteBalance")

            return Success(
                ImagingOptions(
                    brightness_range=brightness_range,
                    color_saturation_range=saturation_range,
                    contrast_range=contrast_range,
                    sharpness_range=sharpness_range,
                    ir_cut_filter_modes=tuple(ir_modes),
                    wdr_supported=wdr_supported,
                    wdr_level_range=wdr_level_range,
                    white_balance_modes=_modes_in(wb_opts),
                    exposure_modes=_modes_in(exp_opts),
                    exposure_time_range=_range_in(exp_opts, "ExposureTime"),
                    exposure_gain_range=_range_in(exp_opts, "Gain"),
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
        if settings.exposure_mode is not None:
            exp_inner = f"<tt:Mode>{xml_escape(settings.exposure_mode)}</tt:Mode>"
            if settings.exposure_time is not None:
                exp_inner += f"<tt:ExposureTime>{settings.exposure_time}</tt:ExposureTime>"
            if settings.exposure_gain is not None:
                exp_inner += f"<tt:Gain>{settings.exposure_gain}</tt:Gain>"
            elements.append(f"<tt:Exposure>{exp_inner}</tt:Exposure>")
        if settings.white_balance_mode is not None:
            elements.append(
                f"<tt:WhiteBalance><tt:Mode>{xml_escape(settings.white_balance_mode)}</tt:Mode></tt:WhiteBalance>"
            )

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
