"""End-to-end integration test verifying FastAPI serves the built web bundle (09-01)."""

import re
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.engine import create_engine_for, upgrade_to_head

DIST_INDEX = (
    Path(__file__).resolve().parent.parent.parent / "src" / "vizenlink_nvr" / "web" / "dist" / "index.html"
)


@pytest.mark.skipif(not DIST_INDEX.exists(), reason="Web dist/index.html not built")
@pytest.mark.asyncio
async def test_fastapi_serves_web_bundle(tmp_path: Path) -> None:
    """Assert FastAPI correctly serves index.html, non-HTML assets, SPA fallbacks, and 404 JSON."""
    db_file = tmp_path / "test_web_bundle.db"
    upgrade_to_head(db_file)
    engine = create_engine_for(db_file)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    app = create_app(session_factory=session_factory)
    transport = ASGITransport(app=app)

    index_html_text = DIST_INDEX.read_text(encoding="utf-8")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. GET / returns 200 text/html containing root mount element
        res_root = await client.get("/")
        assert res_root.status_code == 200
        assert "text/html" in res_root.headers.get("content-type", "")
        assert 'id="root"' in res_root.text

        # 2. Every /assets/... URL referenced by index.html loads with non-HTML content type
        asset_urls = re.findall(r'(?:src|href)=["\'](/assets/[^"\']+)["\']', index_html_text)
        assert len(asset_urls) > 0, "No assets found referenced in index.html"

        for asset_url in asset_urls:
            res_asset = await client.get(asset_url)
            assert res_asset.status_code == 200, f"Failed to load asset {asset_url}"
            ct = res_asset.headers.get("content-type", "")
            assert "text/html" not in ct, f"Asset {asset_url} returned text/html instead of asset type"
            assert "javascript" in ct or "css" in ct or "octet-stream" in ct, (
                f"Unexpected content-type for {asset_url}: {ct}"
            )

        # 3. Deep link GET /playback?camera=x&t=1 returns 200 with index.html body (SPA fallback)
        res_deep = await client.get("/playback?camera=x&t=1")
        assert res_deep.status_code == 200
        assert "text/html" in res_deep.headers.get("content-type", "")
        assert 'id="root"' in res_deep.text
        assert res_deep.text == index_html_text

        # 4. GET /api/v1/does-not-exist returns 404 JSON, not HTML
        res_api_404 = await client.get("/api/v1/does-not-exist")
        assert res_api_404.status_code == 404
        assert "application/json" in res_api_404.headers.get("content-type", "")
        body = res_api_404.json()
        assert "detail" in body
