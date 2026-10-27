"""MediaMTX binary downloader, checksum validator, and execution helper."""

from __future__ import annotations

import io
import json
import os
import platform
import subprocess
import tarfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import platformdirs

if TYPE_CHECKING:
    from vizenlink_nvr.config import NvrSettings

MEDIAMTX_VERSION = "v1.21.3"


class UnsupportedPlatform(Exception):
    """Raised when current OS or architecture is not supported by MediaMTX pins."""


def load_pins() -> dict[str, Any]:
    """Load checksums and asset metadata for pinned MediaMTX releases."""
    pins_file = Path(__file__).parent / "pins.json"
    return json.loads(pins_file.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def platform_key() -> str:
    """Return platform key matching pins.json asset keys."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":
        sys_str = "darwin"
    elif system == "linux":
        sys_str = "linux"
    elif system == "windows":
        sys_str = "windows"
    else:
        raise UnsupportedPlatform(f"Unsupported system: {system}")

    if machine in ("x86_64", "amd64"):
        arch_str = "amd64"
    elif machine in ("arm64", "aarch64"):
        arch_str = "arm64"
    elif machine == "armv7l":
        arch_str = "armv7"
    elif machine == "armv6l":
        arch_str = "armv6"
    else:
        raise UnsupportedPlatform(f"Unsupported architecture: {machine}")

    return f"{sys_str}_{arch_str}"


def default_cache_dir() -> Path:
    """Return user cache directory for current MediaMTX version and platform."""
    base = Path(platformdirs.user_cache_dir("vizenlink-nvr"))
    return base / "mediamtx" / MEDIAMTX_VERSION / platform_key()


def fetch(dest_dir: Path | None = None) -> Path:
    """Download, verify SHA-256, and safely extract the pinned MediaMTX binary."""
    target_dir = dest_dir or default_cache_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    pins = load_pins()
    pkey = platform_key()
    assets = pins.get("assets", {})
    if pkey not in assets:
        raise UnsupportedPlatform(f"No asset found for platform {pkey}")

    asset = assets[pkey]
    url = f"{pins['url_base']}{asset['filename']}"

    with httpx.Client(follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        archive_data = resp.content

    import hashlib

    computed_sha256 = hashlib.sha256(archive_data).hexdigest()
    if computed_sha256.lower() != asset["sha256"].lower():
        raise ValueError(
            f"SHA-256 mismatch for {asset['filename']}: expected {asset['sha256']}, got {computed_sha256}"
        )

    # Safe extraction
    if asset["filename"].endswith(".tar.gz"):
        with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:gz") as tar:
            # Check for path traversal members
            for member in tar.getmembers():
                target_path = (target_dir / member.name).resolve()
                if not str(target_path).startswith(str(target_dir.resolve())):
                    raise ValueError(f"Path traversal detected in tar archive: {member.name}")
            tar.extractall(target_dir, filter="data")
    elif asset["filename"].endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(archive_data)) as z:
            for zip_info in z.infolist():
                target_path = (target_dir / zip_info.filename).resolve()
                if not str(target_path).startswith(str(target_dir.resolve())):
                    raise ValueError(f"Path traversal detected in zip archive: {zip_info.filename}")
                z.extract(zip_info, target_dir)
    else:
        raise ValueError(f"Unknown archive format: {asset['filename']}")

    bin_name = "mediamtx.exe" if os.name == "nt" else "mediamtx"
    bin_path = target_dir / bin_name
    if not bin_path.exists():
        raise FileNotFoundError(f"Binary {bin_name} not found after extraction in {target_dir}")

    if os.name == "posix":
        st = bin_path.stat().st_mode
        bin_path.chmod(st | 0o755)

    return bin_path


def resolve_binary(settings: NvrSettings) -> Path:
    """Resolve MediaMTX binary path from settings or default cache directory."""
    if settings.mediamtx_bin is not None and str(settings.mediamtx_bin).strip():
        p = Path(settings.mediamtx_bin)
        if p.exists():
            return p
        raise FileNotFoundError(f"Configured mediamtx_bin not found: {p}")

    bin_name = "mediamtx.exe" if os.name == "nt" else "mediamtx"
    p = default_cache_dir() / bin_name
    if p.exists():
        return p

    raise FileNotFoundError(
        f"MediaMTX binary not found at {p}. Run 'python tools/fetch_mediamtx.py' to download it."
    )


def binary_version(path: Path) -> str:
    """Return stripped version string of MediaMTX binary."""
    res = subprocess.run(  # noqa: S603
        [str(path), "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout.strip()


def validate_config(binary: Path, config_path: Path) -> tuple[bool, str]:
    """Validate a MediaMTX configuration file using --validate-conf."""
    res = subprocess.run(  # noqa: S603
        [str(binary), "--validate-conf", str(config_path)],
        capture_output=True,
        text=True,
    )
    output = (res.stdout + res.stderr).strip()
    return res.returncode == 0, output
