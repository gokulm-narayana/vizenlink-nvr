"""Unit tests for camera address healer rules, backoff, and event handling (HEAL-01..05)."""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.discovery.ws_discovery import DiscoveredDevice
from vizenlink_nvr.camera.events import (
    CameraEventBus,
    CameraIdMismatchEvent,
)
from vizenlink_nvr.camera.layer import CameraLayer
from vizenlink_nvr.camera.nuraeye.sessions import NuraeyeSessionCache, Session
from vizenlink_nvr.config import NvrSettings
from vizenlink_nvr.secrets.vault import SealedSecret
from vizenlink_nvr.services.recovery import (
    AddressHealer,
    HealKind,
    HealTrigger,
)
from vizenlink_nvr.services.registry import NewCameraRecord, get_camera, insert_camera
from vizenlink_nvr.services.runtime import open_runtime
from vizenlink_nvr.timeutil import UTC, FakeClock


async def _create_test_camera(
    rt,
    *,
    serial: str = "VZL-CAM-RULE-01",
    host: str = "192.168.1.100",
    port: int = 443,
    camera_id_check: bool = True,
) -> None:
    """Helper to insert a camera record in the registry."""
    now = rt.clock.now()
    sealed = SealedSecret(ciphertext=b"enc", nonce=b"nonce", key_id="k1", enc_version=1)
    rec = NewCameraRecord(
        serial=serial,
        host=host,
        https_port=port,
        mac="AA:BB:CC:DD:EE:01",
        name="Front Door",
        location="Front",
        group_tag="",
        manufacturer="VizenLink",
        model="VZL-Pro",
        firmware_version="1.0.0",
        hardware_id="HW-1",
        tls_fingerprint_sha256="sha256:abc",
        camera_id_check=camera_id_check,
        username="admin",
        sealed_password=sealed,
        capabilities_raw="{}",
        streams=[],
        added_at=now,
    )
    async with rt.sessions() as session:
        async with session.begin():
            await insert_camera(session, rec)


@pytest.mark.behavior("HEAL-01")
async def test_healer_ignore_unknown_serial_and_differing_host(tmp_path: Path) -> None:
    """Unknown serial or reported host differing from stored host returns IGNORED."""
    clock = FakeClock(datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC))
    settings = NvrSettings(data_dir=tmp_path)

    async with open_runtime(settings, clock=clock) as rt:
        layer = CameraLayer.create(clock=clock)
        await _create_test_camera(rt, serial="VZL-STORED-01", host="192.168.1.50")

        healer = AddressHealer(
            rt,
            layer,
            discover=AsyncMock(return_value=[]),
            read_serial=AsyncMock(return_value=None),
            clock=clock,
        )

        # 1. Unknown serial -> IGNORED
        res1 = await healer.heal("VZL-UNKNOWN", HealTrigger.ID_MISMATCH)
        assert res1.kind == HealKind.IGNORED

        # 2. Reported host differs from stored host (already moved/healed) -> IGNORED
        res2 = await healer.heal(
            "VZL-STORED-01",
            HealTrigger.ID_MISMATCH,
            reported_host="192.168.1.99",  # different from 192.168.1.50
        )
        assert res2.kind == HealKind.IGNORED


@pytest.mark.behavior("HEAL-01")
async def test_healer_in_flight_deduplication_and_backoff_bypass(tmp_path: Path) -> None:
    """Concurrent heals deduplicate via SKIPPED_IN_FLIGHT; backoff is respected unless forced."""
    clock = FakeClock(datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC))
    settings = NvrSettings(data_dir=tmp_path)

    async with open_runtime(settings, clock=clock) as rt:
        layer = CameraLayer.create(clock=clock)
        await _create_test_camera(rt, serial="VZL-CONC-01", host="192.168.1.60")

        # Fake slow discovery
        discover_started = asyncio.Event()
        finish_discover = asyncio.Event()

        async def slow_discover(thorough: bool):
            discover_started.set()
            await finish_discover.wait()
            return []

        healer = AddressHealer(
            rt,
            layer,
            discover=slow_discover,
            read_serial=AsyncMock(return_value=None),
            clock=clock,
        )

        # 1. Start first heal
        t1 = asyncio.create_task(healer.heal("VZL-CONC-01", HealTrigger.ID_MISMATCH))
        await discover_started.wait()

        # 2. Concurrently trigger second heal for same serial -> SKIPPED_IN_FLIGHT
        res2 = await healer.heal("VZL-CONC-01", HealTrigger.ID_MISMATCH)
        assert res2.kind == HealKind.SKIPPED_IN_FLIGHT

        # Complete first heal
        finish_discover.set()
        res1 = await t1
        assert res1.kind == HealKind.NOT_FOUND

        # 3. Third heal during backoff (non-forced) -> SKIPPED_BACKOFF
        res3 = await healer.heal("VZL-CONC-01", HealTrigger.ID_MISMATCH, force=False)
        assert res3.kind == HealKind.SKIPPED_BACKOFF
        assert res3.next_attempt_at is not None

        # 4. Fourth heal with force=True bypasses backoff and searches
        finish_discover.clear()
        discover_started.clear()
        t4 = asyncio.create_task(healer.heal("VZL-CONC-01", HealTrigger.ID_MISMATCH, force=True))
        await discover_started.wait()
        finish_discover.set()
        res4 = await t4
        assert res4.kind == HealKind.NOT_FOUND


@pytest.mark.behavior("HEAL-02")
async def test_healer_unreachable_verified_in_place_and_60s_window(tmp_path: Path) -> None:
    """Unreachable trigger verifies in place without search; repeated report within 60s skips read."""
    clock = FakeClock(datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC))
    settings = NvrSettings(data_dir=tmp_path)

    async with open_runtime(settings, clock=clock) as rt:
        layer = CameraLayer.create(clock=clock)
        await _create_test_camera(rt, serial="VZL-VERIF-01", host="192.168.1.70", port=443)

        read_serial_mock = AsyncMock(return_value="VZL-VERIF-01")
        discover_mock = AsyncMock(return_value=[])

        healer = AddressHealer(
            rt,
            layer,
            discover=discover_mock,
            read_serial=read_serial_mock,
            clock=clock,
            verified_window=timedelta(seconds=60),
        )

        # 1. First unreachable trigger reads serial at stored address -> VERIFIED_IN_PLACE
        res1 = await healer.heal("VZL-VERIF-01", HealTrigger.UNREACHABLE)
        assert res1.kind == HealKind.VERIFIED_IN_PLACE
        assert read_serial_mock.call_count == 1
        assert discover_mock.call_count == 0  # No network search was needed!

        # 2. Advance clock 30 seconds (still within 60s window)
        clock.advance(timedelta(seconds=30))

        # Second unreachable trigger -> VERIFIED_IN_PLACE without reading serial
        res2 = await healer.heal("VZL-VERIF-01", HealTrigger.UNREACHABLE)
        assert res2.kind == HealKind.VERIFIED_IN_PLACE
        assert read_serial_mock.call_count == 1  # Not called again!

        # 3. Advance past 60s window (40 more seconds -> 70s total)
        clock.advance(timedelta(seconds=40))
        res3 = await healer.heal("VZL-VERIF-01", HealTrigger.UNREACHABLE)
        assert res3.kind == HealKind.VERIFIED_IN_PLACE
        assert read_serial_mock.call_count == 2  # Read serial called again


@pytest.mark.behavior("HEAL-02")
async def test_healer_placeholder_host_skips_precheck(tmp_path: Path) -> None:
    """Stored camera with placeholder host ('0.0.0.0' or 'cloud-') skips straight to search."""
    clock = FakeClock(datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC))
    settings = NvrSettings(data_dir=tmp_path)

    async with open_runtime(settings, clock=clock) as rt:
        layer = CameraLayer.create(clock=clock)
        await _create_test_camera(rt, serial="VZL-CLOUD-01", host="cloud-vz1234")

        discover_mock = AsyncMock(
            return_value=[
                DiscoveredDevice(
                    scheme="https",
                    host="192.168.1.180",
                    port=443,
                    xaddr="https://192.168.1.180:443/onvif/device_service",
                    scopes=[],
                )
            ]
        )

        async def read_serial_impl(host: str, port: int) -> str | None:
            if host == "192.168.1.180":
                return "VZL-CLOUD-01"
            return None

        healer = AddressHealer(
            rt,
            layer,
            discover=discover_mock,
            read_serial=read_serial_impl,
            clock=clock,
        )

        res = await healer.heal("VZL-CLOUD-01", HealTrigger.UNREACHABLE)
        assert res.kind == HealKind.HEALED
        assert res.new_address == "192.168.1.180:443"


@pytest.mark.behavior("HEAL-03")
async def test_healer_match_ambiguity_and_stored_exclusion(tmp_path: Path) -> None:
    """One match heals; two matches returns AMBIGUOUS; stored address is excluded from candidates."""
    clock = FakeClock(datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC))
    settings = NvrSettings(data_dir=tmp_path)

    async with open_runtime(settings, clock=clock) as rt:
        layer = CameraLayer.create(clock=clock)
        await _create_test_camera(rt, serial="VZL-AMBIG-01", host="192.168.1.80", port=443)

        # Candidates returned by discovery
        candidates = [
            DiscoveredDevice(
                scheme="https",
                host="192.168.1.80",
                port=443,
                xaddr="https://192.168.1.80:443/onvif/device_service",
                scopes=[],
            ),  # stored address
            DiscoveredDevice(
                scheme="https",
                host="192.168.1.81",
                port=443,
                xaddr="https://192.168.1.81:443/onvif/device_service",
                scopes=[],
            ),
            DiscoveredDevice(
                scheme="https",
                host="192.168.1.82",
                port=443,
                xaddr="https://192.168.1.82:443/onvif/device_service",
                scopes=[],
            ),
        ]

        async def read_serial_ambiguous(host: str, port: int) -> str | None:
            # Both 81 and 82 claim the serial; stored 80 also returns serial if asked
            return "VZL-AMBIG-01"

        healer = AddressHealer(
            rt,
            layer,
            discover=AsyncMock(return_value=candidates),
            read_serial=read_serial_ambiguous,
            clock=clock,
        )

        res = await healer.heal("VZL-AMBIG-01", HealTrigger.ID_MISMATCH)
        assert res.kind == HealKind.AMBIGUOUS
        assert res.claimants == 2  # Exactly 81 and 82 (stored 80 was excluded!)

        # Database remains unchanged
        async with rt.sessions() as session:
            cam = await get_camera(session, "VZL-AMBIG-01")
            assert cam is not None
            assert cam.host == "192.168.1.80"


@pytest.mark.behavior("HEAL-04")
async def test_healer_exponential_backoff_sequence(tmp_path: Path) -> None:
    """Consecutive NOT_FOUND results set next_attempt_at to now + 30, 60, 120, 240, 480, 600, 600 s."""
    clock = FakeClock(datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC))
    settings = NvrSettings(data_dir=tmp_path)

    async with open_runtime(settings, clock=clock) as rt:
        layer = CameraLayer.create(clock=clock)
        await _create_test_camera(rt, serial="VZL-BACKOFF-01", host="192.168.1.90")

        healer = AddressHealer(
            rt,
            layer,
            discover=AsyncMock(return_value=[]),
            read_serial=AsyncMock(return_value=None),
            clock=clock,
            base_backoff=timedelta(seconds=30),
            max_backoff=timedelta(minutes=10),
        )

        expected_waits = [30, 60, 120, 240, 480, 600, 600]
        actual_waits = []

        for _ in expected_waits:
            before = clock.now()
            res = await healer.heal("VZL-BACKOFF-01", HealTrigger.ID_MISMATCH, force=True)
            assert res.kind == HealKind.NOT_FOUND
            assert res.next_attempt_at is not None
            wait_sec = int((res.next_attempt_at - before).total_seconds())
            actual_waits.append(wait_sec)

        assert actual_waits == expected_waits


@pytest.mark.behavior("HEAL-05")
async def test_healer_healed_updates_db_clears_session_and_uses_blank_credentials(tmp_path: Path) -> None:
    """HEALED updates host/port/host_updated_at, clears old sessions,
    and verifies blank-credential connections.
    """
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC))
    settings = NvrSettings(data_dir=tmp_path)

    async with open_runtime(settings, clock=clock) as rt:
        layer = CameraLayer.create(clock=clock)
        await _create_test_camera(rt, serial="VZL-HEALED-01", host="192.168.1.10", port=443)

        # Populate a session for old host in session cache
        sess_key = NuraeyeSessionCache.session_key("192.168.1.10", "admin")
        layer.sessions.put(
            sess_key,
            Session(
                token="token-old",
                expires_in_sec=1800,
                valid_until=clock.now() + timedelta(seconds=1800),
                username="admin",
                role="admin",
                password_change_required=False,
            ),
        )
        assert layer.sessions.get(sess_key) is not None

        candidate = DiscoveredDevice(
            scheme="https",
            host="192.168.1.20",
            port=443,
            xaddr="https://192.168.1.20:443/onvif/device_service",
            scopes=[],
        )

        connections_checked: list[CameraConnection] = []

        async def read_serial_tracker(host: str, port: int) -> str | None:
            conn = CameraConnection.blank(host, port)
            connections_checked.append(conn)
            if host == "192.168.1.20":
                return "VZL-HEALED-01"
            return None

        healer = AddressHealer(
            rt,
            layer,
            discover=AsyncMock(return_value=[candidate]),
            read_serial=read_serial_tracker,
            clock=clock,
        )

        res = await healer.heal("VZL-HEALED-01", HealTrigger.ID_MISMATCH)
        assert res.kind == HealKind.HEALED
        assert res.old_address == "192.168.1.10:443"
        assert res.new_address == "192.168.1.20:443"

        # 1. Stored DB row updated
        async with rt.sessions() as session:
            cam = await get_camera(session, "VZL-HEALED-01")
            assert cam is not None
            assert cam.host == "192.168.1.20"
            assert cam.host_updated_at == clock.now()

        # 2. Old session cache cleared
        assert layer.sessions.get(sess_key) is None

        # 3. Blank credential invariant checked on every connection
        assert len(connections_checked) > 0
        for conn in connections_checked:
            assert conn.username == ""
            assert conn.password.get_secret_value() == ""


@pytest.mark.behavior("HEAL-01")
async def test_healer_attach_event_bus(tmp_path: Path) -> None:
    """attach() schedules heals on CameraIdMismatchEvent and unsubscribe stops scheduling."""
    clock = FakeClock(datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC))
    settings = NvrSettings(data_dir=tmp_path)

    async with open_runtime(settings, clock=clock) as rt:
        layer = CameraLayer.create(clock=clock)
        await _create_test_camera(rt, serial="VZL-EVENT-01", host="192.168.1.30")

        heal_called = asyncio.Event()

        async def fake_discover(thorough: bool):
            heal_called.set()
            return []

        healer = AddressHealer(
            rt,
            layer,
            discover=fake_discover,
            read_serial=AsyncMock(return_value=None),
            clock=clock,
        )

        bus = CameraEventBus()
        unsub = healer.attach(bus)

        # 1. Publishing event schedules heal
        bus.publish(CameraIdMismatchEvent(host="192.168.1.30", port=443, expected_id="VZL-EVENT-01"))
        await asyncio.wait_for(heal_called.wait(), timeout=2.0)

        # 2. Unsubscribe stops scheduling
        unsub()
        heal_called.clear()
        bus.publish(CameraIdMismatchEvent(host="192.168.1.30", port=443, expected_id="VZL-EVENT-01"))
        await asyncio.sleep(0.05)
        assert not heal_called.is_set()

        await healer.aclose()
