from __future__ import annotations

import httpx
import pytest

from locan_tools import __version__
from locan_tools.client import DEFAULT_BASE_URL, LocanApiError, LocanClient

from .conftest import (
    AI_VISIBILITY,
    BASE_URL,
    CATEGORIES,
    DETAILS,
    DETAILS_VALIDATION_ERROR,
    GBP_AUDIT,
    QUOTA_ERROR,
    RANK_GRID,
    REVIEW_REPLY,
    SUGGESTIONS,
    UPSTREAM_ERROR,
)


def client_for(rec, base_url: str = BASE_URL) -> LocanClient:
    return LocanClient(base_url=base_url, transport=rec.transport)


def test_default_base_url_is_the_hosted_api():
    with LocanClient() as client:
        assert client.base_url == DEFAULT_BASE_URL == "https://api.locan.ai/api"


def test_base_url_comes_from_env_and_loses_its_trailing_slash(monkeypatch):
    monkeypatch.setenv("LOCAN_API_URL", "http://localhost:8080/api/")
    with LocanClient() as client:
        assert client.base_url == "http://localhost:8080/api"


def test_explicit_base_url_wins_over_env(monkeypatch):
    monkeypatch.setenv("LOCAN_API_URL", "http://localhost:8080/api")
    with LocanClient(base_url="https://other.example/api/") as client:
        assert client.base_url == "https://other.example/api"


def test_find_business_calls_places_autocomplete(recorder):
    rec = recorder(SUGGESTIONS)
    with client_for(rec) as client:
        out = client.find_business("dentist kaunas")
    assert rec.request.method == "GET"
    assert rec.request.url.path == "/api/places/autocomplete"
    assert dict(rec.request.url.params) == {"q": "dentist kaunas"}
    assert rec.request.headers["user-agent"] == f"locan-tools/{__version__}"
    assert out == [
        {"placeId": "PLACE1", "name": "Smile Dental", "address": "Laisves al. 1, Kaunas"},
        {"placeId": "PLACE2", "name": "Bright Teeth", "address": "Vilniaus g. 9, Kaunas"},
    ]


def test_find_business_passes_optional_query_parameters(recorder):
    rec = recorder(SUGGESTIONS)
    with client_for(rec) as client:
        client.find_business("dentist", session="tok", lang="lt", region="LT")
    assert dict(rec.request.url.params) == {"q": "dentist", "session": "tok", "lang": "lt", "region": "LT"}


def test_place_details_calls_places_details(recorder):
    rec = recorder(DETAILS)
    with client_for(rec) as client:
        out = client.place_details("PLACE 1")
    assert rec.request.method == "GET"
    assert rec.request.url.path == "/api/places/details/PLACE 1"
    assert out["placeId"] == "PLACE1"


def test_gbp_audit_posts_only_supplied_fields(recorder):
    rec = recorder(GBP_AUDIT)
    with client_for(rec) as client:
        out = client.gbp_audit(business_name="Smile Dental", city="Kaunas")
    assert rec.request.method == "POST"
    assert rec.request.url.path == "/api/tools/gbp-optimizer"
    assert rec.body == {"businessName": "Smile Dental", "city": "Kaunas"}
    assert out["score"] == 72.0


def test_gbp_categories_posts_camel_case_body(recorder):
    rec = recorder(CATEGORIES)
    with client_for(rec) as client:
        client.gbp_categories(
            place_id="PLACE1",
            keywords=["dentist kaunas", "teeth whitening"],
            region_code="LT",
            language_code="lt",
            services_text="implants",
        )
    assert rec.request.url.path == "/api/tools/category-optimizer"
    assert rec.body == {
        "placeId": "PLACE1",
        "keywords": ["dentist kaunas", "teeth whitening"],
        "regionCode": "LT",
        "languageCode": "lt",
        "servicesText": "implants",
    }


def test_rank_grid_posts_camel_case_body(recorder):
    rec = recorder(RANK_GRID)
    with client_for(rec) as client:
        client.rank_grid(place_id="PLACE1", keyword="dentist", grid_size=5, spacing_km=0.5, region_code="LT")
    assert rec.request.url.path == "/api/tools/rank-checker"
    assert rec.body == {
        "placeId": "PLACE1",
        "keyword": "dentist",
        "gridSize": 5,
        "spacingKm": 0.5,
        "regionCode": "LT",
    }


def test_ai_visibility_posts_camel_case_body(recorder):
    rec = recorder(AI_VISIBILITY)
    with client_for(rec) as client:
        client.ai_visibility(business_name="Smile Dental", city="Kaunas", category="dentist")
    assert rec.request.url.path == "/api/tools/ai-visibility"
    assert rec.body == {"businessName": "Smile Dental", "city": "Kaunas", "category": "dentist"}


def test_review_reply_posts_camel_case_body(recorder):
    rec = recorder(REVIEW_REPLY)
    with client_for(rec) as client:
        client.review_reply(
            business_name="Smile Dental",
            review_text="Great visit, friendly staff.",
            rating=5,
            reviewer_name="Ona",
            tone="friendly",
            language="lt",
            sign_off="— Tomas",
            business_type="dentist",
        )
    assert rec.request.url.path == "/api/tools/review-response"
    assert rec.body == {
        "businessName": "Smile Dental",
        "reviewText": "Great visit, friendly staff.",
        "rating": 5,
        "reviewerName": "Ona",
        "tone": "friendly",
        "language": "lt",
        "signOff": "— Tomas",
        "businessType": "dentist",
    }


def test_api_error_carries_status_code_and_message(recorder):
    rec = recorder(QUOTA_ERROR, status=429)
    with client_for(rec) as client:
        with pytest.raises(LocanApiError) as excinfo:
            client.ai_visibility(business_name="Smile Dental", city="Kaunas")
    assert excinfo.value.status == 429
    assert excinfo.value.code == "quota_exceeded"
    assert "today's free limit" in excinfo.value.message


def test_upstream_error_is_raised(recorder):
    rec = recorder(UPSTREAM_ERROR, status=502)
    with client_for(rec) as client:
        with pytest.raises(LocanApiError) as excinfo:
            client.gbp_audit(place_id="PLACE1")
    assert (excinfo.value.status, excinfo.value.code) == (502, "places_upstream")


def test_fastapi_default_validation_shape_falls_back_to_detail(recorder):
    rec = recorder({"detail": [{"loc": ["body", "rating"], "msg": "Input should be less than or equal to 5"}]}, status=422)
    with client_for(rec) as client:
        with pytest.raises(LocanApiError) as excinfo:
            client.review_reply(business_name="Smile Dental", review_text="Bad day.", rating=9)
    assert excinfo.value.code == "http_422"
    assert "less than or equal to 5" in excinfo.value.message


def test_non_json_error_body_falls_back_to_the_status(recorder):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="<html>gateway</html>", request=request)

    with LocanClient(base_url=BASE_URL, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(LocanApiError) as excinfo:
            client.find_business("dentist")
    assert (excinfo.value.status, excinfo.value.code) == (503, "http_503")


def test_non_json_success_body_is_rejected(recorder):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>proxy</html>", request=request)

    with LocanClient(base_url=BASE_URL, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(LocanApiError) as excinfo:
            client.find_business("dentist")
    assert (excinfo.value.status, excinfo.value.code) == (200, "bad_response")


def test_200_error_body_is_raised_as_an_api_error(recorder):
    rec = recorder(DETAILS_VALIDATION_ERROR, status=200)
    with client_for(rec) as client:
        with pytest.raises(LocanApiError) as excinfo:
            client.place_details("x")
    assert (excinfo.value.status, excinfo.value.code) == (200, "validation_error")
    assert excinfo.value.message == "Invalid place id"


def test_200_error_body_without_a_code_is_still_raised(recorder):
    rec = recorder({"error": "Something went wrong upstream"}, status=200)
    with client_for(rec) as client:
        with pytest.raises(LocanApiError) as excinfo:
            client.place_details("x")
    assert (excinfo.value.status, excinfo.value.code) == (200, "error")
    assert excinfo.value.message == "Something went wrong upstream"


def test_connection_failures_stay_httpx_errors(recorder):
    rec = recorder(None, raise_connect_error=True)
    with client_for(rec) as client:
        with pytest.raises(httpx.ConnectError):
            client.find_business("dentist")


def test_review_link_needs_no_network():
    with LocanClient(base_url=BASE_URL, transport=httpx.MockTransport(_no_network)) as client:
        assert client.review_link("PLACE1") == {
            "placeId": "PLACE1",
            "reviewLink": "https://search.google.com/local/writereview?placeid=PLACE1",
        }


def test_schema_jsonld_builds_local_business_markup_without_network():
    with LocanClient(base_url=BASE_URL, transport=httpx.MockTransport(_no_network)) as client:
        data = client.schema_jsonld(DETAILS)
    assert data["@context"] == "https://schema.org"
    assert data["@type"] == "Dentist"
    assert data["@id"] == "https://smile.example#localbusiness"
    assert data["name"] == "Smile Dental"
    assert data["url"] == "https://smile.example"
    assert data["telephone"] == "+370 600 00000"
    assert data["address"] == {
        "@type": "PostalAddress",
        "streetAddress": "Laisves al. 1",
        "addressLocality": "Kaunas",
        "addressRegion": "Kauno apskritis",
        "postalCode": "44001",
        "addressCountry": "LT",
    }
    assert data["geo"] == {"@type": "GeoCoordinates", "latitude": 54.8985, "longitude": 23.9036}
    assert data["hasMap"] == "https://maps.google.com/?cid=1"
    assert "aggregateRating" not in data


def test_schema_jsonld_groups_consecutive_days_and_handles_all_day_opening():
    with LocanClient(base_url=BASE_URL, transport=httpx.MockTransport(_no_network)) as client:
        data = client.schema_jsonld(DETAILS)
    assert data["openingHoursSpecification"] == [
        {"@type": "OpeningHoursSpecification", "dayOfWeek": ["Monday", "Tuesday"], "opens": "09:00", "closes": "18:00"},
        {"@type": "OpeningHoursSpecification", "dayOfWeek": ["Wednesday"], "opens": "10:00", "closes": "16:00"},
        {"@type": "OpeningHoursSpecification", "dayOfWeek": ["Saturday"], "opens": "00:00", "closes": "23:59"},
    ]


def test_schema_jsonld_skips_fields_the_details_response_does_not_have():
    details = {"placeId": "PLACE9", "name": "Corner Shop", "primaryType": "unknown_type"}
    with LocanClient(base_url=BASE_URL, transport=httpx.MockTransport(_no_network)) as client:
        data = client.schema_jsonld(details)
    assert data == {"@context": "https://schema.org", "@type": "LocalBusiness", "name": "Corner Shop"}


def _no_network(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"unexpected request to {request.url}")
