"""mDNS zero-configuration LAN service advertiser using python-zeroconf (MOB-02)."""

from __future__ import annotations

import logging
import socket
from typing import Any

from zeroconf import ServiceInfo, Zeroconf

logger = logging.getLogger(__name__)

SERVICE_TYPE = "_vizenlink-nvr._tcp.local."


def _is_usable_lan_ipv4(ip: str) -> bool:
    """Return True if *ip* is a valid non-loopback, non-link-local IPv4 address."""
    if not ip or ip.startswith(("127.", "169.254.", "0.")):
        return False
    try:
        socket.inet_aton(ip)
    except OSError:
        return False
    return True


def get_local_ip() -> str:
    """Best-effort discovery of primary local IPv4 address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Does not send actual traffic, merely resolves local routing interface
        s.connect(("8.8.8.8", 80))
        candidate = str(s.getsockname()[0])
        if _is_usable_lan_ipv4(candidate):
            return candidate
    except Exception as exc:
        logger.debug("UDP routing IP probe failed, falling back to interface scan: %s", exc)
    finally:
        s.close()

    # Fallback for air-gapped/offline LANs with no default internet route
    try:
        import ifaddr

        for adapter in ifaddr.get_adapters():
            for ip in adapter.ips:
                if isinstance(ip.ip, str) and _is_usable_lan_ipv4(ip.ip):
                    return ip.ip
    except Exception as exc:
        logger.debug("Interface scan fallback failed: %s", exc)

    return "127.0.0.1"


class NvrMdnsAdvertiser:
    """Advertises VizenLink NVR on the local network via mDNS/DNS-SD."""

    def __init__(
        self,
        nvr_id: str,
        name: str = "VizenLink-NVR",
        port: int = 8000,
        ip_address: str | None = None,
        tls: bool = False,
        api_version: str = "v1",
        zeroconf_instance: Zeroconf | None = None,
    ) -> None:
        self.nvr_id = nvr_id
        self.name = name.strip() or "VizenLink-NVR"
        self.port = port
        self.ip_address = ip_address or get_local_ip()
        self.tls = tls
        self.api_version = api_version
        self._custom_zc = zeroconf_instance is not None
        self._zeroconf: Zeroconf | None = zeroconf_instance
        self._info: ServiceInfo | None = None
        self._is_running = False

    @property
    def is_running(self) -> bool:
        """Return True if service is actively registered and advertising."""
        return self._is_running

    @property
    def service_info(self) -> ServiceInfo | None:
        """Return the active Zeroconf ServiceInfo, if registered."""
        return self._info

    def _build_service_info(self, addr_bytes: bytes) -> tuple[str, ServiceInfo]:
        """Build DNS-SD ServiceInfo for the given packed IPv4 address."""
        sanitized_name = self.name.replace(".", "-").replace("/", "-")
        full_service_name = f"{sanitized_name}._vizenlink-nvr._tcp.local."
        server_host = f"{self.nvr_id.replace('.', '-')}.local."

        properties: dict[str, Any] = {
            "api_version": self.api_version,
            "nvr_id": self.nvr_id,
            "name": self.name,
            "model": "VizenLink-NVR",
            "port": str(self.port),
            "tls": "true" if self.tls else "false",
        }

        info = ServiceInfo(
            SERVICE_TYPE,
            full_service_name,
            addresses=[addr_bytes],
            port=self.port,
            properties=properties,
            server=server_host,
        )
        return full_service_name, info

    def start(self) -> bool:
        """Register mDNS service info on the local network."""
        if self._is_running:
            return True

        try:
            addr_bytes = socket.inet_aton(self.ip_address)
        except OSError:
            logger.warning("Invalid IPv4 address %s, falling back to 127.0.0.1", self.ip_address)
            self.ip_address = "127.0.0.1"
            addr_bytes = socket.inet_aton(self.ip_address)

        full_service_name, self._info = self._build_service_info(addr_bytes)

        try:
            if self._zeroconf is None:
                self._zeroconf = Zeroconf()
            self._zeroconf.register_service(self._info)
            self._is_running = True
            logger.info("mDNS advertiser started: %s on %s:%d", full_service_name, self.ip_address, self.port)
            return True
        except Exception as exc:
            logger.error("Failed to register mDNS service: %s", exc)
            self._is_running = False
            return False

    def refresh_ip(self, new_ip: str | None = None) -> bool:
        """Update advertised IPv4 address if the host's LAN IP changed."""
        if not self._is_running or self._zeroconf is None:
            return False

        candidate = new_ip or get_local_ip()
        if candidate == self.ip_address or candidate.startswith("127."):
            return False

        try:
            addr_bytes = socket.inet_aton(candidate)
        except OSError:
            logger.warning("Ignoring invalid mDNS IPv4 address: %s", candidate)
            return False

        full_service_name, new_info = self._build_service_info(addr_bytes)
        old_info = self._info
        try:
            try:
                self._zeroconf.update_service(new_info)
            except Exception as exc:
                logger.debug("mDNS update_service failed, re-registering service: %s", exc)
                if old_info is not None:
                    try:
                        self._zeroconf.unregister_service(old_info)
                    except Exception as unreg_exc:
                        logger.debug("mDNS unregister during refresh ignored: %s", unreg_exc)
                self._zeroconf.register_service(new_info)
            self.ip_address = candidate
            self._info = new_info
            logger.info("mDNS advertiser IP updated: %s on %s:%d", full_service_name, candidate, self.port)
            return True
        except Exception as exc:
            logger.warning("Failed to update mDNS service IP to %s: %s", candidate, exc)
            return False

    def stop(self) -> None:
        """Deregister mDNS service info and close Zeroconf if owned."""
        if not self._is_running and self._info is None:
            return

        if self._zeroconf is not None and self._info is not None:
            try:
                self._zeroconf.unregister_service(self._info)
            except Exception as exc:
                logger.warning("Error unregistering mDNS service: %s", exc)

        if not self._custom_zc and self._zeroconf is not None:
            try:
                self._zeroconf.close()
            except Exception as exc:
                logger.warning("Error closing Zeroconf: %s", exc)
            self._zeroconf = None

        self._info = None
        self._is_running = False
        logger.info("mDNS advertiser stopped")

    def __enter__(self) -> NvrMdnsAdvertiser:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()

