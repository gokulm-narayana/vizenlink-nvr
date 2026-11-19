"""Integration tests for the authenticated /cam WHEP reverse proxy (D-14)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.engine import create_engine_for, upgrade_to_head
from vizenlink_nvr.db.models import Camera, UserCameraPermission
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
def test_db_app(tmp_path: Path):
    db_file = tmp_path / "test_cam_proxy.db"
    upgrade_to_head(db_file)
    engine = create_engine_for(db_file)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app(session_factory=session_factory)
    return app, session_factory


@pytest.mark.asyncio
async def test_cam_proxy_full_matrix(test_db_app: tuple[Any, Any], tmp_path: Path) -> None:
    app, session_factory = test_db_app
    transport = ASGITransport(app=app)

    storage_dir = tmp_path / "recordings"
    storage_dir.mkdir(parents=True, exist_ok=True)

    # 1. Setup owner
    async with AsyncClient(transport=transport, base_url="http://test") as owner_client:
        setup_payload = {
            "owner_username": "owner_admin",
            "owner_password": "securePassword123!",
            "timezone": "UTC",
            "storage_path": str(storage_dir),
            "allow_system_disk": True,
        }
        res = await owner_client.post("/api/v1/auth/setup", json=setup_payload)
        assert res.status_code == 200

        # 2. Add two cameras directly to DB
        now = utc_now()
        async with session_factory() as session:
            cam1 = Camera(
                serial="CAM1",
                host="192.168.1.101",
                https_port=443,
                mac="AA:BB:CC:11:22:33",
                name="Front Door",
                model="Model-X",
                manufacturer="Vizen",
                firmware_version="1.0",
                hardware_id="rev1",
                tls_fingerprint_sha256="11" * 32,
                added_at=now,
                host_updated_at=now,
            )
            cam2 = Camera(
                serial="CAM2",
                host="192.168.1.102",
                https_port=443,
                mac="AA:BB:CC:44:55:66",
                name="Back Yard",
                model="Model-Y",
                manufacturer="Vizen",
                firmware_version="1.0",
                hardware_id="rev2",
                tls_fingerprint_sha256="22" * 32,
                added_at=now,
                host_updated_at=now,
            )
            session.add_all([cam1, cam2])
            await session.commit()

        # 3. Create viewer user via owner client
        viewer_payload = {
            "username": "viewer_bob",
            "password": "viewerPassword123!",
            "role": "viewer",
        }
        res_user = await owner_client.post("/api/v1/users", json=viewer_payload)
        assert res_user.status_code == 201
        viewer_id = res_user.json()["id"]

        # Give viewer permission ONLY to CAM1
        async with session_factory() as session:
            perm = UserCameraPermission(
                user_id=viewer_id,
                camera_serial="CAM1",
                created_at=now,
            )
            session.add(perm)
            await session.commit()

        # Login viewer in a separate client
        async with AsyncClient(transport=transport, base_url="http://test") as viewer_client:
            res_login = await viewer_client.post(
                "/api/v1/auth/login",
                json={"username": "viewer_bob", "password": "viewerPassword123!"},
            )
            assert res_login.status_code == 200

            # Anonymous client
            async with AsyncClient(transport=transport, base_url="http://test") as anon_client:
                recorded_upstream: list[httpx.Request] = []

                def mock_handler(req: httpx.Request) -> httpx.Response:
                    recorded_upstream.append(req)
                    if req.method == "POST":
                        return httpx.Response(
                            201,
                            headers={
                                "content-type": "application/sdp",
                                "location": "/cam/cam1/sub/whep/sess-123",
                                "etag": '"sdp-etag-456"',
                                "accept-patch": "application/trickle-ice-sdpfrag",
                            },
                            content=b"v=0\r\no=- 123 2 IN IP4 127.0.0.1\r\ns=-\r\n",
                        )
                    if req.method == "PATCH":
                        return httpx.Response(204)
                    if req.method == "DELETE":
                        return httpx.Response(200)
                    return httpx.Response(400)

                app.state.cam_proxy_transport = httpx.MockTransport(mock_handler)
                app.state.mediamtx_webrtc_port = 8889

                sdp_offer = b"v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\n"

                # Case A: Owner POSTs WHEP offer with token and extra query param
                res_whep = await owner_client.post(
                    "/cam/CAM1/sub/whep?token=tokenABC&extra=ignored",
                    content=sdp_offer,
                    headers={"Content-Type": "application/sdp"},
                )
                assert res_whep.status_code == 201
                assert res_whep.headers["content-type"] == "application/sdp"
                assert res_whep.headers["location"] == "/cam/CAM1/sub/whep/sess-123"
                assert res_whep.headers["etag"] == '"sdp-etag-456"'
                assert res_whep.content == b"v=0\r\no=- 123 2 IN IP4 127.0.0.1\r\ns=-\r\n"

                assert len(recorded_upstream) == 1
                req0 = recorded_upstream[0]
                assert req0.method == "POST"
                assert str(req0.url) == "http://127.0.0.1:8889/cam/cam1/sub/whep?token=tokenABC"
                assert req0.headers["content-type"] == "application/sdp"
                assert "cookie" not in req0.headers
                assert "authorization" not in req0.headers
                assert req0.content == sdp_offer

                # Case B: Unauthenticated request -> 401, upstream untouched
                count_before = len(recorded_upstream)
                res_anon = await anon_client.post(
                    "/cam/CAM1/sub/whep?token=tokenABC",
                    content=sdp_offer,
                    headers={"Content-Type": "application/sdp"},
                )
                assert res_anon.status_code == 401
                assert len(recorded_upstream) == count_before

                # Case C: Viewer accessing CAM2 (forbidden) -> 403, upstream untouched
                res_viewer_cam2 = await viewer_client.post(
                    "/cam/CAM2/sub/whep?token=tokenABC",
                    content=sdp_offer,
                    headers={"Content-Type": "application/sdp"},
                )
                assert res_viewer_cam2.status_code == 403
                assert len(recorded_upstream) == count_before

                # Case D: Viewer accessing CAM1 (allowed) -> 201
                res_viewer_cam1 = await viewer_client.post(
                    "/cam/CAM1/sub/whep?token=tokenABC",
                    content=sdp_offer,
                    headers={"Content-Type": "application/sdp"},
                )
                assert res_viewer_cam1.status_code == 201
                assert len(recorded_upstream) == count_before + 1

                # Case E: Bad stream -> 422
                res_bad_stream = await owner_client.post(
                    "/cam/CAM1/badstream/whep",
                    content=sdp_offer,
                    headers={"Content-Type": "application/sdp"},
                )
                assert res_bad_stream.status_code in (404, 422)

                # Case F: Path traversal or invalid chars in serial -> 404 or 422
                for bad_serial in ("%2e%2e", "CAM..1", "CAM%2F1", "CAM$1"):
                    res_bad_serial = await owner_client.post(
                        f"/cam/{bad_serial}/sub/whep",
                        content=sdp_offer,
                        headers={"Content-Type": "application/sdp"},
                    )
                    assert res_bad_serial.status_code in (404, 422)

                # Case G: Bad session_id in PATCH / DELETE -> 404 or 422
                res_bad_sess = await owner_client.patch(
                    "/cam/CAM1/sub/whep/bad_session!id",
                    content=b"patch",
                    headers={"Content-Type": "application/trickle-ice-sdpfrag"},
                )
                assert res_bad_sess.status_code in (404, 422)

                # Case H: Body > 64 KiB rejected with 413
                # 1. Header Content-Length > 65536
                res_large_header = await owner_client.post(
                    "/cam/CAM1/sub/whep",
                    content=b"short",
                    headers={
                        "Content-Type": "application/sdp",
                        "Content-Length": "70000",
                    },
                )
                assert res_large_header.status_code == 413

                # 2. Actual body > 65536
                res_large_body = await owner_client.post(
                    "/cam/CAM1/sub/whep",
                    content=b"x" * 65537,
                    headers={"Content-Type": "application/sdp"},
                )
                assert res_large_body.status_code == 413

                # Case I: PATCH forwards If-Match and trickle ICE
                res_patch = await owner_client.patch(
                    "/cam/CAM1/sub/whep/sess-123",
                    content=b"candidate-frag",
                    headers={
                        "Content-Type": "application/trickle-ice-sdpfrag",
                        "If-Match": '"sdp-etag-456"',
                    },
                )
                assert res_patch.status_code == 204
                patch_req = recorded_upstream[-1]
                assert patch_req.method == "PATCH"
                assert str(patch_req.url) == "http://127.0.0.1:8889/cam/cam1/sub/whep/sess-123"
                assert patch_req.headers["if-match"] == '"sdp-etag-456"'
                assert patch_req.headers["content-type"] == "application/trickle-ice-sdpfrag"
                assert "cookie" not in patch_req.headers

                # Case J: DELETE forwards to upstream
                res_del = await owner_client.delete(
                    "/cam/CAM1/sub/whep/sess-123",
                )
                assert res_del.status_code == 200
                del_req = recorded_upstream[-1]
                assert del_req.method == "DELETE"
                assert str(del_req.url) == "http://127.0.0.1:8889/cam/cam1/sub/whep/sess-123"
                assert "cookie" not in del_req.headers

                # Case K: Upstream failure -> 502 {"detail": "Live video service unavailable"}
                def failing_handler(req: httpx.Request) -> httpx.Response:
                    raise httpx.ConnectError("Connection refused")

                app.state.cam_proxy_transport = httpx.MockTransport(failing_handler)
                res_fail = await owner_client.post(
                    "/cam/CAM1/sub/whep",
                    content=sdp_offer,
                    headers={"Content-Type": "application/sdp"},
                )
                assert res_fail.status_code == 502
                assert res_fail.json() == {"detail": "Live video service unavailable"}

                def timeout_handler(req: httpx.Request) -> httpx.Response:
                    raise httpx.ReadTimeout("Timeout")

                app.state.cam_proxy_transport = httpx.MockTransport(timeout_handler)
                res_timeout = await owner_client.post(
                    "/cam/CAM1/sub/whep",
                    content=sdp_offer,
                    headers={"Content-Type": "application/sdp"},
                )
                assert res_timeout.status_code == 502
                assert res_timeout.json() == {"detail": "Live video service unavailable"}


def test_cam_proxy_route_precedence(test_db_app: tuple[Any, Any]) -> None:
    """Assert that /cam routes are registered ahead of the SPA mount in app.routes."""
    app, _ = test_db_app
    spa_indices = [
        i
        for i, r in enumerate(app.routes)
        if getattr(r, "path", None) == "/" or getattr(r, "name", None) == "assets"
    ]
    assert spa_indices, "SPA mount not found in app.routes"
    spa_first_index = min(spa_indices)

    proxy_routes: list[str] = []
    proxy_indices: list[int] = []
    for i, r in enumerate(app.routes):
        if hasattr(r, "original_router") and hasattr(r.original_router, "routes"):
            for sub_r in r.original_router.routes:
                if getattr(sub_r, "path", "").startswith("/cam/"):
                    proxy_routes.append(sub_r.path)
                    proxy_indices.append(i)
        elif getattr(r, "path", "").startswith("/cam/"):
            proxy_routes.append(r.path)
            proxy_indices.append(i)

    assert "/cam/{serial}/{stream}/whep" in proxy_routes
    assert "/cam/{serial}/{stream}/whep/{session_id}" in proxy_routes
    assert all(idx < spa_first_index for idx in proxy_indices)


@pytest.mark.asyncio
async def test_cam_proxy_media_token_options_and_hls(test_db_app: tuple[Any, Any]) -> None:
    """Signed media tokens authorize WHEP POST/PATCH/DELETE, OPTIONS, and the HLS proxy."""
    from vizenlink_nvr.db.models import User
    from vizenlink_nvr.services.media_token import default_media_token_service

    app, session_factory = test_db_app
    now = utc_now()
    async with session_factory() as session:
        owner = User(
            username="media_owner",
            password_hash="not-needed-here",
            role="owner",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        cam = Camera(
            serial="CAM-HLS-1",
            host="192.168.1.120",
            https_port=443,
            mac="AA:BB:CC:DD:EE:11",
            name="Front HLS",
            model="Model-X",
            manufacturer="Vizen",
            firmware_version="1.0",
            hardware_id="rev1",
            tls_fingerprint_sha256="33" * 32,
            added_at=now,
            host_updated_at=now,
        )
        session.add_all([owner, cam])
        await session.commit()
        await session.refresh(owner)
        owner_id = owner.id

    tok = default_media_token_service.generate_token(
        user_id=owner_id, camera_serial="CAM-HLS-1", stream="sub"
    )
    wrong_stream_tok = default_media_token_service.generate_token(
        user_id=owner_id, camera_serial="CAM-HLS-1", stream="main"
    )

    upstream_calls: list[httpx.Request] = []

    def mock_handler(req: httpx.Request) -> httpx.Response:
        upstream_calls.append(req)
        if req.url.port == 8888:
            if req.url.path == "/cam/cam-hls-1/sub/index.m3u8" and b"cookieCheck" not in req.url.query:
                return httpx.Response(
                    302,
                    headers={"location": f"/cam/cam-hls-1/sub/index.m3u8?cookieCheck=1&token={tok}"},
                )
            return httpx.Response(
                200,
                headers={"content-type": "application/vnd.apple.mpegurl"},
                content=b"#EXTM3U\nvideo1_stream.m3u8\n",
            )
        if req.method == "OPTIONS":
            return httpx.Response(204, headers={"accept-post": "application/sdp"})
        if req.method == "POST":
            return httpx.Response(
                201,
                headers={
                    "content-type": "application/sdp",
                    "location": "/cam/cam-hls-1/sub/whep/sess-tok-1",
                },
                content=b"v=0\r\n",
            )
        if req.method == "PATCH":
            return httpx.Response(204)
        if req.method == "DELETE":
            return httpx.Response(200)
        return httpx.Response(404)

    app.state.cam_proxy_transport = httpx.MockTransport(mock_handler)
    app.state.mediamtx_webrtc_port = 8889
    app.state.mediamtx_hls_port = 8888

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. OPTIONS proxies cleanly instead of returning 404
        res_opt = await client.options(f"/cam/CAM-HLS-1/sub/whep?token={tok}")
        assert res_opt.status_code == 204
        assert res_opt.headers["accept-post"] == "application/sdp"

        # 2. Signed media token alone authorizes WHEP POST and keeps token on Location
        res_post = await client.post(
            f"/cam/CAM-HLS-1/sub/whep?token={tok}",
            content=b"v=0\r\n",
            headers={"Content-Type": "application/sdp"},
        )
        assert res_post.status_code == 201
        loc = res_post.headers["location"]
        assert loc == f"/cam/CAM-HLS-1/sub/whep/sess-tok-1?token={tok}"

        # 3. Follow-up PATCH and DELETE work using that Location without cookies/Bearer
        res_patch = await client.patch(
            loc,
            content=b"cand",
            headers={"Content-Type": "application/trickle-ice-sdpfrag"},
        )
        assert res_patch.status_code == 204
        res_del = await client.delete(loc)
        assert res_del.status_code == 200

        # 4. Authenticated HLS proxy handles 302 cookieCheck redirect and serves playlist
        res_hls = await client.get(f"/cam/CAM-HLS-1/sub/hls/{tok}/index.m3u8")
        assert res_hls.status_code == 200
        assert b"#EXTM3U" in res_hls.content

        # 5. HLS enforces token validity, stream match, and traversal safety
        assert (await client.get("/cam/CAM-HLS-1/sub/hls/invalid-tok/index.m3u8")).status_code == 401
        assert (await client.get(f"/cam/CAM-HLS-1/sub/hls/{wrong_stream_tok}/index.m3u8")).status_code == 403
        assert (await client.get(f"/cam/CAM-HLS-1/sub/hls/{tok}/..%2Fsecret")).status_code in (404, 422)