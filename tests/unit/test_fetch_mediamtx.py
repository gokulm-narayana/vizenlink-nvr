"""Unit tests for MediaMTX binary download, checksum verification, and safe extraction."""

from __future__ import annotations

import hashlib
import io
import os
import tarfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vizenlink_nvr.media.binary import fetch


def _make_tar_archive(members: dict[str, bytes]) -> bytes:
    """Helper to create an in-memory tar.gz archive."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_fetch_sha256_mismatch(tmp_path: Path) -> None:
    """Download fails with ValueError on SHA-256 mismatch and nothing is extracted."""
    bad_data = b"not-a-valid-mediamtx-archive"

    mock_resp = MagicMock()
    mock_resp.content = bad_data
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.Client.get", return_value=mock_resp):
        with pytest.raises(ValueError, match="SHA-256 mismatch"):
            fetch(dest_dir=tmp_path)

    # Destination directory contains no extracted files
    bin_name = "mediamtx.exe" if os.name == "nt" else "mediamtx"
    assert not (tmp_path / bin_name).exists()


def test_fetch_path_traversal_refused(tmp_path: Path) -> None:
    """Archives attempting directory traversal are refused with ValueError."""
    evil_archive = _make_tar_archive(
        {
            "mediamtx": b"echo fake",
            "../evil.sh": b"rm -rf /",
        }
    )
    correct_hash = hashlib.sha256(evil_archive).hexdigest()

    mock_resp = MagicMock()
    mock_resp.content = evil_archive
    mock_resp.raise_for_status = MagicMock()

    with (
        patch("httpx.Client.get", return_value=mock_resp),
        patch("vizenlink_nvr.media.binary.load_pins") as mock_pins,
        patch("vizenlink_nvr.media.binary.platform_key", return_value="test_platform"),
    ):
        mock_pins.return_value = {
            "version": "v1.21.3",
            "url_base": "https://example.com/",
            "assets": {
                "test_platform": {
                    "filename": "mediamtx_test.tar.gz",
                    "sha256": correct_hash,
                }
            },
        }
        with pytest.raises(ValueError, match="Path traversal detected"):
            fetch(dest_dir=tmp_path)


def test_fetch_successful_extraction(tmp_path: Path) -> None:
    """Valid archive extracts successfully and marks binary executable on POSIX."""
    bin_name = "mediamtx.exe" if os.name == "nt" else "mediamtx"
    valid_archive = _make_tar_archive(
        {
            bin_name: b"#!/bin/sh\necho fake mediamtx",
            "mediamtx.yml": b"dummy: true",
        }
    )
    correct_hash = hashlib.sha256(valid_archive).hexdigest()

    mock_resp = MagicMock()
    mock_resp.content = valid_archive
    mock_resp.raise_for_status = MagicMock()

    with (
        patch("httpx.Client.get", return_value=mock_resp),
        patch("vizenlink_nvr.media.binary.load_pins") as mock_pins,
        patch("vizenlink_nvr.media.binary.platform_key", return_value="test_platform"),
    ):
        mock_pins.return_value = {
            "version": "v1.21.3",
            "url_base": "https://example.com/",
            "assets": {
                "test_platform": {
                    "filename": "mediamtx_test.tar.gz",
                    "sha256": correct_hash,
                }
            },
        }
        extracted = fetch(dest_dir=tmp_path)

        assert extracted.exists()
        assert extracted == tmp_path / bin_name
        if os.name == "posix":
            assert os.access(extracted, os.X_OK)
