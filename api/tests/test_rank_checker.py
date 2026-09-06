from __future__ import annotations

import json
import math

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.services.geo import haversine_km
from app.services.rank_grid import aggregate_competitors, build_grid, rank_of, summarize

BIZ_ID = "ChIJbiz"
BIZ_LAT, BIZ_LNG = 30.31, -97.71
BIZ_DETAILS = {
    "id": BIZ_ID,
    "displayName": {"text": "Radiant Plumbing"},
    "formattedAddress": "901 Reinli St, Austin, TX 78751, USA",
    "location": {"latitude": BIZ_LAT, "longitude": BIZ_LNG},
}
COMPETITOR_NAMES = {"ChIJa": "Alpha Plumbing", "ChIJb": "Bravo Plumbing"}  # ChIJc has no details → "Unknown business"

REQUEST_BODY = {"placeId": BIZ_ID, "keyword": "  plumber ", "gridSize": 3, "spacingKm": 1}


# --- rank_grid (pure) -----------------------------------------------------------


def test_build_grid_3x3_geometry():
    points = build_grid(BIZ_LAT, BIZ_LNG, 3, 1.0)
    assert len(points) == 9
    by_cell = {(p["row"], p["col"]): p for p in points}
    assert set(by_cell) == {(r, c) for r in range(3) for c in range(3)}

    centre = by_cell[(1, 1)]
    assert (centre["lat"], centre["lng"]) == (BIZ_LAT, BIZ_LNG)

    east = haversine_km(centre["lat"], centre["lng"], by_cell[(1, 2)]["lat"], by_cell[(1, 2)]["lng"])
    north = haversine_km(by_cell[(0, 1)]["lat"], by_cell[(0, 1)]["lng"], centre["lat"], centre["lng"])
    assert east == pytest.approx(1.0, rel=0.02)
    assert north == pytest.approx(1.0, rel=0.02)

    assert by_cell[(0, 1)]["lat"] > by_cell[(2, 1)]["lat"]  # row 0 is north
    assert by_cell[(1, 0)]["lng"] < by_cell[(1, 2)]["lng"]  # col 0 is west


def test_build_grid_5x5_two_km():
    points = build_grid(BIZ_LAT, BIZ_LNG, 5, 2.0)
    assert len(points) == 25
    by_cell = {(p["row"], p["col"]): p for p in points}
    assert (by_cell[(2, 2)]["lat"], by_cell[(2, 2)]["lng"]) == (BIZ_LAT, BIZ_LNG)
    corner = by_cell[(0, 0)]
    assert haversine_km(corner["lat"], corner["lng"], BIZ_LAT, BIZ_LNG) == pytest.approx(math.sqrt(8) * 2, rel=0.03)


def test_rank_of():
    places = [{"id": f"ChIJ{i}"} for i in range(6)]
    assert rank_of("ChIJ4", places) == 5
    assert rank_of("ChIJmissing", places) is None
    assert rank_of("ChIJ0", []) is None


def test_summarize_mixed_ranks():
    assert summarize([1, 3, None, 12]) == {
        "averageRank": 5.3,
        "bestRank": 1,
        "worstRank": 12,
        "visibleShare": 0.75,
        "top3Share": 0.5,
        "pointsChecked": 4,
    }


def test_summarize_nothing_ranked():
    s = summarize([None, None])
    assert s["averageRank"] is None and s["bestRank"] is None and s["worstRank"] is None
    assert s["visibleShare"] == 0.0 and s["top3Share"] == 0.0 and s["pointsChecked"] == 2


def test_aggregate_competitors_orders_and_excludes():
    per_point = [
        ["me", "x", "y", "z"],
        ["y", "me", "x"],
        ["y", "x"],
        ["w"],
    ]
    out = aggregate_competitors(per_point, exclude_id="me")
    assert [c["placeId"] for c in out] == ["y", "x", "w", "z"]  # y (3 seen, avg 1.7) beats x (3 seen, avg 2.3)
    assert out[0] == {"placeId": "y", "appearances": 3, "averageRank": 1.7}
    assert out[1] == {"placeId": "x", "appearances": 3, "averageRank": 2.3}
    assert out[2] == {"placeId": "w", "appearances": 1, "averageRank": 1.0}
    assert out[3] == {"placeId": "z", "appearances": 1, "averageRank": 4.0}
    assert "me" not in {c["placeId"] for c in out}


# --- endpoint -----------------------------------------------------------------


def _cell(center: dict) -> tuple[int, int]:
    """Classify a 3×3 locationBias centre by its offset from the business (north → row 0, west → col 0)."""
    d_lat = center["latitude"] - BIZ_LAT
    d_lng = center["longitude"] - BIZ_LNG
    row = 1 - int(d_lat > 1e-6) + int(d_lat < -1e-6)
    col = 1 + int(d_lng > 1e-6) - int(d_lng < -1e-6)
    return row, col


def _ranking_for(cell: tuple[int, int]) -> list[str]:
    if cell == (1, 1):
        return [BIZ_ID, "ChIJa", "ChIJb"]  # centre: business ranks #1
    if cell == (0, 0):
        return ["ChIJa", "ChIJb", "ChIJc"]  # NW corner: business absent (>20)
    return ["ChIJa", BIZ_ID, "ChIJb"]  # everywhere else: #2


def _mock_places(places_mock, *, failing_cells: set[tuple[int, int]] = frozenset(), business=BIZ_DETAILS):
    def search(request: httpx.Request) -> httpx.Response:
        cell = _cell(json.loads(request.content)["locationBias"]["circle"]["center"])
        if cell in failing_cells:
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(200, json={"places": [{"id": pid} for pid in _ranking_for(cell)]})

    def details(request: httpx.Request) -> httpx.Response:
        pid = request.url.path.rsplit("/", 1)[-1]
        if pid == BIZ_ID:
            return httpx.Response(200, json=business)
        if pid in COMPETITOR_NAMES:
            return httpx.Response(200, json={"id": pid, "displayName": {"text": COMPETITOR_NAMES[pid]}})
        return httpx.Response(404, json={})

    search_route = places_mock.post("/v1/places:searchText").mock(side_effect=search)
    details_route = places_mock.get(path__regex=r"^/v1/places/[^:/]+$").mock(side_effect=details)
    return search_route, details_route


async def test_rank_checker_end_to_end(client, places_mock):
    search_route, details_route = _mock_places(places_mock)

    r = await client.post("/api/tools/rank-checker", json=REQUEST_BODY)
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["business"] == {
        "placeId": BIZ_ID,
        "name": "Radiant Plumbing",
        "address": "901 Reinli St, Austin, TX 78751, USA",
        "lat": BIZ_LAT,
        "lng": BIZ_LNG,
    }
    assert data["keyword"] == "plumber"
    assert data["grid"]["size"] == 3 and data["grid"]["spacingKm"] == 1.0

    points = data["grid"]["points"]
    assert len(points) == 9
    assert [(p["row"], p["col"]) for p in points] == [(r, c) for r in range(3) for c in range(3)]
    by_cell = {(p["row"], p["col"]): p for p in points}
    assert by_cell[(1, 1)]["rank"] == 1
    assert by_cell[(1, 1)]["lat"] == BIZ_LAT and by_cell[(1, 1)]["lng"] == BIZ_LNG
    assert by_cell[(0, 0)]["rank"] is None
    assert sum(1 for p in points if p["rank"] is None) == 1
    assert all(p["error"] is False for p in points)

    assert data["summary"] == {
        "averageRank": 1.9,
        "bestRank": 1,
        "worstRank": 2,
        "visibleShare": 0.89,
        "top3Share": 0.89,
        "pointsChecked": 9,
    }

    assert data["competitors"] == [
        {"placeId": "ChIJa", "name": "Alpha Plumbing", "appearances": 9, "averageRank": 1.1},
        {"placeId": "ChIJb", "name": "Bravo Plumbing", "appearances": 9, "averageRank": 2.9},
        {"placeId": "ChIJc", "name": "Unknown business", "appearances": 1, "averageRank": 3.0},
    ]

    assert search_route.call_count == 9
    for call in search_route.calls:
        body = json.loads(call.request.content)
        assert body["textQuery"] == "plumber"
        assert body["pageSize"] == 20
        assert body["languageCode"] == "en"
        assert "regionCode" not in body
        assert body["locationBias"]["circle"]["radius"] == 500.0
        assert call.request.headers["X-Goog-FieldMask"] == "places.id"
    assert details_route.call_count == 4  # business + 3 competitor names
    name_masks = [c.request.headers["X-Goog-FieldMask"] for c in details_route.calls[1:]]
    assert name_masks == ["id,displayName"] * 3


async def test_rank_checker_forwards_language_and_region(client, places_mock):
    search_route, _ = _mock_places(places_mock)
    r = await client.post("/api/tools/rank-checker", json={**REQUEST_BODY, "languageCode": "de", "regionCode": "at"})
    assert r.status_code == 200, r.text
    body = json.loads(search_route.calls.last.request.content)
    assert body["languageCode"] == "de" and body["regionCode"] == "at"


@pytest.mark.parametrize(("spacing", "radius"), [(0.5, 250.0), (1, 500.0), (2, 1000.0), (2.0, 1000.0)])
async def test_rank_checker_bias_radius_is_half_the_spacing(client, places_mock, spacing, radius):
    search_route, _ = _mock_places(places_mock)
    r = await client.post("/api/tools/rank-checker", json={**REQUEST_BODY, "spacingKm": spacing})
    assert r.status_code == 200, r.text
    assert r.json()["grid"]["spacingKm"] == float(spacing)
    assert json.loads(search_route.calls.last.request.content)["locationBias"]["circle"]["radius"] == radius


async def test_rank_checker_single_failing_cell_is_reported_not_fatal(client, places_mock):
    _mock_places(places_mock, failing_cells={(2, 2)})
    r = await client.post("/api/tools/rank-checker", json=REQUEST_BODY)
    assert r.status_code == 200, r.text
    by_cell = {(p["row"], p["col"]): p for p in r.json()["grid"]["points"]}
    assert by_cell[(2, 2)] == {**by_cell[(2, 2)], "rank": None, "error": True}
    assert by_cell[(1, 1)]["rank"] == 1 and by_cell[(1, 1)]["error"] is False
    assert r.json()["summary"]["pointsChecked"] == 9
    assert r.json()["summary"]["visibleShare"] == 0.78  # 7 of 9 ranked


async def test_rank_checker_all_cells_failing_is_502(client, places_mock):
    _mock_places(places_mock, failing_cells={(r, c) for r in range(3) for c in range(3)})
    r = await client.post("/api/tools/rank-checker", json=REQUEST_BODY)
    assert r.status_code == 502
    assert r.json()["code"] == "places_upstream"


async def test_rank_checker_business_without_location_is_422(client, places_mock):
    _mock_places(places_mock, business={"id": BIZ_ID, "displayName": {"text": "Radiant Plumbing"}})
    r = await client.post("/api/tools/rank-checker", json=REQUEST_BODY)
    assert r.status_code == 422
    assert r.json()["code"] == "no_location"


async def test_rank_checker_unknown_place_is_404(client, places_mock):
    _mock_places(places_mock)
    r = await client.post("/api/tools/rank-checker", json={**REQUEST_BODY, "placeId": "ChIJnope"})
    assert r.status_code == 404
    assert r.json()["code"] == "place_not_found"


@pytest.mark.parametrize(
    "body",
    [
        {**REQUEST_BODY, "gridSize": 4},
        {**REQUEST_BODY, "keyword": "a"},
        {**REQUEST_BODY, "spacingKm": 3},
        {**REQUEST_BODY, "placeId": "ab"},
        {**REQUEST_BODY, "regionCode": "usa"},
        {k: v for k, v in REQUEST_BODY.items() if k != "keyword"},
    ],
)
async def test_rank_checker_validation(client, places_mock, body):
    search_route, _ = _mock_places(places_mock)
    r = await client.post("/api/tools/rank-checker", json=body)
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"
    assert search_route.call_count == 0


async def test_rank_checker_5x5_costs_three_quota_units(places_mock):
    limits = {"autocomplete_ip": 1, "details_ip": 1, "tool_ip": 3, "tools_global": 10, "autocomplete_global": 10}
    cfg = Settings(env="test", google_places_api_key="k", allowed_origins=["http://testserver"], quota_limits=limits)
    app = create_app(cfg)
    places_mock.post("/v1/places:searchText").mock(return_value=httpx.Response(200, json={"places": [{"id": BIZ_ID}]}))
    places_mock.get(f"/v1/places/{BIZ_ID}").mock(return_value=httpx.Response(200, json=BIZ_DETAILS))
    headers = {"x-forwarded-for": "9.9.9.9"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        big = await c.post("/api/tools/rank-checker", json={**REQUEST_BODY, "gridSize": 5}, headers=headers)
        assert big.status_code == 200, big.text
        assert len(big.json()["grid"]["points"]) == 25
        assert big.json()["summary"] == {
            "averageRank": 1.0,
            "bestRank": 1,
            "worstRank": 1,
            "visibleShare": 1.0,
            "top3Share": 1.0,
            "pointsChecked": 25,
        }
        assert big.json()["competitors"] == []

        blocked = await c.post("/api/tools/rank-checker", json=REQUEST_BODY, headers=headers)
        assert blocked.status_code == 429
        assert blocked.json()["code"] == "quota_exceeded"

        other_ip = await c.post("/api/tools/rank-checker", json=REQUEST_BODY, headers={"x-forwarded-for": "8.8.8.8"})
        assert other_ip.status_code == 200
