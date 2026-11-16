"""Declarative MediaMTX path reconciler and synchronization engine."""

from __future__ import annotations

import logging
import os
import secrets
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from sqlalchemy import select

from vizenlink_nvr.db.models import Camera, CameraCredential, CameraStream
from vizenlink_nvr.media.config import camera_path_name
from vizenlink_nvr.paths import mediamtx_dir
from vizenlink_nvr.secrets.vault import SealedSecret, Vault
from vizenlink_nvr.services.recording_settings import should_record_now
from vizenlink_nvr.services.settings import read_clip_minutes
from vizenlink_nvr.timeutil import utc_now

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from vizenlink_nvr.config import NvrSettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PathConfiguration:
    """MediaMTX path definition for RTSP/RTSPS ingestion and fMP4 recording."""

    name: str
    source: str
    source_on_demand: bool
    record: bool
    record_format: str = "fmp4"
    record_part_duration: str = "1s"
    record_segment_duration: str = "60s"
    record_delete_after: str = "0s"
    record_path: str = ""
    run_on_record_segment_complete: str = "nvr recording hook-segment-complete"
    source_fingerprint: str = ""

    def to_api_dict(self) -> dict[str, Any]:
        """Convert to payload expected by MediaMTX /v3/config/paths/* REST API."""
        payload: dict[str, Any] = {
            "source": self.source,
            "sourceOnDemand": self.source_on_demand,
            "record": self.record,
            "recordFormat": self.record_format,
            "recordPartDuration": self.record_part_duration,
            "recordSegmentDuration": self.record_segment_duration,
            "recordDeleteAfter": self.record_delete_after,
            "runOnRecordSegmentComplete": self.run_on_record_segment_complete,
        }
        if self.record_path:
            payload["recordPath"] = self.record_path
        if self.source_fingerprint:
            payload["sourceFingerprint"] = self.source_fingerprint
        return payload


@dataclass(frozen=True)
class ReconcileResult:
    """Summary of reconciler actions executed against MediaMTX."""

    added: list[str]
    patched: list[str]
    deleted: list[str]
    unchanged: list[str]

    @property
    def is_clean(self) -> bool:
        return not (self.added or self.patched or self.deleted)


def get_control_password(settings: NvrSettings) -> str:
    """Retrieve or generate persistent control password for MediaMTX internal API."""
    pw_file = mediamtx_dir(settings) / ".control_password"
    if pw_file.exists():
        return pw_file.read_text(encoding="utf-8").strip()

    mediamtx_dir(settings).mkdir(parents=True, exist_ok=True)
    pw = secrets.token_urlsafe(24)
    pw_file.write_text(pw, encoding="utf-8")
    if os.name == "posix":
        os.chmod(pw_file, 0o600)
    return pw


def _normalize_duration(val: str | None) -> float:
    """Parse MediaMTX duration string (e.g. '60s', '1m0s', '0s', '') to float seconds."""
    if not val:
        return 0.0
    val = val.strip().lower()
    if val in ("0", "0s", "0m", "0h"):
        return 0.0
    total = 0.0
    num = ""
    for ch in val:
        if ch.isdigit() or ch == ".":
            num += ch
        else:
            if num:
                n = float(num)
                num = ""
                if ch == "s":
                    total += n
                elif ch == "m":
                    total += n * 60.0
                elif ch == "h":
                    total += n * 3600.0
                elif ch == "d":
                    total += n * 86400.0
    if num:
        total += float(num)
    return total


def _needs_patch(current: dict[str, Any], desired: dict[str, Any]) -> bool:
    """Compare path configuration fields to determine if a PATCH call is needed."""
    duration_fields = [
        "recordPartDuration",
        "recordSegmentDuration",
        "recordDeleteAfter",
    ]
    for df in duration_fields:
        if df in desired:
            if _normalize_duration(current.get(df)) != _normalize_duration(desired[df]):
                return True

    other_fields = [
        "source",
        "sourceOnDemand",
        "record",
        "recordFormat",
        "runOnRecordSegmentComplete",
    ]
    for field in other_fields:
        if field in desired and current.get(field) != desired[field]:
            return True

    if desired.get("recordPath") and current.get("recordPath") != desired["recordPath"]:
        return True

    if desired.get("sourceFingerprint") and current.get("sourceFingerprint") != desired["sourceFingerprint"]:
        return True

    return False


async def compute_desired_paths(
    session: AsyncSession,
    storage_path: Path,
    volume_ok: bool = True,
    now: datetime | None = None,
    tz_name: str = "UTC",
    vault: Vault | None = None,
) -> dict[str, PathConfiguration]:
    """Compute desired MediaMTX PathConfiguration objects for all active cameras."""
    if now is None:
        now = utc_now()

    # Query active cameras
    cam_stmt = select(Camera).where(Camera.state == "active")
    cam_res = await session.execute(cam_stmt)
    cameras = cam_res.scalars().all()

    desired: dict[str, PathConfiguration] = {}
    # Recorder-wide clip length, read once per pass.
    clip_duration: str | None = None

    for cam in cameras:
        # Decrypt password if credential and vault available
        user = ""
        password_val = ""
        cred_stmt = select(CameraCredential).where(CameraCredential.serial == cam.serial)
        cred_res = await session.execute(cred_stmt)
        cred = cred_res.scalar_one_or_none()

        if cred is not None:
            user = cred.username
            if vault is not None:
                try:
                    sealed = SealedSecret(
                        ciphertext=cred.ciphertext,
                        nonce=cred.nonce,
                        key_id=cred.key_id,
                        enc_version=cred.enc_version,
                    )
                    password_val = vault.open(cam.serial, cred.username, sealed).get_secret_value()
                except Exception as exc:
                    logger.warning("Could not decrypt password for camera %s: %s", cam.serial, exc)

        # Query configured streams
        stream_stmt = select(CameraStream).where(CameraStream.serial == cam.serial)
        stream_res = await session.execute(stream_stmt)
        streams = stream_res.scalars().all()

        stream_by_role: dict[str, CameraStream] = {s.role: s for s in streams}

        # 1. Main stream
        main_stream = stream_by_role.get("main")
        scheme = main_stream.scheme if main_stream else "rtsp"
        port = main_stream.port if main_stream else 554
        path = main_stream.path if main_stream else "/live/main"
        if not path.startswith("/"):
            path = f"/{path}"

        if user and password_val:
            enc_user = urllib.parse.quote(user, safe="")
            enc_pw = urllib.parse.quote(password_val, safe="")
            source_url = f"{scheme}://{enc_user}:{enc_pw}@{cam.host}:{port}{path}"
        else:
            source_url = f"{scheme}://{cam.host}:{port}{path}"

        # Evaluate recording policy
        record_active = False
        if volume_ok:
            record_active = await should_record_now(session, cam.serial, now=now, tz_name=tz_name)

        main_path_name = camera_path_name(cam.serial, "main")
        if clip_duration is None:
            clip_duration = f"{await read_clip_minutes(session) * 60}s"
        record_path_pattern = f"{storage_path}/%path/%Y/%m/%d/%Y-%m-%dT%H-%M-%SZ-%f"

        desired[main_path_name] = PathConfiguration(
            name=main_path_name,
            source=source_url,
            source_on_demand=False,
            record=record_active,
            record_format="fmp4",
            record_part_duration="1s",
            record_segment_duration=clip_duration,
            record_delete_after="0s",
            record_path=record_path_pattern,
            run_on_record_segment_complete="nvr recording hook-segment-complete",
            source_fingerprint=(
                (main_stream.tls_fingerprint_sha256 or "") if main_stream and scheme == "rtsps" else ""
            ),
        )

        # 2. Sub stream (if configured)
        sub_stream = stream_by_role.get("sub")
        if sub_stream is not None:
            sub_scheme = sub_stream.scheme
            sub_port = sub_stream.port
            sub_path = sub_stream.path
            if not sub_path.startswith("/"):
                sub_path = f"/{sub_path}"

            if user and password_val:
                enc_user = urllib.parse.quote(user, safe="")
                enc_pw = urllib.parse.quote(password_val, safe="")
                sub_source_url = f"{sub_scheme}://{enc_user}:{enc_pw}@{cam.host}:{sub_port}{sub_path}"
            else:
                sub_source_url = f"{sub_scheme}://{cam.host}:{sub_port}{sub_path}"

            sub_path_name = camera_path_name(cam.serial, "sub")
            desired[sub_path_name] = PathConfiguration(
                name=sub_path_name,
                source=sub_source_url,
                source_on_demand=True,
                record=False,
                record_format="fmp4",
                record_part_duration="1s",
                record_segment_duration="60s",
                record_delete_after="0s",
                record_path="",
                run_on_record_segment_complete="",
                source_fingerprint=(sub_stream.tls_fingerprint_sha256 or "") if sub_scheme == "rtsps" else "",
            )

    return desired


class MediaMtxReconciler:
    """Synchronizes desired camera path configurations with MediaMTX REST control API."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        api_base: str,
        control_auth: tuple[str, str],
    ) -> None:
        self.client = client
        self.api_base = api_base.rstrip("/")
        self.control_auth = control_auth

    async def get_existing_paths(self) -> dict[str, dict[str, Any]]:
        """Fetch all configured paths currently present in MediaMTX."""
        url = f"{self.api_base}/v3/config/paths/list"
        res = await self.client.get(url, auth=self.control_auth)
        res.raise_for_status()
        data = res.json()
        items = data.get("items", [])
        return {item["name"]: item for item in items if isinstance(item, dict) and "name" in item}

    async def reconcile(
        self,
        desired_paths: dict[str, PathConfiguration],
    ) -> ReconcileResult:
        """Diff and reconcile desired paths into MediaMTX via add, patch, and delete API calls."""
        existing = await self.get_existing_paths()

        added: list[str] = []
        patched: list[str] = []
        deleted: list[str] = []
        unchanged: list[str] = []

        # 1. Add missing or patch modified desired paths
        for name, desired in desired_paths.items():
            payload = desired.to_api_dict()
            if name not in existing:
                add_url = f"{self.api_base}/v3/config/paths/add/{name}"
                res = await self.client.post(add_url, json=payload, auth=self.control_auth)
                res.raise_for_status()
                added.append(name)
            else:
                current = existing[name]
                if _needs_patch(current, payload):
                    patch_url = f"{self.api_base}/v3/config/paths/patch/{name}"
                    res = await self.client.patch(patch_url, json=payload, auth=self.control_auth)
                    res.raise_for_status()
                    patched.append(name)
                else:
                    unchanged.append(name)

        # 2. Delete managed paths ('cam/*') that are no longer desired
        for name in list(existing.keys()):
            if name.startswith("cam/") and name not in desired_paths:
                del_url = f"{self.api_base}/v3/config/paths/delete/{name}"
                res = await self.client.delete(del_url, auth=self.control_auth)
                res.raise_for_status()
                deleted.append(name)

        return ReconcileResult(
            added=added,
            patched=patched,
            deleted=deleted,
            unchanged=unchanged,
        )
