from __future__ import annotations

import httpx

from app.services.notify import (
    NullMailer,
    Notifier,
    confirm_token,
    unsubscribe_token,
    unsubscribe_url,
    verify_confirm_token,
    verify_unsubscribe_token,
)


def _install(app, owner="owner@locan.ai", events=None):
    mailer = NullMailer()
    app.state.notifier = Notifier(mailer, owner, "https://locan.ai", events)
    return mailer


async def test_subscribe_stores_pending_sends_confirmation_and_alerts_owner(app, client):
    mailer = _install(app)
    r = await client.post("/api/subscribe", json={"email": "owner@example.com", "source": "home-hero"})
    assert r.status_code == 200 and r.json() == {"ok": True, "status": "pending"}
    assert app.state.subscribers.subscribers["owner@example.com"]["status"] == "pending"

    to = [m["to"] for m in mailer.sent]
    assert "owner@example.com" in to and "owner@locan.ai" in to
    confirm = next(m for m in mailer.sent if m["to"] == "owner@example.com")
    assert confirm["subject"].startswith("Confirm your email")
    assert "/api/confirm?email=owner%40example.com&token=" in confirm["text"]
    assert "/api/unsubscribe?email=owner%40example.com&token=" in confirm["text"]
    assert confirm["html"] and "Unsubscribe" in confirm["html"]
    alert = next(m for m in mailer.sent if m["to"] == "owner@locan.ai")
    assert alert["subject"].startswith("[locan] subscribe:")
    assert "status: pending" in alert["text"]


async def test_confirm_link_activates_and_confirmed_resubscribe_sends_nothing(app, client, cfg):
    mailer = _install(app)
    await client.post("/api/subscribe", json={"email": "a@example.com"})
    token = confirm_token(cfg.unsubscribe_secret, "a@example.com")

    r = await client.get("/api/confirm", params={"email": "a@example.com", "token": token})
    assert r.status_code == 302 and r.headers["location"] == "https://locan.ai/confirmed/?status=ok"
    sub = app.state.subscribers.subscribers["a@example.com"]
    assert sub["status"] == "active" and sub["confirmedAt"]
    assert any(m["subject"].startswith("[locan] confirm:") for m in mailer.sent)

    before = len([m for m in mailer.sent if m["to"] == "a@example.com"])
    r2 = await client.post("/api/subscribe", json={"email": "a@example.com"})
    assert r2.json()["status"] == "confirmed"
    assert len([m for m in mailer.sent if m["to"] == "a@example.com"]) == before
    assert app.state.subscribers.subscribers["a@example.com"]["status"] == "active"

    bad = await client.get("/api/confirm", params={"email": "a@example.com", "token": "0" * 32})
    assert bad.status_code == 302 and bad.headers["location"].endswith("status=invalid")


async def test_pending_resubscribe_resends_confirmation(app, client):
    mailer = _install(app)
    await client.post("/api/subscribe", json={"email": "b@example.com"})
    await client.post("/api/subscribe", json={"email": "b@example.com"})
    assert len([m for m in mailer.sent if m["to"] == "b@example.com"]) == 2


async def test_subscribe_rejects_invalid_email(client):
    r = await client.post("/api/subscribe", json={"email": "not-an-email"})
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"


def test_tokens_are_stable_purpose_bound_and_case_insensitive():
    t1 = unsubscribe_token("s", "Someone@Example.com")
    t2 = unsubscribe_token("s", "someone@example.com ")
    assert t1 == t2 and len(t1) == 32
    assert verify_unsubscribe_token("s", "someone@example.com", t1)
    assert not verify_unsubscribe_token("other", "someone@example.com", t1)
    assert not verify_unsubscribe_token("s", "someone@example.com", "nope")
    # a confirm token must not double as an unsubscribe token
    assert confirm_token("s", "someone@example.com") != t1
    assert not verify_confirm_token("s", "someone@example.com", t1)
    assert unsubscribe_url("https://api.locan.ai/api", "s", "Someone@Example.com").startswith(
        "https://api.locan.ai/api/unsubscribe?email=someone%40example.com&token="
    )


async def test_unsubscribe_redirects_and_flags_subscriber(app, client, cfg):
    mailer = _install(app)
    await client.post("/api/subscribe", json={"email": "bye@example.com"})
    token = unsubscribe_token(cfg.unsubscribe_secret, "bye@example.com")

    r = await client.get("/api/unsubscribe", params={"email": "bye@example.com", "token": token})
    assert r.status_code == 302
    assert r.headers["location"] == "https://locan.ai/unsubscribe/?status=ok"
    assert app.state.subscribers.subscribers["bye@example.com"]["status"] == "unsubscribed"
    assert any(m["subject"].startswith("[locan] unsubscribe:") for m in mailer.sent)

    bad = await client.get("/api/unsubscribe", params={"email": "bye@example.com", "token": "0" * 32})
    assert bad.status_code == 302 and bad.headers["location"].endswith("status=invalid")


async def test_tool_request_stores_subscribes_and_emails_both_sides(app, client):
    mailer = _install(app)
    body = {
        "email": "maker@example.com",
        "request": "A tool that checks if my opening hours match across Google, Apple Maps and Bing.",
        "business": "Smoke Test Bakery",
        "website": "https://smoketest.example",
        "source": "home",
    }
    r = await client.post("/api/tool-requests", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True and data["id"]

    store = app.state.subscribers
    assert store.requests[0]["request"].startswith("A tool that checks") and store.requests[0]["status"] == "new"
    assert store.subscribers["maker@example.com"]["source"] == "tool-request:home"
    assert store.subscribers["maker@example.com"]["status"] == "pending"

    confirmation = next(m for m in mailer.sent if m["to"] == "maker@example.com")
    assert "3 days" in confirmation["subject"]
    assert "opening hours" in confirmation["text"]
    assert "/api/confirm?" in confirmation["text"] and "/api/unsubscribe?" in confirmation["text"]
    owner = next(m for m in mailer.sent if m["to"] == "owner@locan.ai" and "tool_request" in m["subject"])
    assert "Smoke Test Bakery" in owner["text"] and "opening hours" in owner["text"]


async def test_tool_request_validation(client):
    r = await client.post("/api/tool-requests", json={"email": "maker@example.com", "request": "too short"})
    assert r.status_code == 422


async def test_owner_notified_on_tool_run(app, client, fake_llm):
    mailer = _install(app)
    fake_llm.json_responses.append({"responses": [{"tone": "x", "text": "Thanks!"}], "tips": []})
    r = await client.post(
        "/api/tools/review-response",
        json={"businessName": "Smoke Test Bakery", "reviewText": "Lovely place, great staff", "rating": 5},
    )
    assert r.status_code == 200
    run = next(m for m in mailer.sent if "tool_run" in m["subject"])
    assert "review-response" in run["subject"] and "Smoke Test Bakery" in run["text"]


async def test_notifier_filters_events_and_never_raises():
    class Boom:
        async def send(self, *a, **k):
            raise RuntimeError("ses down")

    n = Notifier(Boom(), "owner@locan.ai", "https://locan.ai", {"error"})
    await n.event("tool_run", "ignored", {})  # filtered, no send attempted
    await n.event("error", "boom", {"x": 1})  # send fails, swallowed


async def test_5xx_api_error_notifies_owner(app, client, places_mock):
    mailer = _install(app)
    places_mock.post("/v1/places:autocomplete").mock(return_value=httpx.Response(500, json={}))
    r = await client.get("/api/places/autocomplete", params={"q": "boom"})
    assert r.status_code == 502
    err = next(m for m in mailer.sent if m["subject"].startswith("[locan] error:"))
    assert "places_upstream" in err["subject"]
