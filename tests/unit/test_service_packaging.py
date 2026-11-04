"""Unit tests for system service packaging and CLI commands (FND-06)."""

from pathlib import Path

from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app
from vizenlink_nvr.service.installer import (
    ServiceManager,
    detect_os,
    generate_launchd_plist,
    generate_systemd_unit,
    generate_windows_config,
)

runner = CliRunner()


def test_generate_systemd_unit() -> None:
    content = generate_systemd_unit(
        exec_path="/custom/path/nvr",
        user="customuser",
        group="customgroup",
        work_dir="/custom/work",
        data_dir="/custom/data",
    )
    assert "[Unit]" in content
    assert "Description=VizenLink Network Video Recorder (NVR)" in content
    assert "ExecStart=/custom/path/nvr run" in content
    assert "User=customuser" in content
    assert "Group=customgroup" in content
    assert "Restart=always" in content
    assert "LimitNOFILE=65536" in content
    assert 'Environment="NVR_DATA_DIR=/custom/data"' in content
    assert "WantedBy=multi-user.target" in content


def test_generate_launchd_plist() -> None:
    content = generate_launchd_plist(
        exec_path="/usr/local/bin/nvr",
        work_dir="/var/lib/vizenlink-nvr",
        log_dir="/var/log/vizenlink-nvr",
    )
    assert '<plist version="1.0">' in content
    assert "<string>com.vizenlink.nvr</string>" in content
    assert "<key>RunAtLoad</key>" in content
    assert "<key>KeepAlive</key>" in content
    assert "<string>/usr/local/bin/nvr</string>" in content
    assert "<string>run</string>" in content
    assert "<string>/var/log/vizenlink-nvr/nvr.log</string>" in content


def test_generate_windows_config() -> None:
    content = generate_windows_config(
        exec_path="C:\\Tools\\nvr.exe",
        work_dir="C:\\Data\\NVR",
    )
    assert "<service>" in content
    assert "<id>vizenlink-nvr</id>" in content
    assert "<executable>C:\\Tools\\nvr.exe</executable>" in content
    assert "<arguments>run</arguments>" in content
    assert '<onfailure action="restart"' in content


def test_service_manager_matrix() -> None:
    for target_os, expected_file in [
        ("linux", "vizenlink-nvr.service"),
        ("darwin", "com.vizenlink.nvr.plist"),
        ("windows", "vizenlink-nvr.xml"),
    ]:
        mgr = ServiceManager(target_os=target_os)  # type: ignore[arg-type]
        assert mgr.get_service_filename() == expected_file
        content = mgr.get_service_content(exec_path="/bin/nvr")
        assert len(content) > 50
        status = mgr.get_service_status()
        assert status["target_os"] == target_os
        assert status["filename"] == expected_file
        assert "installed" in status


def test_detect_os() -> None:
    detected = detect_os()
    assert detected in ("linux", "darwin", "windows")


def test_cli_service_generate_stdout() -> None:
    res = runner.invoke(app, ["service", "generate", "--os", "linux", "--json"])
    assert res.exit_code == 0
    assert '"target_os": "linux"' in res.output
    assert "LimitNOFILE=65536" in res.output


def test_cli_service_generate_file(tmp_path: Path) -> None:
    outfile = tmp_path / "com.vizenlink.nvr.plist"
    res = runner.invoke(app, ["service", "generate", "--os", "darwin", "-o", str(outfile)])
    assert res.exit_code == 0
    assert outfile.exists()
    content = outfile.read_text(encoding="utf-8")
    assert "<string>com.vizenlink.nvr</string>" in content


def test_cli_service_status() -> None:
    res = runner.invoke(app, ["service", "status", "--os", "linux", "--json"])
    assert res.exit_code == 0
    assert '"target_os": "linux"' in res.output
    assert '"filename": "vizenlink-nvr.service"' in res.output
