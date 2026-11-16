"""Search and assistant must respect the same camera grants as video playback."""

import json
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.models import Base, Camera, Event, GalleryItem, Segment, User, UserCameraPermission
from vizenlink_nvr.services.session_manager import SessionManager
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
async def recorder(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'search.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app(session_factory=sessions)
    now = utc_now()
    tokens = {}
    async with sessions() as db:
        for serial, name, state in [("A", "Front Gate", "active"), ("B", "Private Office", "unreachable")]:
            db.add(
                Camera(
                    serial=serial,
                    name=name,
                    location="Ground floor",
                    host="127.0.0.1",
                    tls_fingerprint_sha256="",
                    state=state,
                    added_at=now,
                    host_updated_at=now,
                )
            )
            db.add(Event(camera_serial=serial, event_type="person", start_time=now))
            db.add(
                Segment(
                    camera_serial=serial,
                    stream_type="main" if serial == "A" else "sub",
                    start_time=now - timedelta(minutes=1),
                    end_time=now + timedelta(minutes=1),
                    duration_seconds=120,
                    file_path=f"{serial}.mp4",
                    status="active",
                )
            )
            db.add(
                GalleryItem(
                    camera_serial=serial,
                    item_type="snapshot",
                    title=f"{name} snapshot",
                    file_path=f"{serial}.jpg",
                    file_size_bytes=10,
                    captured_at=now,
                )
            )
        db.add(Event(camera_serial="A", event_type="vehicle", start_time=now, hidden_at=now))
        db.add(
            Segment(
                camera_serial="A",
                start_time=now,
                end_time=now + timedelta(minutes=1),
                duration_seconds=60,
                file_path="missing.mp4",
                status="missing",
            )
        )
        for name, role in [("owner", "owner"), ("viewer", "viewer"), ("no_access", "viewer")]:
            user = User(username=name, role=role, password_hash="not-used-for-session-tests", updated_at=now)
            if name == "viewer":
                user.permissions.append(UserCameraPermission(camera_serial="A"))
            db.add(user)
            await db.flush()
            tokens[name] = (await SessionManager.create_session(db, user.id, "127.0.0.1", "test")).id
        await db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, tokens, now
    await engine.dispose()


def auth(tokens, role="viewer"):
    return {"Authorization": f"Bearer {tokens[role]}"}


@pytest.mark.parametrize("kind", ["events", "recordings", "snapshots"])
async def test_search_camera_scope_and_pagination(recorder, kind):
    client, tokens, _ = recorder
    res = await client.get(f"/api/v1/search?kind={kind}", headers=auth(tokens))
    assert res.status_code == 200
    assert res.json()["total"] == 1
    assert {i["camera_serial"] for i in res.json()["items"]} == {"A"}
    assert "Private Office" not in res.text
    denied = await client.get(f"/api/v1/search?kind={kind}&camera_serial=B", headers=auth(tokens))
    assert denied.status_code == 403
    empty = await client.get(f"/api/v1/search?kind={kind}", headers=auth(tokens, "no_access"))
    assert empty.json()["total"] == 0
    page = await client.get(f"/api/v1/search?kind={kind}&limit=1&offset=1", headers=auth(tokens, "owner"))
    assert page.json()["total"] == 2
    assert len(page.json()["items"]) == 1


async def test_search_overlap_hidden_events_and_literal_query(recorder):
    client, tokens, now = recorder
    overlap = await client.get(
        "/api/v1/search",
        headers=auth(tokens),
        params={
            "kind": "recordings",
            "start_time": now.isoformat(),
            "end_time": (now + timedelta(seconds=10)).isoformat(),
            "event_type": "person",
        },
    )
    assert overlap.status_code == 200
    assert overlap.json()["total"] == 1
    outside_event_window = await client.get(
        "/api/v1/search",
        headers=auth(tokens),
        params={
            "kind": "recordings",
            "start_time": (now + timedelta(seconds=1)).isoformat(),
            "event_type": "person",
        },
    )
    assert outside_event_window.json()["total"] == 0
    for kind in ("events", "recordings"):
        hidden = await client.get(f"/api/v1/search?kind={kind}&event_type=vehicle", headers=auth(tokens))
        assert hidden.json()["total"] == 0
    named = await client.get("/api/v1/search?q=front", headers=auth(tokens))
    assert named.json()["total"] == 1
    literal = await client.get("/api/v1/search?q=%25", headers=auth(tokens))
    assert literal.json()["total"] == 0
    invalid = await client.get(
        "/api/v1/search",
        headers=auth(tokens),
        params={
            "start_time": now.isoformat(),
            "end_time": (now - timedelta(seconds=1)).isoformat(),
        },
    )
    assert invalid.status_code == 422


async def test_search_combines_camera_filters_without_bypassing_grants(recorder):
    client, tokens, _ = recorder
    params = [("camera_serials", "A"), ("camera_serials", "B"), ("camera_serials", "A")]
    result = await client.get("/api/v1/search", headers=auth(tokens, "owner"), params=params)
    assert result.status_code == 200
    assert result.json()["total"] == 2
    links = {item["camera_serial"]: item["href"] for item in result.json()["items"]}
    assert links["A"].startswith("/playback?camera=A&")
    assert links["B"].startswith("/events/")
    denied = await client.get("/api/v1/search", headers=auth(tokens), params=params)
    assert denied.status_code == 403


async def test_search_and_assistant_require_login(recorder):
    client, _, _ = recorder
    assert (await client.get("/api/v1/search")).status_code == 401
    assert (await client.get("/api/v1/assistant/status")).status_code == 401
    assert (await client.post("/api/v1/assistant/chat", json={"message": "camera status"})).status_code == 401


async def test_assistant_scopes_summary_and_never_treats_policy_as_recording(recorder):
    client, tokens, _ = recorder
    res = await client.post("/api/v1/assistant/chat", headers=auth(tokens), json={"message": "camera status"})
    assert res.status_code == 200
    assert "1 cameras added" in res.json()["message"]
    assert "Private Office" not in res.text
    res = await client.post(
        "/api/v1/assistant/chat", headers=auth(tokens), json={"message": "show Private Office"}
    )
    assert all("camera=B" not in a["href"] for a in res.json()["actions"])
    res = await client.post(
        "/api/v1/assistant/chat", headers=auth(tokens), json={"message": "reboot Front Gate"}
    )
    assert "don't change settings" in res.json()["message"]
    assert res.json()["mode"] == "recorder"


async def test_assistant_searches_dates_and_camera_without_false_vehicle_match(recorder):
    client, tokens, _ = recorder
    res = await client.post(
        "/api/v1/assistant/chat",
        headers=auth(tokens),
        json={
            "message": "Find person events at Front Gate today",
        },
    )
    params = parse_qs(urlparse(res.json()["actions"][0]["href"]).query)
    assert params == {"event_type": ["person"], "camera": ["A"], "range": ["today"]}
    res = await client.post(
        "/api/v1/assistant/chat", headers=auth(tokens), json={"message": "find camera Front Gate"}
    )
    assert "event_type=vehicle" not in res.text


async def test_model_is_optional_and_failures_are_explicit(recorder, monkeypatch):
    client, tokens, _ = recorder
    monkeypatch.delenv("NVR_ASSISTANT_MODEL", raising=False)
    assert (await client.get("/api/v1/assistant/status", headers=auth(tokens))).json()[
        "model_configured"
    ] is False
    res = await client.post(
        "/api/v1/assistant/chat",
        headers=auth(tokens),
        json={
            "message": "camera status",
            "use_model": True,
        },
    )
    assert res.status_code == 503


async def test_model_only_receives_scoped_credential_free_context(recorder, monkeypatch):
    client, tokens, _ = recorder
    monkeypatch.setenv("NVR_ASSISTANT_MODEL", "test-model")
    captured = []

    async def fake_post(self, url, **kwargs):
        captured.append(kwargs["json"])
        return httpx.Response(
            200,
            json={"message": {"content": "Your accessible camera is reachable."}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("vizenlink_nvr.api.v1.assistant.httpx.AsyncClient.post", fake_post)
    # The patch is for the model client; send the API call with request() directly.
    res = await client.request(
        "POST",
        "/api/v1/assistant/chat",
        headers=auth(tokens),
        json={
            "message": "camera status",
            "use_model": True,
        },
    )
    assert res.status_code == 200
    assert res.json()["mode"] == "ollama"
    context = captured[0]["messages"][0]["content"]
    assert "Front Gate" in context
    assert "Private Office" not in context
    assert "tls_fingerprint" not in context
    assert "rtsp" not in context
    assert "not-used-for-session-tests" not in context


async def test_model_selection_is_owner_only_and_persists(recorder, monkeypatch):
    client, tokens, _ = recorder
    monkeypatch.delenv("NVR_ASSISTANT_MODEL", raising=False)

    async def tags(self, url, **kwargs):
        return httpx.Response(
            200, json={"models": [{"name": "local-test:2b"}]}, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr("vizenlink_nvr.api.v1.assistant.httpx.AsyncClient.get", tags)
    for path in ("/api/v1/assistant/models", "/api/v1/assistant/model"):
        method = "GET" if path.endswith("models") else "PUT"
        res = await client.request(
            method,
            path,
            headers=auth(tokens),
            **({"json": {"model": "local-test:2b"}} if method == "PUT" else {}),
        )
        assert res.status_code == 403
    res = await client.request("GET", "/api/v1/assistant/models", headers=auth(tokens, "owner"))
    assert res.json()["models"] == ["local-test:2b"]
    invalid = await client.put(
        "/api/v1/assistant/model", headers=auth(tokens, "owner"), json={"model": "not-installed"}
    )
    assert invalid.status_code == 422
    selected = await client.put(
        "/api/v1/assistant/model", headers=auth(tokens, "owner"), json={"model": "local-test:2b"}
    )
    assert selected.status_code == 200
    assert selected.json()["model"] == "local-test:2b"
    status = await client.request("GET", "/api/v1/assistant/status", headers=auth(tokens))
    assert status.json()["model_configured"] is True
    disconnected = await client.put(
        "/api/v1/assistant/model", headers=auth(tokens, "owner"), json={"model": None}
    )
    assert disconnected.json()["model_configured"] is False


async def test_host_managed_model_cannot_be_overridden(recorder, monkeypatch):
    client, tokens, _ = recorder
    monkeypatch.setenv("NVR_ASSISTANT_MODEL", "host-selected")
    result = await client.put("/api/v1/assistant/model", headers=auth(tokens, "owner"), json={"model": None})
    assert result.status_code == 409


async def test_gemini_provider_autodetect_and_header_auth(recorder, monkeypatch):
    client, tokens, _ = recorder
    monkeypatch.delenv("NVR_ASSISTANT_MODEL", raising=False)
    captured_gets = []
    captured_posts = []

    async def fake_get(self, url, **kwargs):
        captured_gets.append((str(url), kwargs))
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/gemini-2.5-flash",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/gemini-3.5-flash-lite",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/gemini-3.5-flash-lite-tts",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/gemini-3.1-flash-lite",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                ]
            },
            request=httpx.Request("GET", url),
        )

    async def fake_post(self, url, **kwargs):
        captured_posts.append((str(url), kwargs))
        target = str(url)
        if "gemini-2.5-flash" in target:
            return httpx.Response(
                404,
                json={"error": {"message": "models/gemini-2.5-flash is no longer available to new users."}},
                request=httpx.Request("POST", url),
            )
        first_text = kwargs["json"]["contents"][0]["parts"][0]["text"]
        if "gemini-3.5-flash-lite" in target and first_text == "Reply OK":
            return httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": "OK"}]}, "finishReason": "STOP"}]},
                request=httpx.Request("POST", url),
            )
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "internal thought", "thought": True},
                                {"text": "Front Gate camera is active."},
                            ]
                        },
                        "finishReason": "STOP",
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("vizenlink_nvr.api.v1.assistant.httpx.AsyncClient.get", fake_get)
    monkeypatch.setattr("vizenlink_nvr.api.v1.assistant.httpx.AsyncClient.post", fake_post)

    saved = await client.request(
        "PUT",
        "/api/v1/assistant/provider",
        headers=auth(tokens, "owner"),
        json={"provider": "gemini", "api_key": "secret-gemini-test-key-1234567890"},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["active_provider"] == "gemini"
    assert body["model"] == "gemini-3.5-flash-lite"
    gemini_summary = next(p for p in body["providers"] if p["id"] == "gemini")
    assert gemini_summary["selected_model"] == "gemini-3.5-flash-lite"
    assert "gemini-3.5-flash-lite-tts" not in gemini_summary["models"]
    assert captured_gets[0][1]["headers"]["x-goog-api-key"] == "secret-gemini-test-key-1234567890"

    chat_res = await client.request(
        "POST",
        "/api/v1/assistant/chat",
        headers=auth(tokens),
        json={"message": "camera status", "use_model": True},
    )
    assert chat_res.status_code == 200
    assert chat_res.json()["message"] == "Front Gate camera is active."
    assert chat_res.json()["mode"] == "gemini"
    chat_url, chat_kwargs = captured_posts[-1]
    assert "gemini-3.5-flash-lite:generateContent" in chat_url
    assert chat_kwargs.get("params") is None
    assert chat_kwargs["headers"]["x-goog-api-key"] == "secret-gemini-test-key-1234567890"
    assert chat_kwargs["json"]["generationConfig"]["maxOutputTokens"] == 1024


async def test_provider_detect_skips_retired_models_and_rejects_bad_keys(recorder, monkeypatch):
    client, tokens, _ = recorder
    monkeypatch.delenv("NVR_ASSISTANT_MODEL", raising=False)

    denied = await client.request(
        "POST",
        "/api/v1/assistant/provider/detect",
        headers=auth(tokens, "viewer"),
        json={"provider": "gemini", "api_key": "secret-gemini-test-key-1234567890"},
    )
    assert denied.status_code == 403

    async def bad_key_get(self, url, **kwargs):
        return httpx.Response(
            400,
            json={"error": {"message": "API key not valid. Please pass a valid API key."}},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr("vizenlink_nvr.api.v1.assistant.httpx.AsyncClient.get", bad_key_get)
    rejected = await client.request(
        "POST",
        "/api/v1/assistant/provider/detect",
        headers=auth(tokens, "owner"),
        json={"provider": "gemini", "api_key": "bad-secret-value-1234567890"},
    )
    assert rejected.status_code == 422
    assert "rejected this API key" in rejected.json()["detail"]
    assert "bad-secret-value" not in rejected.text

    async def mixed_get(self, url, **kwargs):
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/gemini-3.5-flash-lite",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/gemini-3.1-flash-lite",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                ]
            },
            request=httpx.Request("GET", url),
        )

    async def mixed_post(self, url, **kwargs):
        if "gemini-3.5-flash-lite" in str(url):
            return httpx.Response(
                404, json={"error": {"message": "Not found"}}, request=httpx.Request("POST", url)
            )
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "OK"}]}, "finishReason": "STOP"}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("vizenlink_nvr.api.v1.assistant.httpx.AsyncClient.get", mixed_get)
    monkeypatch.setattr("vizenlink_nvr.api.v1.assistant.httpx.AsyncClient.post", mixed_post)
    detected = await client.request(
        "POST",
        "/api/v1/assistant/provider/detect",
        headers=auth(tokens, "owner"),
        json={"provider": "gemini", "api_key": "secret-gemini-test-key-1234567890"},
    )
    assert detected.status_code == 200
    assert detected.json()["recommended_model"] == "gemini-3.1-flash-lite"
    assert "gemini-3.5-flash-lite" not in detected.json()["models"]


async def test_deprecated_saved_model_self_heals_and_surfaces_safe_errors(recorder, data_dir, monkeypatch):
    client, tokens, _ = recorder
    monkeypatch.delenv("NVR_ASSISTANT_MODEL", raising=False)
    secret = "ultra-secret-gemini-key-99999"
    (data_dir / "assistant-providers.json").write_text(
        json.dumps(
            {
                "active_provider": "gemini",
                "providers": {"gemini": {"model": "gemini-2.5-flash", "api_key": secret}},
            }
        )
    )

    status = await client.get("/api/v1/assistant/status", headers=auth(tokens))
    assert status.status_code == 200
    assert status.json()["model"] == "gemini-3.5-flash-lite"

    async def fake_get(self, url, **kwargs):
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/gemini-3.5-flash-lite",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/gemini-3.1-flash-lite",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                ]
            },
            request=httpx.Request("GET", url),
        )

    async def quota_post(self, url, **kwargs):
        return httpx.Response(
            429,
            json={"error": {"message": f"Quota exceeded for key {secret}"}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("vizenlink_nvr.api.v1.assistant.httpx.AsyncClient.get", fake_get)
    monkeypatch.setattr("vizenlink_nvr.api.v1.assistant.httpx.AsyncClient.post", quota_post)
    quota_res = await client.request(
        "POST",
        "/api/v1/assistant/chat",
        headers=auth(tokens),
        json={"message": "hi", "use_model": True},
    )
    assert quota_res.status_code == 503
    assert "quota or rate limit exceeded" in quota_res.json()["detail"].lower()
    assert secret not in quota_res.text

    async def heal_post(self, url, **kwargs):
        if "gemini-3.5-flash-lite" in str(url):
            return httpx.Response(
                404, json={"error": {"message": "Not found"}}, request=httpx.Request("POST", url)
            )
        if kwargs["json"]["contents"][0]["parts"][0]["text"] == "Reply OK":
            return httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": "OK"}]}, "finishReason": "STOP"}]},
                request=httpx.Request("POST", url),
            )
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "Recovered on 3.1 flash lite."}]} }]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("vizenlink_nvr.api.v1.assistant.httpx.AsyncClient.post", heal_post)
    healed = await client.request(
        "POST",
        "/api/v1/assistant/chat",
        headers=auth(tokens),
        json={"message": "hi", "use_model": True},
    )
    assert healed.status_code == 200
    assert healed.json()["message"] == "Recovered on 3.1 flash lite."
    saved_after = json.loads((data_dir / "assistant-providers.json").read_text())
    assert saved_after["providers"]["gemini"]["model"] == "gemini-3.1-flash-lite"


async def test_real_camera_snapshot_and_recording_mode_in_recorder_mode(recorder):
    client, tokens, _ = recorder

    snap = await client.post(
        "/api/v1/assistant/chat",
        headers=auth(tokens),
        json={"message": "can u show me the snapshot of the Front Gate camera"},
    )
    assert snap.status_code == 200
    snap_body = snap.json()
    assert snap_body["mode"] == "tool"
    assert snap_body["tool_results"][0]["tool_name"] == "get_camera_snapshot"
    assert snap_body["tool_results"][0]["camera_serial"] == "A"
    assert "/api/v1/cameras/A/snapshot" in snap_body["tool_results"][0]["snapshot_url"]

    denied = await client.post(
        "/api/v1/assistant/chat",
        headers=auth(tokens, "viewer"),
        json={"message": "set Front Gate recording to event"},
    )
    assert denied.status_code == 200
    assert "only operators or the nvr owner" in denied.json()["message"].lower()
    assert denied.json()["tool_results"] == []

    updated = await client.post(
        "/api/v1/assistant/chat",
        headers=auth(tokens, "owner"),
        json={"message": "set Front Gate recording to scheduled"},
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["mode"] == "tool"
    assert updated_body["tool_results"][0]["tool_name"] == "set_recording_mode"
    assert "scheduled" in updated_body["message"]

    rec_status = await client.get("/api/v1/recording/status", headers=auth(tokens, "owner"))
    modes = {item["camera_serial"]: item["mode"] for item in rec_status.json()}
    assert modes["A"] == "scheduled"


async def test_gemini_function_calling_executes_tools_and_preserves_thought_signature(
    recorder, data_dir, monkeypatch
):
    client, tokens, _ = recorder
    monkeypatch.delenv("NVR_ASSISTANT_MODEL", raising=False)
    (data_dir / "assistant-providers.json").write_text(
        json.dumps(
            {
                "active_provider": "gemini",
                "providers": {
                    "gemini": {"model": "gemini-3.5-flash-lite", "api_key": "secret-gemini-tool-key"}
                },
            }
        )
    )

    recorded_requests = []

    async def tool_calling_post(self, url, **kwargs):
        payload = kwargs["json"]
        recorded_requests.append(payload)
        contents = payload["contents"]
        if len(contents) == 1:
            assert "tools" in payload
            decl_names = {d["name"] for d in payload["tools"][0]["functionDeclarations"]}
            assert {"get_camera_snapshot", "set_recording_mode", "set_camera_night_mode"} <= decl_names
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "role": "model",
                                "parts": [
                                    {"text": "calling tools", "thought": True},
                                    {
                                        "functionCall": {
                                            "name": "set_recording_mode",
                                            "args": {"camera": "Front Gate", "mode": "event"},
                                        },
                                        "thoughtSignature": "sig-abc-123",
                                    },
                                    {
                                        "functionCall": {
                                            "name": "get_camera_snapshot",
                                            "args": {"camera": "Front Gate"},
                                        }
                                    },
                                ],
                            },
                            "finishReason": "STOP",
                        }
                    ]
                },
                request=httpx.Request("POST", url),
            )
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        "Updated **Front Gate** to event recording and "
                                        "attached its live snapshot."
                                    )
                                }
                            ]
                        },
                        "finishReason": "STOP",
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("vizenlink_nvr.api.v1.assistant.httpx.AsyncClient.post", tool_calling_post)

    owner_res = await client.request(
        "POST",
        "/api/v1/assistant/chat",
        headers=auth(tokens, "owner"),
        json={"message": "switch Front Gate to event recording and show snapshot", "use_model": True},
    )
    assert owner_res.status_code == 200
    body = owner_res.json()
    assert body["mode"] == "gemini"
    assert len(body["tool_results"]) == 2
    assert body["tool_results"][0]["tool_name"] == "set_recording_mode"
    assert body["tool_results"][1]["tool_name"] == "get_camera_snapshot"
    assert "/api/v1/cameras/A/snapshot" in body["tool_results"][1]["snapshot_url"]

    turn2 = recorded_requests[1]
    assert turn2["contents"][1]["parts"][1]["thoughtSignature"] == "sig-abc-123"
    fn_responses = {
        p["functionResponse"]["name"]: p["functionResponse"]["response"]
        for p in turn2["contents"][2]["parts"]
    }
    assert fn_responses["set_recording_mode"]["ok"] is True
    assert fn_responses["set_recording_mode"]["recording_mode"] == "event"
    assert fn_responses["get_camera_snapshot"]["ok"] is True

    recorded_requests.clear()
    viewer_res = await client.request(
        "POST",
        "/api/v1/assistant/chat",
        headers=auth(tokens, "viewer"),
        json={"message": "switch Front Gate to event recording", "use_model": True},
    )
    assert viewer_res.status_code == 200
    viewer_turn2 = recorded_requests[1]
    viewer_fn_responses = {
        p["functionResponse"]["name"]: p["functionResponse"]["response"]
        for p in viewer_turn2["contents"][2]["parts"]
    }
    assert viewer_fn_responses["set_recording_mode"]["ok"] is False
    assert "only operators or the nvr owner" in viewer_fn_responses["set_recording_mode"]["error"].lower()


async def test_duplicate_camera_names_disambiguate_by_location():
    from vizenlink_nvr.api.v1.assistant import _match_cameras

    cam1 = Camera(serial="VL01", name="Vizenlink Camera", location="floor 1", host="127.0.0.1")
    cam2 = Camera(serial="VL02", name="Vizenlink Camera", location=None, host="127.0.0.2")
    assert [c.serial for c in _match_cameras("snapshot of the floor 1 camera", [cam1, cam2])] == ["VL01"]
    assert [c.serial for c in _match_cameras("vizenlink camera (floor 1)", [cam1, cam2])] == ["VL01"]
