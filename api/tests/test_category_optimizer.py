from __future__ import annotations

import json

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.services.category_scoring import (
    ClientSnapshot,
    CompetitorCategory,
    Recommendation,
    aggregate_competitor_categories,
    build_client_snapshot,
    build_opportunity,
    extract_categories,
    humanize_type,
    score_recommendations,
    term_overlap,
)

# ── unit: humanize_type / extract_categories / snapshot ──────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("water_heater_installation_service", "Water Heater Installation Service"),
        ("plumber", "Plumber"),
        ("point_of_interest", ""),
        ("establishment", ""),
        ("store", ""),
        ("food", ""),
        ("place_of_worship", ""),
        ("Establishment", ""),  # skip set is case-insensitive
        ("", ""),
        ("  ", ""),
        ("__drain__cleaning__", "Drain Cleaning"),
    ],
)
def test_humanize_type(raw, expected):
    assert humanize_type(raw) == expected


def test_extract_categories_primary_first_deduped_and_skips_generic():
    place = {
        "primaryTypeDisplayName": {"text": "Plumber"},
        "types": ["plumber", "water_heater_repair_service", "point_of_interest", "establishment", "PLUMBER"],
    }
    assert extract_categories(place) == ["Plumber", "Water Heater Repair Service"]


def test_extract_categories_without_primary():
    assert extract_categories({"types": ["drain_cleaning_service", "store"]}) == ["Drain Cleaning Service"]
    assert extract_categories({}) == []


def test_build_client_snapshot_joins_reviews_and_defaults():
    place = {
        "id": "ChIJx",
        "displayName": {"text": "Radiant Plumbing"},
        "primaryTypeDisplayName": {"text": "Plumber"},
        "types": ["plumber", "establishment"],
        "userRatingCount": 42,
        "reviews": [{"text": {"text": "Fixed our water heater."}}, {"text": {"text": "  "}}, {"text": {"text": "Fast."}}],
    }
    snap = build_client_snapshot(place)
    assert snap.place_id == "ChIJx"
    assert snap.business_name == "Radiant Plumbing"
    assert snap.primary_category == "Plumber"
    assert snap.all_categories == ["Plumber"]
    assert snap.review_count == 42
    assert snap.combined_review_text == "Fixed our water heater. \n Fast."

    empty = build_client_snapshot({"id": "ChIJy"})
    assert empty.primary_category is None
    assert empty.all_categories == []
    assert empty.review_count == 0
    assert empty.combined_review_text is None


# ── unit: term_overlap ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("category", "text", "expected"),
    [
        ("Bar", "best bar in austin", False),  # 3-char tokens are ignored
        ("Plumber", "best plumber austin", True),
        ("Plumber", "BEST PLUMBER AUSTIN", True),
        ("Water Heater Repair Service", "we do drain cleaning", False),
        ("Water Heater Repair Service", "they fixed our water heater", True),
        ("Plumber", "", False),
        ("", "plumber", False),
        ("Spa & Gym", "gym and spa", False),  # all tokens too short
    ],
)
def test_term_overlap(category, text, expected):
    assert term_overlap(category, text) is expected


# ── unit: aggregation ────────────────────────────────────────────────────────────


def test_aggregate_competitor_categories_counts_and_source_keywords():
    c1 = {"primaryTypeDisplayName": {"text": "Plumber"}, "types": ["plumber", "water_heater_repair_service"]}
    c2 = {"primaryTypeDisplayName": {"text": "Water Heater Repair Service"}, "types": ["water_heater_repair_service"]}
    c3 = {"types": ["plumber", "point_of_interest"]}
    result = aggregate_competitor_categories([("water heater repair austin", [c1, c2]), ("Plumber Austin", [c3])])
    assert [(c.category, c.count, c.out_of) for c in result] == [
        ("Plumber", 2, 3),
        ("Water Heater Repair Service", 2, 3),
    ]
    assert result[0].source_keywords == ["water heater repair austin", "Plumber Austin"]
    assert result[1].source_keywords == ["water heater repair austin"]


# ── unit: scoring ────────────────────────────────────────────────────────────────


def _snapshot(primary="Plumber", categories=("Plumber",), reviews=None) -> ClientSnapshot:
    return ClientSnapshot(
        place_id="ChIJclient",
        business_name="Radiant Plumbing",
        primary_category=primary,
        all_categories=list(categories),
        review_count=10,
        combined_review_text=reviews,
    )


def test_score_recommendations_reference_scenario():
    competitors = [
        CompetitorCategory("Water Heater Repair Service", 3, 3, ["water heater repair austin"]),
        CompetitorCategory("Drain Cleaning Service", 1, 3, ["plumber austin"]),
        CompetitorCategory("Plumber", 3, 3, ["water heater repair austin", "plumber austin"]),
    ]
    recs = score_recommendations(
        _snapshot(),
        competitors,
        keywords=["water heater repair austin", "plumber austin"],
        services_text="drain cleaning",
        business_description=None,
    )
    assert recs == [
        Recommendation("Plumber", "keep", 100, ["Current primary category"]),
        Recommendation(
            "Water Heater Repair Service", "add", 60, ["3 of 3 competitors use it", "Matches your target keywords"]
        ),
        # round(1/3*40)=13, +20 services = 33 → avoid; no penalty because services overlap
        Recommendation(
            "Drain Cleaning Service", "avoid", 33, ["1 of 3 competitors use it", "Listed in services you provide"]
        ),
    ]


def test_score_recommendations_penalty_and_clamp():
    competitors = [CompetitorCategory("Sewer Line Inspection", 1, 3, ["plumber austin"])]
    recs = score_recommendations(_snapshot(), competitors, ["plumber austin"], None, None)
    assert recs[1] == Recommendation(
        "Sewer Line Inspection",
        "avoid",
        0,  # 13 - 25 clamped to 0
        ["1 of 3 competitors use it", "No evidence client offers this — verify before adding"],
    )


def test_score_recommendations_description_and_reviews_signals():
    competitors = [CompetitorCategory("Water Heater Repair Service", 2, 4, ["plumber austin"])]
    recs = score_recommendations(
        _snapshot(reviews="They replaced our water heater in an hour."),
        competitors,
        keywords=["plumber austin"],
        services_text=None,
        business_description="Full-service plumbing incl. water heater work.",
    )
    assert recs[1] == Recommendation(
        "Water Heater Repair Service",
        "consider",
        40,  # 20 freq + 10 description + 10 reviews
        ["2 of 4 competitors use it", "Mentioned in business description", "Customers mention this in reviews"],
    )


def test_score_recommendations_without_primary_and_case_insensitive_skip():
    competitors = [
        CompetitorCategory("PLUMBER", 3, 3, ["plumber austin"]),
        CompetitorCategory("Drain Cleaning Service", 3, 3, ["plumber austin"]),
        CompetitorCategory("drain cleaning service", 1, 3, ["plumber austin"]),  # duplicate casing → skipped
    ]
    recs = score_recommendations(_snapshot(primary=None, categories=["Plumber"]), competitors, ["plumber austin"], None, None)
    assert [r.category for r in recs] == ["Drain Cleaning Service"]
    assert recs[0].score == 40 and recs[0].action == "consider"


# ── unit: opportunity ────────────────────────────────────────────────────────────


def test_build_opportunity_no_gaps():
    recs = [Recommendation("Plumber", "keep", 100, []), Recommendation("Bakery", "avoid", 0, [])]
    opp = build_opportunity(recs)
    assert opp.missing_category_count == 0
    assert opp.estimated_keyword_match_gain == 0
    assert opp.estimated_service_search_gain == 0
    assert opp.estimated_local_pack_gaps_closed == 0
    assert opp.headline == "Your categories already match the top competitors in this market."


def test_build_opportunity_two_missing():
    recs = [
        Recommendation("Plumber", "keep", 100, []),
        Recommendation("Water Heater Repair Service", "add", 60, []),
        Recommendation("Drain Cleaning Service", "consider", 40, []),
        Recommendation("Bakery", "avoid", 0, []),
    ]
    opp = build_opportunity(recs)
    assert opp.missing_category_count == 2
    assert opp.estimated_keyword_match_gain == 6  # 1*4 + 1*2
    assert opp.estimated_service_search_gain == 2
    assert opp.estimated_local_pack_gaps_closed == 1
    assert opp.headline == "You are missing 2 categories used by competitors ranking above you."


def test_build_opportunity_singular_headline_and_gap_cap():
    recs = [Recommendation("X", "add", 60, [])]
    assert build_opportunity(recs).headline == "You are missing 1 category used by competitors ranking above you."
    many = [Recommendation(f"C{i}", "add", 60, []) for i in range(7)]
    assert build_opportunity(many).estimated_local_pack_gaps_closed == 5


# ── end-to-end via HTTP with mocked Places ───────────────────────────────────────

CLIENT_ID = "ChIJclient"

CLIENT_DETAILS = {
    "id": CLIENT_ID,
    "displayName": {"text": "Radiant Plumbing"},
    "primaryTypeDisplayName": {"text": "Plumber"},
    "types": ["plumber", "point_of_interest", "establishment"],
    "userRatingCount": 120,
    "reviews": [
        {"text": {"text": "They fixed our water heater fast."}},
        {"text": {"text": "Great plumber, fair price."}},
    ],
}

COMPETITOR_DETAILS = {
    "ChIJc1": {
        "id": "ChIJc1",
        "displayName": {"text": "Hot Water Pros"},
        "primaryTypeDisplayName": {"text": "Water Heater Repair Service"},
        "types": ["water_heater_repair_service", "plumber", "point_of_interest", "establishment"],
    },
    "ChIJc2": {
        "id": "ChIJc2",
        "displayName": {"text": "Austin Plumbing Co"},
        "primaryTypeDisplayName": {"text": "Plumber"},
        "types": ["plumber", "water_heater_repair_service", "establishment"],
    },
    "ChIJc3": {
        "id": "ChIJc3",
        "displayName": {"text": "Drain Masters"},
        "primaryTypeDisplayName": {"text": "Plumber"},
        "types": ["plumber", "drain_cleaning_service", "point_of_interest"],
    },
    "ChIJc4": {
        "id": "ChIJc4",
        "displayName": {"text": "Pipe Dreams"},
        "primaryTypeDisplayName": {"text": "Plumber"},
        "types": ["plumber", "store"],
    },
}

SEARCH_RESULTS = {
    "water heater repair austin": [CLIENT_ID, "ChIJc1", "ChIJc2"],  # client must be excluded
    "plumber austin": ["ChIJc3", "ChIJc4", "ChIJbroken"],  # details for ChIJbroken 404s → skipped
    "Radiant Plumbing Austin": [CLIENT_ID],
    "Nowhere Plumbing Mars": [],
}


def _mock_places(places_mock):
    def search(request: httpx.Request) -> httpx.Response:
        query = json.loads(request.content)["textQuery"]
        ids = SEARCH_RESULTS.get(query, [])
        return httpx.Response(200, json={"places": [{"id": pid} for pid in ids]})

    def details(request: httpx.Request) -> httpx.Response:
        pid = request.url.path.rsplit("/", 1)[-1]
        if pid == CLIENT_ID:
            return httpx.Response(200, json=CLIENT_DETAILS)
        if pid in COMPETITOR_DETAILS:
            return httpx.Response(200, json=COMPETITOR_DETAILS[pid])
        return httpx.Response(404, json={})

    search_route = places_mock.post("/v1/places:searchText").mock(side_effect=search)
    details_route = places_mock.get(path__regex=r"^/v1/places/[^:/]+$").mock(side_effect=details)
    return search_route, details_route


REQUEST_BODY = {
    "placeId": CLIENT_ID,
    "keywords": ["water heater repair austin", "  ", "plumber austin"],
    "competitorsPerKeyword": 3,
    "servicesText": "drain cleaning, leak detection",
}


async def test_category_optimizer_end_to_end(client, places_mock):
    search_route, details_route = _mock_places(places_mock)

    r = await client.post("/api/tools/category-optimizer", json=REQUEST_BODY)
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["client"] == {
        "placeId": CLIENT_ID,
        "businessName": "Radiant Plumbing",
        "primaryCategory": "Plumber",
        "allCategories": ["Plumber"],
        "reviewCount": 120,
    }

    assert data["competitorCategories"] == [
        {
            "category": "Plumber",
            "count": 4,
            "outOf": 4,
            "sourceKeywords": ["water heater repair austin", "plumber austin"],
        },
        {"category": "Water Heater Repair Service", "count": 2, "outOf": 4, "sourceKeywords": ["water heater repair austin"]},
        {"category": "Drain Cleaning Service", "count": 1, "outOf": 4, "sourceKeywords": ["plumber austin"]},
    ]

    assert data["recommendations"] == [
        {"category": "Plumber", "action": "keep", "score": 100, "reasons": ["Current primary category"]},
        {
            "category": "Water Heater Repair Service",
            "action": "consider",
            "score": 50,  # 20 freq + 20 keywords + 10 reviews
            "reasons": ["2 of 4 competitors use it", "Matches your target keywords", "Customers mention this in reviews"],
        },
        {
            "category": "Drain Cleaning Service",
            "action": "avoid",
            "score": 30,  # 10 freq + 20 services
            "reasons": ["1 of 4 competitors use it", "Listed in services you provide"],
        },
    ]

    assert data["opportunity"] == {
        "missingCategoryCount": 1,
        "estimatedKeywordMatchGain": 2,
        "estimatedServiceSearchGain": 0,
        "estimatedLocalPackGapsClosed": 0,
        "headline": "You are missing 1 category used by competitors ranking above you.",
    }

    # one search per non-blank keyword, pageSize = take + 2
    assert search_route.call_count == 2
    sent_queries = {json.loads(c.request.content)["textQuery"] for c in search_route.calls}
    assert sent_queries == {"water heater repair austin", "plumber austin"}
    assert all(json.loads(c.request.content)["pageSize"] == 5 for c in search_route.calls)

    # client fetched once with reviews; competitors without reviews; client id never re-fetched as competitor
    fetched = [c.request.url.path.rsplit("/", 1)[-1] for c in details_route.calls]
    assert fetched.count(CLIENT_ID) == 1
    assert sorted(p for p in fetched if p != CLIENT_ID) == ["ChIJbroken", "ChIJc1", "ChIJc2", "ChIJc3", "ChIJc4"]
    masks = {c.request.url.path.rsplit("/", 1)[-1]: c.request.headers["X-Goog-FieldMask"] for c in details_route.calls}
    assert masks[CLIENT_ID] == "id,displayName,types,primaryTypeDisplayName,userRatingCount,reviews"
    assert masks["ChIJc1"] == "id,displayName,types,primaryTypeDisplayName"
    assert all(h["X-Goog-Api-Key"] == "test-places" for h in (c.request.headers for c in details_route.calls))


async def test_category_optimizer_resolves_by_business_name_and_city(client, places_mock):
    search_route, _ = _mock_places(places_mock)
    r = await client.post(
        "/api/tools/category-optimizer",
        json={"businessName": "Radiant Plumbing", "city": "Austin", "keywords": ["plumber austin"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["client"]["placeId"] == CLIENT_ID
    first = json.loads(search_route.calls[0].request.content)
    assert first == {"textQuery": "Radiant Plumbing Austin", "pageSize": 1}


async def test_category_optimizer_place_not_found(client, places_mock):
    _mock_places(places_mock)
    r = await client.post(
        "/api/tools/category-optimizer",
        json={"businessName": "Nowhere Plumbing", "city": "Mars", "keywords": ["plumber mars"]},
    )
    assert r.status_code == 404
    assert r.json() == {"error": "Could not locate the client's Google Business Profile.", "code": "place_not_found"}

    r = await client.post("/api/tools/category-optimizer", json={"placeId": "ChIJmissing", "keywords": ["plumber"]})
    assert r.status_code == 404
    assert r.json()["code"] == "place_not_found"


async def test_category_optimizer_requires_name_or_place_id(client, places_mock):
    r = await client.post("/api/tools/category-optimizer", json={"keywords": ["plumber austin"]})
    assert r.status_code == 422
    assert r.json() == {"error": "Provide a business name or place id.", "code": "validation_error"}


@pytest.mark.parametrize(
    "keywords",
    [[], ["  ", ""], ["a"], ["x" * 81], [f"kw{i}" for i in range(11)]],
)
async def test_category_optimizer_rejects_invalid_keywords(client, places_mock, keywords):
    r = await client.post("/api/tools/category-optimizer", json={"placeId": CLIENT_ID, "keywords": keywords})
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"


async def test_category_optimizer_clamps_competitors_per_keyword(client, places_mock):
    search_route, _ = _mock_places(places_mock)
    body = {**REQUEST_BODY, "competitorsPerKeyword": 50}
    r = await client.post("/api/tools/category-optimizer", json=body)
    assert r.status_code == 200, r.text
    assert all(json.loads(c.request.content)["pageSize"] == 12 for c in search_route.calls)  # clamp 10 → +2


async def test_category_optimizer_429_after_per_ip_quota(places_mock):
    cfg = Settings(
        env="test",
        google_places_api_key="test-places",
        allowed_origins=["http://testserver"],
        quota_limits={"autocomplete_ip": 10, "details_ip": 10, "tool_ip": 1, "tools_global": 10, "autocomplete_global": 10},
    )
    app = create_app(cfg)
    _mock_places(places_mock)
    headers = {"x-forwarded-for": "9.9.9.9, 10.0.0.1"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        ok = await c.post("/api/tools/category-optimizer", json=REQUEST_BODY, headers=headers)
        assert ok.status_code == 200, ok.text
        blocked = await c.post("/api/tools/category-optimizer", json=REQUEST_BODY, headers=headers)
        assert blocked.status_code == 429
        assert blocked.json()["code"] == "quota_exceeded"
        other = await c.post("/api/tools/category-optimizer", json=REQUEST_BODY, headers={"x-forwarded-for": "8.8.8.8"})
        assert other.status_code == 200
