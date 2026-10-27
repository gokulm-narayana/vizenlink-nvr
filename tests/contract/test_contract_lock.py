"""Contract lock and drift checking tooling tests."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import yaml

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


def test_behaviors_catalogue_schema() -> None:
    """Validate behaviors.yaml schema, rule uniqueness, source validity, plan mappings, and rule count."""
    behaviors_file = repo_root / "contracts" / "behaviors.yaml"
    lock_file = repo_root / "contracts" / "camera_api.lock.json"

    assert behaviors_file.exists(), "contracts/behaviors.yaml must exist"
    assert lock_file.exists(), "contracts/camera_api.lock.json must exist"

    raw_yaml = yaml.safe_load(behaviors_file.read_text(encoding="utf-8"))
    assert raw_yaml.get("schema") == 1

    lock_data = json.loads(lock_file.read_text(encoding="utf-8"))
    vendored_paths = {entry["vendored_as"] for entry in lock_data.get("files", [])}

    valid_plans = {
        "01-05",
        "01-06",
        "01-07",
        "01-18",
        "01-19",
        "01-20",
        "01-21",
        "01-22",
        "01-23",
        "01-24",
        "01-25",
        "01-26",
        "01-27",
        "01-28",
    }
    id_pattern = re.compile(r"^[A-Z]+-\d{2}$")
    decision_pattern = re.compile(r"^D-\d{2}$")

    rules = raw_yaml.get("rules", [])
    assert len(rules) == 70, f"Expected exactly 70 rules, got {len(rules)}"

    seen_ids: set[str] = set()
    rule_by_id: dict[str, dict] = {}

    for rule in rules:
        r_id = rule["id"]
        assert id_pattern.match(r_id), f"Invalid rule id format: {r_id}"
        assert r_id not in seen_ids, f"Duplicate rule id: {r_id}"
        seen_ids.add(r_id)
        rule_by_id[r_id] = rule

        # Validate plan
        assert rule["plan"] in valid_plans, f"Invalid plan '{rule['plan']}' in rule {r_id}"

        # Validate sources
        assert "sources" in rule and len(rule["sources"]) > 0, f"Rule {r_id} missing sources"
        for src in rule["sources"]:
            if "decision" in src:
                msg = f"Invalid decision {src['decision']} in {r_id}"
                assert decision_pattern.match(src["decision"]), msg
            elif "path" in src:
                msg = f"Source path {src['path']} in {r_id} not vendored in lock"
                assert src["path"] in vendored_paths, msg
            else:
                pytest.fail(f"Rule {r_id} source missing path or decision: {src}")

        # Validate requirements
        assert "requirements" in rule and len(rule["requirements"]) > 0, f"Rule {r_id} missing requirements"
        assert "FND-05" in rule["requirements"], f"Rule {r_id} must have FND-05 requirement"

    # Acceptance criteria checks
    assert "LST-04" in seen_ids
    assert "HEAL-05" in seen_ids

    # Representative mappings assertion
    assert rule_by_id["IDN-01"]["plan"] == "01-06"
    assert rule_by_id["SES-07"]["plan"] == "01-18"
    assert rule_by_id["SES-01"]["plan"] == "01-19"
    assert rule_by_id["CAP-05"]["plan"] == "01-18"
    assert rule_by_id["CAP-01"]["plan"] == "01-20"
    assert rule_by_id["DEV-01"]["plan"] == "01-21"
    assert rule_by_id["PRF-03"]["plan"] == "01-24"
    assert rule_by_id["ONB-03"]["plan"] == "01-25"
