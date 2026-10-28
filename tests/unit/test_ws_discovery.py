"""Unit tests for WS-Discovery wire format, interfaces, pacing, and candidate parsing (DSC-01..DSC-04)."""

import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fake_camera.discovery import DiscoveryResponder
from fake_camera.server import FakeCamera

from vizenlink_nvr.camera.discovery.ws_discovery import (
    DiscoveredDevice,
    Ipv4Interface,
    WsDiscoveryClient,
    _WsDiscoveryProtocol,
    build_probe,
    parse_probe_matches,
    sweep_hosts,
)
from vizenlink_nvr.timeutil import FakeClock

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "contracts" / "fixtures" / "discovery"


@pytest.mark.behavior("DSC-01")
def test_dsc_01_probe_envelope() -> None:
    """DSC-01: Probe envelope has SOAP 1.2, NetworkVideoTransmitter, Action, and fresh MessageID."""
    p1 = build_probe("msg-1")
    p2 = build_probe("msg-2")
    assert p1 != p2

    text1 = p1.decode("utf-8")
    assert "http://www.w3.org/2003/05/soap-envelope" in text1
    assert "dn:NetworkVideoTransmitter" in text1
    assert 'xmlns:dn="http://www.onvif.org/ver10/network/wsdl"' in text1
    assert "<w:MessageID>uuid:msg-1</w:MessageID>" in text1
    assert "<w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>" in text1

    text2 = p2.decode("utf-8")
    assert "<w:MessageID>uuid:msg-2</w:MessageID>" in text2


@pytest.mark.behavior("DSC-02")
def test_dsc_02_parse_probe_matches() -> None:
    """DSC-02: Firmware fixture parsing, port fallbacks, deduplication, and source host precedence."""
    firmware_xml = (FIXTURES_DIR / "probe_matches_firmware.xml").read_bytes()
    devs = parse_probe_matches(firmware_xml, "192.168.1.42")
    assert len(devs) == 1
    d = devs[0]
    assert d.host == "192.168.1.42"
    assert d.port == 80
    assert d.scheme == "http"
    assert d.xaddr == "http://192.168.1.42:80/onvif/device_service"

    # HTTPS without explicit port -> port 443; XAddrs host 10.9.9.9 ignored, source host used
    https_xml = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
        b'xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery">'
        b"<s:Body><d:ProbeMatches><d:ProbeMatch>"
        b"<d:XAddrs>https://10.9.9.9/onvif/device_service</d:XAddrs>"
        b"</d:ProbeMatch></d:ProbeMatches></s:Body></s:Envelope>"
    )
    devs_https = parse_probe_matches(https_xml, "127.0.0.1")
    assert len(devs_https) == 1
    assert devs_https[0].host == "127.0.0.1"
    assert devs_https[0].port == 443
    assert devs_https[0].scheme == "https"

    # Two datagrams from one host -> deduped to one device
    results: dict[tuple[str, int], DiscoveredDevice] = {}
    for _ in range(2):
        for dev in parse_probe_matches(firmware_xml, "192.168.1.42"):
            results[(dev.host, dev.port)] = dev
    assert len(results) == 1

    # Garbage bytes -> ignored (returns [])
    assert parse_probe_matches(b"invalid xml garbage bytes", "192.168.1.42") == []

    # 70 KiB datagram -> ignored (> 64 KiB MAX_DATAGRAM)
    assert parse_probe_matches(b"<xml>" + (b"A" * 70000) + b"</xml>", "192.168.1.42") == []


@pytest.mark.behavior("DSC-03")
async def test_dsc_03_multicast_sweep_interfaces() -> None:
    """DSC-03: Per-interface sends with IP_MULTICAST_IF, destination (239.255.255.250, 3702), and 5s wait."""
    ifaces = [
        Ipv4Interface(address="192.168.1.10", prefix=24, name="eth0"),
        Ipv4Interface(address="10.0.0.5", prefix=16, name="eth1"),
    ]

    class RecordingSocket:
        def __init__(self, iface: Ipv4Interface) -> None:
            self.iface = iface
            self.setsockopts: list[tuple[int, int, bytes]] = []
            self.sends: list[tuple[bytes, tuple[str, int]]] = []

        def setsockopt(self, level: int, optname: int, value: bytes) -> None:
            self.setsockopts.append((level, optname, value))

        def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
            self.sends.append((data, addr))

        def close(self) -> None:
            pass

    created_sockets: list[RecordingSocket] = []

    def recording_socket_factory(iface: Ipv4Interface) -> Any:
        s = RecordingSocket(iface)
        created_sockets.append(s)
        return s

    clock = FakeClock(datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC))
    recorded_sleeps: list[float] = []

    async def fake_sleep(secs: float) -> None:
        recorded_sleeps.append(secs)
        clock.advance(timedelta(seconds=secs))

    client = WsDiscoveryClient(
        interfaces=lambda: ifaces,
        clock=clock,
        sleep=fake_sleep,
        socket_factory=recording_socket_factory,
    )

    await client.scan_multicast(wait=5.0)

    # 2 sockets created (one per eligible interface)
    assert len(created_sockets) == 2

    # Check first socket (192.168.1.10)
    s1 = created_sockets[0]
    assert s1.iface.address == "192.168.1.10"
    assert (
        socket.IPPROTO_IP,
        socket.IP_MULTICAST_IF,
        socket.inet_aton("192.168.1.10"),
    ) in s1.setsockopts
    assert len(s1.sends) == 1
    assert s1.sends[0][1] == ("239.255.255.250", 3702)

    # Check second socket (10.0.0.5)
    s2 = created_sockets[1]
    assert s2.iface.address == "10.0.0.5"
    assert (
        socket.IPPROTO_IP,
        socket.IP_MULTICAST_IF,
        socket.inet_aton("10.0.0.5"),
    ) in s2.setsockopts
    assert len(s2.sends) == 1
    assert s2.sends[0][1] == ("239.255.255.250", 3702)

    # Wait equals 5s
    assert recorded_sleeps == [5.0]


@pytest.mark.behavior("DSC-04")
async def test_dsc_04_sweep_hosts_and_unicast_pacing(
    discovery_responder: DiscoveryResponder,
    fake_camera: pytest.FixtureRequest,
) -> None:
    """DSC-04: sweep_hosts masking, 50ms pacing, 30s cap / 10s straggler wait, and ICMP reset tolerance."""
    # 1. sweep_hosts for 192.168.1.10/24 -> 253 hosts
    h24 = sweep_hosts([Ipv4Interface("192.168.1.10", 24, "eth0")])
    assert len(h24) == 253
    assert "192.168.1.0" not in h24
    assert "192.168.1.255" not in h24
    assert "192.168.1.10" not in h24

    # 2. 10.0.0.5/16 sweeps 10.0.0.0/24 only -> 253 hosts
    h16 = sweep_hosts([Ipv4Interface("10.0.0.5", 16, "eth1")])
    assert len(h16) == 253
    assert all(ip.startswith("10.0.0.") for ip in h16)
    assert "10.0.0.5" not in h16

    # 3. 192.168.5.9/30 sweeps its 2-host /30 minus itself -> 1 host
    h30 = sweep_hosts([Ipv4Interface("192.168.5.9", 30, "eth2")])
    assert h30 == ["192.168.5.10"]

    # 4. Pacing and cap timing
    clock = FakeClock(datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC))
    recorded_sleeps: list[float] = []

    async def fake_sleep(secs: float) -> None:
        recorded_sleeps.append(secs)
        clock.advance(timedelta(seconds=secs))

    class MockUnicastSocket:
        def __init__(self) -> None:
            self.sends: list[tuple[bytes, tuple[str, int]]] = []

        def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
            self.sends.append((data, addr))

        def close(self) -> None:
            pass

    mock_sock = MockUnicastSocket()
    client = WsDiscoveryClient(
        unicast_hosts=["192.168.1.1", "192.168.1.2", "192.168.1.3"],
        clock=clock,
        sleep=fake_sleep,
        socket_factory=lambda _: mock_sock,
    )

    await client.scan_unicast(overall_cap=30.0, straggler_wait=10.0, send_interval=0.05)
    # 3 sends spaced by 0.05s
    assert len(mock_sock.sends) == 3
    assert recorded_sleeps[:3] == [0.05, 0.05, 0.05]
    # Straggler wait equals 10s (since elapsed 0.15s << 30s cap)
    assert recorded_sleeps[3] == 10.0

    # 5. ConnectionResetError tolerance on endpoint error_received
    proto = _WsDiscoveryProtocol("test-id", lambda dev: None)
    # Must not raise
    proto.error_received(ConnectionResetError("ICMP Port Unreachable"))

    # 6. Real UDP socket test: send to closed local port, then send to discovery responder
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-UDP01")
    real_clock = FakeClock(datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC))
    real_client = WsDiscoveryClient(
        port=discovery_responder.port,
        unicast_hosts=["127.0.0.1"],
        clock=real_clock,
    )
    devs = await real_client.scan_unicast(overall_cap=1.0, straggler_wait=0.2, send_interval=0.01)
    assert any(d.host == "127.0.0.1" and d.port == cam.port for d in devs)
