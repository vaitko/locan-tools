"""AI Visibility Checker: how often ChatGPT / Gemini / Perplexity / Google AI name a business for local buyer queries
(port of the legacy /api/analyze and /api/chat endpoints; wire contracts unchanged)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic.alias_generators import to_camel

from ..deps import enforce_tool_quota, notify_tool_run
from ..errors import ApiError
from ..services import ai_visibility

router = APIRouter()


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


BusinessName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
City = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Message = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class AnalyzeRequest(_Camel):
    business_name: BusinessName
    city: City
    category: str = Field(default="", max_length=80)


class ChatRequest(_Camel):
    message: Message
    business_name: str = Field(max_length=200)
    city: str = Field(max_length=100)
    category: str = Field(max_length=200)
    score: int
    top_competitor: str = Field(max_length=200)
    missing: list[str] = Field(max_length=10)
    actions: list[Any] = Field(max_length=10)


class EngineOut(_Camel):
    mentions: int
    queries: int
    confidence: str
    avg_position: int | None


class QueryOut(_Camel):
    text: str
    mentioned: bool
    engine: str
    failed: bool = False


class CompetitorOut(_Camel):
    name: str
    score: int
    reasons: list[str]


class ActionOut(_Camel):
    title: str
    desc: str


class AnalyzeResponse(_Camel):
    score: int
    score_label: str
    total_mentions: int
    total_queries: int
    failed_queries: int = 0
    visibility_rate: int
    category: str
    engines: dict[str, EngineOut]
    queries: list[QueryOut]
    competitors: list[CompetitorOut]
    missing: list[str]
    actions: list[ActionOut]


class ChatResponse(BaseModel):
    reply: str


@router.post("/ai-visibility", response_model=AnalyzeResponse)
async def analyze(request: Request, body: AnalyzeRequest) -> dict:
    await enforce_tool_quota(request, "tool_ai_visibility")
    biz = ai_visibility.clean_business_name(body.business_name)
    if not biz:
        raise ApiError(422, "validation_error", "Provide a business name.")
    result = await ai_visibility.analyze(biz, body.city, body.category)
    await notify_tool_run(
        request,
        "ai-visibility",
        f"{biz}, {body.city} — {result['score']}/100",
        {"business": biz, "city": body.city, "category": result["category"], "score": result["score"], "competitors": ", ".join(c["name"] for c in result["competitors"])},
    )
    return result


@router.post("/ai-visibility/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest) -> dict:
    await enforce_tool_quota(request, "tool_ai_visibility_chat")
    reply = await ai_visibility.chat(
        body.message,
        business_name=body.business_name,
        city=body.city,
        category=body.category,
        score=body.score,
        top_competitor=body.top_competitor,
        missing=body.missing,
        actions=body.actions,
    )
    return {"reply": reply}
