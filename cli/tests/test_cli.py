from __future__ import annotations

import json

import httpx
import pytest
from typer.testing import CliRunner

from locan_tools import cli as cli_module
from locan_tools.client import LocanClient

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

runner = CliRunner()


@pytest.fixture
def invoke(monkeypatch):
    def run(rec, args: list[str]):
        monkeypatch.setattr(cli_module, "make_client", lambda: LocanClient(base_url=BASE_URL, transport=rec.transport))
        return runner.invoke(cli_module.app, args)

    return run


def output_json(result) -> object:
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def test_find_business_prints_suggestions(invoke, recorder):
    rec = recorder(SUGGESTIONS)
    result = invoke(rec, ["find-business", "dentist kaunas"])
    assert output_json(result) == SUGGESTIONS["suggestions"]
    assert dict(rec.request.url.params) == {"q": "dentist kaunas"}


def test_gbp_audit_sends_the_supplied_fields(invoke, recorder):
    rec = recorder(GBP_AUDIT)
    result = invoke(rec, ["gbp-audit", "--business-name", "Smile Dental", "--city", "Kaunas"])
    assert output_json(result) == GBP_AUDIT
    assert rec.body == {"businessName": "Smile Dental", "city": "Kaunas"}


def test_gbp_audit_accepts_a_maps_url(invoke, recorder):
    rec = recorder(GBP_AUDIT)
    result = invoke(rec, ["gbp-audit", "--gbp-url", "https://maps.app.goo.gl/abc"])
    assert result.exit_code == 0, result.output
    assert rec.body == {"gbpUrl": "https://maps.app.goo.gl/abc"}


def test_gbp_categories_repeats_the_keyword_option(invoke, recorder):
    rec = recorder(CATEGORIES)
    result = invoke(
        rec,
        ["gbp-categories", "--place-id", "PLACE1", "--keyword", "dentist kaunas", "--keyword", "teeth whitening"],
    )
    assert output_json(result) == CATEGORIES
    assert rec.body == {"placeId": "PLACE1", "keywords": ["dentist kaunas", "teeth whitening"]}


def test_rank_grid_sends_grid_size_and_spacing(invoke, recorder):
    rec = recorder(RANK_GRID)
    result = invoke(
        rec,
        ["rank-grid", "--place-id", "PLACE1", "--keyword", "dentist", "--grid-size", "5", "--spacing-km", "0.5"],
    )
    assert output_json(result) == RANK_GRID
    assert rec.body == {"placeId": "PLACE1", "keyword": "dentist", "gridSize": 5, "spacingKm": 0.5}


def test_rank_grid_omits_options_the_user_did_not_set(invoke, recorder):
    rec = recorder(RANK_GRID)
    result = invoke(rec, ["rank-grid", "--place-id", "PLACE1", "--keyword", "dentist"])
    assert result.exit_code == 0, result.output
    assert rec.body == {"placeId": "PLACE1", "keyword": "dentist"}


def test_ai_visibility_sends_business_city_and_category(invoke, recorder):
    rec = recorder(AI_VISIBILITY)
    result = invoke(
        rec,
        ["ai-visibility", "--business-name", "Smile Dental", "--city", "Kaunas", "--category", "dentist"],
    )
    assert output_json(result) == AI_VISIBILITY
    assert rec.body == {"businessName": "Smile Dental", "city": "Kaunas", "category": "dentist"}


def test_review_reply_sends_the_review_and_rating(invoke, recorder):
    rec = recorder(REVIEW_REPLY)
    result = invoke(
        rec,
        [
            "review-reply",
            "--business-name",
            "Smile Dental",
            "--review-text",
            "Great visit, friendly staff.",
            "--rating",
            "5",
            "--tone",
            "friendly",
        ],
    )
    assert output_json(result) == REVIEW_REPLY
    assert rec.body == {
        "businessName": "Smile Dental",
        "reviewText": "Great visit, friendly staff.",
        "rating": 5,
        "tone": "friendly",
    }


def test_review_link_makes_no_request(invoke, recorder):
    rec = recorder(None, raise_connect_error=True)
    result = invoke(rec, ["review-link", "PLACE1"])
    assert output_json(result) == {
        "placeId": "PLACE1",
        "reviewLink": "https://search.google.com/local/writereview?placeid=PLACE1",
    }
    assert rec.requests == []


def test_schema_jsonld_fetches_details_and_prints_markup(invoke, recorder):
    rec = recorder(DETAILS)
    result = invoke(rec, ["schema-jsonld", "PLACE1"])
    data = output_json(result)
    assert rec.request.url.path == "/api/places/details/PLACE1"
    assert data["@type"] == "Dentist"
    assert data["address"]["addressLocality"] == "Kaunas"


def test_schema_jsonld_200_error_body_exits_with_code_1(invoke, recorder):
    rec = recorder(DETAILS_VALIDATION_ERROR, status=200)
    result = invoke(rec, ["schema-jsonld", "PLACE1"])
    assert result.exit_code == 1
    assert "error: Invalid place id (validation_error)" in result.stderr


def test_non_json_response_exits_with_code_1(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>proxy</html>", request=request)

    monkeypatch.setattr(
        cli_module, "make_client", lambda: LocanClient(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    )
    result = runner.invoke(cli_module.app, ["find-business", "dentist"])
    assert result.exit_code == 1
    assert "error: API returned a non-JSON response (bad_response)" in result.stderr


def test_pretty_renders_a_table_instead_of_json(invoke, recorder):
    rec = recorder(SUGGESTIONS)
    result = invoke(rec, ["--pretty", "find-business", "dentist kaunas"])
    assert result.exit_code == 0
    assert "Smile Dental" in result.stdout
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.stdout)


def test_quota_error_exits_with_code_1_and_the_api_message(invoke, recorder):
    rec = recorder(QUOTA_ERROR, status=429)
    result = invoke(rec, ["ai-visibility", "--business-name", "Smile Dental", "--city", "Kaunas"])
    assert result.exit_code == 1
    assert "error: You've reached today's free limit for this tool." in result.stderr
    assert "(quota_exceeded)" in result.stderr


def test_upstream_error_exits_with_code_1(invoke, recorder):
    rec = recorder(UPSTREAM_ERROR, status=502)
    result = invoke(rec, ["gbp-audit", "--place-id", "PLACE1"])
    assert result.exit_code == 1
    assert "error: Google Places returned HTTP 500. (places_upstream)" in result.stderr


def test_connection_failure_names_the_base_url(invoke, recorder):
    rec = recorder(None, raise_connect_error=True)
    result = invoke(rec, ["find-business", "dentist"])
    assert result.exit_code == 1
    assert f"error: could not reach {BASE_URL}" in result.stderr


def test_client_factory_reads_the_env_base_url(monkeypatch):
    monkeypatch.setenv("LOCAN_API_URL", "http://localhost:8080/api/")
    with cli_module.make_client() as client:
        assert client.base_url == "http://localhost:8080/api"
