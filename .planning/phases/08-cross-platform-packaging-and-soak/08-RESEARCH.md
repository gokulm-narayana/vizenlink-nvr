# Phase 08: Cross-Platform Packaging & Soak - Research & Technical Specifications

## 1. Operating System Service Managers
- **Linux Systemd:**
  - Standard unit location: `/etc/systemd/system/vizenlink-nvr.service` or user units `~/.config/systemd/user/`.
  - Service parameters:
    ```ini
    [Unit]
    Description=VizenLink Network Video Recorder
    After=network.target network-online.target
    Wants=network-online.target

    [Service]
    Type=simple
    User=vizenlink
    Group=vizenlink
    WorkingDirectory=/var/lib/vizenlink-nvr
    ExecStart=/usr/local/bin/nvr run
    Restart=always
    RestartSec=5s
    LimitNOFILE=65536
    TimeoutStopSec=30s

    [Install]
    WantedBy=multi-user.target
    ```
- **macOS LaunchDaemon:**
  - Standard plist location: `/Library/LaunchDaemons/com.vizenlink.nvr.plist`
  - Attributes: `Label`, `ProgramArguments`, `RunAtLoad=true`, `KeepAlive=true`, `StandardOutPath`, `StandardErrorPath`.
- **Windows Service:**
  - WinSW or `sc.exe` command definition.

## 2. Power Management & Sleep Prevention
- **macOS:**
  - `caffeinate -d -i -s -w <pid>` or standalone managed subprocess.
- **Linux:**
  - `systemd-inhibit --what=sleep:idle --who="VizenLink NVR" --why="Active camera recording" ...`
- **Windows:**
  - `ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)` (ES_CONTINUOUS | ES_SYSTEM_REQUIRED).

## 3. Atomic Database Backup & Restore
- **Backup:**
  - SQLite `VACUUM INTO 'destination_path.db'` creates a clean, fully consistent snapshot of the active database even under concurrent writes without WAL lockup.
  - Generates manifest with timestamp, SQLite user_version / alembic head revision, and SHA-256 hash.
- **Restore:**
  - Verifies file exists, checks `PRAGMA integrity_check == "ok"`.
  - Atomically replaces active database (with backup of previous DB file).

## 4. 16-Camera Concurrency & Soak
- 16 cameras generating 30-second segments.
- Over a multi-cycle simulation:
  - 16 streams writing fMP4 segments.
  - Retention janitor running.
  - Gap watchdog evaluating windows.
  - 2 simulated viewers seeking video segments.
  - Reconciler and database verifying no deadlock, no corruption, zero unrecorded segments.

