"""Cross-platform system service configuration generators and manager (FND-06)."""

from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Any, Literal

TargetOS = Literal["linux", "darwin", "windows"]


def detect_os() -> TargetOS:
    """Detect current host operating system."""
    system = platform.system().lower()
    if system == "darwin":
        return "darwin"
    if system == "windows":
        return "windows"
    return "linux"


def generate_systemd_unit(
    exec_path: str = "/usr/local/bin/nvr",
    user: str = "vizenlink",
    group: str = "vizenlink",
    work_dir: str = "/var/lib/vizenlink-nvr",
    data_dir: str = "/var/lib/vizenlink-nvr/data",
) -> str:
    """Generate systemd unit file for Linux service supervision."""
    return f"""[Unit]
Description=VizenLink Network Video Recorder (NVR)
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User={user}
Group={group}
WorkingDirectory={work_dir}
ExecStart={exec_path} run
Restart=always
RestartSec=5s
LimitNOFILE=65536
TimeoutStopSec=30s
Environment="NVR_DATA_DIR={data_dir}"

[Install]
WantedBy=multi-user.target
"""


def generate_launchd_plist(
    exec_path: str = "/usr/local/bin/nvr",
    work_dir: str = "/var/lib/vizenlink-nvr",
    log_dir: str = "/var/log/vizenlink-nvr",
) -> str:
    """Generate LaunchDaemon plist for macOS service supervision."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.vizenlink.nvr</string>
    <key>ProgramArguments</key>
    <array>
        <string>{exec_path}</string>
        <string>run</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>{work_dir}</string>
    <key>StandardOutPath</key>
    <string>{log_dir}/nvr.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/nvr_error.log</string>
</dict>
</plist>
"""


def generate_windows_config(
    exec_path: str = "C:\\Program Files\\VizenLink\\nvr.exe",
    work_dir: str = "C:\\ProgramData\\VizenLink",
) -> str:
    """Generate WinSW XML configuration for Windows Service installation."""
    return f"""<service>
    <id>vizenlink-nvr</id>
    <name>VizenLink NVR</name>
    <description>VizenLink Network Video Recorder Service</description>
    <executable>{exec_path}</executable>
    <arguments>run</arguments>
    <workingdirectory>{work_dir}</workingdirectory>
    <logmode>rotate</logmode>
    <onfailure action="restart" delay="5 sec"/>
</service>
"""


class ServiceManager:
    """Manages service definitions and system registration metadata."""

    def __init__(self, target_os: TargetOS | None = None) -> None:
        self.target_os: TargetOS = target_os or detect_os()

    def get_service_filename(self) -> str:
        """Return canonical service configuration filename for current target OS."""
        if self.target_os == "linux":
            return "vizenlink-nvr.service"
        if self.target_os == "darwin":
            return "com.vizenlink.nvr.plist"
        return "vizenlink-nvr.xml"

    def get_service_content(
        self,
        exec_path: str | None = None,
        work_dir: str | None = None,
    ) -> str:
        """Generate service definition content."""
        binary = exec_path or sys.executable
        if self.target_os == "linux":
            return generate_systemd_unit(
                exec_path=binary,
                work_dir=work_dir or "/var/lib/vizenlink-nvr",
            )
        if self.target_os == "darwin":
            return generate_launchd_plist(
                exec_path=binary,
                work_dir=work_dir or "/var/lib/vizenlink-nvr",
            )
        return generate_windows_config(
            exec_path=binary,
            work_dir=work_dir or "C:\\ProgramData\\VizenLink",
        )

    def get_service_status(self) -> dict[str, Any]:
        """Check system service configuration availability."""
        system_destinations: dict[TargetOS, Path] = {
            "linux": Path("/etc/systemd/system/vizenlink-nvr.service"),
            "darwin": Path("/Library/LaunchDaemons/com.vizenlink.nvr.plist"),
            "windows": Path("C:\\ProgramData\\VizenLink\\vizenlink-nvr.xml"),
        }
        dest = system_destinations.get(self.target_os)
        installed = dest.exists() if dest else False
        return {
            "target_os": self.target_os,
            "filename": self.get_service_filename(),
            "standard_path": str(dest) if dest else None,
            "installed": installed,
        }
