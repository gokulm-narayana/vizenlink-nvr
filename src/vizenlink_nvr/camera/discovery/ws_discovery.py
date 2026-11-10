# mirrors: mobile_app/packages/camera_api/lib/src/lan/discovery/ws_discovery_client.dart@9c4d91a9fccd
"""WS-Discovery client for discovering ONVIF and VizenLink cameras on the local network."""

import asyncio
import ipaddress
import logging
import re
import socket
import urllib.parse
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import defusedxml.ElementTree as ET
import ifaddr

from vizenlink_nvr.camera.onvif.device import (
    LOCATION_SCOPE_PREFIX,
    MAC_SCOPE_PREFIX,
    NAME_SCOPE_PREFIX,
    normalize_mac,
)
from vizenlink_nvr.camera.onvif.soap import find_text
from vizenlink_nvr.timeutil import Clock

logger = logging.getLogger(__name__)

MAX_DATAGRAM = 65536
MAX_CANDIDATES = 512
MULTICAST_GROUP = "239.255.255.250"
DISCOVERY_PORT = 3702
ONVIF_NETWORK_NAMESPACE = "http://www.onvif.org/ver10/network/wsdl"
ACTION_PROBE = "http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe"
TO_DISCOVERY = "urn:schemas-xmlsoap-org:ws:2005:04:discovery"


@dataclass(frozen=True)
class Ipv4Interface:
    """Local IPv4 network interface descriptor."""

    address: str
    prefix: int
    name: str


@dataclass(frozen=True)
class DiscoveredDevice:
    """Device discovered via WS-Discovery ProbeMatches."""

    host: str
    port: int
    scheme: str
    xaddr: str
    scopes: list[str]
    mac_hint: str | None = None
    name_hint: str | None = None
    location_hint: str | None = None


def local_ipv4_interfaces() -> list[Ipv4Interface]:
    """List eligible local IPv4 network interfaces, skipping loopback and link-local (169.254/16)."""
    interfaces: list[Ipv4Interface] = []
    adapters = ifaddr.get_adapters()
    for adapter in adapters:
        for ip in adapter.ips:
            if not isinstance(ip.ip, str) or "." not in ip.ip:
                continue
            try:
                addr = ipaddress.IPv4Address(ip.ip)
            except ValueError:
                continue

            if addr.is_loopback or addr.is_link_local:
                continue

            interfaces.append(
                Ipv4Interface(
                    address=ip.ip,
                    prefix=ip.network_prefix,
                    name=adapter.name,
                )
            )
    return interfaces


def sweep_hosts(interfaces: list[Ipv4Interface]) -> list[str]:
    """Derive unicast sweep target IPs from interfaces, bounded to max(prefix, 24)."""
    own_ips = {iface.address for iface in interfaces}
    hosts: list[str] = []
    seen: set[str] = set()

    for iface in interfaces:
        sweep_prefix = max(iface.prefix, 24)
        try:
            network = ipaddress.IPv4Network(f"{iface.address}/{sweep_prefix}", strict=False)
        except ValueError:
            continue

        for host in network.hosts():
            h_str = str(host)
            if h_str not in own_ips and h_str not in seen:
                seen.add(h_str)
                hosts.append(h_str)

    return hosts


def build_probe(message_id: str) -> bytes:
    """Build WS-Discovery Probe SOAP 1.2 XML datagram bytes."""
    msg_id = message_id if message_id.startswith("uuid:") else f"uuid:{message_id}"
    xml_str = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing" '
        'xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" '
        f'xmlns:dn="{ONVIF_NETWORK_NAMESPACE}">\n'
        "  <e:Header>\n"
        f"    <w:MessageID>{msg_id}</w:MessageID>\n"
        f"    <w:To>{TO_DISCOVERY}</w:To>\n"
        f"    <w:Action>{ACTION_PROBE}</w:Action>\n"
        "  </e:Header>\n"
        "  <e:Body>\n"
        "    <d:Probe>\n"
        "      <d:Types>dn:NetworkVideoTransmitter</d:Types>\n"
        "    </d:Probe>\n"
        "  </e:Body>\n"
        "</e:Envelope>"
    )
    return xml_str.encode("utf-8")


def parse_probe_matches(data: bytes, source_host: str) -> list[DiscoveredDevice]:
    """Parse ProbeMatches response bytes into DiscoveredDevice entries."""
    if len(data) > MAX_DATAGRAM:
        return []

    try:
        root = ET.fromstring(data)
    except Exception:
        return []

    devices: list[DiscoveredDevice] = []
    probe_matches = [
        el for el in root.iter() if (el.tag.split("}")[-1] if "}" in el.tag else el.tag) == "ProbeMatch"
    ]
    search_nodes = probe_matches if probe_matches else [root]

    for node in search_nodes:
        xaddrs_str = find_text(node, "XAddrs")
        if not xaddrs_str:
            continue

        first_url = ""
        for token in xaddrs_str.split():
            clean = token.strip()
            if clean.startswith("http://") or clean.startswith("https://"):
                first_url = clean
                break

        if not first_url:
            continue

        try:
            parts = urllib.parse.urlsplit(first_url)
        except Exception as exc:
            logger.debug("Failed to parse XAddrs URL %s: %s", first_url, exc)
            continue

        scheme = parts.scheme.lower()
        port = parts.port if parts.port is not None else (443 if scheme == "https" else 80)

        if parts.hostname and parts.hostname != source_host:
            logger.debug("XAddrs host %s differs from source host %s", parts.hostname, source_host)

        scopes_str = find_text(node, "Scopes")
        scopes = [s.strip() for s in scopes_str.split()] if scopes_str else []

        mac_hint: str | None = None
        name_hint: str | None = None
        location_hint: str | None = None

        for s in scopes:
            if s.startswith(MAC_SCOPE_PREFIX):
                raw_mac = s[len(MAC_SCOPE_PREFIX) :]
                # camera_api normalizeMac: only a 12-hex-digit MAC counts; anything else is no hint.
                if len(re.sub(r"[^0-9A-Fa-f]", "", raw_mac)) == 12:
                    mac_hint = normalize_mac(raw_mac)
            elif s.startswith(NAME_SCOPE_PREFIX):
                name_hint = urllib.parse.unquote(s[len(NAME_SCOPE_PREFIX) :])
            elif s.startswith(LOCATION_SCOPE_PREFIX):
                location_hint = urllib.parse.unquote(s[len(LOCATION_SCOPE_PREFIX) :])

        devices.append(
            DiscoveredDevice(
                host=source_host,
                port=port,
                scheme=scheme,
                xaddr=first_url,
                scopes=scopes,
                mac_hint=mac_hint,
                name_hint=name_hint,
                location_hint=location_hint,
            )
        )

    return devices


class _WsDiscoveryProtocol(asyncio.DatagramProtocol):
    """Asyncio UDP datagram protocol collecting correlated probe matches."""

    def __init__(
        self,
        expected_msg_id: str,
        on_candidate: Callable[[DiscoveredDevice], None],
    ) -> None:
        self.expected_msg_id = expected_msg_id
        self.on_candidate = on_candidate
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if len(data) > MAX_DATAGRAM:
            return

        # Check RelatesTo correlation
        match = re.search(rb"<[a-zA-Z0-9_:]*RelatesTo[^>]*>([^<]+)</", data)
        if match:
            relates_to = match.group(1).decode("utf-8", errors="ignore").strip()
            clean_expected = (
                self.expected_msg_id[5:] if self.expected_msg_id.startswith("uuid:") else self.expected_msg_id
            )
            clean_relates = relates_to[5:] if relates_to.startswith("uuid:") else relates_to
            if clean_relates != clean_expected:
                return

        devices = parse_probe_matches(data, addr[0])
        for dev in devices:
            self.on_candidate(dev)

    def error_received(self, exc: Exception) -> None:
        # Ignore ConnectionResetError / OSError (Windows ICMP unreachable)
        pass


def _create_proto_factory(
    mid: str,
    cb: Callable[[DiscoveredDevice], None],
) -> Callable[[], _WsDiscoveryProtocol]:
    """Factory creating protocol instance bound to specific message ID."""

    def _factory() -> _WsDiscoveryProtocol:
        return _WsDiscoveryProtocol(mid, cb)

    return _factory


class WsDiscoveryClient:
    """Client coordinating multicast and unicast WS-Discovery passes."""

    def __init__(
        self,
        *,
        port: int = DISCOVERY_PORT,
        multicast_group: str = MULTICAST_GROUP,
        interfaces: Callable[[], list[Ipv4Interface]] = local_ipv4_interfaces,
        unicast_hosts: list[str] | None = None,
        clock: Clock,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        socket_factory: Any = None,
    ) -> None:
        self.port = port
        self.multicast_group = multicast_group
        self.interfaces = interfaces
        self.unicast_hosts = unicast_hosts
        self.clock = clock
        self.sleep = sleep
        self.socket_factory = socket_factory

    async def scan_multicast(self, wait: float = 5.0) -> list[DiscoveredDevice]:
        """Perform multicast WS-Discovery sweep across local IPv4 interfaces (DSC-03)."""
        ifaces = self.interfaces()
        # Fallback for loopback testing if no physical interfaces
        if not ifaces and self.multicast_group in ("127.0.0.1", "localhost"):
            ifaces = [Ipv4Interface(address="127.0.0.1", prefix=8, name="lo0")]

        if not ifaces:
            return []

        results: dict[tuple[str, int], DiscoveredDevice] = {}

        def on_candidate(dev: DiscoveredDevice) -> None:
            if len(results) < MAX_CANDIDATES:
                results[(dev.host, dev.port)] = dev

        loop = asyncio.get_running_loop()
        transports: list[asyncio.DatagramTransport] = []
        mock_socks: list[Any] = []

        try:
            for iface in ifaces:
                msg_id = str(uuid.uuid4())
                probe_bytes = build_probe(msg_id)

                sock = None
                if self.socket_factory is not None:
                    try:
                        sock = self.socket_factory(iface)
                    except TypeError:
                        sock = self.socket_factory()
                else:
                    raw_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                    raw_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    raw_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    raw_sock.bind(("", 0))
                    sock = raw_sock

                if hasattr(sock, "setsockopt") and self.multicast_group not in ("127.0.0.1", "localhost"):
                    try:
                        sock.setsockopt(
                            socket.IPPROTO_IP,
                            socket.IP_MULTICAST_IF,
                            socket.inet_aton(iface.address),
                        )
                    except OSError:
                        pass

                if isinstance(sock, socket.socket):
                    transport, _ = await loop.create_datagram_endpoint(
                        _create_proto_factory(msg_id, on_candidate),
                        sock=sock,
                    )
                    transports.append(transport)
                    transport.sendto(probe_bytes, (self.multicast_group, self.port))
                elif sock is not None:
                    mock_socks.append(sock)
                    sock.sendto(probe_bytes, (self.multicast_group, self.port))

            await self.sleep(wait)
        finally:
            for t in transports:
                t.close()
            for s in mock_socks:
                if hasattr(s, "close"):
                    s.close()

        return list(results.values())

    async def scan_unicast(
        self,
        overall_cap: float = 30.0,
        straggler_wait: float = 10.0,
        send_interval: float = 0.05,
    ) -> list[DiscoveredDevice]:
        """Perform unicast WS-Discovery sweep across target IPv4 subnets (DSC-04)."""
        if self.unicast_hosts is not None:
            hosts = self.unicast_hosts
        else:
            ifaces = self.interfaces()
            hosts = sweep_hosts(ifaces)

        if not hosts:
            return []

        results: dict[tuple[str, int], DiscoveredDevice] = {}

        def on_candidate(dev: DiscoveredDevice) -> None:
            if len(results) < MAX_CANDIDATES:
                results[(dev.host, dev.port)] = dev

        loop = asyncio.get_running_loop()
        msg_id = str(uuid.uuid4())
        probe_bytes = build_probe(msg_id)

        sock = None
        if self.socket_factory is not None:
            try:
                sock = self.socket_factory(None)
            except TypeError:
                sock = self.socket_factory()
        else:
            raw_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            raw_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            raw_sock.bind(("", 0))
            sock = raw_sock

        transport: asyncio.DatagramTransport | None = None
        mock_sock: Any = None

        if isinstance(sock, socket.socket):
            transport, _ = await loop.create_datagram_endpoint(
                _create_proto_factory(msg_id, on_candidate),
                sock=sock,
            )
        else:
            mock_sock = sock

        start_time = self.clock.now()
        try:
            for ip in hosts:
                elapsed = (self.clock.now() - start_time).total_seconds()
                if elapsed >= overall_cap:
                    break

                if transport is not None:
                    transport.sendto(probe_bytes, (ip, self.port))
                elif mock_sock is not None:
                    mock_sock.sendto(probe_bytes, (ip, self.port))

                await self.sleep(send_interval)

            elapsed = (self.clock.now() - start_time).total_seconds()
            remaining_cap = overall_cap - elapsed
            wait = min(remaining_cap, straggler_wait) if remaining_cap > 0 else 0
            if wait > 0:
                await self.sleep(wait)
        finally:
            if transport is not None:
                transport.close()
            elif mock_sock is not None and hasattr(mock_sock, "close"):
                mock_sock.close()

        return list(results.values())
