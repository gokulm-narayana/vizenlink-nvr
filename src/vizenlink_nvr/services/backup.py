"""Atomic SQLite database backup, manifest generation, and restore service (FND-06)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vizenlink_nvr.db.engine import current_revision

logger = logging.getLogger(__name__)


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file in streaming chunks."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def create_backup(
    db_file: Path,
    output_dir: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Create an atomic online SQLite snapshot using VACUUM INTO and emit metadata manifest."""
    if not db_file.exists():
        raise FileNotFoundError(f"Database file not found: {db_file}")

    target_dir = output_dir or (db_file.parent / "backups")
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    backup_file = target_dir / f"nvr_backup_{timestamp_str}.db"
    meta_file = target_dir / f"nvr_backup_{timestamp_str}.meta.json"

    # In the unlikely event of collision, increment suffix
    counter = 1
    while backup_file.exists():
        backup_file = target_dir / f"nvr_backup_{timestamp_str}_{counter}.db"
        meta_file = target_dir / f"nvr_backup_{timestamp_str}_{counter}.meta.json"
        counter += 1

    # SQLite VACUUM INTO creates an atomic online copy even with active concurrent writers
    conn = sqlite3.connect(str(db_file.resolve()))
    try:
        conn.execute(f"VACUUM INTO '{backup_file.resolve().as_posix()}'")
    finally:
        conn.close()

    # Integrity verification on snapshot
    check_conn = sqlite3.connect(str(backup_file.resolve()))
    try:
        res = check_conn.execute("PRAGMA integrity_check").fetchall()
        if not res or res[0][0] != "ok":
            raise ValueError(f"Snapshot integrity check failed: {res}")
    finally:
        check_conn.close()

    sha256 = compute_sha256(backup_file)
    size_bytes = backup_file.stat().st_size
    rev = current_revision(backup_file)

    meta: dict[str, Any] = {
        "backup_file": backup_file.name,
        "created_at": datetime.now(UTC).isoformat(),
        "sha256": sha256,
        "size_bytes": size_bytes,
        "schema_revision": rev,
    }

    meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    logger.info("Backup created at %s (SHA-256: %s)", backup_file, sha256)
    return backup_file, meta


def verify_backup(backup_db_path: Path) -> dict[str, Any]:
    """Verify integrity check and checksum manifest of a backup snapshot."""
    if not backup_db_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_db_path}")

    # Check manifest if present
    meta_file = backup_db_path.with_name(backup_db_path.stem + ".meta.json")
    if meta_file.exists():
        meta_data = json.loads(meta_file.read_text(encoding="utf-8"))
        expected_sha = meta_data.get("sha256")
        if expected_sha:
            actual_sha = compute_sha256(backup_db_path)
            if actual_sha != expected_sha:
                raise ValueError(
                    f"Checksum mismatch for {backup_db_path.name}: expected {expected_sha}, got {actual_sha}"
                )

    # SQLite integrity check
    conn = sqlite3.connect(str(backup_db_path.resolve()))
    try:
        res = conn.execute("PRAGMA integrity_check").fetchall()
        if not res or res[0][0] != "ok":
            raise ValueError(f"Corrupt backup file: {res}")
    finally:
        conn.close()

    return {
        "backup_file": str(backup_db_path),
        "integrity": "ok",
        "sha256": compute_sha256(backup_db_path),
        "size_bytes": backup_db_path.stat().st_size,
    }


def restore_backup(
    backup_db_path: Path,
    target_db_path: Path,
) -> dict[str, Any]:
    """Safely restore a database backup into target DB with rollback guard."""
    verification = verify_backup(backup_db_path)

    target_db_path.parent.mkdir(parents=True, exist_ok=True)
    rollback_path: Path | None = None

    if target_db_path.exists():
        rollback_path = target_db_path.with_name(f"{target_db_path.name}.rollback")
        shutil.copy2(target_db_path, rollback_path)
        logger.info("Created target database rollback snapshot at %s", rollback_path)

    # Write to a temporary file in same folder then atomic replace
    tmp_target = target_db_path.with_name(f"{target_db_path.name}.tmp_restore")
    try:
        shutil.copy2(backup_db_path, tmp_target)

        # Clear any stale WAL / SHM files for target DB
        for ext in ["-wal", "-shm"]:
            wal_file = target_db_path.parent / (target_db_path.name + ext)
            if wal_file.exists():
                wal_file.unlink()

        os.replace(tmp_target, target_db_path)
    except Exception as exc:
        if tmp_target.exists():
            tmp_target.unlink()
        if rollback_path and rollback_path.exists():
            os.replace(rollback_path, target_db_path)
        raise RuntimeError(f"Database restore failed; rolled back to previous state: {exc}") from exc

    # Final sanity check on restored file
    verify_backup(target_db_path)

    return {
        "status": "restored",
        "target_db": str(target_db_path),
        "backup_source": str(backup_db_path),
        "rollback_created": str(rollback_path) if rollback_path else None,
        "size_bytes": target_db_path.stat().st_size,
        "verification": verification,
    }


def list_backups(backup_dir: Path) -> list[dict[str, Any]]:
    """List available database backups sorted by creation timestamp descending."""
    if not backup_dir.exists():
        return []

    backups: list[dict[str, Any]] = []
    for f in backup_dir.glob("*.db"):
        meta_file = f.with_name(f.stem + ".meta.json")
        meta: dict[str, Any] = {}
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:  # noqa: S110
                pass

        backups.append(
            {
                "filename": f.name,
                "path": str(f.resolve()),
                "size_bytes": f.stat().st_size,
                "created_at": meta.get(
                    "created_at",
                    datetime.fromtimestamp(f.stat().st_mtime, UTC).isoformat(),
                ),
                "schema_revision": meta.get("schema_revision"),
                "sha256": meta.get("sha256"),
            }
        )

    backups.sort(key=lambda b: b.get("created_at") or "", reverse=True)
    return backups
