"""Unit tests for SQLite backup, integrity verification, and restoration (FND-06)."""

import json
from pathlib import Path

from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app
from vizenlink_nvr.db.engine import upgrade_to_head
from vizenlink_nvr.services.backup import (
    compute_sha256,
    create_backup,
    list_backups,
    restore_backup,
    verify_backup,
)

runner = CliRunner()


def _init_sample_db(db_path: Path) -> None:
    upgrade_to_head(db_path)
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS test_data (id INTEGER PRIMARY KEY, note TEXT)")
    conn.execute("INSERT INTO test_data (note) VALUES ('original_data')")
    conn.commit()
    conn.close()


def test_create_and_verify_backup(tmp_path: Path) -> None:
    src_db = tmp_path / "nvr.db"
    _init_sample_db(src_db)

    backup_dir = tmp_path / "backups"
    backup_file, meta = create_backup(src_db, output_dir=backup_dir)

    assert backup_file.exists()
    assert backup_file.stat().st_size > 0
    assert meta["backup_file"] == backup_file.name
    assert meta["sha256"] == compute_sha256(backup_file)
    assert meta["schema_revision"] is not None

    meta_file = backup_dir / f"{backup_file.stem}.meta.json"
    assert meta_file.exists()

    # Verify backup
    res = verify_backup(backup_file)
    assert res["integrity"] == "ok"


def test_verify_backup_checksum_mismatch(tmp_path: Path) -> None:
    src_db = tmp_path / "nvr.db"
    _init_sample_db(src_db)

    backup_dir = tmp_path / "backups"
    backup_file, meta = create_backup(src_db, output_dir=backup_dir)

    # Tamper with meta.json expected sha256
    meta_file = backup_dir / f"{backup_file.stem}.meta.json"
    meta_data = json.loads(meta_file.read_text(encoding="utf-8"))
    meta_data["sha256"] = "0000000000000000000000000000000000000000000000000000000000000000"
    meta_file.write_text(json.dumps(meta_data), encoding="utf-8")

    import pytest

    with pytest.raises(ValueError, match="Checksum mismatch"):
        verify_backup(backup_file)


def test_restore_backup_with_rollback(tmp_path: Path) -> None:
    src_db = tmp_path / "nvr.db"
    _init_sample_db(src_db)

    backup_dir = tmp_path / "backups"
    backup_file, _ = create_backup(src_db, output_dir=backup_dir)

    # Modify src_db with new data
    import sqlite3

    conn = sqlite3.connect(str(src_db))
    conn.execute("INSERT INTO test_data (note) VALUES ('mutated_after_backup')")
    conn.commit()
    count_before_restore = conn.execute("SELECT count(*) FROM test_data").fetchone()[0]
    conn.close()
    assert count_before_restore == 2

    # Perform restore
    report = restore_backup(backup_file, src_db)
    assert report["status"] == "restored"
    assert report["rollback_created"] is not None
    assert Path(report["rollback_created"]).exists()

    # Verify restored state has reverted the mutation
    conn2 = sqlite3.connect(str(src_db))
    count_after_restore = conn2.execute("SELECT count(*) FROM test_data").fetchone()[0]
    conn2.close()
    assert count_after_restore == 1


def test_list_backups(tmp_path: Path) -> None:
    src_db = tmp_path / "nvr.db"
    _init_sample_db(src_db)

    backup_dir = tmp_path / "backups"
    b1, _ = create_backup(src_db, output_dir=backup_dir)
    b2, _ = create_backup(src_db, output_dir=backup_dir)

    backups = list_backups(backup_dir)
    assert len(backups) == 2
    filenames = [b["filename"] for b in backups]
    assert b1.name in filenames
    assert b2.name in filenames


def test_cli_backup_lifecycle(tmp_path: Path) -> None:
    data_dir = tmp_path / "nvr_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_file = data_dir / "nvr.db"
    _init_sample_db(db_file)

    # Test create
    create_res = runner.invoke(app, ["backup", "create", "--data-dir", str(data_dir), "--json"])
    assert create_res.exit_code == 0
    assert '"sha256":' in create_res.output

    # Test list
    list_res = runner.invoke(app, ["backup", "list", "--data-dir", str(data_dir), "--json"])
    assert list_res.exit_code == 0
    assert '"count": 1' in list_res.output
    listed_data = json.loads(list_res.output)
    created_backup_path = listed_data["backups"][0]["path"]

    # Test restore
    restore_res = runner.invoke(
        app,
        [
            "backup",
            "restore",
            "--file",
            created_backup_path,
            "--data-dir",
            str(data_dir),
            "--force",
            "--json",
        ],
    )
    assert restore_res.exit_code == 0
    assert '"status": "restored"' in restore_res.output
