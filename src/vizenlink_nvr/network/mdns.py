"""mDNS zero-configuration LAN service advertiser using python-zeroconf (MOB-02)."""

from __future__ import annotations

import logging
import socket
from typing import Any

from zeroconf import ServiceInfo, Zeroconf

logger = logging.getLogger(__name__)

SERVICE_TYPE = "_vizenlink-nvr._tcp.local."


def get_local_ip() -> str:
    """Best-effort discovery of primary local IPv4 address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Does not send actual traffic, merely resolves local routing interface
        s.connect(("8.8.8.8", 80))
        return str(s.getsockname()[0])
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


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

    def start(self) -> bool:
        """Register mDNS service info on the local network."""
        if self._is_running:
            return True

        # Sanitize name for DNS-SD: remove slashes/dots from local instance name
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

        try:
            addr_bytes = socket.inet_aton(self.ip_address)
        except OSError:
            logger.warning("Invalid IPv4 address %s, falling back to 127.0.0.1", self.ip_address)
            self.ip_address = "127.0.0.1"
            addr_bytes = socket.inet_aton(self.ip_address)

        self._info = ServiceInfo(
            SERVICE_TYPE,
            full_service_name,
            addresses=[addr_bytes],
            port=self.port,
            properties=properties,
            server=server_host,
        )

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
