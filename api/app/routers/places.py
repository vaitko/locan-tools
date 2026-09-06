from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ..config import Settings
from ..deps import client_ip, places, quota_repo, settings
from ..quota import QuotaRepo, enforce
from ..services.places import DETAILS_FIELDS_FULL, PlacesClient, normalize_details

router = APIRouter(prefix="/places")


@router.get("/autocomplete")
async def autocomplete(
    request: Request,
    q: str = Query(min_length=2, max_length=120),
    session: str | None = Query(default=None, max_length=64),
    lang: str = Query(default="en", min_length=2, max_length=10),
    region: str | None = Query(default=None, min_length=2, max_length=2),
    cfg: Settings = Depends(settings),
    client: PlacesClient = Depends(places),
    repo: QuotaRepo = Depends(quota_repo),
) -> dict:
    await enforce(
        repo,
        "autocomplete",
        client_ip(request),
        limit_ip=cfg.quota_limits["autocomplete_ip"],
        limit_global=cfg.quota_limits["autocomplete_global"],
    )
    suggestions = await client.autocomplete(q.strip(), session_token=session, language=lang, region=region)
    return {"suggestions": [s.to_dict() for s in suggestions]}


@router.get("/details/{place_id}")
async def details(
    request: Request,
    place_id: str,
    session: str | None = Query(default=None, max_length=64),
    cfg: Settings = Depends(settings),
    client: PlacesClient = Depends(places),
    repo: QuotaRepo = Depends(quota_repo),
) -> dict:
    if not (3 <= len(place_id) <= 300):
        return {"error": "Invalid place id", "code": "validation_error"}
    await enforce(repo, "details", client_ip(request), limit_ip=cfg.quota_limits["details_ip"])
    raw = await client.details(place_id, DETAILS_FIELDS_FULL, session_token=session)
    return normalize_details(raw)
