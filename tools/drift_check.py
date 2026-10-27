"""Drift detection tool verifying contracts against the lock file or upstream repositories."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_self(root: Path) -> int:
    """Verify all vendored files match contracts/camera_api.lock.json."""
    lock_path = root / "contracts" / "camera_api.lock.json"
    if not lock_path.exists():
        print(f"Error: lock file not found: {lock_path}", file=sys.stderr)
        return 1

    lock: dict[str, Any] = json.loads(lock_path.read_text(encoding="utf-8"))
    files = lock.get("files", [])
    drifted: list[str] = []

    for f in files:
        target = root / f["vendored_as"]
        if not target.exists():
            print(f"Missing vendored file: {f['vendored_as']}")
            drifted.append(f["vendored_as"])
            continue
        curr_hash = _sha256(target)
        if curr_hash != f["sha256"]:
            print(f"Hash mismatch on {f['vendored_as']}: expected {f['sha256']}, got {curr_hash}")
            drifted.append(f["vendored_as"])

    if drifted:
        print(f"\nDrift detected in {len(drifted)} file(s).", file=sys.stderr)
        return 1

    print("All vendored contract files match camera_api.lock.json.")
    return 0


def check_batch(batch_num: int, root: Path) -> int:
    """Verify files listed in contracts/batches/NN.json match disk hashes."""
    batch_file = root / "contracts" / "batches" / f"{batch_num:02d}.json"
    if not batch_file.exists():
        print(f"Error: batch manifest not found: {batch_file}", file=sys.stderr)
        return 1

    data = json.loads(batch_file.read_text(encoding="utf-8"))
    files = data.get("files", [])
    drifted: list[str] = []

    for f in files:
        target = root / f["vendored_as"]
        if not target.exists():
            print(f"Missing batch file: {f['vendored_as']}")
            drifted.append(f["vendored_as"])
            continue
        curr_hash = _sha256(target)
        if curr_hash != f["sha256"]:
            print(f"Hash mismatch on {f['vendored_as']}: expected {f['sha256']}, got {curr_hash}")
            drifted.append(f["vendored_as"])

    if drifted:
        print(f"\nDrift detected in {len(drifted)} file(s) for batch {batch_num}.", file=sys.stderr)
        return 1

    print(f"All batch {batch_num} files match manifest.")
    return 0


def check_upstream(upstream_dir: Path, mobile_dir: Path, root: Path) -> int:
    """Compare upstream repo files against vendored copies and print unified diffs on drift."""
    lock_path = root / "contracts" / "camera_api.lock.json"
    if not lock_path.exists():
        print(f"Error: lock file not found: {lock_path}", file=sys.stderr)
        return 1

    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    files = lock.get("files", [])
    has_drift = False

    for f in files:
        src_repo = upstream_dir if f["origin"] == "nuraeye-rt" else mobile_dir
        src_file = src_repo / f["path"]
        vendored_file = root / f["vendored_as"]

        if not src_file.exists():
            print(f"Upstream file missing: {src_file}", file=sys.stderr)
            has_drift = True
            continue

        if not vendored_file.exists():
            print(f"Vendored file missing: {vendored_file}", file=sys.stderr)
            has_drift = True
            continue

        src_bytes = src_file.read_bytes()
        vend_bytes = vendored_file.read_bytes()

        if src_bytes != vend_bytes:
            has_drift = True
            print(f"--- Upstream drift in {f['vendored_as']} ---")
            diff = difflib.unified_diff(
                vend_bytes.decode("utf-8", errors="replace").splitlines(keepends=True),
                src_bytes.decode("utf-8", errors="replace").splitlines(keepends=True),
                fromfile=f["vendored_as"],
                tofile=str(src_file),
            )
            sys.stdout.writelines(diff)

    return 1 if has_drift else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Check contract files for drift against lock or upstream")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--self", action="store_true", help="Verify vendored files match camera_api.lock.json")
    group.add_argument("--batch", type=int, choices=range(1, 6), help="Verify batch manifest against disk")
    group.add_argument("--upstream", type=Path, help="Path to nuraeye-rt upstream repository")

    parser.add_argument("--mobile", type=Path, help="Path to mobilecctvapp repository (with --upstream)")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Target repository root")

    args = parser.parse_args()

    if getattr(args, "self", False):
        code = check_self(args.root)
        sys.exit(code)
    elif args.batch:
        code = check_batch(args.batch, args.root)
        sys.exit(code)
    elif args.upstream:
        if not args.mobile:
            print("Error: --mobile required when --upstream is specified", file=sys.stderr)
            sys.exit(2)
        code = check_upstream(args.upstream, args.mobile, args.root)
        sys.exit(code)
    else:
        parser.print_help(sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
