"""Integration tests for nvr status credential reports and canary verification."""

import json
import os
from pathlib import Path

from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.paths import secrets_dir
from vizenlink_nvr.secrets.vault import CANARY_KEY
from vizenlink_nvr.services.runtime import open_runtime
from vizenlink_nvr.services.settings import get_setting


def test_status_credentials_lifecycle(cli: CliRunner, data_dir: Path) -> None:
    """Verify nvr status --json credentials report, key permissions, mismatch, and missing key."""
    # Run 1: initial run creates file key and canary
    res1 = cli.invoke(app, ["status", "--json", "--data-dir", str(data_dir)])
    assert res1.exit_code == 0
    data1 = json.loads(res1.output)
    assert data1["credentials_status"] == "ok"
    key_id1 = data1["key_id"]
    assert key_id1 is not None and key_id1.startswith("file:")

    key_file = secrets_dir(load_settings(data_dir)) / "data.key"
    assert key_file.exists()
    if os.name == "posix":
        assert oct(key_file.stat().st_mode & 0o777) == "0o600"

    # Run 2: second run reports exact same key_id and status ok
    res2 = cli.invoke(app, ["status", "--json", "--data-dir", str(data_dir)])
    assert res2.exit_code == 0
    data2 = json.loads(res2.output)
    assert data2["credentials_status"] == "ok"
    assert data2["key_id"] == key_id1

    # Read canary byte-for-byte from db
    import asyncio

    async def _get_canary() -> str:
        async with open_runtime(load_settings(data_dir)) as rt:
            c = await get_setting(rt, CANARY_KEY)
            return c or ""

    canary_before = asyncio.run(_get_canary())
    assert len(canary_before) > 0

    # Overwrite data.key with 32 different bytes -> status reports mismatch
    different_key = os.urandom(32)
    key_file.write_bytes(different_key)

    res3 = cli.invoke(app, ["status", "--json", "--data-dir", str(data_dir)])
    assert res3.exit_code == 0
    data3 = json.loads(res3.output)
    assert data3["credentials_status"] == "mismatch"

    # Canary row remains unchanged
    canary_after_mismatch = asyncio.run(_get_canary())
    assert canary_after_mismatch == canary_before

    # Delete data.key -> status reports missing_key, and no new key was created
    key_file.unlink()

    res4 = cli.invoke(app, ["status", "--json", "--data-dir", str(data_dir)])
    assert res4.exit_code == 0
    data4 = json.loads(res4.output)
    assert data4["credentials_status"] == "missing_key"
    assert not key_file.exists()

    # Canary row still remains byte-identical
    canary_after_delete = asyncio.run(_get_canary())
    assert canary_after_delete == canary_before


def test_status_explicit_configuration_mismatch(
    cli: CliRunner,
    data_dir: Path,
    monkeypatch,
) -> None:
    """Explicit configuration contradicting recorded source reports mismatch."""
    # First create file vault
    res1 = cli.invoke(app, ["status", "--json", "--data-dir", str(data_dir)])
    assert res1.exit_code == 0
    assert json.loads(res1.output)["credentials_status"] == "ok"

    # Now set NVR_SECRETS_BACKEND=keyring
    monkeypatch.setenv("NVR_SECRETS_BACKEND", "keyring")
    res2 = cli.invoke(app, ["status", "--json", "--data-dir", str(data_dir)])
    assert res2.exit_code == 0
    data2 = json.loads(res2.output)
    assert data2["credentials_status"] == "mismatch"
