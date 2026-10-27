"""Camera connection endpoint configuration and credentials."""

from dataclasses import dataclass, replace
from typing import Self

from pydantic import SecretStr

DEVICE_SERVICE_PATH = "/onvif/device_service"


@dataclass(frozen=True)
class CameraConnection:
    """Network connection parameters, credentials, and pinned certificate for a camera."""

    host: str
    port: int = 443
    username: str = ""
    password: SecretStr = SecretStr("")
    serial: str | None = None
    mac: str | None = None
    tls_pin_sha256: str | None = None

    @classmethod
    def blank(cls, host: str, port: int = 443, serial: str | None = None) -> Self:
        """Create a blank credential connection for initial discovery/probe."""
        return cls(host=host, port=port, serial=serial)

    def with_address(self, host: str, port: int | None = None) -> Self:
        """Return a copy with updated address/port."""
        new_port = self.port if port is None else port
        return replace(self, host=host, port=new_port)

    def with_credentials(self, username: str, password: str | SecretStr) -> Self:
        """Return a copy with updated credentials."""
        pw = password if isinstance(password, SecretStr) else SecretStr(password)
        return replace(self, username=username, password=pw)

    @property
    def base_url(self) -> str:
        """Compute base HTTPS URL, bracketing IPv6 literal hosts."""
        h = self.host
        if ":" in h and not (h.startswith("[") and h.endswith("]")):
            h = f"[{h}]"
        return f"https://{h}:{self.port}"
