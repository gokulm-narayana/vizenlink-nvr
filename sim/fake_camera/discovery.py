"""WS-Discovery UDP responder for fake camera devices."""

import asyncio
import re
import urllib.parse
import uuid

from fake_camera.server import FakeCamera


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    """Protocol handling incoming WS-Discovery UDP Probe datagrams."""

    def __init__(self, responder: "DiscoveryResponder") -> None:
        self.responder = responder
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if not self.transport:
            return
        msg = data.decode("utf-8", errors="ignore")
        match = re.search(r"<[a-zA-Z0-9_:]*MessageID[^>]*>([^<]+)</", msg)
        msg_id = match.group(1).strip() if match else f"urn:uuid:{uuid.uuid4()}"

        for cam in self.responder.cameras:
            reply = self.responder.build_probe_matches(cam, msg_id)
            self.transport.sendto(reply.encode("utf-8"), addr)


class DiscoveryResponder:
    """UDP WS-Discovery responder on loopback answering Probes for registered cameras."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = port
        self.cameras: list[FakeCamera] = []
        self._transport: asyncio.DatagramTransport | None = None

    def attach(self, cam: FakeCamera) -> None:
        """Register a fake camera to be announced in probe matches."""
        if cam not in self.cameras:
            self.cameras.append(cam)

    def build_probe_matches(self, cam: FakeCamera, relates_to: str) -> str:
        """Construct ProbeMatches SOAP XML for a given camera."""
        name_enc = urllib.parse.quote(cam.state.name)
        loc_enc = urllib.parse.quote(cam.state.location)
        scopes = (
            f"onvif://www.onvif.org/type/video_encoder "
            f"onvif://www.onvif.org/type/audio_encoder "
            f"onvif://www.onvif.org/hardware/{cam.state.hardware_id} "
            f"onvif://www.onvif.org/name/{name_enc} "
            f"onvif://www.onvif.org/location/{loc_enc} "
            f"onvif://www.onvif.org/MAC/{cam.state.mac}"
        )
        xaddr = f"https://{cam.host}:{cam.port}/onvif/device_service"
        reply_uuid = f"urn:uuid:{uuid.uuid4()}"

        return (
            f'<?xml version="1.0" encoding="utf-8"?>\n'
            f'<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"\n'
            f'               xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"\n'
            f'               xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"\n'
            f'               xmlns:dn="http://www.onvif.org/ver10/network/wsdl">\n'
            f"  <soap:Header>\n"
            f"    <wsa:MessageID>{reply_uuid}</wsa:MessageID>\n"
            f"    <wsa:RelatesTo>{relates_to}</wsa:RelatesTo>\n"
            f"    <wsa:To>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</wsa:To>\n"
            f"    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches</wsa:Action>\n"
            f"  </soap:Header>\n"
            f"  <soap:Body>\n"
            f"    <d:ProbeMatches>\n"
            f"      <d:ProbeMatch>\n"
            f"        <wsa:EndpointReference>\n"
            f"          <wsa:Address>urn:uuid:{cam.state.serial}</wsa:Address>\n"
            f"        </wsa:EndpointReference>\n"
            f"        <d:Types>dn:NetworkVideoTransmitter</d:Types>\n"
            f"        <d:Scopes>{scopes}</d:Scopes>\n"
            f"        <d:XAddrs>{xaddr}</d:XAddrs>\n"
            f"        <d:MetadataVersion>1</d:MetadataVersion>\n"
            f"      </d:ProbeMatch>\n"
            f"    </d:ProbeMatches>\n"
            f"  </soap:Body>\n"
            f"</soap:Envelope>"
        )

    async def start(self) -> None:
        """Start UDP listener on loopback port."""
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _DiscoveryProtocol(self),
            local_addr=(self.host, self.port),
        )
        self._transport = transport
        self.port = transport.get_extra_info("sockname")[1]

    async def close(self) -> None:
        """Close UDP transport."""
        if self._transport is not None:
            self._transport.close()
            self._transport = None
