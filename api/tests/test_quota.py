from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.errors import QuotaExceeded
from app.main import create_app
from app.quota import MemoryQuotaRepo, enforce


async def test_enforce_per_ip_limit():
    repo = MemoryQuotaRepo()
    for _ in range(3):
        await enforce(repo, "tool_x", "1.2.3.4", limit_ip=3)
    with pytest.raises(QuotaExceeded):
        await enforce(repo, "tool_x", "1.2.3.4", limit_ip=3)
    # a different IP is unaffected
    await enforce(repo, "tool_x", "5.6.7.8", limit_ip=3)


async def test_enforce_global_limit():
    repo = MemoryQuotaRepo()
    await enforce(repo, "ac", "a", limit_ip=100, limit_global=2)
    await enforce(repo, "ac", "b", limit_ip=100, limit_global=2)
    with pytest.raises(QuotaExceeded):
        await enforce(repo, "ac", "c", limit_ip=100, limit_global=2)


async def test_enforce_units_consume_multiple():
    repo = MemoryQuotaRepo()
    await enforce(repo, "grid", "ip", limit_ip=3, units=3)
    with pytest.raises(QuotaExceeded):
        await enforce(repo, "grid", "ip", limit_ip=3, units=1)


async def test_autocomplete_returns_429_after_limit(places_mock):
    cfg = Settings(
        env="test",
        google_places_api_key="k",
        allowed_origins=["http://testserver"],
        quota_limits={"autocomplete_ip": 1, "details_ip": 1, "tool_ip": 1, "tools_global": 10, "autocomplete_global": 10},
    )
    app = create_app(cfg)
    places_mock.post("/v1/places:autocomplete").mock(return_value=httpx.Response(200, json={"suggestions": []}))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        ok = await c.get("/api/places/autocomplete", params={"q": "ab"}, headers={"x-forwarded-for": "9.9.9.9, 10.0.0.1"})
        assert ok.status_code == 200
        blocked = await c.get("/api/places/autocomplete", params={"q": "ab"}, headers={"x-forwarded-for": "9.9.9.9, 10.0.0.1"})
        assert blocked.status_code == 429
        assert blocked.json()["code"] == "quota_exceeded"
        other = await c.get("/api/places/autocomplete", params={"q": "ab"}, headers={"x-forwarded-for": "8.8.8.8"})
        assert other.status_code == 200


async def test_origin_verify_header_required_when_configured():
    cfg = Settings(env="prod", allowed_origins=["https://locan.ai"], origin_verify_secret="s3cret")
    app = create_app(cfg)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/api/health")).status_code == 200
        assert (await c.get("/api/places/autocomplete", params={"q": "ab"})).status_code == 403
        r = await c.get("/api/places/autocomplete", params={"q": "ab"}, headers={"x-origin-verify": "s3cret"})
        assert r.status_code != 403
