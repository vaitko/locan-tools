from __future__ import annotations

import json

import httpx
import pytest

from app.config import DEFAULT_QUOTAS, Settings
from app.errors import ApiError
from app.main import create_app
from app.routers.gbp_optimizer import (
    DETAILS_FIELDS,
    EMPTY_AI,
    SEARCH_FIELDS,
    SUMMARY_NO_DETAILS,
    SUMMARY_NOT_FOUND,
    SUMMARY_OK,
)
from app.services import llm
from app.services.gbp_scoring import GENERIC_RECOMMENDATIONS, phone_of, score_place

FULL_PLACE = {
    "id": "ChIJabc",
    "displayName": {"text": "Radiant Plumbing"},
    "formattedAddress": "901 Reinli St, Austin, TX 78751, USA",
    "websiteUri": "https://radiantplumbing.com",
    "nationalPhoneNumber": "(512) 555-0100",
    "internationalPhoneNumber": "+1 512-555-0100",
    "regularOpeningHours": {"weekdayDescriptions": ["Monday: 8:00 AM – 5:30 PM"]},
    "types": ["plumber", "point_of_interest"],
    "rating": 4.8,
    "userRatingCount": 1200,
    "googleMapsUri": "https://maps.google.com/?cid=1",
    "photos": [{"name": f"places/ChIJabc/photos/{i}"} for i in range(7)],
    "location": {"latitude": 30.31, "longitude": -97.71},
}

AI_PAYLOAD = {
    "optimizedDescription": "Radiant Plumbing keeps Austin homes flowing with fast, friendly repairs.",
    "longTailKeywords": ["emergency plumber austin", "water heater repair hyde park"],
    "googlePostIdeas": ["Spring drain-cleaning special"],
    "localFAQ": [{"q": "Do you offer 24/7 service?", "a": "Yes, call anytime."}],
    "reviewReplyTemplates": ["Thanks for the kind words!"],
    "localCitationIdeas": ["Austin Chamber of Commerce"],
}

EMPTY_AI_JSON = EMPTY_AI.model_dump(by_alias=True)


def _without(place: dict, *keys: str) -> dict:
    return {k: v for k, v in place.items() if k not in keys}


def _mock_details(places_mock, payload: dict = FULL_PLACE, status: int = 200):
    return places_mock.get("/v1/places/ChIJabc").mock(return_value=httpx.Response(status, json=payload))


def _mock_search(places_mock, results: list[dict]):
    return places_mock.post("/v1/places:searchText").mock(return_value=httpx.Response(200, json={"places": results}))


# --- scoring (pure) ---------------------------------------------------------


def test_score_full_profile_is_100_a():
    result = score_place(FULL_PLACE)
    assert (result.score, result.grade) == (100, "A")
    assert [c["name"] for c in result.checks] == [
        "Website",
        "Opening hours",
        "Phone number",
        "Photos",
        "Reviews",
        "Relevant category",
    ]
    assert all(c["pass"] for c in result.checks)
    assert [c["detail"] for c in result.checks] == [
        "Website present",
        "Hours set",
        "Phone present",
        "7 photos",
        "1200 reviews",
        "Primary category set",
    ]
    assert result.recommendations == GENERIC_RECOMMENDATIONS


def test_score_empty_profile_needs_work():
    result = score_place({})
    assert (result.score, result.grade) == (0, "Needs work")
    assert not any(c["pass"] for c in result.checks)
    assert [c["detail"] for c in result.checks] == [
        "Add your website URL",
        "Add accurate opening hours",
        "Add a phone number",
        "Upload at least 5 quality photos",
        "Aim for 10+ recent reviews",
        "Pick the most accurate primary category",
    ]
    assert len(result.recommendations) == 9
    assert result.recommendations[:6] == [
        "Add your website URL to your profile.",
        "Set accurate opening hours (incl. holidays).",
        "Add a visible phone number customers can call.",
        "Upload 5–10 high-quality photos (exterior, interior, team, products).",
        "Request new reviews via SMS/email and reply to each review.",
        "Choose the best primary category; add 2–3 relevant secondary categories.",
    ]
    assert result.recommendations[6:] == GENERIC_RECOMMENDATIONS


@pytest.mark.parametrize(
    ("missing", "score", "grade"),
    [
        (("websiteUri",), 85, "B+"),
        (("photos",), 80, "B+"),
        (("userRatingCount",), 75, "B"),
        (("userRatingCount", "nationalPhoneNumber", "internationalPhoneNumber"), 65, "C"),
        (("userRatingCount", "photos"), 55, "Needs work"),
    ],
)
def test_grade_thresholds(missing, score, grade):
    result = score_place(_without(FULL_PLACE, *missing))
    assert (result.score, result.grade) == (score, grade)


def test_photo_and_review_thresholds():
    below = {**FULL_PLACE, "photos": FULL_PLACE["photos"][:4], "userRatingCount": 9}
    checks = {c["name"]: c for c in score_place(below).checks}
    assert checks["Photos"]["pass"] is False and checks["Reviews"]["pass"] is False

    at = {**FULL_PLACE, "photos": FULL_PLACE["photos"][:5], "userRatingCount": 10}
    checks = {c["name"]: c for c in score_place(at).checks}
    assert checks["Photos"] == {"name": "Photos", "pass": True, "detail": "5 photos"}
    assert checks["Reviews"] == {"name": "Reviews", "pass": True, "detail": "10 reviews"}


def test_phone_falls_back_to_international():
    place = _without(FULL_PLACE, "nationalPhoneNumber")
    assert phone_of(place) == "+1 512-555-0100"
    assert {c["name"]: c["pass"] for c in score_place(place).checks}["Phone number"] is True
    assert phone_of({"nationalPhoneNumber": "   "}) is None


# --- endpoint ---------------------------------------------------------------


async def test_place_id_full_profile(client, places_mock, fake_llm):
    details = _mock_details(places_mock)
    fake_llm.json_responses.append(AI_PAYLOAD)

    r = await client.post("/api/tools/gbp-optimizer", json={"placeId": "ChIJabc"})

    assert r.status_code == 200
    d = r.json()
    assert (d["score"], d["grade"], d["summary"]) == (100, "A", SUMMARY_OK)
    assert len(d["checks"]) == 6 and all(c["pass"] for c in d["checks"])
    assert d["checks"][0] == {"name": "Website", "pass": True, "detail": "Website present"}
    assert d["recommendations"] == GENERIC_RECOMMENDATIONS
    assert d["place"] == {
        "name": "Radiant Plumbing",
        "address": "901 Reinli St, Austin, TX 78751, USA",
        "website": "https://radiantplumbing.com",
        "phone": "(512) 555-0100",
        "url": "https://maps.google.com/?cid=1",
        "rating": 4.8,
        "reviews": 1200,
        "photos": 7,
        "lat": 30.31,
        "lng": -97.71,
    }
    assert d["ai"] == AI_PAYLOAD
    assert details.calls.last.request.headers["X-Goog-FieldMask"] == DETAILS_FIELDS

    messages = fake_llm.calls[0]["messages"]
    assert messages[0]["role"] == "system" and "STRICT JSON" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "Name: Radiant Plumbing" in messages[1]["content"]
    assert "Rating: 4.8 (1200 reviews)" in messages[1]["content"]


async def test_business_name_resolves_via_text_search(client, places_mock, fake_llm):
    search = _mock_search(places_mock, [{"id": "ChIJabc", "displayName": {"text": "Radiant Plumbing"}}])
    _mock_details(places_mock, _without(FULL_PLACE, "websiteUri", "photos"))
    fake_llm.json_responses.append(AI_PAYLOAD)

    r = await client.post("/api/tools/gbp-optimizer", json={"businessName": "Radiant Plumbing", "city": "Austin"})

    assert r.status_code == 200
    d = r.json()
    assert d["place"]["name"] == "Radiant Plumbing"
    assert (d["score"], d["grade"]) == (65, "C")
    sent = json.loads(search.calls.last.request.read())
    assert sent["textQuery"] == "Radiant Plumbing Austin"
    assert sent["pageSize"] == 1
    assert search.calls.last.request.headers["X-Goog-FieldMask"] == SEARCH_FIELDS
    assert "Detected gaps to prioritize: Website, Photos" in fake_llm.calls[0]["messages"][1]["content"]


async def test_gbp_url_is_used_as_search_query(client, places_mock, fake_llm):
    search = _mock_search(places_mock, [{"id": "ChIJabc"}])
    _mock_details(places_mock)
    fake_llm.json_responses.append(AI_PAYLOAD)

    r = await client.post("/api/tools/gbp-optimizer", json={"gbpUrl": " https://maps.app.goo.gl/abc "})

    assert r.status_code == 200
    assert json.loads(search.calls.last.request.read())["textQuery"] == "https://maps.app.goo.gl/abc"


async def test_text_search_without_results_returns_empty_result(client, places_mock, fake_llm):
    _mock_search(places_mock, [])

    r = await client.post("/api/tools/gbp-optimizer", json={"businessName": "Nonexistent Biz"})

    assert r.status_code == 200
    assert r.json() == {
        "score": 0,
        "grade": "Needs work",
        "summary": SUMMARY_NOT_FOUND,
        "checks": [],
        "recommendations": [],
        "place": None,
        "ai": EMPTY_AI_JSON,
    }
    assert fake_llm.calls == []


async def test_details_not_found_returns_empty_result(client, places_mock, fake_llm):
    _mock_details(places_mock, {}, status=404)

    r = await client.post("/api/tools/gbp-optimizer", json={"placeId": "ChIJabc"})

    assert r.status_code == 200
    d = r.json()
    assert (d["score"], d["grade"], d["summary"]) == (0, "Needs work", SUMMARY_NO_DETAILS)
    assert d["place"] is None and d["checks"] == [] and d["ai"] == EMPTY_AI_JSON
    assert fake_llm.calls == []


async def test_details_upstream_error_propagates_as_502(client, places_mock, fake_llm):
    _mock_details(places_mock, {"error": "boom"}, status=500)

    r = await client.post("/api/tools/gbp-optimizer", json={"placeId": "ChIJabc"})

    assert r.status_code == 502
    assert r.json()["code"] == "places_upstream"
    assert fake_llm.calls == []


async def test_ai_malformed_types_are_coerced(client, places_mock, fake_llm):
    _mock_details(places_mock)
    fake_llm.json_responses.append(
        {
            "OptimizedDescription": "x" * 800,
            "longTailKeywords": "emergency plumber austin",
            "googlePostIdeas": ["ok", 42, None, {"title": "nope"}, "   "],
            "localFAQ": [{"q": "Q1", "a": "A1"}, {"Question": "Q2", "Answer": "A2"}, "junk", {"q": "", "a": "x"}],
            "reviewReplyTemplates": None,
            "localCitationIdeas": [f"Directory {i}" for i in range(20)],
        }
    )

    r = await client.post("/api/tools/gbp-optimizer", json={"placeId": "ChIJabc"})

    assert r.status_code == 200
    ai = r.json()["ai"]
    assert len(ai["optimizedDescription"]) == 700
    assert ai["longTailKeywords"] == ["emergency plumber austin"]
    assert ai["googlePostIdeas"] == ["ok", "42"]
    assert ai["localFAQ"] == [{"q": "Q1", "a": "A1"}, {"q": "Q2", "a": "A2"}]
    assert ai["reviewReplyTemplates"] == []
    assert len(ai["localCitationIdeas"]) == 12


async def test_ai_failure_yields_empty_ai(client, places_mock, monkeypatch):
    _mock_details(places_mock)

    async def boom(*args, **kwargs):
        raise ApiError(502, "llm_upstream", "AI request failed: APIConnectionError")

    monkeypatch.setattr(llm, "chat_json", boom)

    r = await client.post("/api/tools/gbp-optimizer", json={"placeId": "ChIJabc"})

    assert r.status_code == 200
    d = r.json()
    assert (d["score"], d["grade"]) == (100, "A")
    assert d["ai"] == EMPTY_AI_JSON


@pytest.mark.parametrize("body", [{}, {"businessName": "   ", "city": "Austin"}])
async def test_missing_identifiers_is_validation_error(client, body):
    r = await client.post("/api/tools/gbp-optimizer", json=body)
    assert r.status_code == 422
    assert r.json() == {
        "error": "Provide a business name, a Google Maps link, or a place id.",
        "code": "validation_error",
    }


async def test_request_field_length_limits(client):
    r = await client.post("/api/tools/gbp-optimizer", json={"businessName": "x" * 201})
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"
    assert r.json()["error"].startswith("businessName:")


async def test_quota_scope_tool_gbp_is_enforced(places_mock, fake_llm):
    cfg = Settings(
        env="test",
        openai_api_key="k",
        google_places_api_key="k",
        allowed_origins=["http://t"],
        quota_limits={**DEFAULT_QUOTAS, "tool_ip": 1},
    )
    app = create_app(cfg)
    _mock_details(places_mock)
    fake_llm.json_responses.append(AI_PAYLOAD)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        ok = await c.post("/api/tools/gbp-optimizer", json={"placeId": "ChIJabc"})
        assert ok.status_code == 200
        blocked = await c.post("/api/tools/gbp-optimizer", json={"placeId": "ChIJabc"})
        assert blocked.status_code == 429
        assert blocked.json()["code"] == "quota_exceeded"

    assert any(key.startswith("QUOTA#tool_gbp#") for key in app.state.quota._counts)
