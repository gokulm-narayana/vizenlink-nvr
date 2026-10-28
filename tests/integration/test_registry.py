"""Integration tests for camera registry, storage, cascading deletes, and credential sealing."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from vizenlink_nvr.db.engine import create_engine_for, upgrade_to_head
from vizenlink_nvr.db.models import Camera, CameraCapabilitiesRow, CameraCredential, CameraStream
from vizenlink_nvr.secrets.vault import Vault
from vizenlink_nvr.services.registry import (
    CameraView,
    NewCameraRecord,
    camera_counts,
    get_camera,
    insert_camera,
    list_cameras,
    load_connection,
    replace_capabilities_and_streams,
    replace_credential,
    set_state,
    stream_url,
    update_host,
)
from vizenlink_nvr.services.streams import StreamRecord


@pytest.fixture
async def db_session(tmp_path: Path):
    """Create fresh database with head schema and yield an async sessionmaker."""
    db_file = tmp_path / "registry_test.db"
    upgrade_to_head(db_file)
    engine = create_engine_for(db_file)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest.fixture
def vault() -> Vault:
    """In-memory Vault for test sealing and opening."""
    return Vault(key=b"\x01" * 32, key_id="vault-test-1", source="test")


async def test_insert_and_get_camera_view(db_session, vault: Vault) -> None:
    """insert_camera writes camera and related records; get_camera returns safe CameraView without secrets."""
    now = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
    sealed = vault.seal("VZL-CAM-001", "admin", SecretStr("TestPass123"))

    streams = [
        StreamRecord(
            role="main",
            profile_token="Profile_1",
            profile_name="MainStream",
            venc_token="VideoEncoder_1",
            codec="H265",
            width=2560,
            height=1440,
            transport="rtsp",
            scheme="rtsps",
            port=554,
            path="/high",
            source="nuraeye",
            sub_is_main=False,
        ),
        StreamRecord(
            role="sub",
            profile_token="Profile_2",
            profile_name="SubStream",
            venc_token="VideoEncoder_2",
            codec="H265",
            width=1280,
            height=720,
            transport="rtsp",
            scheme="rtsps",
            port=554,
            path="/low",
            source="nuraeye",
            sub_is_main=False,
        ),
    ]

    record = NewCameraRecord(
        serial="VZL-CAM-001",
        host="192.168.1.50",
        https_port=443,
        mac="AA:BB:CC:DD:EE:01",
        name="Front Door",
        location="Porch",
        group_tag="Outdoors",
        manufacturer="VizenLink",
        model="VZL-Dome-1",
        firmware_version="1.0.0",
        hardware_id="HW-001",
        tls_fingerprint_sha256="sha256-dummy-fingerprint",
        camera_id_check=True,
        username="admin",
        sealed_password=sealed,
        capabilities_raw='{"ptz": false}',
        streams=streams,
        added_at=now,
    )

    async with db_session() as session:
        view = await insert_camera(session, record)
        await session.commit()

    assert isinstance(view, CameraView)
    assert view.serial == "VZL-CAM-001"
    assert view.name == "Front Door"
    assert len(view.streams) == 2
    # Verify no secret fields exist on CameraView
    assert not hasattr(view, "password")
    assert not hasattr(view, "ciphertext")
    assert not hasattr(view, "nonce")

    # get_camera check
    async with db_session() as session:
        fetched = await get_camera(session, "VZL-CAM-001")
        assert fetched is not None
        assert fetched.serial == "VZL-CAM-001"
        assert fetched.host == "192.168.1.50"
        assert len(fetched.streams) == 2

        # Nonexistent serial returns None
        assert await get_camera(session, "NONEXISTENT") is None


async def test_update_host_and_state(db_session, vault: Vault) -> None:
    """update_host changes host/port; set_state updates operational status."""
    now = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
    sealed = vault.seal("VZL-CAM-002", "admin", SecretStr("Pass"))

    record = NewCameraRecord(
        serial="VZL-CAM-002",
        host="192.168.1.51",
        https_port=443,
        mac="AA:BB:CC:DD:EE:02",
        name="Back Yard",
        location="Yard",
        group_tag="Outdoors",
        manufacturer="VizenLink",
        model="VZL-Dome-2",
        firmware_version="1.0.0",
        hardware_id="HW-002",
        tls_fingerprint_sha256="fp-02",
        camera_id_check=True,
        username="admin",
        sealed_password=sealed,
        capabilities_raw="{}",
        streams=[],
        added_at=now,
    )

    async with db_session() as session:
        await insert_camera(session, record)
        await session.commit()

    later = datetime(2026, 10, 28, 12, 30, 0, tzinfo=UTC)
    async with db_session() as session:
        await update_host(session, "VZL-CAM-002", "192.168.1.99", 8443, later)
        await set_state(session, "VZL-CAM-002", "unreachable", last_error="Connection timed out")
        await session.commit()

    async with db_session() as session:
        cam = await get_camera(session, "VZL-CAM-002")
        assert cam is not None
        assert cam.host == "192.168.1.99"
        assert cam.https_port == 8443
        assert cam.host_updated_at == later
        assert cam.state == "unreachable"
        assert cam.last_error == "Connection timed out"


async def test_replace_credential_and_load_connection(db_session, vault: Vault) -> None:
    """replace_credential updates cipher envelope; load_connection opens and decrypts password."""
    now = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
    sealed1 = vault.seal("VZL-CAM-003", "admin", SecretStr("OldPass"))

    record = NewCameraRecord(
        serial="VZL-CAM-003",
        host="192.168.1.52",
        https_port=443,
        mac="AA:BB:CC:DD:EE:03",
        name="Garage",
        location="Garage",
        group_tag="",
        manufacturer="VizenLink",
        model="VZL-Bullet-3",
        firmware_version="1.0.0",
        hardware_id="HW-003",
        tls_fingerprint_sha256="fp-03",
        camera_id_check=True,
        username="admin",
        sealed_password=sealed1,
        capabilities_raw="{}",
        streams=[],
        added_at=now,
    )

    async with db_session() as session:
        await insert_camera(session, record)
        await session.commit()

    # Load initial connection
    async with db_session() as session:
        conn1 = await load_connection(session, vault, "VZL-CAM-003")
        assert conn1.username == "admin"
        assert conn1.password.get_secret_value() == "OldPass"
        assert conn1.tls_pin_sha256 == "fp-03"

    # Replace credential with new password
    later = datetime(2026, 10, 28, 13, 0, 0, tzinfo=UTC)
    sealed2 = vault.seal("VZL-CAM-003", "admin", SecretStr("NewSecret123"))
    async with db_session() as session:
        await replace_credential(session, "VZL-CAM-003", "admin", sealed2, later)
        await session.commit()

    # Load updated connection
    async with db_session() as session:
        conn2 = await load_connection(session, vault, "VZL-CAM-003")
        assert conn2.password.get_secret_value() == "NewSecret123"


async def test_replace_capabilities_and_streams(db_session, vault: Vault) -> None:
    """replace_capabilities_and_streams updates capabilities json and replaces streams."""
    now = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
    sealed = vault.seal("VZL-CAM-004", "admin", SecretStr("Pass"))

    record = NewCameraRecord(
        serial="VZL-CAM-004",
        host="192.168.1.53",
        https_port=443,
        mac="AA:BB:CC:DD:EE:04",
        name="Kitchen",
        location="House",
        group_tag="",
        manufacturer="VizenLink",
        model="VZL-Mini",
        firmware_version="1.0.0",
        hardware_id="HW-004",
        tls_fingerprint_sha256="fp-04",
        camera_id_check=True,
        username="admin",
        sealed_password=sealed,
        capabilities_raw='{"version": 1}',
        streams=[
            StreamRecord(
                role="main",
                profile_token="Profile_1",
                profile_name="Main",
                venc_token="venc1",
                codec="H264",
                width=1920,
                height=1080,
                transport="rtsp",
                scheme="rtsps",
                port=554,
                path="/live/0",
                source="nuraeye",
                sub_is_main=True,
            )
        ],
        added_at=now,
    )

    async with db_session() as session:
        await insert_camera(session, record)
        await session.commit()

    later = datetime(2026, 10, 28, 13, 0, 0, tzinfo=UTC)
    new_streams = [
        StreamRecord(
            role="main",
            profile_token="Profile_1",
            profile_name="MainUpdated",
            venc_token="venc1",
            codec="H265",
            width=2560,
            height=1440,
            transport="rtsp",
            scheme="rtsps",
            port=554,
            path="/live/high",
            source="nuraeye",
            sub_is_main=False,
        ),
        StreamRecord(
            role="sub",
            profile_token="Profile_2",
            profile_name="SubNew",
            venc_token="venc2",
            codec="H265",
            width=1280,
            height=720,
            transport="rtsp",
            scheme="rtsps",
            port=554,
            path="/live/low",
            source="nuraeye",
            sub_is_main=False,
        ),
    ]

    async with db_session() as session:
        await replace_capabilities_and_streams(
            session,
            "VZL-CAM-004",
            '{"version": 2, "h265": true}',
            "2.0.0",
            new_streams,
            later,
        )
        await session.commit()

    async with db_session() as session:
        cam = await get_camera(session, "VZL-CAM-004")
        assert cam is not None
        assert len(cam.streams) == 2
        assert cam.streams[0].codec == "H265"
        assert cam.streams[0].width == 2560

        # Check raw capabilities row
        caps = (
            await session.execute(
                select(CameraCapabilitiesRow).where(CameraCapabilitiesRow.serial == "VZL-CAM-004")
            )
        ).scalar_one()
        assert caps.raw_json == '{"version": 2, "h265": true}'
        assert caps.firmware_version_at_probe == "2.0.0"


async def test_camera_counts_and_list_cameras(db_session, vault: Vault) -> None:
    """list_cameras returns ordered views; camera_counts aggregates state counts."""
    now = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)

    async with db_session() as session:
        for i, s in enumerate(["B", "A", "C"]):
            rec = NewCameraRecord(
                serial=f"SERIAL-{s}",
                host=f"10.0.0.{i + 1}",
                https_port=443,
                mac=f"00:11:22:33:44:0{i}",
                name=f"Cam-{s}",
                location="",
                group_tag="",
                manufacturer="VZL",
                model="Model-1",
                firmware_version="1.0",
                hardware_id="HW",
                tls_fingerprint_sha256="fp",
                camera_id_check=True,
                username="admin",
                sealed_password=vault.seal(f"SERIAL-{s}", "admin", SecretStr("p")),
                capabilities_raw="{}",
                streams=[],
                added_at=now,
            )
            await insert_camera(session, rec)
        await session.commit()

    async with db_session() as session:
        cams = await list_cameras(session)
        assert [c.serial for c in cams] == ["SERIAL-A", "SERIAL-B", "SERIAL-C"]

        counts = await camera_counts(session)
        assert counts["total"] == 3
        assert counts["active"] == 3
        assert counts["unreachable"] == 0


async def test_stream_url_and_cascade_delete(db_session, vault: Vault) -> None:
    """stream_url builds URL without credentials; deleting Camera cascades to related tables."""
    now = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
    rec = NewCameraRecord(
        serial="VZL-CASCADE",
        host="192.168.1.100",
        https_port=443,
        mac="AA:BB:CC:DD:EE:FF",
        name="Cascade Cam",
        location="",
        group_tag="",
        manufacturer="VZL",
        model="Model",
        firmware_version="1.0",
        hardware_id="HW",
        tls_fingerprint_sha256="fp",
        camera_id_check=True,
        username="admin",
        sealed_password=vault.seal("VZL-CASCADE", "admin", SecretStr("p")),
        capabilities_raw="{}",
        streams=[
            StreamRecord(
                role="main",
                profile_token="Profile_1",
                profile_name="Main",
                venc_token="v1",
                codec="H264",
                width=1920,
                height=1080,
                transport="rtsp",
                scheme="rtsps",
                port=554,
                path="/live/ch0",
                source="nuraeye",
                sub_is_main=False,
            )
        ],
        added_at=now,
    )

    async with db_session() as session:
        cam_view = await insert_camera(session, rec)
        await session.commit()

    # stream_url check
    url = stream_url(cam_view, cam_view.streams[0])
    assert url == "rtsps://192.168.1.100:554/live/ch0"
    assert "admin" not in url

    # Delete Camera and verify cascade
    async with db_session() as session:
        cam_obj = (await session.execute(select(Camera).where(Camera.serial == "VZL-CASCADE"))).scalar_one()
        await session.delete(cam_obj)
        await session.commit()

    async with db_session() as session:
        # Related rows should be gone
        creds = (
            await session.execute(select(CameraCredential).where(CameraCredential.serial == "VZL-CASCADE"))
        ).all()
        assert len(creds) == 0
        caps = (
            await session.execute(
                select(CameraCapabilitiesRow).where(CameraCapabilitiesRow.serial == "VZL-CASCADE")
            )
        ).all()
        assert len(caps) == 0
        streams = (
            await session.execute(select(CameraStream).where(CameraStream.serial == "VZL-CASCADE"))
        ).all()
        assert len(streams) == 0
