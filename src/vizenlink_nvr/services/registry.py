"""Camera registry service for managing camera records, credentials, and streams."""

from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.db.models import (
    Camera,
    CameraCapabilitiesRow,
    CameraCredential,
    CameraOutage,
    CameraStream,
    EventSubscription,
    RecordingSettings,
    UserCameraPermission,
)
from vizenlink_nvr.secrets.vault import SealedSecret, Vault
from vizenlink_nvr.services.streams import StreamRecord
from vizenlink_nvr.timeutil import utc_now


class StreamView(BaseModel):
    """View model for camera video stream (main or sub)."""

    role: str
    profile_token: str
    profile_name: str
    venc_token: str
    codec: str
    width: int
    height: int
    transport: str
    scheme: str
    port: int
    path: str
    source: str
    sub_is_main: bool
    probed_at: datetime


MAX_GROUP_LENGTH: int = 64


class CameraView(BaseModel):
    """Safe view model for camera details without secret credentials."""

    serial: str
    host: str
    https_port: int
    mac: str
    name: str
    location: str
    group_tag: str
    manufacturer: str
    model: str
    firmware_version: str
    hardware_id: str
    tls_fingerprint_sha256: str
    camera_id_check: bool
    state: str
    added_at: datetime
    host_updated_at: datetime
    identity_synced_at: datetime | None
    last_error: str | None
    archived: bool = False
    streams: list[StreamView] = []


@dataclass(frozen=True)
class NewCameraRecord:
    """Input payload for adding a new camera to the registry."""

    serial: str
    host: str
    https_port: int
    mac: str
    name: str
    location: str
    group_tag: str
    manufacturer: str
    model: str
    firmware_version: str
    hardware_id: str
    tls_fingerprint_sha256: str
    camera_id_check: bool
    username: str
    sealed_password: SealedSecret
    capabilities_raw: str
    streams: list[StreamRecord]
    added_at: datetime


def _to_camera_view(camera: Camera) -> CameraView:
    """Convert DB model into safe public CameraView."""
    stream_views = [
        StreamView(
            role=s.role,
            profile_token=s.profile_token,
            profile_name=s.profile_name,
            venc_token=s.venc_token,
            codec=s.codec,
            width=s.width,
            height=s.height,
            transport=s.transport,
            scheme=s.scheme,
            port=s.port,
            path=s.path,
            source=s.source,
            sub_is_main=s.sub_is_main,
            probed_at=s.probed_at,
        )
        for s in camera.streams
    ]
    stream_views.sort(key=lambda s: 0 if s.role == "main" else 1)

    return CameraView(
        serial=camera.serial,
        host=camera.host,
        https_port=camera.https_port,
        mac=camera.mac,
        name=camera.name,
        archived=camera.archived,
        location=camera.location,
        group_tag=camera.group_tag,
        manufacturer=camera.manufacturer,
        model=camera.model,
        firmware_version=camera.firmware_version,
        hardware_id=camera.hardware_id,
        tls_fingerprint_sha256=camera.tls_fingerprint_sha256,
        camera_id_check=camera.camera_id_check,
        state=camera.state,
        added_at=camera.added_at,
        host_updated_at=camera.host_updated_at,
        identity_synced_at=camera.identity_synced_at,
        last_error=camera.last_error,
        streams=stream_views,
    )


def stream_url(camera: CameraView | Camera, stream: StreamView | CameraStream) -> str:
    """Construct RTSP stream URL without credentials (D-14, D-16)."""
    return f"{stream.scheme}://{camera.host}:{stream.port}{stream.path}"


async def archive_camera(session: AsyncSession, camera: Camera) -> None:
    """Retain historical media and remove all live configuration and camera access grants."""
    camera.archived = True
    for model, column in (
        (CameraCredential, CameraCredential.serial),
        (CameraCapabilitiesRow, CameraCapabilitiesRow.serial),
        (CameraStream, CameraStream.serial),
        (RecordingSettings, RecordingSettings.camera_serial),
        (EventSubscription, EventSubscription.camera_serial),
        (UserCameraPermission, UserCameraPermission.camera_serial),
    ):
        await session.execute(delete(model).where(column == camera.serial))
    await session.execute(
        update(CameraOutage)
        .where(CameraOutage.camera_serial == camera.serial, CameraOutage.ended_at.is_(None))
        .values(ended_at=utc_now())
    )


async def insert_camera(
    session: AsyncSession,
    record: NewCameraRecord,
) -> CameraView:
    """Insert new camera with credential, capabilities, and stream records in a single transaction."""
    fields = dict(
        archived=False,
        host=record.host,
        https_port=record.https_port,
        mac=record.mac,
        name=record.name,
        location=record.location,
        group_tag=record.group_tag,
        manufacturer=record.manufacturer,
        model=record.model,
        firmware_version=record.firmware_version,
        hardware_id=record.hardware_id,
        tls_fingerprint_sha256=record.tls_fingerprint_sha256,
        camera_id_check=record.camera_id_check,
        state="active",
        added_at=record.added_at,
        host_updated_at=record.added_at,
        identity_synced_at=record.added_at,
        last_error=None,
    )
    restored = await session.scalar(
        update(Camera)
        .where(Camera.serial == record.serial, Camera.archived.is_(True))
        .values(**fields)
        .returning(Camera.serial)
    )
    if restored is None:
        session.add(Camera(serial=record.serial, **fields))

    cred = CameraCredential(
        serial=record.serial,
        username=record.username,
        ciphertext=record.sealed_password.ciphertext,
        nonce=record.sealed_password.nonce,
        key_id=record.sealed_password.key_id,
        enc_version=record.sealed_password.enc_version,
        updated_at=record.added_at,
    )
    session.add(cred)

    caps = CameraCapabilitiesRow(
        serial=record.serial,
        raw_json=record.capabilities_raw,
        probed_at=record.added_at,
        firmware_version_at_probe=record.firmware_version,
    )
    session.add(caps)

    for s in record.streams:
        st = CameraStream(
            serial=record.serial,
            role=s.role,
            profile_token=s.profile_token,
            profile_name=s.profile_name,
            venc_token=s.venc_token,
            codec=s.codec,
            width=s.width,
            height=s.height,
            transport=s.transport,
            scheme=s.scheme,
            port=s.port,
            path=s.path,
            source=s.source,
            sub_is_main=s.sub_is_main,
            probed_at=record.added_at,
        )
        session.add(st)

    await session.flush()
    # Re-fetch with relationships loaded
    stmt = select(Camera).options(selectinload(Camera.streams)).where(Camera.serial == record.serial)
    res = await session.execute(stmt)
    saved = res.scalar_one()
    return _to_camera_view(saved)


async def get_camera(
    session: AsyncSession,
    serial: str,
) -> CameraView | None:
    """Fetch camera by serial, returning CameraView or None."""
    stmt = select(Camera).options(selectinload(Camera.streams)).where(Camera.serial == serial)
    res = await session.execute(stmt)
    camera = res.scalar_one_or_none()
    if camera is None:
        return None
    return _to_camera_view(camera)


async def list_cameras(
    session: AsyncSession,
    *, playback: bool = False,
) -> list[CameraView]:
    """List all registered cameras sorted by serial."""
    stmt = select(Camera).options(selectinload(Camera.streams)).order_by(Camera.archived, Camera.serial)
    if playback:
        stmt = stmt.execution_options(include_archived=True).where(~Camera.archived | Camera.segments.any())
    res = await session.execute(stmt)
    return [_to_camera_view(c) for c in res.scalars()]


async def update_host(
    session: AsyncSession,
    serial: str,
    host: str,
    port: int,
    at: datetime,
) -> None:
    """Update camera network host, port, and update timestamp."""
    stmt = select(Camera).where(Camera.serial == serial)
    res = await session.execute(stmt)
    cam = res.scalar_one()
    cam.host = host
    cam.https_port = port
    cam.host_updated_at = at
    await session.flush()


async def update_identity(
    session: AsyncSession,
    serial: str,
    *,
    name: str | None = None,
    location: str | None = None,
    group: str | None = None,
    at: datetime,
) -> CameraView:
    """Update camera name, location, or group tag, and record identity sync timestamp."""
    stmt = select(Camera).options(selectinload(Camera.streams)).where(Camera.serial == serial)
    res = await session.execute(stmt)
    cam = res.scalar_one()
    if name is not None:
        cam.name = name
    if location is not None:
        cam.location = location
    if group is not None:
        cam.group_tag = group
    cam.identity_synced_at = at
    await session.flush()
    return _to_camera_view(cam)


async def set_tls_fingerprint(
    session: AsyncSession,
    serial: str,
    sha256_hex: str,
    at: datetime,
) -> None:
    """Update stored TLS certificate pin for camera."""
    stmt = select(Camera).where(Camera.serial == serial)
    res = await session.execute(stmt)
    cam = res.scalar_one()
    cam.tls_fingerprint_sha256 = sha256_hex
    await session.flush()


async def set_state(
    session: AsyncSession,
    serial: str,
    state: str,
    last_error: str | None = None,
) -> None:
    """Update camera operating state and last error message."""
    stmt = select(Camera).where(Camera.serial == serial)
    res = await session.execute(stmt)
    cam = res.scalar_one()
    cam.state = state
    cam.last_error = last_error
    await session.flush()


async def replace_credential(
    session: AsyncSession,
    serial: str,
    username: str,
    sealed: SealedSecret,
    at: datetime,
) -> None:
    """Replace encrypted camera password envelope."""
    stmt = select(CameraCredential).where(CameraCredential.serial == serial)
    res = await session.execute(stmt)
    cred = res.scalar_one()
    cred.username = username
    cred.ciphertext = sealed.ciphertext
    cred.nonce = sealed.nonce
    cred.key_id = sealed.key_id
    cred.enc_version = sealed.enc_version
    cred.updated_at = at
    await session.flush()


async def replace_capabilities_and_streams(
    session: AsyncSession,
    serial: str,
    capabilities_raw: str,
    firmware_version: str,
    streams: list[StreamRecord],
    at: datetime,
) -> None:
    """Replace cached capabilities and stream definitions for camera."""
    caps_stmt = select(CameraCapabilitiesRow).where(CameraCapabilitiesRow.serial == serial)
    res = await session.execute(caps_stmt)
    caps = res.scalar_one()
    caps.raw_json = capabilities_raw
    caps.firmware_version_at_probe = firmware_version
    caps.probed_at = at

    # Remove existing streams and insert updated ones
    streams_stmt = select(CameraStream).where(CameraStream.serial == serial)
    existing_streams = (await session.execute(streams_stmt)).scalars().all()
    for stream_row in existing_streams:
        await session.delete(stream_row)

    for st_rec in streams:
        st = CameraStream(
            serial=serial,
            role=st_rec.role,
            profile_token=st_rec.profile_token,
            profile_name=st_rec.profile_name,
            venc_token=st_rec.venc_token,
            codec=st_rec.codec,
            width=st_rec.width,
            height=st_rec.height,
            transport=st_rec.transport,
            scheme=st_rec.scheme,
            port=st_rec.port,
            path=st_rec.path,
            source=st_rec.source,
            sub_is_main=st_rec.sub_is_main,
            probed_at=at,
        )
        session.add(st)

    await session.flush()


async def load_connection(
    session: AsyncSession,
    vault: Vault,
    serial: str,
) -> CameraConnection:
    """Load camera connection parameters and decrypt password via Vault."""
    cam_stmt = select(Camera).where(Camera.serial == serial)
    cam = (await session.execute(cam_stmt)).scalar_one()

    cred_stmt = select(CameraCredential).where(CameraCredential.serial == serial)
    cred = (await session.execute(cred_stmt)).scalar_one()

    sealed = SealedSecret(
        ciphertext=cred.ciphertext,
        nonce=cred.nonce,
        key_id=cred.key_id,
        enc_version=cred.enc_version,
    )
    password = vault.open(serial, cred.username, sealed)

    return CameraConnection(
        host=cam.host,
        port=cam.https_port,
        username=cred.username,
        password=password,
        serial=cam.serial,
        tls_pin_sha256=cam.tls_fingerprint_sha256,
    )


async def camera_counts(session: AsyncSession) -> dict[str, int]:
    """Return dictionary of camera counts grouped by state plus total."""
    stmt = select(Camera.state, func.count(Camera.serial)).group_by(Camera.state)
    res = await session.execute(stmt)
    counts = dict(res.all())
    total = sum(counts.values())
    return {
        "total": total,
        "active": counts.get("active", 0),
        "unreachable": counts.get("unreachable", 0),
        "auth_failed": counts.get("auth_failed", 0),
        "tls_changed": counts.get("tls_changed", 0),
    }
