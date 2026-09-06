"""AI Visibility Checker: four simulated AI assistants answer local buyer queries and we measure how often the
business is named. Port of the legacy /api/analyze + /api/chat (src/locan.ai/api/server.py), trimmed to ≤15 LLM
calls."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from ..errors import ApiError
from . import llm

log = logging.getLogger(__name__)

MODEL = "gpt-4o-mini"
QUERIES_PER_ENGINE = 3
MAX_COMPETITORS = 3
MAX_ITEMS = 5
SNIPPET_CHARS = 200
COMBINED_CHARS = 5000
FALLBACK_CATEGORY = "Local Business"

ENGINES: list[dict[str, str]] = [
    {
        "key": "chatgpt",
        "name": "ChatGPT",
        "persona": (
            "You are ChatGPT by OpenAI. Answer helpfully and specifically. "
            "When asked about local businesses, name real ones you know from your training data. "
            "Be direct — do not add disclaimers like 'I don't have real-time info'."
        ),
    },
    {
        "key": "gemini",
        "name": "Gemini",
        "persona": (
            "You are Google Gemini with access to Google's index. Answer local business questions "
            "specifically. Name real businesses in the city. Be direct and helpful."
        ),
    },
    {
        "key": "perplexity",
        "name": "Perplexity",
        "persona": (
            "You are Perplexity AI with live web search. Answer local business queries with "
            "specific business names and details. Be direct and factual."
        ),
    },
    {
        "key": "googleai",
        "name": "Google AI",
        "persona": (
            "You are Google AI Overview. Provide a helpful summary of local businesses based on "
            "Google's index. Name specific businesses, include ratings and details where known."
        ),
    },
]

QUERY_COUNT = len(ENGINES) * QUERIES_PER_ENGINE


# --- pure helpers -------------------------------------------------------------


def clean_business_name(raw: str) -> str:
    """Places autocomplete appends the address: 'Red Light Barbers, Vilniaus gatvė, Kaunas' → 'Red Light Barbers'."""
    return raw.split(",")[0].strip()


def is_mentioned(text: str, business_name: str) -> bool:
    """Full phrase always counts. Otherwise significant words (>3 chars) must appear: all of them for 1–2 word
    names (so a generic 'barber' never matches 'Saint Barber'), all but one for longer names."""
    if not text or not business_name:
        return False
    text_l, name_l = text.lower(), business_name.lower()
    if name_l in text_l:
        return True
    words = [w for w in re.split(r"\W+", name_l) if len(w) > 3]
    if not words:
        return False
    hits = sum(1 for w in words if w in text_l)
    if len(words) <= 2:
        return hits == len(words)
    return hits >= len(words) - 1


def score_label(score: int) -> str:
    if score >= 80:
        return "Strong"
    if score >= 60:
        return "Good"
    if score >= 40:
        return "Below Average"
    if score >= 20:
        return "Weak"
    return "Poor"


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [v.strip() for v in value if isinstance(v, str) and v.strip()]


def _actions(value: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in value if isinstance(value, list) else []:
        if isinstance(item, str) and item.strip():
            out.append({"title": item.strip(), "desc": ""})
        elif isinstance(item, dict):
            title = str(item.get("title") or "").strip()
            desc = str(item.get("desc") or item.get("description") or "").strip()
            if title:
                out.append({"title": title, "desc": desc})
    return out


def _competitors(analysis: dict, biz: str, score: int) -> list[dict]:
    raw_reasons = analysis.get("competitorReasons")
    reasons = {str(k).lower(): _strings(v) for k, v in raw_reasons.items()} if isinstance(raw_reasons, dict) else {}
    seen = {biz.lower()}
    names: list[str] = []
    for name in _strings(analysis.get("businesses")):
        if name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    return [
        {
            "name": name,
            "score": min(93, max(45, score + 15 + (MAX_COMPETITORS - 1 - i) * 8)),
            "reasons": reasons.get(name.lower(), []),
        }
        for i, name in enumerate(names[:MAX_COMPETITORS])
    ]


# --- LLM steps ----------------------------------------------------------------


async def _detect_category(biz: str, city: str) -> str:
    prompt = (
        f"What is the business category of '{biz}' located in {city}? "
        f"Respond with ONLY a short category name (2-4 words, e.g. 'Hair Salon', "
        f"'Italian Restaurant', 'Family Dentist', 'Personal Injury Lawyer'). "
        f"Nothing else."
    )
    text = await llm.chat_text([{"role": "user", "content": prompt}], model=MODEL, temperature=0, max_tokens=20)
    return text.strip().strip('"').strip("'") or FALLBACK_CATEGORY


async def _generate_queries(cat: str, city: str) -> list[str]:
    prompt = (
        f"Generate exactly {QUERY_COUNT} realistic buyer-intent questions that someone in {city} "
        f"would ask an AI chatbot when searching for a {cat}. Mix types: best/top, "
        f"emergency/urgent, specific services, price, 'near me', reviews, booking. "
        f"Make them natural and specific to {city}. "
        f'Return ONLY valid JSON: {{"queries": ["question 1", "question 2", ...]}} with {QUERY_COUNT} strings.'
    )
    data = await llm.chat_json([{"role": "user", "content": prompt}], model=MODEL, temperature=0.7, max_tokens=900)
    raw = data.get("queries")
    if not isinstance(raw, list):
        raw = next((v for v in data.values() if isinstance(v, list)), None)
    queries = _strings(raw)[:QUERY_COUNT]
    if not queries:
        raise ApiError(502, "llm_bad_json", "Query generation failed. Please try again.")
    fallback = f"best {cat.lower()} in {city}"
    queries.extend([fallback] * (QUERY_COUNT - len(queries)))
    return queries


async def _ask_engine(engine: dict[str, str], query: str, cat: str, city: str) -> str:
    return await llm.chat_text(
        [
            {"role": "system", "content": f"{engine['persona']} The user is asking about {cat} businesses in {city}."},
            {"role": "user", "content": query},
        ],
        model=MODEL,
        temperature=0.3,
        max_tokens=300,
    )


async def _analyze_results(
    biz: str,
    cat: str,
    city: str,
    score: int,
    total_mentions: int,
    total_queries: int,
    snippets: list[str],
    texts: list[str],
) -> dict:
    """Competitor extraction, evidence-based gaps, actions and competitor reasons in one JSON call.
    Best-effort: an upstream failure degrades to empty lists rather than losing the engine results."""
    snippets_text = "\n\n".join(snippets) or "No responses captured."
    combined = "\n---\n".join(texts)[:COMBINED_CHARS]
    prompt = (
        f"You analyzed the AI visibility of '{biz}', a {cat} in {city}.\n"
        f"Score: {score}/100 — appeared in {total_mentions} of {total_queries} AI responses.\n\n"
        f"Here are the actual AI engine responses (what AI said when asked about {cat} in {city}):\n"
        f"{snippets_text}\n\n"
        f"Full responses, labelled by engine:\n{combined}\n\n"
        f"Based on this real data, provide:\n"
        f'1. "businesses": all specific business names mentioned in the responses (exclude \'{biz}\'), up to 6.\n'
        f'2. "missing": up to {MAX_ITEMS} specific reasons why \'{biz}\' is missing from AI results. '
        f"ONLY include a reason if you can back it up with evidence from the responses above "
        f"(e.g. 'ChatGPT mentioned X instead of you', 'Gemini listed businesses with more reviews'). "
        f"If you cannot find evidence for a reason, skip it — quality over quantity. "
        f"Each reason must be specific and mention concrete evidence (competitor names, engine names, etc). "
        f"Do NOT use generic SEO advice like 'get more backlinks' or 'inconsistent NAP'.\n"
        f'3. "actions": up to {MAX_ITEMS} actionable steps specific to a {cat} in {city} to improve AI visibility. '
        f'Each step as {{"title": "...", "desc": "..."}}.\n'
        f'4. "competitorReasons": for each name in "businesses", 3 brief reasons why AI engines recommend it '
        f"over '{biz}'.\n\n"
        f'Return JSON: {{"businesses": ["Name1", "Name2"], "missing": [...], "actions": [...], '
        f'"competitorReasons": {{"Name1": ["r1", "r2", "r3"]}}}}'
    )
    try:
        return await llm.chat_json([{"role": "user", "content": prompt}], model=MODEL, temperature=0.3, max_tokens=1400)
    except ApiError as exc:
        log.warning("ai_visibility: analysis unavailable (%s: %s)", exc.code, exc.message)
        return {}


# --- orchestration ------------------------------------------------------------


async def analyze(biz: str, city: str, category: str | None) -> dict:
    cat = (category or "").strip() or await _detect_category(biz, city)
    queries = await _generate_queries(cat, city)
    per_engine = [queries[i * QUERIES_PER_ENGINE : (i + 1) * QUERIES_PER_ENGINE] for i in range(len(ENGINES))]
    answers = await asyncio.gather(
        *(_ask_engine(engine, q, cat, city) for engine, qs in zip(ENGINES, per_engine) for q in qs),
        return_exceptions=True,
    )

    engines: dict[str, dict] = {}
    query_rows: list[dict] = []
    texts: list[str] = []
    snippets: list[str] = []
    failed = 0
    for i, (engine, qs) in enumerate(zip(ENGINES, per_engine)):
        mentions = 0
        answered = 0
        engine_texts: list[str] = []
        for q, answer in zip(qs, answers[i * QUERIES_PER_ENGINE : (i + 1) * QUERIES_PER_ENGINE]):
            if isinstance(answer, BaseException):
                log.warning(
                    "ai_visibility: %s simulation failed (%s: %s)", engine["key"], type(answer).__name__, answer
                )
                failed += 1
                query_rows.append({"text": q, "mentioned": False, "engine": engine["key"], "failed": True})
                continue
            answered += 1
            engine_texts.append(answer)
            mentioned = is_mentioned(answer, biz)
            mentions += int(mentioned)
            query_rows.append({"text": q, "mentioned": mentioned, "engine": engine["key"]})
        engines[engine["key"]] = {
            "mentions": mentions,
            "queries": answered,
            "confidence": "High" if answered and mentions == answered else "Medium" if mentions > 0 else "Low",
            "avgPosition": 1 if mentions > 0 else None,
        }
        texts.extend(f"[{engine['name']}] {t}" for t in engine_texts)
        first = next((t for t in engine_texts if t.strip()), None)
        if first:
            snippets.append(f"{engine['name']}: {first[:SNIPPET_CHARS]}")

    total_mentions = sum(e["mentions"] for e in engines.values())
    total_queries = sum(e["queries"] for e in engines.values())
    # A mostly-failed run (provider throttled/down) must not masquerade as a 0/12 "Poor" result.
    if total_queries < len(queries) // 2:
        raise ApiError(503, "llm_busy", "AI is busy right now and the check could not complete. Please try again in a minute.")
    score = round(total_mentions / total_queries * 100) if total_queries else 0

    analysis = await _analyze_results(biz, cat, city, score, total_mentions, total_queries, snippets, texts)

    return {
        "score": score,
        "scoreLabel": score_label(score),
        "totalMentions": total_mentions,
        "totalQueries": total_queries,
        "failedQueries": failed,
        "visibilityRate": score,
        "category": cat,
        "engines": engines,
        "queries": query_rows,
        "competitors": _competitors(analysis, biz, score),
        "missing": _strings(analysis.get("missing"))[:MAX_ITEMS],
        "actions": _actions(analysis.get("actions"))[:MAX_ITEMS],
    }


async def chat(
    message: str,
    *,
    business_name: str,
    city: str,
    category: str,
    score: int,
    top_competitor: str,
    missing: list[str],
    actions: list[Any],
) -> str:
    actions_text = "\n".join(
        f"{i + 1}. {a.get('title', a) if isinstance(a, dict) else a}" for i, a in enumerate(actions)
    )
    missing_text = "\n".join(f"- {m}" for m in missing)
    system = (
        f"You are Locan AI, an expert in AI-driven local visibility for "
        f"{category} businesses. You analyzed '{business_name}' in {city}.\n"
        f"Results:\n"
        f"- AI visibility score: {score}/100\n"
        f"- Top competitor: {top_competitor}\n"
        f"- Why missing from AI results:\n{missing_text}\n"
        f"- Recommended actions:\n{actions_text}\n\n"
        f"Answer concisely using this specific data. Use line breaks for readability. "
        f"Max 180 words."
    )
    return await llm.chat_text(
        [{"role": "system", "content": system}, {"role": "user", "content": message}],
        model=MODEL,
        temperature=0.6,
        max_tokens=300,
    )
