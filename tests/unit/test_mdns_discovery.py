"""Unit tests for NvrMdnsAdvertiser (MOB-02)."""

from __future__ import annotations

import socket
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from vizenlink_nvr.network.mdns import SERVICE_TYPE, NvrMdnsAdvertiser, get_local_ip


def test_get_local_ip_fallback() -> None:
    """Ensure get_local_ip returns a non-empty valid IPv4 string."""
    ip = get_local_ip()
    assert isinstance(ip, str)
    # verify valid ip address bytes
    assert len(socket.inet_aton(ip)) == 4


def test_mdns_advertiser_service_info_properties() -> None:
    """Verify ServiceInfo creation with expected DNS-SD properties."""
    mock_zc = MagicMock()
    adv = NvrMdnsAdvertiser(
        nvr_id="test-nvr-1234",
        name="Front Office NVR",
        port=8080,
        ip_address="192.168.1.100",
        tls=True,
        api_version="v1",
        zeroconf_instance=mock_zc,
    )

    started = adv.start()
    assert started is True
    assert adv.is_running is True
    assert adv.service_info is not None

    info = adv.service_info
    assert info.type == SERVICE_TYPE
    assert info.name == "Front Office NVR._vizenlink-nvr._tcp.local."
    assert info.port == 8080
    assert info.parsed_addresses() == ["192.168.1.100"]

    # Check decoded properties
    props = {k.decode("utf-8"): v.decode("utf-8") for k, v in info.properties.items()}
    assert props["api_version"] == "v1"
    assert props["nvr_id"] == "test-nvr-1234"
    assert props["name"] == "Front Office NVR"
    assert props["model"] == "VizenLink-NVR"
    assert props["port"] == "8080"
    assert props["tls"] == "true"

    mock_zc.register_service.assert_called_once_with(info)

    adv.stop()
    assert adv.is_running is False
    assert adv.service_info is None
    mock_zc.unregister_service.assert_called_once_with(info)
    # Mock passed in, should not close external zeroconf
    mock_zc.close.assert_not_called()


def test_mdns_advertiser_reentrancy() -> None:
    """Calling start() or stop() multiple times should be safe."""
    mock_zc = MagicMock()
    adv = NvrMdnsAdvertiser(
        nvr_id="test-nvr-5678",
        zeroconf_instance=mock_zc,
    )

    assert adv.start() is True
    assert adv.start() is True
    assert mock_zc.register_service.call_count == 1

    adv.stop()
    adv.stop()
    assert mock_zc.unregister_service.call_count == 1


def test_mdns_advertiser_context_manager() -> None:
    """Verify context manager enters and exits cleanly."""
    mock_zc = MagicMock()
    with NvrMdnsAdvertiser(nvr_id="cm-test", zeroconf_instance=mock_zc) as adv:
        assert adv.is_running is True
        assert mock_zc.register_service.call_count == 1

    assert adv.is_running is False
    assert mock_zc.unregister_service.call_count == 1


def test_mdns_advertiser_invalid_ip_fallback() -> None:
    """Invalid IP falls back to 127.0.0.1 gracefully."""
    mock_zc = MagicMock()
    adv = NvrMdnsAdvertiser(
        nvr_id="invalid-ip-test",
        ip_address="not.an.ip.address",
        zeroconf_instance=mock_zc,
    )
    assert adv.start() is True
    assert adv.ip_address == "127.0.0.1"
    assert adv.service_info.parsed_addresses() == ["127.0.0.1"]
    adv.stop()


def test_mdns_advertiser_register_exception_handling() -> None:
    """Registration errors return False and do not crash."""
    mock_zc = MagicMock()
    mock_zc.register_service.side_effect = OSError("Network unreachable")
    adv = NvrMdnsAdvertiser(
        nvr_id="err-test",
        zeroconf_instance=mock_zc,
    )
    assert adv.start() is False
    assert adv.is_running is False


def test_get_local_ip_offline_lan_uses_interface_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    """When external routing fails (offline LAN), get_local_ip scans local interfaces."""
    class FailingSocket:
        def connect(self, *_args: object) -> None:
            raise OSError("Network unreachable")

        def close(self) -> None:
            pass

    monkeypatch.setattr("vizenlink_nvr.network.mdns.socket.socket", lambda *_a, **_kw: FailingSocket())
    fake_adapters = [
        SimpleNamespace(ips=[SimpleNamespace(ip="127.0.0.1"), SimpleNamespace(ip="169.254.1.5")]),
        SimpleNamespace(ips=[SimpleNamespace(ip="192.168.77.25")]),
    ]
    monkeypatch.setattr("ifaddr.get_adapters", lambda: fake_adapters)

    assert get_local_ip() == "192.168.77.25"


def test_mdns_advertiser_refresh_ip() -> None:
    """refresh_ip updates the advertised ServiceInfo address without restart."""
    mock_zc = MagicMock()
    adv = NvrMdnsAdvertiser(
        nvr_id="refresh-test",
        name="Refresh NVR",
        port=8000,
        ip_address="192.168.1.10",
        zeroconf_instance=mock_zc,
    )
    assert adv.refresh_ip("192.168.1.20") is False  # Not started yet

    assert adv.start() is True
    assert adv.refresh_ip("192.168.1.10") is False  # Unchanged
    assert adv.refresh_ip("127.0.0.1") is False  # Never replace LAN IP with loopback

    assert adv.refresh_ip("192.168.1.20") is True
    assert adv.ip_address == "192.168.1.20"
    assert adv.service_info is not None
    assert adv.service_info.parsed_addresses() == ["192.168.1.20"]
    mock_zc.update_service.assert_called_once_with(adv.service_info)
    adv.stop()
