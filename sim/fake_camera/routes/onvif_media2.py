"""ONVIF Media2 service routes for fake camera simulator."""

from fake_camera.routes import route
from fake_camera.routes.onvif_device import onvif_settings
from fake_camera.state import CameraState


@route("POST", "/onvif/media2_service")
async def handle_media2_service(
    state: CameraState,
    body: bytes,
    headers: list[tuple[bytes, bytes]],
) -> tuple[int, str]:
    """Handle POST /onvif/media2_service."""
    body_text = body.decode("utf-8", errors="replace")
    settings = onvif_settings(state)

    if not settings.media2_enabled:
        return 404, (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">\n'
            "<s:Body>\n"
            "<s:Fault>\n"
            "<s:Code><s:Value>s:Sender</s:Value><s:Subcode><s:Value>ter:ActionNotSupported</s:Value></s:Subcode></s:Code>\n"
            '<s:Reason><s:Text xml:lang="en">Media2 service disabled</s:Text></s:Reason>\n'
            "</s:Fault>\n"
            "</s:Body>\n"
            "</s:Envelope>"
        )

    # 1. GetProfiles
    if "GetProfiles" in body_text:
        profiles_xml_parts: list[str] = []
        for p in settings.profiles:
            encoding = p.get("encoding", "H265")
            venc_block = ""
            if "venc_token" in p and "width" in p and "height" in p:
                w, h = p["width"], p["height"]
                venc_block = (
                    f'      <tr2:VideoEncoder token="{p["venc_token"]}" encoding="{encoding}">\n'
                    f"        <tt:Resolution>\n"
                    f"          <tt:Width>{w}</tt:Width><tt:Height>{h}</tt:Height>\n"
                    f"        </tt:Resolution>\n"
                    f"        <tt:Encoding>{encoding}</tt:Encoding>\n"
                    "      </tr2:VideoEncoder>\n"
                )
            profiles_xml_parts.append(
                f'    <tr2:Profiles token="{p["token"]}" fixed="true">\n'
                f"      <tt:Name>{p.get('name', p['token'])}</tt:Name>\n"
                "      <tr2:Configurations>\n"
                f"{venc_block}"
                "      </tr2:Configurations>\n"
                "    </tr2:Profiles>\n"
            )

        profiles_xml = "".join(profiles_xml_parts)
        return 200, (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">\n'
            "  <s:Body>\n"
            '    <tr2:GetProfilesResponse xmlns:tr2="http://www.onvif.org/ver20/media/wsdl" '
            'xmlns:tt="http://www.onvif.org/ver10/schema">\n'
            f"{profiles_xml}"
            "    </tr2:GetProfilesResponse>\n"
            "  </s:Body>\n"
            "</s:Envelope>"
        )

    # 2. GetStreamUri
    if "GetStreamUri" in body_text:
        host = "127.0.0.1"
        for k, v in headers:
            if k.lower() == b"host":
                host = v.decode("latin1").split(":")[0]
                break

        uri = settings.stream_uri_template.format(host=host)
        return 200, (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">\n'
            "  <s:Body>\n"
            '    <tr2:GetStreamUriResponse xmlns:tr2="http://www.onvif.org/ver20/media/wsdl" '
            'xmlns:tt="http://www.onvif.org/ver10/schema">\n'
            f"      <tt:Uri>{uri}</tt:Uri>\n"
            "    </tr2:GetStreamUriResponse>\n"
            "  </s:Body>\n"
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
