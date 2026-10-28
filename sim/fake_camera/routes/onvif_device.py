"""ONVIF Device service routes for fake camera simulator."""

import weakref
from dataclasses import dataclass, field
from typing import Any

from fake_camera.routes import route
from fake_camera.state import CameraState


@dataclass
class OnvifSimSettings:
    """Configurable ONVIF behavior settings per simulated camera instance."""

    profiles: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {
                "token": "Profile_1",
                "name": "MainStream",
                "venc_token": "VideoEncoder_1",
                "width": 2560,
                "height": 1440,
                "encoding": "H265",
            },
            {
                "token": "Profile_2",
                "name": "SubStream",
                "venc_token": "VideoEncoder_2",
                "width": 1280,
                "height": 720,
                "encoding": "H265",
            },
        ]
    )
    media2_enabled: bool = True
    anonymous_onvif_ops: set[str] = field(
        default_factory=lambda: {"GetDeviceInformation", "GetScopes", "GetServices"}
    )
    stream_uri_template: str = "rtsps://{host}:554/high"


_SETTINGS: weakref.WeakKeyDictionary[Any, OnvifSimSettings] = weakref.WeakKeyDictionary()


def onvif_settings(camera: Any) -> OnvifSimSettings:
    """Retrieve or initialize OnvifSimSettings for a FakeCamera or CameraState."""
    state = getattr(camera, "state", camera)
    settings = getattr(state, "_onvif_settings", None)
    if settings is None:
        try:
            settings = _SETTINGS.get(camera)
        except TypeError:
            settings = None

    if settings is None:
        settings = OnvifSimSettings()

    try:
        _SETTINGS[camera] = settings
    except TypeError:
        pass

    try:
        state._onvif_settings = settings
    except (AttributeError, TypeError):
        pass

    return settings


@route("POST", "/onvif/device_service")
async def handle_device_service(
    state: CameraState,
    body: bytes,
    headers: list[tuple[bytes, bytes]],
) -> tuple[int, str]:
    """Handle POST /onvif/device_service."""
    body_text = body.decode("utf-8", errors="replace")
    settings = onvif_settings(state)

    if "GetDeviceInformation" in body_text:
        # Check anonymous permission
        if "GetDeviceInformation" not in settings.anonymous_onvif_ops:
            return 401, (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">\n'
                "<s:Body>\n"
                "<s:Fault>\n"
                "<s:Code><s:Value>s:Sender</s:Value><s:Subcode><s:Value>ter:NotAuthorized</s:Value></s:Subcode></s:Code>\n"
                '<s:Reason><s:Text xml:lang="en">Not authorized</s:Text></s:Reason>\n'
                "</s:Fault>\n"
                "</s:Body>\n"
                "</s:Envelope>"
            )

        return 200, (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">\n'
            "<s:Body>\n"
            '<tds:GetDeviceInformationResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl">\n'
            f"<tds:Manufacturer>{state.manufacturer}</tds:Manufacturer>\n"
            f"<tds:Model>{state.model}</tds:Model>\n"
            f"<tds:FirmwareVersion>{state.firmware}</tds:FirmwareVersion>\n"
            f"<tds:SerialNumber>{state.serial}</tds:SerialNumber>\n"
            f"<tds:HardwareId>{state.hardware_id}</tds:HardwareId>\n"
            "</tds:GetDeviceInformationResponse>\n"
            "</s:Body>\n"
            "</s:Envelope>"
        )

    return 400, (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">\n'
        "<s:Body>\n"
        "<s:Fault>\n"
        "<s:Code><s:Value>s:Sender</s:Value><s:Subcode><s:Value>ter:ActionNotSupported</s:Value></s:Subcode></s:Code>\n"
        '<s:Reason><s:Text xml:lang="en">Action not supported</s:Text></s:Reason>\n'
        "</s:Fault>\n"
        "</s:Body>\n"
        "</s:Envelope>"
    )
