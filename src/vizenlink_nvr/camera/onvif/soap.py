# mirrors: mobile_app/packages/camera_api/lib/src/lan/onvif/soap_fault.dart@ffb2a21c3a54
# mirrors: mobile_app/packages/camera_api/lib/src/lan/onvif/onvif_device_client.dart@bd2e63476c9c
"""SOAP message envelope builder, XML parser, and fault-first response handler for ONVIF."""

import re
import xml.etree.ElementTree as ET

import defusedxml.ElementTree as Det
from pydantic import SecretStr

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.http import CameraHttp
from vizenlink_nvr.camera.result import (
    CameraResult,
    Failure,
    FailureKind,
    Success,
    Timeout,
    parse_retry_after,
)
from vizenlink_nvr.camera.wsse import WsseToken, make_token
from vizenlink_nvr.timeutil import Clock

SOAP_CONTENT_TYPE = "application/soap+xml; charset=utf-8"
MAX_XML_BYTES = 1024 * 1024  # 1 MiB


def xml_escape(text: str) -> str:
    """Escape XML special characters (& < > " ')."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def build_envelope(body_xml: str, username: str, token: WsseToken) -> str:
    """Construct SOAP 1.2 envelope with WSSE UsernameToken."""
    escaped_user = xml_escape(username)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
        "<s:Header>"
        '<wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">'
        "<wsse:UsernameToken>"
        f"<wsse:Username>{escaped_user}</wsse:Username>"
        '<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">'
        f"{token.digest}</wsse:Password>"
        '<wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">'
        f"{token.nonce_b64}</wsse:Nonce>"
        '<wsu:Created xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">'
        f"{token.created}</wsu:Created>"
        "</wsse:UsernameToken>"
        "</wsse:Security>"
        "</s:Header>"
        f"<s:Body>{body_xml}</s:Body>"
        "</s:Envelope>"
    )


def parse_xml(text: str) -> ET.Element:
    """Parse XML string with size limit and entity expansion protection."""
    if len(text.encode("utf-8")) > MAX_XML_BYTES:
        raise ValueError("XML payload exceeds 1 MiB")
    return Det.fromstring(text)  # type: ignore[no-any-return]


def find_text(el: ET.Element, tag: str) -> str:
    """Find text of first descendant element with matching local tag name."""
    found = el.find(f".//{{*}}{tag}")
    if found is not None and found.text:
        return found.text.strip()

    for child in el.iter():
        local_name = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if local_name == tag and child.text:
            return child.text.strip()
    return ""


def soap_fault_reason(xml: str) -> str | None:
    """Extract reason text from SOAP fault body if present, else None."""
    try:
        root = parse_xml(xml)
    except Exception:
        return None

    fault_el: ET.Element | None = None
    for el in root.iter():
        local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if local == "Fault":
            fault_el = el
            break

    if fault_el is None:
        return None

    for el in fault_el.iter():
        local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if local == "Text" and el.text:
            return el.text.strip()

    return "SOAP fault (no reason given)"


def soap_fault_subcode(xml: str) -> str | None:
    """Extract the innermost/last fault subcode from SOAP fault XML."""
    try:
        root = parse_xml(xml)
        subcodes: list[str] = []
        for el in root.iter():
            local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if local == "Subcode":
                for child in el:
                    child_local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if child_local == "Value" and child.text:
                        val = child.text.strip()
                        if ":" in val:
                            val = val.split(":", 1)[1]
                        subcodes.append(val)
        if subcodes:
            return subcodes[-1]
    except (ET.ParseError, ValueError, AttributeError, TypeError):
        # Fall back to regex if XML structure is non-standard
        pass

    m = re.findall(r"<[^>]*Subcode[^>]*>[\s\S]*?<[^>]*Value[^>]*>\s*(?:[a-zA-Z0-9_-]+:)?([A-Za-z0-9_]+)", xml)
    return m[-1] if m else None


async def post_soap(
    http: CameraHttp,
    conn: CameraConnection,
    path: str,
    body_xml: str,
    *,
    clock: Clock,
    timeout: float = 8.0,
) -> CameraResult[str]:
    """Send SOAP request with WSSE UsernameToken header and parse fault-first responses."""
    raw_pw = conn.password.get_secret_value() if isinstance(conn.password, SecretStr) else str(conn.password)
    token = make_token(raw_pw, clock)
    envelope = build_envelope(body_xml, conn.username, token)
    headers = [("Content-Type", SOAP_CONTENT_TYPE)]

    resp = await http.send(
        conn,
        "POST",
        path,
        body=envelope.encode("utf-8"),
        headers=headers,
        timeout=timeout,
    )
    if isinstance(resp, (Failure, Timeout)):
        return resp

    status_code = resp.status
    body_text = resp.body.decode("utf-8", errors="replace")

    fault_reason = soap_fault_reason(body_text)
    if fault_reason is not None:
        subcode = soap_fault_subcode(body_text)
        if "InsufficientUserLevel" in body_text:
            return Failure(
                kind=FailureKind.FORBIDDEN,
                reason=fault_reason,
                http_status=status_code,
                fault_subcode=subcode,
            )
        if "TooManyAttempts" in body_text:
            return Failure(
                kind=FailureKind.BLOCKED,
                reason=fault_reason,
                http_status=status_code,
                retry_after=parse_retry_after(None, fault_reason),
                fault_subcode=subcode,
            )
        if "PasswordChangeRequired" in body_text:
            return Failure(
                kind=FailureKind.PASSWORD_CHANGE_REQUIRED,
                reason=fault_reason,
                http_status=status_code,
                fault_subcode=subcode,
            )
        if (
            subcode in ("NotAuthorized", "AuthenticationFailed")
            or "notauthorized" in body_text.lower()
            or "authentication failed" in fault_reason.lower()
        ):
            return Failure(
                kind=FailureKind.UNAUTHORIZED,
                reason=fault_reason,
                http_status=status_code,
                fault_subcode=subcode,
            )

        reason_str = f"{fault_reason} [ter:{subcode}]" if subcode else fault_reason
        return Failure(
            kind=FailureKind.GENERIC,
            reason=reason_str,
            http_status=status_code,
            fault_subcode=subcode,
        )

    if status_code == 401:
        return Failure(
            kind=FailureKind.UNAUTHORIZED,
            reason=f"HTTP 401: {body_text[:500]}",
            http_status=401,
        )
    if status_code == 429:
        return Failure(
            kind=FailureKind.BLOCKED,
            reason=f"HTTP 429: {body_text[:500]}",
            http_status=429,
            retry_after=parse_retry_after(None, body_text),
        )
    if status_code == 428:
        return Failure(
            kind=FailureKind.PASSWORD_CHANGE_REQUIRED,
            reason=f"HTTP 428: {body_text[:500]}",
            http_status=428,
        )
    if status_code != 200:
        return Failure(
            kind=FailureKind.GENERIC,
            reason=f"HTTP {status_code}: {body_text[:500]}",
            http_status=status_code,
        )

    return Success(body_text)
