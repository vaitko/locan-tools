from __future__ import annotations

import pytest
from mcp import Client

from locan_tools import mcp_server as server_module
from locan_tools.client import LocanClient

from .conftest import BASE_URL, DETAILS, DETAILS_VALIDATION_ERROR, QUOTA_ERROR, SUGGESTIONS

TOOL_NAMES = {
    "find_business",
    "gbp_audit",
    "gbp_categories",
    "rank_grid",
    "ai_visibility",
    "review_reply",
    "review_link",
    "schema_jsonld",
}


CAMEL_ARG_TOKENS = ("placeId", "businessName", "gridSize", "spacingKm", "gbpUrl", "reviewText")


@pytest.fixture
def bind(monkeypatch):
    def run(rec):
        monkeypatch.setattr(
            server_module, "make_client", lambda: LocanClient(base_url=BASE_URL, transport=rec.transport)
        )

    return run


async def test_tools_list_exposes_the_eight_tools_with_descriptions():
    async with Client(server_module.server) as client:
        result = await client.list_tools()
    assert {tool.name for tool in result.tools} == TOOL_NAMES
    for tool in result.tools:
        assert tool.description and tool.description.strip()


async def test_rank_grid_description_states_the_places_cost():
    async with Client(server_module.server) as client:
        result = await client.list_tools()
    rank_grid = next(tool for tool in result.tools if tool.name == "rank_grid")
    assert "one Places request per cell; 25 for a 5×5" in rank_grid.description
    assert "daily limits apply on the hosted API; self-host for unlimited runs" in rank_grid.description


async def test_tool_descriptions_name_arguments_the_way_the_schemas_do():
    async with Client(server_module.server) as client:
        result = await client.list_tools()
    offenders = [
        (tool.name, token)
        for tool in result.tools
        for token in CAMEL_ARG_TOKENS
        if token in tool.description
    ]
    assert offenders == []
    rank_grid = next(tool for tool in result.tools if tool.name == "rank_grid")
    assert {"place_id", "grid_size", "spacing_km"} <= set(rank_grid.input_schema["properties"])


async def test_find_business_returns_the_suggestions(bind, recorder):
    rec = recorder(SUGGESTIONS)
    bind(rec)
    async with Client(server_module.server) as client:
        result = await client.call_tool("find_business", {"query": "dentist kaunas"})
    assert result.is_error is False
    assert result.structured_content == {"result": SUGGESTIONS["suggestions"]}
    assert dict(rec.request.url.params) == {"q": "dentist kaunas"}


async def test_review_link_needs_no_api_call(bind, recorder):
    rec = recorder(None, raise_connect_error=True)
    bind(rec)
    async with Client(server_module.server) as client:
        result = await client.call_tool("review_link", {"place_id": "PLACE1"})
    assert result.is_error is False
    assert result.structured_content["reviewLink"] == "https://search.google.com/local/writereview?placeid=PLACE1"
    assert rec.requests == []


async def test_schema_jsonld_builds_markup_from_the_details_response(bind, recorder):
    rec = recorder(DETAILS)
    bind(rec)
    async with Client(server_module.server) as client:
        result = await client.call_tool("schema_jsonld", {"place_id": "PLACE1"})
    assert result.is_error is False
    assert result.structured_content["@type"] == "Dentist"


async def test_schema_jsonld_200_error_body_comes_back_as_a_tool_error(bind, recorder):
    rec = recorder(DETAILS_VALIDATION_ERROR, status=200)
    bind(rec)
    async with Client(server_module.server) as client:
        result = await client.call_tool("schema_jsonld", {"place_id": "x"})
    assert result.is_error is True
    text = "".join(block.text for block in result.content if block.type == "text")
    assert "validation_error" in text
    assert "Invalid place id" in text


async def test_quota_error_comes_back_as_a_tool_error(bind, recorder):
    rec = recorder(QUOTA_ERROR, status=429)
    bind(rec)
    async with Client(server_module.server) as client:
        result = await client.call_tool("ai_visibility", {"business_name": "Smile Dental", "city": "Kaunas"})
    assert result.is_error is True
    text = "".join(block.text for block in result.content if block.type == "text")
    assert "quota_exceeded" in text
    assert "today's free limit" in text


async def test_connection_failure_comes_back_as_a_tool_error(bind, recorder):
    rec = recorder(None, raise_connect_error=True)
    bind(rec)
    async with Client(server_module.server) as client:
        result = await client.call_tool("find_business", {"query": "dentist"})
    assert result.is_error is True
    text = "".join(block.text for block in result.content if block.type == "text")
    assert f"could not reach {BASE_URL}" in text
