from __future__ import annotations

import httpx
from starlette.requests import Request

from app.config import Settings
from app.deps import enforce_tool_quota
from app.main import create_app
from app.quota import NoQuotaRepo
from app.routers import health


def test_settings_from_env_self_hosted_and_openai_base_url(monkeypatch):
    monkeypatch.setenv("SELF_HOSTED", "true")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1/")
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    cfg = Settings.from_env()
    assert cfg.self_hosted is True
    assert cfg.openai_base_url == "http://localhost:11434/v1"


def test_settings_from_env_cors_defaults_open_when_self_hosted_and_unset(monkeypatch):
    monkeypatch.setenv("SELF_HOSTED", "true")
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    cfg = Settings.from_env()
    assert cfg.allowed_origins == ["*"]


def test_settings_from_env_cors_respects_explicit_value_when_self_hosted(monkeypatch):
    monkeypatch.setenv("SELF_HOSTED", "true")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:5000")
    cfg = Settings.from_env()
    assert cfg.allowed_origins == ["http://localhost:5000"]


def test_settings_from_env_cors_treats_blank_allowed_origins_as_unset_when_self_hosted(monkeypatch):
    monkeypatch.setenv("SELF_HOSTED", "true")
    monkeypatch.setenv("ALLOWED_ORIGINS", "   ")
    assert Settings.from_env().allowed_origins == ["*"]
    monkeypatch.setenv("ALLOWED_ORIGINS", "")
    assert Settings.from_env().allowed_origins == ["*"]


def test_settings_from_env_blank_allowed_origins_stays_empty_when_hosted(monkeypatch):
    monkeypatch.delenv("SELF_HOSTED", raising=False)
    monkeypatch.setenv("ALLOWED_ORIGINS", "")
    assert Settings.from_env().allowed_origins == []


def test_settings_from_env_not_self_hosted_by_default(monkeypatch):
    monkeypatch.delenv("SELF_HOSTED", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    cfg = Settings.from_env()
    assert cfg.self_hosted is False
    assert cfg.allowed_origins == ["http://localhost:4321", "http://localhost:4322"]


async def test_quota_never_raises_after_100_calls_when_self_hosted():
    app = create_app(Settings(self_hosted=True))
    assert isinstance(app.state.quota, NoQuotaRepo)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/tools/x",
        "query_string": b"",
        "headers": [],
        "client": ("1.2.3.4", 1234),
        "app": app,
    }
    request = Request(scope)
    for _ in range(100):
        await enforce_tool_quota(request, "tool_x")


async def test_subscribe_endpoints_disabled_when_self_hosted():
    app = create_app(Settings(self_hosted=True))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/subscribe", json={"email": "a@b.com"})
        assert r.status_code == 404
        assert r.json() == {"error": "disabled", "code": "disabled"}
        r = await c.get("/api/confirm", params={"e": "a@b.com", "t": "x"})
        assert r.status_code == 404
        assert r.json() == {"error": "disabled", "code": "disabled"}
        r = await c.get("/api/unsubscribe", params={"e": "a@b.com", "t": "x"})
        assert r.status_code == 404
        assert r.json() == {"error": "disabled", "code": "disabled"}
        r = await c.post("/api/tool-requests", json={"email": "a@b.com", "request": "please add another tool"})
        assert r.status_code == 404
        assert r.json() == {"error": "disabled", "code": "disabled"}
        r = await c.get("/openapi.json")
        assert r.status_code == 200
        paths = r.json()["paths"]
        assert not {"/api/subscribe", "/api/confirm", "/api/unsubscribe", "/api/tool-requests"} & set(paths)


async def test_health_carries_self_hosted_flag_only_when_enabled():
    self_hosted_app = create_app(Settings(self_hosted=True))
    hosted_app = create_app(Settings())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self_hosted_app), base_url="http://t") as c:
        r = await c.get("/api/health")
        assert r.json() == {"ok": True, "version": health.VERSION, "selfHosted": True}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=hosted_app), base_url="http://t") as c:
        r = await c.get("/api/health")
        assert r.json() == {"ok": True, "version": health.VERSION}


def test_docs_stay_open_when_self_hosted_even_in_prod():
    app = create_app(Settings(env="prod", self_hosted=True))
    assert app.docs_url == "/api/docs"


async def test_origin_verify_middleware_never_installed_when_self_hosted():
    app = create_app(Settings(env="prod", self_hosted=True, origin_verify_secret="s3cret", allowed_origins=["*"]))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/health")
        assert r.status_code == 200
        r = await c.get("/api/places/autocomplete", params={"q": "ab"})
        assert r.status_code != 403


async def test_review_response_without_llm_keys_returns_clean_upstream_error_not_500():
    app = create_app(Settings(self_hosted=True, allowed_origins=["*"]))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(
            "/api/tools/review-response",
            json={"businessName": "Test Biz", "reviewText": "Great service, thank you so much!", "rating": 5},
        )
        assert r.status_code == 503
        assert r.json() == {
            "error": "AI features are temporarily unavailable. Please try again later.",
            "code": "llm_not_configured",
        }
