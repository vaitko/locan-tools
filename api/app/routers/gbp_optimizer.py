"""GBP Optimizer: scores a public Google Business Profile and adds AI suggestions (port of the .NET tool)."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from ..deps import enforce_tool_quota, notify_tool_run, places
from ..errors import ApiError
from ..services import llm
from ..services.gbp_scoring import phone_of, score_place
from ..services.places import PlacesClient

log = logging.getLogger(__name__)
router = APIRouter()

DETAILS_FIELDS = (
    "id,displayName,formattedAddress,websiteUri,nationalPhoneNumber,internationalPhoneNumber,"
    "regularOpeningHours,types,rating,userRatingCount,googleMapsUri,photos,location"
)
SEARCH_FIELDS = "places.id,places.displayName,places.formattedAddress"

SUMMARY_OK = "We analyzed your public Google Business Profile for key visibility factors."
SUMMARY_NOT_FOUND = "We couldn't find that business on Google Maps. Try adding the city or paste a Maps link."
SUMMARY_NO_DETAILS = "Couldn't fetch details for that profile."

MAX_AI_ITEMS = 12
MAX_AI_DESCRIPTION = 700
MAX_AI_TEXT = 500

SYSTEM_PROMPT = """You are a local SEO strategist. Produce STRICT JSON only. No prose.
Use short, specific, local-first ideas. Output must be valid JSON matching this schema:
{
  "optimizedDescription": "string (<= 700 chars, conversational, includes service + city, avoids keyword stuffing)",
  "longTailKeywords": ["service + neighborhood", "problem + city", "near me" variations (8–12 items)],
  "googlePostIdeas": ["10 short post ideas with hooks, promotions, events, FAQs"],
  "localFAQ": [{ "q": "question", "a": "useful, concise answer" }, ... up to 8],
  "reviewReplyTemplates": ["4 short templates: positive, neutral, negative, no-comment"],
  "localCitationIdeas": ["10 credible local/niche directories for this business type/city"]
}"""


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class GbpOptimizeRequest(_Camel):
    business_name: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    place_id: str | None = Field(default=None, max_length=300)
    gbp_url: str | None = Field(default=None, max_length=500)


class Check(_Camel):
    name: str = Field(max_length=40)
    passed: bool = Field(alias="pass")
    detail: str = Field(max_length=80)


class Place(_Camel):
    name: str | None = Field(default=None, max_length=300)
    address: str | None = Field(default=None, max_length=500)
    website: str | None = Field(default=None, max_length=2048)
    phone: str | None = Field(default=None, max_length=50)
    url: str | None = Field(default=None, max_length=2048)
    rating: float | None = None
    reviews: int | None = None
    photos: int | None = None
    lat: float | None = None
    lng: float | None = None


AiText = Annotated[str, Field(max_length=MAX_AI_TEXT)]


class QA(_Camel):
    q: AiText
    a: AiText


class AiSuggestions(_Camel):
    optimized_description: str | None = Field(default=None, max_length=MAX_AI_DESCRIPTION)
    long_tail_keywords: list[AiText] = Field(default_factory=list, max_length=MAX_AI_ITEMS)
    google_post_ideas: list[AiText] = Field(default_factory=list, max_length=MAX_AI_ITEMS)
    local_faq: list[QA] = Field(default_factory=list, max_length=MAX_AI_ITEMS, alias="localFAQ")
    review_reply_templates: list[AiText] = Field(default_factory=list, max_length=MAX_AI_ITEMS)
    local_citation_ideas: list[AiText] = Field(default_factory=list, max_length=MAX_AI_ITEMS)


EMPTY_AI = AiSuggestions()


class GbpOptimizeResult(_Camel):
    score: float = Field(ge=0, le=100)
    grade: str = Field(max_length=20)
    summary: str = Field(max_length=200)
    checks: list[Check] = Field(default_factory=list, max_length=10)
    recommendations: list[str] = Field(default_factory=list, max_length=12)
    place: Place | None = None
    ai: AiSuggestions = Field(default_factory=AiSuggestions)


def _empty(summary: str) -> GbpOptimizeResult:
    return GbpOptimizeResult(score=0, grade="Needs work", summary=summary, ai=EMPTY_AI)


# --- AI suggestions -----------------------------------------------------------


def _strings(value: Any) -> list[str]:
    """Coerce a model-supplied list to clean strings: a lone string counts as one item, non-scalars are dropped."""
    items = [value] if isinstance(value, str) else value if isinstance(value, list) else []
    out: list[str] = []
    for item in items:
        if isinstance(item, bool) or not isinstance(item, (str, int, float)):
            continue
        text = str(item).strip()
        if text:
            out.append(text[:MAX_AI_TEXT])
    return out[:MAX_AI_ITEMS]


def _faq(value: Any) -> list[QA]:
    out: list[QA] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        fields = {str(k).lower(): v for k, v in item.items()}
        q = fields.get("q") or fields.get("question")
        a = fields.get("a") or fields.get("answer")
        if isinstance(q, str) and isinstance(a, str) and q.strip() and a.strip():
            out.append(QA(q=q.strip()[:MAX_AI_TEXT], a=a.strip()[:MAX_AI_TEXT]))
    return out[:MAX_AI_ITEMS]


def parse_ai(data: Any) -> AiSuggestions:
    """Best-effort mapping of the model's JSON; keys are case-insensitive like the .NET deserializer was."""
    if not isinstance(data, dict):
        return EMPTY_AI
    d = {str(k).lower(): v for k, v in data.items()}
    description = d.get("optimizeddescription")
    description = description.strip()[:MAX_AI_DESCRIPTION] if isinstance(description, str) else ""
    return AiSuggestions(
        optimized_description=description or None,
        long_tail_keywords=_strings(d.get("longtailkeywords")),
        google_post_ideas=_strings(d.get("googlepostideas")),
        local_faq=_faq(d.get("localfaq")),
        review_reply_templates=_strings(d.get("reviewreplytemplates")),
        local_citation_ideas=_strings(d.get("localcitationideas")),
    )


def _snapshot(place: Place, gaps: list[str]) -> str:
    def s(value: Any) -> str:
        return "" if value is None else str(value)

    return "\n".join(
        [
            "Business snapshot:",
            f"Name: {s(place.name)}",
            f"Address: {s(place.address)}",
            f"Phone: {s(place.phone)}",
            f"Website: {s(place.website)}",
            f"Rating: {s(place.rating)} ({s(place.reviews)} reviews)",
            f"City hint (from address): {s(place.address)}",
            "Detected gaps to prioritize: " + ", ".join(gaps),
        ]
    )


async def _ai_suggestions(place: Place, checks: list[Check]) -> AiSuggestions:
    try:
        gaps = [c.name for c in checks if not c.passed]
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _snapshot(place, gaps)},
        ]
        data = await llm.chat_json(messages, temperature=0.5, max_tokens=1400)
        return parse_ai(data)
    except Exception as exc:  # AI is best-effort: never fail the analysis because of it
        log.warning("gbp_optimizer: AI suggestions unavailable (%s: %s)", exc.__class__.__name__, exc)
        return EMPTY_AI


# --- endpoint -----------------------------------------------------------------


@router.post("/gbp-optimizer")
async def gbp_optimizer(
    request: Request,
    body: GbpOptimizeRequest,
    client: PlacesClient = Depends(places),
) -> GbpOptimizeResult:
    await enforce_tool_quota(request, "tool_gbp")

    name = (body.business_name or "").strip()
    place_id = (body.place_id or "").strip()
    gbp_url = (body.gbp_url or "").strip()
    if not (name or place_id or gbp_url):
        raise ApiError(422, "validation_error", "Provide a business name, a Google Maps link, or a place id.")

    if not place_id:
        query = f"{name} {(body.city or '').strip()}".strip() if name else gbp_url
        found = await client.search_text(query, fields=SEARCH_FIELDS, max_results=1)
        first = (found.get("places") or [{}])[0]
        place_id = first.get("id") or ""
        if not place_id:
            return _empty(SUMMARY_NOT_FOUND)

    try:
        raw = await client.details(place_id, DETAILS_FIELDS)
    except ApiError as exc:
        if exc.status != 404:
            raise
        return _empty(SUMMARY_NO_DETAILS)

    scoring = score_place(raw)
    checks = [Check.model_validate(c) for c in scoring.checks]
    location = raw.get("location") or {}
    place = Place(
        name=(raw.get("displayName") or {}).get("text"),
        address=raw.get("formattedAddress"),
        website=raw.get("websiteUri"),
        phone=phone_of(raw),
        url=raw.get("googleMapsUri"),
        rating=raw.get("rating"),
        reviews=raw.get("userRatingCount"),
        photos=len(raw.get("photos") or []),
        lat=location.get("latitude"),
        lng=location.get("longitude"),
    )
    ai = await _ai_suggestions(place, checks)
    await notify_tool_run(
        request,
        "gbp-optimizer",
        f"{place.name} — {scoring.score:.0f}/{scoring.grade}",
        {"business": place.name, "address": place.address, "score": scoring.score, "grade": scoring.grade},
    )
    return GbpOptimizeResult(
        score=scoring.score,
        grade=scoring.grade,
        summary=SUMMARY_OK,
        checks=checks,
        recommendations=scoring.recommendations,
        place=place,
        ai=ai,
    )
