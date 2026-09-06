"""GBP Category Optimizer: compares the client's Google categories with top competitors per keyword
and scores which categories to add (port of the .NET GbpCategoryOptimizerService). No LLM involved."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from pydantic.alias_generators import to_camel

from ..deps import enforce_tool_quota, notify_tool_run, places
from ..errors import ApiError
from ..services.category_scoring import (
    aggregate_competitor_categories,
    build_client_snapshot,
    build_opportunity,
    score_recommendations,
)
from ..services.places import PlacesClient

router = APIRouter()

CLIENT_FIELDS = "id,displayName,types,primaryTypeDisplayName,userRatingCount,reviews"
COMPETITOR_FIELDS = "id,displayName,types,primaryTypeDisplayName"
SEARCH_FIELDS = "places.id"
MIN_COMPETITORS, MAX_COMPETITORS = 3, 10
MAX_CONCURRENT_KEYWORDS = 4


def _not_found() -> ApiError:
    return ApiError(404, "place_not_found", "Could not locate the client's Google Business Profile.")


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]


class CategoryOptimizeRequest(_Camel):
    business_name: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    place_id: str | None = Field(default=None, max_length=300)
    keywords: list[Keyword] = Field(min_length=1, max_length=10)
    competitors_per_keyword: int = 5
    region_code: str | None = Field(default=None, min_length=2, max_length=2)
    language_code: str = Field(default="en", min_length=2, max_length=10)
    services_text: str | None = Field(default=None, max_length=2000)
    business_description: str | None = Field(default=None, max_length=2000)

    @field_validator("keywords", mode="before")
    @classmethod
    def _drop_blank_keywords(cls, value: object) -> object:
        if isinstance(value, list):
            return [k.strip() for k in value if isinstance(k, str) and k.strip()]
        return value


class ClientOut(_Camel):
    place_id: str | None
    business_name: str | None = Field(default=None, max_length=300)
    primary_category: str | None = Field(default=None, max_length=200)
    all_categories: list[str]
    review_count: int


class CompetitorCategoryOut(_Camel):
    category: str = Field(max_length=200)
    count: int
    out_of: int
    source_keywords: list[str]


class RecommendationOut(_Camel):
    category: str = Field(max_length=200)
    action: str = Field(max_length=20)
    score: int = Field(ge=0, le=100)
    reasons: list[str]


class OpportunityOut(_Camel):
    missing_category_count: int
    estimated_keyword_match_gain: int
    estimated_service_search_gain: int
    estimated_local_pack_gaps_closed: int
    headline: str = Field(max_length=300)


class CategoryOptimizeResponse(_Camel):
    client: ClientOut
    competitor_categories: list[CompetitorCategoryOut]
    recommendations: list[RecommendationOut]
    opportunity: OpportunityOut


@router.post("/category-optimizer", response_model=CategoryOptimizeResponse)
async def optimize_categories(
    request: Request,
    body: CategoryOptimizeRequest,
    client: PlacesClient = Depends(places),
) -> CategoryOptimizeResponse:
    await enforce_tool_quota(request, "tool_category")

    place_id = (body.place_id or "").strip()
    business_name = (body.business_name or "").strip()
    if not place_id and not business_name:
        raise ApiError(422, "validation_error", "Provide a business name or place id.")
    take = max(MIN_COMPETITORS, min(MAX_COMPETITORS, body.competitors_per_keyword))

    client_place = await _resolve_client_place(client, place_id, business_name, (body.city or "").strip())
    snapshot = build_client_snapshot(client_place)

    sem = asyncio.Semaphore(MAX_CONCURRENT_KEYWORDS)
    per_keyword = await asyncio.gather(
        *(_search_competitors(client, kw, take, snapshot.place_id or place_id, sem) for kw in body.keywords)
    )
    competitor_categories = aggregate_competitor_categories(list(zip(body.keywords, per_keyword)))
    recs = score_recommendations(
        snapshot, competitor_categories, body.keywords, body.services_text, body.business_description
    )
    opportunity = build_opportunity(recs)
    await notify_tool_run(
        request,
        "category-optimizer",
        f"{snapshot.business_name} — {opportunity.missing_category_count} missing",
        {"business": snapshot.business_name, "city": body.city, "keywords": ", ".join(body.keywords), "missing": opportunity.missing_category_count},
    )

    return CategoryOptimizeResponse(
        client=ClientOut(
            place_id=snapshot.place_id,
            business_name=snapshot.business_name,
            primary_category=snapshot.primary_category,
            all_categories=snapshot.all_categories,
            review_count=snapshot.review_count,
        ),
        competitor_categories=[
            CompetitorCategoryOut(
                category=c.category, count=c.count, out_of=c.out_of, source_keywords=c.source_keywords
            )
            for c in competitor_categories
        ],
        recommendations=[
            RecommendationOut(category=r.category, action=r.action, score=r.score, reasons=r.reasons) for r in recs
        ],
        opportunity=OpportunityOut(
            missing_category_count=opportunity.missing_category_count,
            estimated_keyword_match_gain=opportunity.estimated_keyword_match_gain,
            estimated_service_search_gain=opportunity.estimated_service_search_gain,
            estimated_local_pack_gaps_closed=opportunity.estimated_local_pack_gaps_closed,
            headline=opportunity.headline,
        ),
    )


async def _resolve_client_place(client: PlacesClient, place_id: str, business_name: str, city: str) -> dict:
    if not place_id:
        data = await client.search_text(f"{business_name} {city}".strip(), fields=SEARCH_FIELDS, max_results=1)
        found = data.get("places") or []
        place_id = (found[0].get("id") if found else None) or ""
        if not place_id:
            raise _not_found()
    try:
        place = await client.details(place_id, CLIENT_FIELDS)
    except ApiError as exc:
        if exc.status == 404:
            raise _not_found() from exc
        raise
    if not place:
        raise _not_found()
    return place


async def _search_competitors(
    client: PlacesClient, keyword: str, take: int, exclude_place_id: str, sem: asyncio.Semaphore
) -> list[dict]:
    """Top `take` profiles for `keyword`, excluding the client. Upstream failures degrade to fewer results."""
    async with sem:
        try:
            data = await client.search_text(keyword, fields=SEARCH_FIELDS, max_results=min(take + 2, 20))
        except ApiError:
            return []
        competitors: list[dict] = []
        for place in data.get("places") or []:
            if len(competitors) >= take:
                break
            pid = place.get("id")
            if not pid or pid.lower() == exclude_place_id.lower():
                continue
            try:
                details = await client.details(pid, COMPETITOR_FIELDS)
            except ApiError:
                continue
            if details:
                competitors.append(details)
        return competitors
