"""Real NVR routes with simulated camera responses: scope, roles, validation and secrets."""

import asyncio
import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from typer.testing import CliRunner

from vizenlink_nvr.camera.result import Failure, FailureKind, Success
from vizenlink_nvr.cli.app import app as cli_app
from vizenlink_nvr.db.models import AuditLog
from vizenlink_nvr.services.camera_features import (
    CATALOG,
    GROUPS,
    INTERNAL,
    OPERATIONS,
    CameraFeaturesService,
    sanitize,
    validate,
)
from vizenlink_nvr.services.camera_settings import CameraSettingsService

pytest_plugins = ["test_camera_settings_api"]

CAPS = {
    "local_storage_capable": True,
    "accelerometer_capable": True,
    "supported_movement_sensitivities": ["Off", "Low", "High"],
    "supported_event_types": ["PersonDetected", "PrivacyModeChanged"],
    "supported_event_deterrence_options": {"PersonDetected": ["mobile_alert", "siren"]},
    "supported_recording_modes": ["continuous", "scheduled"],
    "max_recording_schedule_windows": 2,
    "loitering_duration_min_seconds": 10,
    "loitering_duration_max_seconds": 90,
}


def test_pinned_catalog_is_reproducible_and_covers_every_operation():
    build = runpy.run_path(str(Path(__file__).parents[2] / "tools/generate_camera_operations.py"))["build"]
    assert build() == CATALOG
    assert len(OPERATIONS) == 60
    exposed = [op for group in GROUPS.values() for op in group["operations"]]
    assert len(exposed) == len(set(exposed))
    assert set(exposed) | set(INTERNAL) == set(OPERATIONS)
    assert "Off" in OPERATIONS["setMirrorFlip"]["schema"]["properties"]["mode"]["enum"]


@pytest.mark.parametrize(
    "operation,payload",
    [
        ("setEventPreferences", {"InventedEvent": True}),
        ("setEventResponseActions", {"PrivacyModeChanged": []}),
        ("setEventResponseActions", {"PersonDetected": ["warning"]}),
        ("setLoiteringDuration", {"loitering_duration_seconds": 1000}),
        ("setRecordingMode", {"mode": "scheduled", "schedule": []}),
        (
            "setRecordingMode",
            {"mode": "scheduled", "schedule": [{"day_of_week": 1, "start_minute": 200, "end_minute": 100}]},
        ),
        ("setMovementProtectionSensitivity", {"sensitivity": "Extreme"}),
        ("deleteRecordings", {}),
    ],
)
def test_camera_capabilities_reject_unsupported_writes(operation, payload):
    with pytest.raises(HTTPException) as exc:
        CameraFeaturesService.validate_capabilities(operation, payload, CAPS)
    assert exc.value.status_code == 422


def test_buzzer_refused_only_when_camera_says_it_has_none():
    """camera_api has no buzzer flag yet; absent means unknown and must keep working."""
    no_buzzer = {**CAPS, "buzzer_capable": False}
    for operation, payload in [
        ("setBuzzer", {"active": True, "duration_seconds": 5}),
        ("setAlertRule", {"rule": "R", "mobile_notifications": True, "buzzer_activation": True}),
    ]:
        with pytest.raises(HTTPException) as exc:
            CameraFeaturesService.validate_capabilities(operation, payload, no_buzzer)
        assert exc.value.status_code == 422
        unknown = {k: v for k, v in CAPS.items() if k != "buzzer_capable"}
        CameraFeaturesService.validate_capabilities(operation, payload, unknown)
    CameraFeaturesService.validate_capabilities(
        "setAlertRule", {"rule": "R", "mobile_notifications": True, "buzzer_activation": False}, no_buzzer
    )


@pytest.mark.parametrize(
    "value,schema",
    [
        ({"enabled": "true"}, {"type": "object", "properties": {"enabled": {"type": "boolean"}}}),
        ({"unknown": 1}, {"type": "object", "properties": {}}),
        (True, {"type": "integer"}),
        (float("inf"), {"type": "number"}),
        ({}, {"type": "object", "required": ["type"]}),
    ],
)
def test_schema_validator_rejects_bad_input(value, schema):
    with pytest.raises(HTTPException):
        validate(value, schema)


def test_redaction_never_returns_credentials():
    assert sanitize(
        {
            "psk": "wifi",
            "nested": {"access_token": "secret", "enabled": True},
            "uri": "rtsps://admin:password@192.168.1.2:560/talk?token=secret",
        }
    ) == {"nested": {"enabled": True}, "uri": "rtsps://192.168.1.2:560/talk"}


@pytest.mark.asyncio
async def test_feature_routes_scope_and_real_camera_payload(app_fixture):
    app = app_fixture["app"]
    service = CameraFeaturesService(CameraSettingsService())
    camera = SimpleNamespace(request=AsyncMock(return_value=Success({})))

    async def respond(method, path, *args, **kwargs):
        if path == "/nuraeye/capabilities":
            return Success(CAPS.copy())
        if path == "/nuraeye/wifi":
            return Success({"ssid": "Office", "psk": "do-not-expose"})
        return Success({"applied": True})

    camera.request.side_effect = respond
    service.client = AsyncMock(return_value=camera)
    app.state.camera_features = service
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        viewer = {"Authorization": f"Bearer {app_fixture['viewer_token']}"}
        owner = {"Authorization": f"Bearer {app_fixture['owner_token']}"}
        operator = {"Authorization": f"Bearer {app_fixture['operator_token']}"}
        base = "/api/v1/cameras/CAM-SET-1/features"
        assert (
            await client.get("/api/v1/cameras/CAM-SET-2/features/network", headers=viewer)
        ).status_code == 403
        state = await client.get(base + "/network", headers=viewer)
        assert state.status_code == 200
        assert state.json()["values"]["getWifi"] == {"ssid": "Office"}
        assert (await client.post(base + "/actions/sessionLogin", headers=owner, json={})).status_code == 404
        assert (await client.post(base + "/actions/setWifi", headers=operator, json={})).status_code == 403
        assert (
            await client.post(
                base + "/actions/setEventPreferences",
                headers=viewer,
                json={"payload": {"PersonDetected": False}},
            )
        ).status_code == 403
        bad = await client.post(
            base + "/actions/setEventPreferences", headers=operator, json={"payload": {"Unknown": True}}
        )
        assert bad.status_code == 422
        saved = await client.post(
            base + "/actions/setEventPreferences",
            headers=operator,
            json={"payload": {"PersonDetected": False}},
        )
        assert saved.status_code == 200
        camera.request.assert_any_call(
            "POST", "/nuraeye/events/preferences", {"PersonDetected": False}, timeout=15
        )
        wifi = {"payload": {"ssid": "New office", "psk": "top-secret", "verify": True}}
        assert (await client.post(base + "/actions/setWifi", headers=owner, json=wifi)).status_code == 409
        wifi["confirmation"] = "CAM-SET-1"
        assert (await client.post(base + "/actions/setWifi", headers=owner, json=wifi)).status_code == 200
        camera.request.side_effect = None
        camera.request.return_value = Failure(
            FailureKind.UNAUTHORIZED, "Camera credentials rejected", http_status=401
        )
        assert (await client.get(base + "/privacy", headers=viewer)).status_code == 502
    async with app.state.session_factory() as db:
        records = (
            (await db.execute(select(AuditLog).where(AuditLog.action == "camera.api.setWifi")))
            .scalars()
            .all()
        )
        assert len(records) == 1
        assert "top-secret" not in str(records[0].details_json)


@pytest.mark.asyncio
async def test_masks_validate_before_writing_and_return_camera_tokens(app_fixture):
    app = app_fixture["app"]
    root = "/api/v1/cameras/CAM-SET-1/features/privacy/masks"
    payload = {
        "polygon": [
            {"x": -0.8, "y": 0.8},
            {"x": 0.2, "y": 0.8},
            {"x": 0.2, "y": -0.2},
            {"x": -0.8, "y": -0.2},
        ],
        "type": "Color",
    }
    with patch("vizenlink_nvr.api.v1.camera_features.OnvifMaskClient") as factory:
        camera = factory.return_value
        camera.options = AsyncMock(return_value=Success({"max_masks": 1, "types": ["Color"], "colors": []}))
        camera.masks = AsyncMock(return_value=Success([]))
        camera.save = AsyncMock(return_value=Success({"token": "CameraMask_42"}))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            operator = {"Authorization": f"Bearer {app_fixture['operator_token']}"}
            viewer = {"Authorization": f"Bearer {app_fixture['viewer_token']}"}
            assert (await client.post(root, headers=viewer, json=payload)).status_code == 403
            invalid = {**payload, "polygon": [{"x": 1.1, "y": 0}] * 4}
            assert (await client.post(root, headers=operator, json=invalid)).status_code == 422
            assert (
                await client.post(root, headers=operator, json={**payload, "type": "Blur"})
            ).status_code == 422
            camera.save.assert_not_awaited()
            result = await client.post(root, headers=operator, json=payload)
            assert result.json() == {"token": "CameraMask_42"}
            camera.masks.return_value = Success([{"token": "CameraMask_42"}])
            assert (await client.post(root, headers=operator, json=payload)).status_code == 422
            assert (await client.put(root + "/missing", headers=operator, json=payload)).status_code == 404


@pytest.mark.asyncio
async def test_snapshot_uses_digest_and_rejects_non_images(app_fixture):
    from vizenlink_nvr.camera.http import HttpResponse

    app = app_fixture["app"]
    service = CameraSettingsService(http=AsyncMock())
    app.state.camera_settings_service = service
    service.http.send.return_value = HttpResponse(200, [], b"\xff\xd8\xfftest-jpeg")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {app_fixture['viewer_token']}"}
        result = await client.get("/api/v1/cameras/CAM-SET-1/snapshot", headers=headers)
        assert result.status_code == 200
        assert result.headers["cache-control"] == "private, no-store"
        sent_headers = dict(service.http.send.call_args.kwargs["headers"])
        assert sent_headers["Authorization"].startswith('Digest username="admin"')
        service.http.send.return_value = HttpResponse(200, [], b"not a jpeg")
        assert (await client.get("/api/v1/cameras/CAM-SET-1/snapshot", headers=headers)).status_code == 502


@pytest.mark.asyncio
async def test_camera_vault_missing_is_not_replaced_with_a_fake_key(app_fixture):
    app = app_fixture["app"]
    del app.state.vault
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        result = await client.get(
            "/api/v1/cameras/CAM-SET-1/settings",
            headers={"Authorization": f"Bearer {app_fixture['owner_token']}"},
        )
        assert result.status_code == 503


def test_nvr_run_opens_camera_vault_in_the_selected_data_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("NVR_SECRETS_BACKEND", "file")
    data_dir = tmp_path / "recorder"
    recordings = tmp_path / "recordings"
    recordings.mkdir()

    async def check_api(app):
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
        ):
            assert app.state.runtime.settings.data_dir == data_dir
            assert app.state.runtime.vault is not None
            # `nvr run` starts the recorder (MediaMTX + recording loops) with the app.
            assert app.state.recorder is not None
            recorder_start.assert_awaited_once()
            setup = await client.post(
                "/api/v1/auth/setup",
                json={
                    "owner_username": "owner",
                    "owner_password": "Recorder-password-42!",
                    "timezone": "UTC",
                    "storage_path": str(recordings),
                    "allow_system_disk": True,
                },
            )
            assert setup.status_code == 200, setup.text
            assert (await client.get("/api/v1/cameras/MISSING/settings")).status_code == 404
        assert app.state.runtime is None

    def serve(app, **_kwargs):
        asyncio.run(check_api(app))

    monkeypatch.setattr("uvicorn.run", serve)
    # Keep the unit run hermetic: no real MediaMTX process, no global log handlers.
    recorder_start = AsyncMock()
    monkeypatch.setattr("vizenlink_nvr.services.recorder.RecorderSupervisor.start", recorder_start)
    monkeypatch.setattr("vizenlink_nvr.services.recorder.RecorderSupervisor.stop", AsyncMock())
    monkeypatch.setattr("vizenlink_nvr.log.configure_logging", lambda *a, **k: None)
    result = CliRunner().invoke(cli_app, ["run", "--no-mdns", "--data-dir", str(data_dir)])
    if result.exception:
        raise result.exception
    assert result.exit_code == 0, result.output


@pytest.mark.asyncio
async def test_sd_recording_range_playback_and_export_are_scoped_and_bounded(app_fixture):
    from vizenlink_nvr.api.v1.camera_recordings import CHUNK
    from vizenlink_nvr.camera.http import HttpResponse

    app = app_fixture["app"]
    service = CameraFeaturesService(CameraSettingsService())
    first, last = b"x" * CHUNK, b"tail"
    total = len(first) + len(last)
    camera = SimpleNamespace(request=AsyncMock(return_value=Success(CAPS)))

    async def chunk(clip_id, byte_range):
        if byte_range.startswith(f"bytes={CHUNK}-"):
            return HttpResponse(206, [("Content-Range", f"bytes {CHUNK}-{total - 1}/{total}")], last)
        return HttpResponse(206, [("Content-Range", f"bytes 0-{CHUNK - 1}/{total}")], first)

    camera.recording_chunk = AsyncMock(side_effect=chunk)
    service.client = AsyncMock(return_value=camera)
    app.state.camera_features = service
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {app_fixture['viewer_token']}"}
        root = "/api/v1/cameras/CAM-SET-1/sd-recordings/123/clip"
        assert (await client.get(root.replace("CAM-SET-1", "CAM-SET-2"), headers=headers)).status_code == 403
        result = await client.get(root, headers={**headers, "Range": f"bytes={CHUNK}-"})
        assert result.status_code == 206 and result.content == last
        assert result.headers["content-range"] == f"bytes {CHUNK}-{total - 1}/{total}"
        assert (await client.get(root, headers={**headers, "Range": "bytes=0-31"})).status_code == 502
        playback = await client.get(root, headers=headers)
        assert playback.status_code == 200 and playback.content == first + last
        assert playback.headers["content-length"] == str(total)
        assert "content-range" not in playback.headers
        assert "content-disposition" not in playback.headers
        export = await client.get(root + "?download=true", headers=headers)
        assert export.status_code == 200 and export.content == first + last
        assert export.headers["content-length"] == str(total)
        assert "attachment" in export.headers["content-disposition"]
        assert (await client.get(root, headers={**headers, "Range": "bytes=9-1"})).status_code == 416
        camera.recording_chunk.side_effect = None
        camera.recording_chunk.return_value = HttpResponse(404, [], b"")
        assert (await client.get(root, headers=headers)).status_code == 404
    async with app.state.session_factory() as db:
        exports = await db.scalars(select(AuditLog).where(AuditLog.action == "camera.recording.export"))
        assert len(exports.all()) == 1


@pytest.mark.asyncio
async def test_camera_accounts_require_owner_protect_admin_and_use_onvif(app_fixture):
    root = "/api/v1/cameras/CAM-SET-1/accounts"
    caps = {"multi_user": True, "max_users": 5, "user_roles": ["Operator", "User"]}
    users = (
        "<Response><User><Username>admin</Username><UserLevel>Administrator</UserLevel></User>"
        "<User><Username>bob</Username><UserLevel>User</UserLevel></User></Response>"
    )

    async def soap(*args, **kwargs):
        return Success(users if "GetUsers" in args[3] else "<Response/>")

    with (
        patch(
            "vizenlink_nvr.camera.nuraeye.client.NuraeyeClient.request",
            new=AsyncMock(return_value=Success(caps)),
        ),
        patch("vizenlink_nvr.api.v1.camera_accounts.post_soap", new=AsyncMock(side_effect=soap)) as wire,
        patch(
            "vizenlink_nvr.api.v1.camera_accounts.OnvifDeviceClient.set_user_password",
            new=AsyncMock(return_value=Success(None)),
        ) as password,
    ):
        app = app_fixture["app"]
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            owner = {"Authorization": f"Bearer {app_fixture['owner_token']}"}
            operator = {"Authorization": f"Bearer {app_fixture['operator_token']}"}
            assert (await client.get(root, headers=operator)).status_code == 403
            result = await client.get(root, headers=owner)
            assert result.status_code == 200 and result.json()["accounts"][0]["role"] == "Administrator"
            base = {"confirmation": "CAM-SET-1", "username": "bob"}
            assert (
                await client.post(root, headers=owner, json={**base, "action": "delete", "username": "admin"})
            ).status_code == 422
            assert (
                await client.post(
                    root, headers=owner, json={**base, "action": "role", "role": "Administrator"}
                )
            ).status_code == 422
            for action in ("create", "role", "password", "delete"):
                payload = {**base, "action": action, "username": "new-user" if action == "create" else "bob"}
                if action in ("create", "password"):
                    payload["password"] = "Camera-secret-42!"
                if action in ("create", "role"):
                    payload["role"] = "Operator"
                saved = await client.post(root, headers=owner, json=payload)
                assert saved.status_code == 200, saved.text
            assert password.await_count == 1
            requests = [c.args[3] for c in wire.call_args_list]
            assert any(
                "<tds:CreateUsers" in xml and "<tt:UserLevel>Operator</tt:UserLevel>" in xml
                for xml in requests
            )
            assert any(
                "<tds:DeleteUsers" in xml and "<tds:Username>bob</tds:Username>" in xml for xml in requests
            )
        async with app.state.session_factory() as db:
            entries = (
                (await db.execute(select(AuditLog).where(AuditLog.action.like("camera.account.%"))))
                .scalars()
                .all()
            )
            assert len(entries) == 4
            assert all("Camera-secret" not in str(entry.details_json) for entry in entries)
