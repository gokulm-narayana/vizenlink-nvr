# Phase 08: Cross-Platform Packaging & Soak - Context & Architectural Boundaries

## Purpose
Phase 08 delivers cross-platform system service packaging, power management sleep inhibition, database backup and restoration tooling, and a 16-camera scale/soak simulation proving the NVR's core value: "Never miss footage" under full load across Linux, macOS, and Windows targets (`FND-06`).

## In Scope Requirements
- **FND-06**: Same codebase runs reliably on Linux (x86_64, Raspberry Pi 64-bit, Jetson), macOS (Intel & Apple Silicon), and Windows (x86_64 & ARM64).
- **Service Supervision**: Production boot-time service templates and installers for systemd (Linux), LaunchDaemon (macOS), and Windows Service (WinSW).
- **Host Sleep Inhibition**: Power management guard preventing system sleep/standby during active recording sessions.
- **Database Backup & Recovery**: Atomic online SQLite backup (`VACUUM INTO`) and safety-verified database restoration with schema validation.
- **16-Camera Soak Simulation**: Concurrency test validating 16 simultaneous camera recording feeds, 2 concurrent playback viewers, zero unaccounted gaps, and resilient recovery.

## Architectural Boundaries & Principles
1. **Multi-OS Service Abstraction:**
   - Linux: Systemd unit `vizenlink-nvr.service` with `Restart=always`, `RestartSec=5s`, sandboxing directives, and dependent MediaMTX execution.
   - macOS: LaunchDaemon plist `com.vizenlink.nvr.plist` with `KeepAlive=true`, `RunAtLoad=true`, and standard log redirection.
   - Windows: Service configuration compatible with Windows Service Control Manager / WinSW.
   - CLI commands `nvr service [install|status|uninstall]` provide automated installation or print generation commands without requiring root during dry runs.
2. **Sleep Prevention Invariant:**
   - When recording is enabled, the NVR acquires a sleep inhibition lock so the operating system does not enter sleep or suspend:
     - macOS: Managed `caffeinate` child process (`-d -i -s`).
     - Linux: `systemd-inhibit` or D-Bus `org.freedesktop.login1.Manager.Inhibit`.
     - Windows: Kernel32 `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)`.
3. **Database Backup & Restore Integrity:**
   - Atomic online backup using SQLite's native `VACUUM INTO` command, generating a consistent snapshot without shutting down recording.
   - Restoration verifies SQLite integrity (`PRAGMA integrity_check`), ensures foreign keys are consistent, and tests migrations against the current head.
4. **16-Camera Scale Verification:**
   - Automated soak test simulating 16 cameras streaming fMP4 chunks concurrently.
   - Evaluates segment indexer, retention janitor, and gap watchdog concurrently under simulated load.
