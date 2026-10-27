"""Contract lock and drift checking tooling tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

# Ensure tools directory is importable
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import pytest  # noqa: E402

from tools.drift_check import check_batch, check_self  # noqa: E402
from tools.vendor_contracts import (  # noqa: E402
    InventoryItem,
    finalize_lock,
    vendor_batch,
)


def _init_git_repo(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)  # noqa: S603, S607
    subprocess.run(  # noqa: S603
        ["git", "config", "user.email", "test@example.com"],  # noqa: S607
        cwd=path,
        capture_output=True,
        check=True,
    )
    subprocess.run(  # noqa: S603
        ["git", "config", "user.name", "Test Runner"],  # noqa: S607
        cwd=path,
        capture_output=True,
        check=True,
    )
    dummy = path / "dummy.txt"
    dummy.write_text("initial commit", encoding="utf-8")
    subprocess.run(["git", "add", "dummy.txt"], cwd=path, capture_output=True, check=True)  # noqa: S603, S607
    subprocess.run(  # noqa: S603
        ["git", "commit", "-m", "init"],  # noqa: S607
        cwd=path,
        capture_output=True,
        check=True,
    )
    commit = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return commit


def test_batch_vendoring_and_drift_check(tmp_path: Path) -> None:
    """Test full cycle: batch copying, batch verification, tamper detection, and finalization."""
    mock_upstream = tmp_path / "upstream"
    mock_mobile = tmp_path / "mobile"
    dest_root = tmp_path / "nvr_repo"
    dest_root.mkdir()

    _init_git_repo(mock_upstream)
    _init_git_repo(mock_mobile)

    # Create dummy files for batches 1..5 in mock repos
    mock_inventory: list[InventoryItem] = []
    # 10 items for batch 1..4, 9 items for batch 5
    for b in range(1, 6):
        count = 9 if b == 5 else 10
        for i in range(count):
            origin = "mobilecctvapp" if (b == 5 and i >= 5) else "nuraeye-rt"
            rel_path = f"file_b{b}_{i}.txt"
            repo = mock_mobile if origin == "mobilecctvapp" else mock_upstream
            file_path = repo / rel_path
            file_path.write_text(f"content for {rel_path}", encoding="utf-8")
            # git add and commit so they are tracked
            subprocess.run(["git", "add", rel_path], cwd=repo, capture_output=True, check=True)  # noqa: S603, S607

            vendored_prefix = "contracts/mobile_app" if origin == "mobilecctvapp" else "contracts/camera_api"
            mock_inventory.append(
                InventoryItem(
                    batch=b,
                    origin=origin,
                    path=rel_path,
                    vendored_as=f"{vendored_prefix}/{rel_path}",
                    mirrored_by=[],
                    behaviors=[],
                )
            )

    subprocess.run(["git", "commit", "-m", "add files"], cwd=mock_upstream, capture_output=True, check=True)  # noqa: S603, S607
    subprocess.run(["git", "commit", "-m", "add files"], cwd=mock_mobile, capture_output=True, check=True)  # noqa: S603, S607

    with patch("tools.vendor_contracts.INVENTORY", mock_inventory):
        # 1. Vendor batches 1 through 5
        for b in range(1, 6):
            vendor_batch(b, mock_upstream, mock_mobile, dest_root)

        # 2. Check batch 1 passes
        assert check_batch(1, dest_root) == 0

        # 3. Tamper with a batch 1 file -> check_batch fails
        tampered_file = dest_root / "contracts/camera_api/file_b1_0.txt"
        tampered_file.write_text("tampered content", encoding="utf-8")
        assert check_batch(1, dest_root) == 1

        # Restore
        tampered_file.write_text("content for file_b1_0.txt", encoding="utf-8")
        assert check_batch(1, dest_root) == 0

        # 4. Finalize lock
        finalize_lock(dest_root)

        # 5. Check self against lock passes
        assert check_self(dest_root) == 0

        # 6. Tamper with file -> check_self fails
        tampered_file.write_text("tampered content", encoding="utf-8")
        assert check_self(dest_root) == 1


def test_finalize_guards(tmp_path: Path) -> None:
    """Finalize refuses missing batches, duplicate paths, or missing disk files."""
    dest_root = tmp_path / "nvr_repo"
    batches_dir = dest_root / "contracts" / "batches"
    batches_dir.mkdir(parents=True)

    # Missing batch 1
    with pytest.raises(FileNotFoundError, match="Missing batch manifest"):
        finalize_lock(dest_root)


def test_reference_repositories_remain_untouched() -> None:
    """Read-only inspection of reference checkouts leaves their git status completely unchanged."""
    paths = [Path("/Users/gokul/Desktop/vizenlinkvms/nuraeye-rt"), Path("/Users/gokul/mobilecctvapp")]

    for p in paths:
        if not p.exists():
            continue
        status_before = subprocess.run(  # noqa: S603
            ["git", "-C", str(p), "status", "--porcelain"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        ).stdout

        # Simulate read-only operations
        for item in p.rglob("*.dart"):
            if item.is_file():
                _ = item.read_bytes()
                break

        status_after = subprocess.run(  # noqa: S603
            ["git", "-C", str(p), "status", "--porcelain"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        ).stdout

        assert status_before == status_after, f"Status changed in reference repo {p}"
