from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.main import create_app

URL = "/api/tools/review-response"
REVIEW = "We had booked a table for 7pm, waited 40 minutes and the soup arrived cold."
SIGN_OFF = "— Maria, Owner"

BASE = {"businessName": "Rūta's Kitchen", "reviewText": REVIEW, "rating": 2}

LABELS = ["Professional", "Professional · short", "Professional · with CTA"]


def _llm_payload(n: int = 3, tips: int = 4) -> dict:
    return {
        "responses": [{"tone": LABELS[i % 3], "text": f"Reply variant {i + 1} about the cold soup."} for i in range(n)],
        "tips": [f"Tip {i + 1}" for i in range(tips)],
    }


# --- validation -------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({**BASE, "rating": 0}, "rating"),
        ({**BASE, "rating": 6}, "rating"),
        ({**BASE, "reviewText": "bad"}, "reviewText"),
        ({k: v for k, v in BASE.items() if k != "businessName"}, "businessName"),
        ({**BASE, "businessName": "   "}, "businessName"),
        ({**BASE, "tone": "angry"}, "tone"),
    ],
    ids=["rating-0", "rating-6", "review-too-short", "missing-business-name", "blank-business-name", "unknown-tone"],
)
async def test_validation_errors(client, fake_llm, body, field):
    r = await client.post(URL, json=body)

    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"
    assert field in r.json()["error"]
    assert fake_llm.calls == []


# --- happy path -------------------------------------------------------------


async def test_generates_three_replies_and_tips(client, fake_llm):
    fake_llm.json_responses.append(_llm_payload())

    r = await client.post(URL, json={**BASE, "reviewerName": "Jonas", "businessType": "Restaurant"})

    assert r.status_code == 200
    d = r.json()
    assert [x["tone"] for x in d["responses"]] == LABELS
    assert [x["text"] for x in d["responses"]] == [f"Reply variant {i} about the cold soup." for i in (1, 2, 3)]
    assert d["tips"] == ["Tip 1", "Tip 2", "Tip 3", "Tip 4"]

    assert len(fake_llm.calls) == 1
    messages = fake_llm.calls[0]["messages"]
    assert messages[0]["role"] == "system" and "never invent" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    user = messages[1]["content"]
    assert REVIEW in user
    assert "Rating: 2" in user
    assert "Business name: Rūta's Kitchen" in user
    assert "Business type: Restaurant" in user
    assert "Reviewer name: Jonas" in user
    assert "Requested tone: professional" in user
    assert "Reply language: auto" in user


async def test_sign_off_appended_once(client, fake_llm):
    fake_llm.json_responses.append(
        {
            "responses": [
                {"tone": "Friendly", "text": "Thanks so much for coming in!"},
                {"tone": "Friendly · short", "text": f"Thanks for visiting!\n\n{SIGN_OFF}"},
                {"tone": "Friendly · with CTA", "text": "Thanks! Book again soon.   "},
            ],
            "tips": [],
        }
    )

    r = await client.post(URL, json={**BASE, "rating": 5, "tone": "friendly", "signOff": SIGN_OFF})

    assert r.status_code == 200
    texts = [x["text"] for x in r.json()["responses"]]
    assert texts == [
        f"Thanks so much for coming in!\n\n{SIGN_OFF}",
        f"Thanks for visiting!\n\n{SIGN_OFF}",
        f"Thanks! Book again soon.\n\n{SIGN_OFF}",
    ]
    assert all(t.count(SIGN_OFF) == 1 for t in texts)
    assert SIGN_OFF in fake_llm.calls[0]["messages"][1]["content"]


async def test_no_sign_off_leaves_text_untouched(client, fake_llm):
    fake_llm.json_responses.append(_llm_payload())

    r = await client.post(URL, json=BASE)

    assert r.json()["responses"][0]["text"] == "Reply variant 1 about the cold soup."


async def test_language_passthrough(client, fake_llm):
    fake_llm.json_responses.append(_llm_payload())

    r = await client.post(URL, json={**BASE, "language": "Lithuanian"})

    assert r.status_code == 200
    assert "Reply language: Lithuanian" in fake_llm.calls[0]["messages"][1]["content"]


# --- defensive parsing ------------------------------------------------------


async def test_malformed_responses_is_502(client, fake_llm):
    fake_llm.json_responses.append({"responses": "text", "tips": ["Flag it"]})

    r = await client.post(URL, json=BASE)

    assert r.status_code == 502
    assert r.json()["code"] == "llm_bad_json"


async def test_drops_malformed_items_and_defaults_tips(client, fake_llm):
    fake_llm.json_responses.append(
        {
            "responses": [
                {"tone": "Professional", "text": "Thank you for letting us know."},
                {"tone": "Professional · short"},
                {"text": "No label here"},
                "just a string",
                {"tone": "Professional · with CTA", "text": "   "},
            ]
        }
    )

    r = await client.post(URL, json=BASE)

    assert r.status_code == 200
    assert r.json() == {
        "responses": [{"tone": "Professional", "text": "Thank you for letting us know."}],
        "tips": [],
    }


async def test_trims_to_three_responses_and_five_tips(client, fake_llm):
    fake_llm.json_responses.append(_llm_payload(n=5, tips=7))

    r = await client.post(URL, json=BASE)

    d = r.json()
    assert len(d["responses"]) == 3
    assert d["tips"] == [f"Tip {i}" for i in range(1, 6)]


# --- quota ------------------------------------------------------------------


async def test_per_ip_quota_returns_429_without_calling_llm(fake_llm):
    cfg = Settings(
        env="test",
        openai_api_key="test-openai",
        allowed_origins=["http://testserver"],
        quota_limits={"autocomplete_ip": 10, "details_ip": 10, "tool_ip": 1, "tools_global": 10, "autocomplete_global": 10},
    )
    app = create_app(cfg)
    fake_llm.json_responses.append(_llm_payload())
    headers = {"x-forwarded-for": "9.9.9.9, 10.0.0.1"}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        ok = await c.post(URL, json=BASE, headers=headers)
        assert ok.status_code == 200
        blocked = await c.post(URL, json=BASE, headers=headers)
        assert blocked.status_code == 429
        assert blocked.json()["code"] == "quota_exceeded"

    assert len(fake_llm.calls) == 1
