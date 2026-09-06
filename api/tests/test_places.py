from __future__ import annotations

import httpx
import pytest

from app.services.places import normalize_details

AUTOCOMPLETE_PAYLOAD = {
    "suggestions": [
        {
            "placePrediction": {
                "placeId": "ChIJabc",
                "text": {"text": "Radiant Plumbing, Austin, TX, USA"},
                "structuredFormat": {
                    "mainText": {"text": "Radiant Plumbing"},
                    "secondaryText": {"text": "Austin, TX, USA"},
                },
            }
        },
        {"queryPrediction": {"text": {"text": "plumbers near me"}}},
    ]
}

DETAILS_PAYLOAD = {
    "id": "ChIJabc",
    "displayName": {"text": "Radiant Plumbing"},
    "formattedAddress": "901 Reinli St, Austin, TX 78751, USA",
    "addressComponents": [
        {"longText": "901", "types": ["street_number"]},
        {"longText": "Reinli Street", "types": ["route"]},
        {"longText": "Austin", "types": ["locality"]},
        {"longText": "Texas", "shortText": "TX", "types": ["administrative_area_level_1"]},
        {"longText": "78751", "types": ["postal_code"]},
        {"longText": "United States", "types": ["country"]},
    ],
    "location": {"latitude": 30.31, "longitude": -97.71},
    "nationalPhoneNumber": "(512) 555-0100",
    "websiteUri": "https://radiantplumbing.com",
    "regularOpeningHours": {
        "periods": [{"open": {"day": 1, "hour": 8, "minute": 0}, "close": {"day": 1, "hour": 17, "minute": 30}}],
        "weekdayDescriptions": ["Monday: 8:00 AM – 5:30 PM"],
    },
    "primaryType": "plumber",
    "primaryTypeDisplayName": {"text": "Plumber"},
    "rating": 4.8,
    "userRatingCount": 1200,
    "googleMapsUri": "https://maps.google.com/?cid=1",
}


async def test_health(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


async def test_autocomplete_maps_place_predictions_only(client, places_mock):
    route = places_mock.post("/v1/places:autocomplete").mock(return_value=httpx.Response(200, json=AUTOCOMPLETE_PAYLOAD))
    r = await client.get("/api/places/autocomplete", params={"q": "radiant", "session": "abc"})
    assert r.status_code == 200
    assert r.json() == {"suggestions": [{"placeId": "ChIJabc", "name": "Radiant Plumbing", "address": "Austin, TX, USA"}]}
    sent = route.calls.last.request
    assert sent.headers["X-Goog-Api-Key"] == "test-places"
    body = sent.read()
    assert b'"sessionToken": "abc"' in body or b'"sessionToken":"abc"' in body


async def test_autocomplete_requires_two_chars(client):
    r = await client.get("/api/places/autocomplete", params={"q": "a"})
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"


async def test_autocomplete_upstream_error_is_502(client, places_mock):
    places_mock.post("/v1/places:autocomplete").mock(return_value=httpx.Response(403, json={"error": "denied"}))
    r = await client.get("/api/places/autocomplete", params={"q": "radiant"})
    assert r.status_code == 502
    assert r.json()["code"] == "places_upstream"


async def test_details_normalized(client, places_mock):
    route = places_mock.get("/v1/places/ChIJabc").mock(return_value=httpx.Response(200, json=DETAILS_PAYLOAD))
    r = await client.get("/api/places/details/ChIJabc")
    assert r.status_code == 200
    d = r.json()
    assert d["name"] == "Radiant Plumbing"
    assert d["addressComponents"] == {
        "street": "901 Reinli Street",
        "locality": "Austin",
        "region": "Texas",
        "postalCode": "78751",
        "country": "United States",
    }
    assert d["lat"] == 30.31 and d["lng"] == -97.71
    assert d["openingHours"] == [{"day": 1, "open": "08:00", "close": "17:30"}]
    assert d["primaryTypeLabel"] == "Plumber"
    assert "displayName" in route.calls.last.request.headers["X-Goog-FieldMask"]


async def test_details_not_found(client, places_mock):
    places_mock.get("/v1/places/nope").mock(return_value=httpx.Response(404, json={}))
    r = await client.get("/api/places/details/nope")
    assert r.status_code == 404
    assert r.json()["code"] == "place_not_found"


def test_normalize_details_handles_empty_payload():
    d = normalize_details({})
    assert d["placeId"] is None and d["openingHours"] == [] and d["addressComponents"]["street"] is None


@pytest.mark.parametrize("origin", ["http://testserver"])
async def test_cors_preflight_allows_configured_origin(client, origin):
    r = await client.options(
        "/api/places/autocomplete",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == origin
