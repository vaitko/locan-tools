"""AI Review Response Generator: drafts three public replies to a Google review in the owner's voice."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from ..deps import enforce_tool_quota, notify_tool_run
from ..errors import ApiError
from ..services import llm

router = APIRouter()

MAX_RESPONSES = 3
MAX_TIPS = 5

Tone = Literal["professional", "friendly", "empathetic", "concise"]

SYSTEM_PROMPT = """You write public replies to Google reviews on behalf of a local business owner. Sound like the owner: warm, specific and human, never corporate.

Rules:
- You never invent facts, services, names or promises that are not in the review or the business details provided.
- Never offer discounts, refunds or compensation unless the review itself mentions one.
- Ratings of 3 or below: acknowledge the specific issue raised, apologise sincerely without being defensive or making excuses, and invite the reviewer to continue the conversation offline using a placeholder in square brackets such as [phone] or [email].
- Ratings of 4 or above: thank the reviewer, echo one specific detail they mentioned, and welcome them back.
- Never mention the star rating or its number.
- No hashtags, no emojis.
- Length: 40 to 120 words per reply; when the requested tone is "concise", 25 to 60 words.
- Language: when the requested reply language is "auto", write in the language the review is written in; otherwise write in the requested language.
- If the review looks fake, spam or violates Google's review policy, still reply calmly and professionally, and include a tip about flagging it to Google.
- Do not add a signature or sign-off line; the owner's sign-off is appended automatically when provided.

Return STRICT JSON only, no prose, exactly in this shape:
{"responses": [{"tone": "<label>", "text": "<reply>"}, {"tone": "<label>", "text": "<reply>"}, {"tone": "<label>", "text": "<reply>"}], "tips": ["3-5 short, practical tips for handling this specific review"]}

The three responses are variants of the requested tone: 1) the requested tone, 2) the same tone but shorter, 3) the same tone with a gentle call-to-action (for example: book again, get in touch). Label them like "Professional", "Professional · short", "Professional · with CTA"."""


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, str_strip_whitespace=True)


class ReviewResponseRequest(_Camel):
    business_name: str = Field(min_length=1, max_length=200)
    review_text: str = Field(min_length=5, max_length=2000)
    rating: int = Field(ge=1, le=5)
    reviewer_name: str | None = Field(default=None, max_length=80)
    tone: Tone = "professional"
    language: str = Field(default="auto", max_length=40)
    sign_off: str | None = Field(default=None, max_length=80)
    business_type: str | None = Field(default=None, max_length=80)


class ReviewReply(_Camel):
    tone: str
    text: str


class ReviewResponseResult(_Camel):
    responses: list[ReviewReply]
    tips: list[str] = Field(default_factory=list)


def _user_prompt(body: ReviewResponseRequest) -> str:
    language = body.language or "auto"
    lines = [f"Business name: {body.business_name}"]
    if body.business_type:
        lines.append(f"Business type: {body.business_type}")
    if body.reviewer_name:
        lines.append(f"Reviewer name: {body.reviewer_name}")
    lines.append(f"Rating: {body.rating}/5")
    lines.append(f"Requested tone: {body.tone}")
    lines.append(f"Reply language: {language}" + (" (match the review's language)" if language == "auto" else ""))
    if body.sign_off:
        lines.append(f"Owner sign-off (appended automatically, do not write your own): {body.sign_off}")
    lines += ["", "Review text:", '"""', body.review_text, '"""']
    return "\n".join(lines)


def parse_result(data: dict) -> ReviewResponseResult:
    """Keep only well-formed {tone, text} items and string tips; fail if no usable reply is left."""
    raw = data.get("responses")
    responses = [
        ReviewReply(tone=item["tone"], text=item["text"])
        for item in (raw if isinstance(raw, list) else [])
        if isinstance(item, dict)
        and isinstance(item.get("tone"), str)
        and item["tone"].strip()
        and isinstance(item.get("text"), str)
        and item["text"].strip()
    ]
    if not responses:
        raise ApiError(502, "llm_bad_json", "AI returned an unusable response. Please try again.")
    raw_tips = data.get("tips")
    tips = [t.strip() for t in (raw_tips if isinstance(raw_tips, list) else []) if isinstance(t, str) and t.strip()]
    return ReviewResponseResult(responses=responses[:MAX_RESPONSES], tips=tips[:MAX_TIPS])


@router.post("/review-response", response_model=ReviewResponseResult)
async def review_response(request: Request, body: ReviewResponseRequest) -> ReviewResponseResult:
    await enforce_tool_quota(request, "tool_review")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _user_prompt(body)},
    ]
    data = await llm.chat_json(messages, temperature=0.7, max_tokens=1200)
    result = parse_result(data)

    # Models tend to echo the example labels from the prompt; derive them from the requested tone instead.
    tone_label = body.tone.capitalize()
    variant_labels = [tone_label, f"{tone_label} · short", f"{tone_label} · with CTA"]
    for reply, label in zip(result.responses, variant_labels):
        reply.tone = label

    if body.sign_off:
        for reply in result.responses:
            if not reply.text.endswith(body.sign_off):
                reply.text = f"{reply.text}\n\n{body.sign_off}"
    await notify_tool_run(
        request,
        "review-response",
        f"{body.business_name} — {body.rating}★ {body.tone}",
        {"business": body.business_name, "rating": body.rating, "tone": body.tone, "language": body.language, "review": body.review_text[:300]},
    )
    return result
