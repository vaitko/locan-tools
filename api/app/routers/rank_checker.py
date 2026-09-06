"""Local Rank Checker: approximates a Google Maps ranking heat map by running one Places Text Search per grid
cell with a `locationBias` circle centred on that cell and reading off the business's 1-based position."""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from pydantic.alias_generators import to_camel

from ..deps import enforce_tool_quota, notify_tool_run, places
from ..errors import ApiError
from ..services.places import PlacesClient
from ..services.rank_grid import aggregate_competitors, build_grid, rank_of, summarize

log = logging.getLogger(__name__)
router = APIRouter()

BUSINESS_FIELDS = "id,displayName,formattedAddress,location"
NAME_FIELDS = "id,displayName"
SEARCH_FIELDS = "places.id"
PAGE_SIZE = 20
TOP_COMPETITORS = 5
SEARCH_CONCURRENCY = 5
DETAILS_CONCURRENCY = 3
SPACINGS_KM = (0.5, 1.0, 2.0)
UNKNOWN_NAME = "Unknown business"


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]


class RankCheckRequest(_Camel):
    place_id: str = Field(min_length=3, max_length=300)
    keyword: Keyword
    grid_size: Literal[3, 5] = 3
    spacing_km: float = 1.0
    language_code: str = Field(default="en", min_length=2, max_length=10)
    region_code: str | None = Field(default=None, min_length=2, max_length=2)

    @field_validator("spacing_km")
    @classmethod
    def _allowed_spacing(cls, value: float) -> float:
        if value not in SPACINGS_KM:
            raise ValueError("must be one of 0.5, 1 or 2")
        return float(value)


class BusinessOut(_Camel):
    place_id: str
    name: str | None
    address: str | None
    lat: float
    lng: float


class PointOut(_Camel):
    row: int
    col: int
    lat: float
    lng: float
    rank: int | None
    error: bool = False


class GridOut(_Camel):
    size: int
    spacing_km: float
    points: list[PointOut]


class SummaryOut(_Camel):
    average_rank: float | None
    best_rank: int | None
    worst_rank: int | None
    visible_share: float
    top3_share: float
    points_checked: int


class CompetitorOut(_Camel):
    place_id: str
    name: str
    appearances: int
    average_rank: float


class RankCheckResponse(_Camel):
    business: BusinessOut
    keyword: str
    grid: GridOut
    summary: SummaryOut
    competitors: list[CompetitorOut]


async def _search_point(
    client: PlacesClient, sem: asyncio.Semaphore, point: dict, body: RankCheckRequest
) -> list[dict] | None:
    """Ranked places for one grid cell, or None when Places failed for that cell."""
    async with sem:
        try:
            data = await client.search_text(
                body.keyword,
                fields=SEARCH_FIELDS,
                max_results=PAGE_SIZE,
                location_bias=(point["lat"], point["lng"], body.spacing_km * 500),
                language=body.language_code,
                region=body.region_code,
            )
        except ApiError as exc:
            log.warning("rank_checker: cell (%s,%s) failed: %s", point["row"], point["col"], exc.message)
            return None
    return data.get("places") or []


async def _display_name(client: PlacesClient, sem: asyncio.Semaphore, place_id: str) -> str:
    async with sem:
        try:
            raw = await client.details(place_id, NAME_FIELDS)
        except ApiError:
            return UNKNOWN_NAME
    return (raw.get("displayName") or {}).get("text") or UNKNOWN_NAME


@router.post("/rank-checker", response_model=RankCheckResponse)
async def rank_checker(
    request: Request,
    body: RankCheckRequest,
    client: PlacesClient = Depends(places),
) -> RankCheckResponse:
    await enforce_tool_quota(request, "tool_rank", units=3 if body.grid_size == 5 else 1)

    raw = await client.details(body.place_id, BUSINESS_FIELDS)
    location = raw.get("location") or {}
    lat, lng = location.get("latitude"), location.get("longitude")
    if lat is None or lng is None:
        raise ApiError(422, "no_location", "We couldn't determine this business's location.")
    place_id = raw.get("id") or body.place_id

    points = build_grid(lat, lng, body.grid_size, body.spacing_km)
    search_sem = asyncio.Semaphore(SEARCH_CONCURRENCY)
    results = await asyncio.gather(*(_search_point(client, search_sem, p, body) for p in points))
    if all(r is None for r in results):
        raise ApiError(502, "places_upstream", "Google Places is unavailable right now. Please try again.")
    ranks = [rank_of(place_id, r or []) for r in results]

    per_point_ids = [[p["id"] for p in (r or []) if p.get("id")] for r in results]
    top = aggregate_competitors(per_point_ids, place_id)[:TOP_COMPETITORS]
    details_sem = asyncio.Semaphore(DETAILS_CONCURRENCY)
    names = await asyncio.gather(*(_display_name(client, details_sem, c["placeId"]) for c in top))
    business_name = (raw.get("displayName") or {}).get("text")
    ranked = [r for r in ranks if r is not None]
    await notify_tool_run(
        request,
        "rank-checker",
        f"{business_name} — '{body.keyword}' {body.grid_size}x{body.grid_size}",
        {"business": business_name, "keyword": body.keyword, "grid": f"{body.grid_size}x{body.grid_size} @ {body.spacing_km} km", "visible_cells": f"{len(ranked)}/{len(ranks)}", "best_rank": min(ranked) if ranked else None},
    )

    return RankCheckResponse(
        business=BusinessOut(
            place_id=place_id,
            name=business_name,
            address=raw.get("formattedAddress"),
            lat=lat,
            lng=lng,
        ),
        keyword=body.keyword,
        grid=GridOut(
            size=body.grid_size,
            spacing_km=body.spacing_km,
            points=[PointOut(**p, rank=rank, error=r is None) for p, rank, r in zip(points, ranks, results)],
        ),
        summary=SummaryOut(**summarize(ranks)),
        competitors=[CompetitorOut(**c, name=name) for c, name in zip(top, names)],
    )
