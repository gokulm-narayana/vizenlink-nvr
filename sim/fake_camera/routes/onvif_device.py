"""ONVIF Device service routes for fake camera simulator."""

import re
import weakref
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, unquote

import defusedxml.ElementTree as ET

from fake_camera.routes import route
from fake_camera.state import CameraState
from vizenlink_nvr.camera.onvif.device import LOCATION_SCOPE_PREFIX, NAME_SCOPE_PREFIX
from vizenlink_nvr.camera.roles import CameraRole


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


def _extract_wsse(body: bytes) -> tuple[str, str, str, str]:
    header_match = re.search(
        rb"<[a-zA-Z0-9_:]*Header[^>]*>(.*?)</[a-zA-Z0-9_:]*Header>",
        body,
        re.DOTALL,
    )
    if not header_match:
        return "", "", "", ""
    hdr = header_match.group(1)
    match_user = re.search(rb"<[a-zA-Z0-9_:]*Username[^>]*>([^<]*)</", hdr)
    match_nonce = re.search(rb"<[a-zA-Z0-9_:]*Nonce[^>]*>([^<]*)</", hdr)
    match_created = re.search(rb"<[a-zA-Z0-9_:]*Created[^>]*>([^<]*)</", hdr)
    match_pwd = re.search(rb"<[a-zA-Z0-9_:]*Password[^>]*>([^<]*)</", hdr)

    u = match_user.group(1).decode("utf-8") if match_user else ""
    n = match_nonce.group(1).decode("utf-8") if match_nonce else ""
    c = match_created.group(1).decode("utf-8") if match_created else ""
    d = match_pwd.group(1).decode("utf-8") if match_pwd else ""
    return u, n, c, d


def _make_soap_fault(
    subcode: str,
    reason: str,
    parent_subcode: str | None = None,
    status: int = 400,
) -> tuple[int, str]:
    if parent_subcode:
        subcode_xml = (
            f"<s:Subcode><s:Value>ter:{parent_subcode}</s:Value>"
            f"<s:Subcode><s:Value>ter:{subcode}</s:Value></s:Subcode></s:Subcode>"
        )
    else:
        subcode_xml = f"<s:Subcode><s:Value>ter:{subcode}</s:Value></s:Subcode>"

    return status, (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">\n'
        "<s:Body>\n"
        "<s:Fault>\n"
        f"<s:Code><s:Value>s:Sender</s:Value>{subcode_xml}</s:Code>\n"
        f'<s:Reason><s:Text xml:lang="en">{reason}</s:Text></s:Reason>\n'
        "</s:Fault>\n"
        "</s:Body>\n"
        "</s:Envelope>"
    )


@route("POST", "/onvif/device_service")
async def handle_device_service(
    state: CameraState,
    body: bytes,
    headers: list[tuple[bytes, bytes]],
) -> tuple[int, str]:
    """Handle POST /onvif/device_service."""
    body_text = body.decode("utf-8", errors="replace")
    settings = onvif_settings(state)

    # 1. GetDeviceInformation
    if "GetDeviceInformation" in body_text:
        if "GetDeviceInformation" not in settings.anonymous_onvif_ops:
            u, n, c, d = _extract_wsse(body)
            acc, _ = state.verify_wsse(u, n, c, d)
            if acc is None:
                return _make_soap_fault("NotAuthorized", "Not authorized", status=401)

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

    # 2. GetScopes
    if "GetScopes" in body_text:
        if "GetScopes" not in settings.anonymous_onvif_ops:
            u, n, c, d = _extract_wsse(body)
            acc, _ = state.verify_wsse(u, n, c, d)
            if acc is None:
                return _make_soap_fault("NotAuthorized", "Not authorized", status=401)

        name_quoted = quote(state.name, safe="!~*'()")
        loc_quoted = quote(state.location, safe="!~*'()")
        return 200, (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">\n'
            "<s:Body>\n"
            '<tds:GetScopesResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl" '
            'xmlns:tt="http://www.onvif.org/ver10/schema">\n'
            "<tds:Scopes><tt:ScopeDef>Fixed</tt:ScopeDef>"
            "<tt:ScopeItem>onvif://www.onvif.org/Profile/Streaming</tt:ScopeItem></tds:Scopes>\n"
            f"<tds:Scopes><tt:ScopeDef>Configurable</tt:ScopeDef>"
            f"<tt:ScopeItem>{NAME_SCOPE_PREFIX}{name_quoted}</tt:ScopeItem></tds:Scopes>\n"
            f"<tds:Scopes><tt:ScopeDef>Configurable</tt:ScopeDef>"
            f"<tt:ScopeItem>{LOCATION_SCOPE_PREFIX}{loc_quoted}</tt:ScopeItem></tds:Scopes>\n"
            "</tds:GetScopesResponse>\n"
            "</s:Body>\n"
            "</s:Envelope>"
        )

    # 3. SetScopes
    if "SetScopes" in body_text:
        u, n, c, d = _extract_wsse(body)
        acc, _ = state.verify_wsse(u, n, c, d)
        if acc is None:
            return _make_soap_fault("NotAuthorized", "Not authorized", status=401)
        if acc.role != CameraRole.ADMINISTRATOR:
            return _make_soap_fault(
                "InsufficientUserLevel",
                "The authenticated user level is not permitted to perform this operation.",
                parent_subcode="OperationProhibited",
            )
        if state.first_password_gate:
            return _make_soap_fault(
                "PasswordChangeRequired",
                "The Administrator must set a new password first.",
                parent_subcode="OperationProhibited",
            )

        try:
            root = ET.fromstring(body)
            scopes: list[str] = []
            for el in root.iter():
                local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
                if local == "Scopes" and el.text:
                    scopes.append(el.text.strip())

            if len(scopes) > 2:
                return _make_soap_fault(
                    "TooManyScopes",
                    "SetScopes accepts at most 2 scope items",
                )

            for s in scopes:
                if s.startswith(NAME_SCOPE_PREFIX):
                    state.name = unquote(s[len(NAME_SCOPE_PREFIX) :])
                elif s.startswith(LOCATION_SCOPE_PREFIX):
                    state.location = unquote(s[len(LOCATION_SCOPE_PREFIX) :])

            return 200, (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">\n'
                "<s:Body>\n"
                '<tds:SetScopesResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/>\n'
                "</s:Body>\n"
                "</s:Envelope>"
            )
        except Exception as exc:
            return _make_soap_fault("InvalidArgs", f"Failed to parse SetScopes request: {exc}")

    # 4. GetNetworkInterfaces
    if "GetNetworkInterfaces" in body_text:
        return 200, (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">\n'
            "<s:Body>\n"
            '<tds:GetNetworkInterfacesResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl" '
            'xmlns:tt="http://www.onvif.org/ver10/schema">\n'
            '<tds:NetworkInterfaces token="eth0">\n'
            "<tt:Enabled>true</tt:Enabled>\n"
            "<tt:Info>\n"
            "<tt:Name>wlan</tt:Name>\n"
            f"<tt:HwAddress>{state.mac}</tt:HwAddress>\n"
            "<tt:MTU>1500</tt:MTU>\n"
            "</tt:Info>\n"
            "<tt:IPv4>\n"
            "<tt:Enabled>true</tt:Enabled>\n"
            "<tt:Config>\n"
            "<tt:FromDHCP>\n"
            "<tt:Address>127.0.0.1</tt:Address>\n"
            "<tt:PrefixLength>24</tt:PrefixLength>\n"
            "</tt:FromDHCP>\n"
            "<tt:DHCP>true</tt:DHCP>\n"
            "</tt:Config>\n"
            "</tt:IPv4>\n"
            "</tds:NetworkInterfaces>\n"
            "</tds:GetNetworkInterfacesResponse>\n"
            "</s:Body>\n"
            "</s:Envelope>"
        )

    # 5. GetServices
    if "GetServices" in body_text:
        if "GetServices" not in settings.anonymous_onvif_ops:
            u, n, c, d = _extract_wsse(body)
            acc, _ = state.verify_wsse(u, n, c, d)
            if acc is None:
                return _make_soap_fault("NotAuthorized", "Not authorized", status=401)

        media2_service = (
            "      <tds:Service>\n"
            "        <tds:Namespace>http://www.onvif.org/ver20/media/wsdl</tds:Namespace>\n"
            "        <tds:XAddr>https://10.9.9.9/onvif/media2_service</tds:XAddr>\n"
            "      </tds:Service>\n"
            if settings.media2_enabled
            else ""
        )
        return 200, (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
            'xmlns:tds="http://www.onvif.org/ver10/device/wsdl">\n'
            "  <s:Body>\n"
            "    <tds:GetServicesResponse>\n"
            "      <tds:Service>\n"
            "        <tds:Namespace>http://www.onvif.org/ver10/device/wsdl</tds:Namespace>\n"
            "        <tds:XAddr>https://10.9.9.9/onvif/device_service</tds:XAddr>\n"
            "      </tds:Service>\n"
            f"{media2_service}"
            "    </tds:GetServicesResponse>\n"
            "  </s:Body>\n"
            "</s:Envelope>"
        )

    # 6. SetUser
    if "SetUser" in body_text:
        u, n, c, d = _extract_wsse(body)
        acc, _ = state.verify_wsse(u, n, c, d)
        if acc is None:
            return _make_soap_fault("NotAuthorized", "Not authorized", status=401)
        if acc.role != CameraRole.ADMINISTRATOR:
            return _make_soap_fault(
                "InsufficientUserLevel",
                "The authenticated user level is not permitted to perform this operation.",
                parent_subcode="OperationProhibited",
            )

        try:
            root = ET.fromstring(body)
            target_username = ""
            new_password = ""

            # Only search inside the SOAP Body
            body_el = None
            for child in root:
                if child.tag.endswith("Body"):
                    body_el = child
                    break
            search_root = body_el if body_el is not None else root

            for el in search_root.iter():
                local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
                if local == "Username" and el.text:
                    target_username = el.text.strip()
                elif local == "Password" and el.text:
                    new_password = el.text.strip()

            if not target_username:
                return _make_soap_fault("InvalidArgs", "Missing Username in SetUser")

            if new_password.lower() == "password":
                return _make_soap_fault("PasswordNotAllowed", "Password is not allowed")

            try:
                state.set_password(target_username, new_password)
            except ValueError:
                return _make_soap_fault("PasswordNotAllowed", "Password is not allowed")

            return 200, (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">\n'
                "<s:Body>\n"
                '<tds:SetUserResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/>\n'
                "</s:Body>\n"
                "</s:Envelope>"
            )
        except Exception as exc:
            return _make_soap_fault("InvalidArgs", f"Failed to parse SetUser request: {exc}")

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
