"""Tool to vendor contract files in bounded batches and finalize the combined lock."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class InventoryItem:
    batch: int
    origin: str  # "nuraeye-rt" | "mobilecctvapp"
    path: str
    vendored_as: str
    mirrored_by: list[str]
    behaviors: list[str]


INVENTORY: list[InventoryItem] = [
    # --- Batch 1 (Docs & OpenAPI) ---
    InventoryItem(
        1,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/API_REFERENCE.md",
        "contracts/camera_api/mobile_app/packages/camera_api/API_REFERENCE.md",
        [],
        [],
    ),
    InventoryItem(
        1,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/SETTINGS_API_GUIDE.md",
        "contracts/camera_api/mobile_app/packages/camera_api/SETTINGS_API_GUIDE.md",
        [],
        [],
    ),
    InventoryItem(
        1,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/STREAMING_GUIDE.md",
        "contracts/camera_api/mobile_app/packages/camera_api/STREAMING_GUIDE.md",
        [],
        [],
    ),
    InventoryItem(
        1,
        "nuraeye-rt",
        "design/Camera-REST-API.openapi.yaml",
        "contracts/camera_api/design/Camera-REST-API.openapi.yaml",
        [],
        [],
    ),
    InventoryItem(
        1,
        "nuraeye-rt",
        "docs/external-api/camera-rest-api.openapi.yaml",
        "contracts/camera_api/docs/external-api/camera-rest-api.openapi.yaml",
        [],
        [],
    ),
    InventoryItem(
        1,
        "nuraeye-rt",
        "docs/external-api/camera-onvif-api.md",
        "contracts/camera_api/docs/external-api/camera-onvif-api.md",
        [],
        [],
    ),
    InventoryItem(
        1,
        "nuraeye-rt",
        "docs/external-api/camera-rest-api.md",
        "contracts/camera_api/docs/external-api/camera-rest-api.md",
        [],
        [],
    ),
    InventoryItem(
        1,
        "nuraeye-rt",
        "docs/external-api/README.md",
        "contracts/camera_api/docs/external-api/README.md",
        [],
        [],
    ),
    InventoryItem(
        1,
        "nuraeye-rt",
        "docs/external-api/CHANGELOG.md",
        "contracts/camera_api/docs/external-api/CHANGELOG.md",
        [],
        [],
    ),
    InventoryItem(
        1,
        "nuraeye-rt",
        "docs/external-api/quick-start.md",
        "contracts/camera_api/docs/external-api/quick-start.md",
        [],
        [],
    ),
    # --- Batch 2 (Dart sources 1) ---
    InventoryItem(
        2,
        "nuraeye-rt",
        "testing_utilities/camera_id_check_test.py",
        "contracts/camera_api/testing_utilities/camera_id_check_test.py",
        ["sim/fake_camera/server.py"],
        ["HTTP-07"],
    ),
    InventoryItem(
        2,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/lib/src/camera_result.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/lib/src/camera_result.dart",
        ["src/vizenlink_nvr/camera/result.py"],
        ["RES-01", "RES-02", "RES-03"],
    ),
    InventoryItem(
        2,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/lib/src/camera_connection.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/lib/src/camera_connection.dart",
        ["src/vizenlink_nvr/camera/connection.py"],
        [],
    ),
    InventoryItem(
        2,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/lib/src/camera_role.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/lib/src/camera_role.dart",
        ["src/vizenlink_nvr/camera/roles.py"],
        [],
    ),
    InventoryItem(
        2,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/lib/src/recording_mode_types.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/lib/src/recording_mode_types.dart",
        ["src/vizenlink_nvr/camera/nuraeye/capabilities.py"],
        [],
    ),
    InventoryItem(
        2,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/lib/src/device_reset_types.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/lib/src/device_reset_types.dart",
        ["src/vizenlink_nvr/camera/onvif/device.py"],
        [],
    ),
    InventoryItem(
        2,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/lib/src/lan/camera_id_mismatch.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/lib/src/lan/camera_id_mismatch.dart",
        ["src/vizenlink_nvr/camera/events.py", "src/vizenlink_nvr/camera/http.py"],
        ["HTTP-03", "HTTP-04"],
    ),
    InventoryItem(
        2,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/lib/src/lan/wsse_digest.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/lib/src/lan/wsse_digest.dart",
        ["src/vizenlink_nvr/camera/wsse.py"],
        ["WSSE-01", "WSSE-02"],
    ),
    InventoryItem(
        2,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/lib/src/lan/insecure_camera_http_client.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/lib/src/lan/insecure_camera_http_client.dart",
        ["src/vizenlink_nvr/camera/http.py"],
        ["HTTP-05", "HTTP-06"],
    ),
    InventoryItem(
        2,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/lib/src/lan/nuraeye/nuraeye_client.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/lib/src/lan/nuraeye/nuraeye_client.dart",
        ["src/vizenlink_nvr/camera/nuraeye/client.py"],
        [
            "RES-04",
            "IDN-01",
            "IDN-02",
            "IDN-03",
            "SES-01",
            "SES-02",
            "SES-03",
            "SES-04",
            "SES-06",
            "SES-07",
        ],
    ),
    # --- Batch 3 (Dart sources 2 & Tests 1) ---
    InventoryItem(
        3,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/lib/src/lan/nuraeye/nuraeye_rest_client.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/lib/src/lan/nuraeye/nuraeye_rest_client.dart",
        ["src/vizenlink_nvr/camera/nuraeye/rest.py"],
        ["RES-06", "RES-07", "HTTP-08"],
    ),
    InventoryItem(
        3,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/lib/src/lan/nuraeye/rest_identity_discovery_client.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/lib/src/lan/nuraeye/rest_identity_discovery_client.dart",
        ["src/vizenlink_nvr/camera/nuraeye/models.py"],
        [],
    ),
    InventoryItem(
        3,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/lib/src/lan/nuraeye/rest_result.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/lib/src/lan/nuraeye/rest_result.dart",
        ["src/vizenlink_nvr/camera/nuraeye/rest.py"],
        [],
    ),
    InventoryItem(
        3,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/lib/src/lan/nuraeye/capabilities_client.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/lib/src/lan/nuraeye/capabilities_client.dart",
        ["src/vizenlink_nvr/camera/nuraeye/capabilities.py"],
        [],
    ),
    InventoryItem(
        3,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/lib/src/lan/nuraeye/live_stream_uri_client.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/lib/src/lan/nuraeye/live_stream_uri_client.dart",
        ["src/vizenlink_nvr/camera/nuraeye/live_stream_uri.py"],
        [],
    ),
    InventoryItem(
        3,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/lib/src/lan/onvif/onvif_device_client.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/lib/src/lan/onvif/onvif_device_client.dart",
        ["src/vizenlink_nvr/camera/onvif/device.py"],
        [
            "DEV-01",
            "DEV-02",
            "DEV-03",
            "DEV-04",
            "DEV-05",
            "DEV-06",
            "DEV-07",
            "WSSE-03",
            "SOAP-02",
            "SOAP-06",
        ],
    ),
    InventoryItem(
        3,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/lib/src/lan/onvif/onvif_video_encoder_client.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/lib/src/lan/onvif/onvif_video_encoder_client.dart",
        ["src/vizenlink_nvr/camera/onvif/media2.py"],
        ["PRF-01", "PRF-02"],
    ),
    InventoryItem(
        3,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/lib/src/lan/onvif/soap_fault.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/lib/src/lan/onvif/soap_fault.dart",
        ["src/vizenlink_nvr/camera/onvif/soap.py"],
        ["SOAP-02"],
    ),
    InventoryItem(
        3,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/lib/src/lan/discovery/ws_discovery_client.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/lib/src/lan/discovery/ws_discovery_client.dart",
        ["src/vizenlink_nvr/camera/discovery/ws_discovery.py"],
        [],
    ),
    InventoryItem(
        3,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/test/camera_id_header_test.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/test/camera_id_header_test.dart",
        [],
        ["HTTP-01", "HTTP-03", "HTTP-04"],
    ),
    # --- Batch 4 (Dart tests 2) ---
    InventoryItem(
        4,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/test/case_preserving_http_client_test.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/test/case_preserving_http_client_test.dart",
        [],
        ["HTTP-02"],
    ),
    InventoryItem(
        4,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/test/camera_unreachable_event_test.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/test/camera_unreachable_event_test.dart",
        [],
        ["HTTP-05"],
    ),
    InventoryItem(
        4,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/test/nuraeye_digest_test.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/test/nuraeye_digest_test.dart",
        [],
        ["WSSE-01"],
    ),
    InventoryItem(
        4,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/test/nuraeye_are_you_nuraeye_device_test.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/test/nuraeye_are_you_nuraeye_device_test.dart",
        [],
        ["IDN-01", "IDN-02", "IDN-03"],
    ),
    InventoryItem(
        4,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/test/nuraeye_client_session_expiry_test.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/test/nuraeye_client_session_expiry_test.dart",
        [],
        ["SES-01", "SES-02", "SES-03", "SES-04"],
    ),
    InventoryItem(
        4,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/test/nuraeye_client_concurrency_test.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/test/nuraeye_client_concurrency_test.dart",
        [],
        ["SES-05"],
    ),
    InventoryItem(
        4,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/test/nuraeye_client_failure_reason_test.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/test/nuraeye_client_failure_reason_test.dart",
        [],
        ["RES-05"],
    ),
    InventoryItem(
        4,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/test/capabilities_client_test.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/test/capabilities_client_test.dart",
        [],
        ["CAP-01", "CAP-02", "CAP-03"],
    ),
    InventoryItem(
        4,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/test/live_stream_uri_client_test.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/test/live_stream_uri_client_test.dart",
        [],
        ["LST-01", "LST-02", "LST-03"],
    ),
    InventoryItem(
        4,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/test/onvif_device_client_test.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/test/onvif_device_client_test.dart",
        [],
        ["DEV-01", "DEV-02", "DEV-03", "DEV-04", "DEV-05", "DEV-06", "DEV-07", "SOAP-01"],
    ),
    # --- Batch 5 (Dart tests 3 & mobilecctvapp flow files) ---
    InventoryItem(
        5,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/test/onvif_video_encoder_client_test.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/test/onvif_video_encoder_client_test.dart",
        [],
        ["PRF-01", "PRF-02"],
    ),
    InventoryItem(
        5,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/test/ws_discovery_wire_format_test.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/test/ws_discovery_wire_format_test.dart",
        [],
        ["DSC-02"],
    ),
    InventoryItem(
        5,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/test/multi_user_accounts_test.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/test/multi_user_accounts_test.dart",
        [],
        ["SOAP-03", "SOAP-04", "SOAP-05", "DEV-06"],
    ),
    InventoryItem(
        5,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/test/camera_connection_test.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/test/camera_connection_test.dart",
        [],
        [],
    ),
    InventoryItem(
        5,
        "nuraeye-rt",
        "mobile_app/packages/camera_api/test/rest_mock_helpers.dart",
        "contracts/camera_api/mobile_app/packages/camera_api/test/rest_mock_helpers.dart",
        [],
        [],
    ),
    InventoryItem(
        5,
        "mobilecctvapp",
        "lib/app_state/camera_onboarding.dart",
        "contracts/mobile_app/lib/app_state/camera_onboarding.dart",
        [],
        [],
    ),
    InventoryItem(
        5,
        "mobilecctvapp",
        "lib/app_state/camera_scan.dart",
        "contracts/mobile_app/lib/app_state/camera_scan.dart",
        [],
        [],
    ),
    InventoryItem(
        5,
        "mobilecctvapp",
        "lib/app_state/camera_address_recovery.dart",
        "contracts/mobile_app/lib/app_state/camera_address_recovery.dart",
        [],
        [],
    ),
    InventoryItem(
        5,
        "mobilecctvapp",
        "lib/utils/camera_account_rules.dart",
        "contracts/mobile_app/lib/utils/camera_account_rules.dart",
        [],
        [],
    ),
]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _get_git_info(repo_path: Path, files: list[str]) -> tuple[str, list[str]]:
    commit = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo_path), "rev-parse", "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    status_out = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo_path), "status", "--porcelain", "--", *files],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    dirty = [line.strip().split()[-1] for line in status_out.splitlines() if line.strip()]
    return commit, dirty


def vendor_batch(
    batch_num: int,
    upstream_dir: Path,
    mobile_dir: Path,
    root: Path,
    reviewed_on: str = "2026-10-26",
) -> None:
    """Vendor a single batch of files and write contracts/batches/NN.json."""
    items = [item for item in INVENTORY if item.batch == batch_num]
    if not items:
        raise ValueError(f"Invalid batch number: {batch_num}")

    root_resolved = root.resolve()
    batch_files_info: list[dict[str, Any]] = []

    # Map origins to paths
    nuraeye_paths = [item.path for item in items if item.origin == "nuraeye-rt"]
    mobile_paths = [item.path for item in items if item.origin == "mobilecctvapp"]

    nura_commit = ""
    nura_dirty: list[str] = []
    if nuraeye_paths:
        nura_commit, nura_dirty = _get_git_info(upstream_dir, nuraeye_paths)

    mob_commit = ""
    mob_dirty: list[str] = []
    if mobile_paths:
        mob_commit, mob_dirty = _get_git_info(mobile_dir, mobile_paths)

    for item in items:
        src_repo = upstream_dir if item.origin == "nuraeye-rt" else mobile_dir
        src_file = src_repo / item.path
        if not src_file.exists():
            print(f"Error: missing upstream file {src_file}", file=sys.stderr)
            sys.exit(2)

        content = src_file.read_bytes()
        file_sha256 = _sha256(content)

        dest_file = (root / item.vendored_as).resolve()
        # Security: protect against directory traversal
        if not str(dest_file).startswith(str(root_resolved)):
            raise ValueError(f"Path traversal detected: {dest_file}")
        if dest_file.is_symlink():
            raise ValueError(f"Symlinks not allowed: {dest_file}")

        dest_file.parent.mkdir(parents=True, exist_ok=True)
        dest_file.write_bytes(content)

        batch_files_info.append(
            {
                "origin": item.origin,
                "path": item.path,
                "sha256": file_sha256,
                "vendored_as": item.vendored_as,
                "mirrored_by": item.mirrored_by,
                "behaviors": item.behaviors,
            }
        )

    # Sort files deterministically
    batch_files_info.sort(key=lambda x: (x["origin"], x["path"]))

    manifest: dict[str, Any] = {
        "batch": batch_num,
        "upstream": {},
        "files": batch_files_info,
    }
    if nuraeye_paths:
        manifest["upstream"]["nuraeye-rt"] = {
            "repo": "onchiptech/nuraeye-rt",
            "commit": nura_commit,
            "dirty_files": nura_dirty,
            "reviewed_on": reviewed_on,
        }
    if mobile_paths:
        manifest["upstream"]["mobilecctvapp"] = {
            "repo": "onchiptech/mobilecctvapp",
            "commit": mob_commit,
            "dirty_files": mob_dirty,
            "reviewed_on": reviewed_on,
        }

    batches_dir = root / "contracts" / "batches"
    batches_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = batches_dir / f"{batch_num:02d}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Batch {batch_num} vendored: wrote {len(items)} files and {manifest_path}")


def finalize_lock(root: Path) -> None:
    """Read all 5 manifests, validate 49 files and current hashes, and write lock."""
    batches_dir = root / "contracts" / "batches"
    all_files: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    upstream_meta: dict[str, Any] = {}

    for b in range(1, 6):
        mpath = batches_dir / f"{b:02d}.json"
        if not mpath.exists():
            raise FileNotFoundError(f"Missing batch manifest: {mpath}")
        data = json.loads(mpath.read_text(encoding="utf-8"))
        for origin, meta in data.get("upstream", {}).items():
            if origin not in upstream_meta:
                upstream_meta[origin] = meta
            else:
                if upstream_meta[origin]["commit"] != meta["commit"]:
                    raise ValueError(f"Commit mismatch for {origin} across batches")
                upstream_meta[origin]["dirty_files"] = sorted(
                    list(set(upstream_meta[origin]["dirty_files"] + meta.get("dirty_files", [])))
                )

        for f in data.get("files", []):
            p = f["vendored_as"]
            if p in seen_paths:
                raise ValueError(f"Duplicate path in batches: {p}")
            seen_paths.add(p)

            # Check file on disk and verify hash
            disk_path = root / p
            if not disk_path.exists():
                raise FileNotFoundError(f"Vendored file not found on disk: {disk_path}")
            current_sha = _sha256(disk_path.read_bytes())
            if current_sha != f["sha256"]:
                raise ValueError(f"Hash mismatch on disk for {p}: {current_sha} != {f['sha256']}")

            all_files.append(f)

    if len(all_files) != 49:
        raise ValueError(f"Expected exactly 49 files, found {len(all_files)}")

    all_files.sort(key=lambda x: (x["origin"], x["path"]))

    lock_data: dict[str, Any] = {
        "schema": 1,
        "upstream": upstream_meta,
        "files": all_files,
    }
    lock_path = root / "contracts" / "camera_api.lock.json"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(lock_data, indent=2) + "\n", encoding="utf-8")
    print(f"Finalized lock with {len(all_files)} files written to {lock_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Vendor contract files in bounded batches")
    parser.add_argument("--batch", type=int, choices=range(1, 6), help="Batch number to vendor (1..5)")
    parser.add_argument(
        "--finalize", action="store_true", help="Finalize camera_api.lock.json from manifests"
    )
    parser.add_argument("--upstream", type=Path, help="Path to nuraeye-rt repository")
    parser.add_argument("--mobile", type=Path, help="Path to mobilecctvapp repository")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Root directory of target repository")
    parser.add_argument("--reviewed-on", default="2026-10-26", help="Review date string")

    args = parser.parse_args()

    if not args.batch and not args.finalize:
        parser.error("Either --batch N (1..5) or --finalize must be specified")

    if args.batch:
        if not args.upstream or not args.mobile:
            parser.error("--upstream and --mobile required when specifying --batch")
        vendor_batch(
            batch_num=args.batch,
            upstream_dir=args.upstream,
            mobile_dir=args.mobile,
            root=args.root,
            reviewed_on=args.reviewed_on,
        )
    elif args.finalize:
        finalize_lock(root=args.root)


if __name__ == "__main__":
    main()
