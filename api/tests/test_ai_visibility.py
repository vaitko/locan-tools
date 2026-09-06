from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.services.ai_visibility import ENGINES, clean_business_name, is_mentioned, score_label

ANALYZE_URL = "/api/tools/ai-visibility"
CHAT_URL = "/api/tools/ai-visibility/chat"

BIZ = "Red Light Barbers"
CITY = "Kaunas"
QUERIES = [f"query {i} about barbers in Kaunas" for i in range(12)]
MENTION = "Locals love Red Light Barbers for sharp fades."
NO_MENTION = "Smile Cuts and Fade Lab are popular choices."
# chatgpt 3/3, gemini 1/3, perplexity 1/3, googleai 0/3 → 5 of 12 → round(41.67) = 42
ENGINE_TEXTS = [MENTION] * 4 + [NO_MENTION] * 2 + [MENTION] + [NO_MENTION] * 5
ANALYSIS = {
    "businesses": ["Smile Cuts", "Red Light Barbers", "Fade Lab"],
    "missing": ["m1"],
    "actions": [{"title": "t", "desc": "d"}],
    "competitorReasons": {"smile cuts": ["r1"]},
}
CHAT_BODY = {
    "message": "What should I do first?",
    "businessName": BIZ,
    "city": CITY,
    "category": "Barbershop",
    "score": 42,
    "topCompetitor": "Smile Cuts",
    "missing": ["m1", "m2"],
    "actions": [{"title": "Collect reviews", "desc": "d"}, "Add photos"],
}


def _queue_analysis(fake_llm, *, detect_category=True, engine_texts=ENGINE_TEXTS, queries=QUERIES, analysis=ANALYSIS):
    if detect_category:
        fake_llm.text_responses.append("Barbershop")
    fake_llm.text_responses.extend(engine_texts)
    fake_llm.json_responses.extend([{"queries": list(queries)}, analysis])


# --- pure helpers -----------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "name", "expected"),
    [
        ("Locals love Fadelab for sharp fades.", "FadeLab", True),  # 1 word, case-insensitive
        ("Smile Cuts is great.", "FadeLab", False),
        ("The best barber in Kaunas is Smile Cuts.", "Saint Barber", False),  # 2 words: generic word alone is not enough
        ("Saint runs a barber shop downtown.", "Saint Barber", True),  # 2 words: both present
        ("Red Light in Kaunas is great.", "Red Light Barbers Kaunas", True),  # 3 significant words: one may be missing
        ("Kaunas has many shops.", "Red Light Barbers Kaunas", False),  # two missing
        ("Try RED LIGHT BARBERS KAUNAS now.", "Red Light Barbers Kaunas", True),  # full phrase
        ("we love it", "Bob", False),  # no significant words, no phrase
        ("", "FadeLab", False),
        ("some text", "", False),
    ],
)
def test_is_mentioned(text, name, expected):
    assert is_mentioned(text, name) is expected


def test_clean_business_name():
    assert clean_business_name("Red Light Barbers Kaunas, Vilniaus gatvė, Kaunas") == "Red Light Barbers Kaunas"
    assert clean_business_name("  Fade Lab ") == "Fade Lab"
    assert clean_business_name("") == ""


@pytest.mark.parametrize(
    ("score", "label"),
    [
        (100, "Strong"),
        (80, "Strong"),
        (79, "Good"),
        (60, "Good"),
        (59, "Below Average"),
        (40, "Below Average"),
        (39, "Weak"),
        (20, "Weak"),
        (19, "Poor"),
        (0, "Poor"),
    ],
)
def test_score_label(score, label):
    assert score_label(score) == label


def test_engines_are_the_four_legacy_personas():
    assert [e["key"] for e in ENGINES] == ["chatgpt", "gemini", "perplexity", "googleai"]
    assert [e["name"] for e in ENGINES] == ["ChatGPT", "Gemini", "Perplexity", "Google AI"]


# --- analyze endpoint -------------------------------------------------------


async def test_analyze_end_to_end(client, fake_llm):
    _queue_analysis(fake_llm)

    r = await client.post(ANALYZE_URL, json={"businessName": f"{BIZ}, Vilniaus g., Kaunas", "city": CITY})

    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["score"], d["scoreLabel"], d["visibilityRate"]) == (42, "Below Average", 42)
    assert (d["totalMentions"], d["totalQueries"]) == (5, 12)
    assert d["category"] == "Barbershop"
    assert list(d["engines"]) == ["chatgpt", "gemini", "perplexity", "googleai"]
    assert d["engines"]["chatgpt"] == {"mentions": 3, "queries": 3, "confidence": "High", "avgPosition": 1}
    assert d["engines"]["gemini"] == {"mentions": 1, "queries": 3, "confidence": "Medium", "avgPosition": 1}
    assert d["engines"]["googleai"] == {"mentions": 0, "queries": 3, "confidence": "Low", "avgPosition": None}
    assert len(d["queries"]) == 12
    assert d["queries"][0] == {"text": QUERIES[0], "mentioned": True, "engine": "chatgpt", "failed": False}
    assert d["queries"][4] == {"text": QUERIES[4], "mentioned": False, "engine": "gemini", "failed": False}
    assert d["queries"][11] == {"text": QUERIES[11], "mentioned": False, "engine": "googleai", "failed": False}
    assert d["competitors"] == [
        {"name": "Smile Cuts", "score": 73, "reasons": ["r1"]},
        {"name": "Fade Lab", "score": 65, "reasons": []},
    ]
    assert d["missing"] == ["m1"]
    assert d["actions"] == [{"title": "t", "desc": "d"}]

    assert len(fake_llm.calls) == 15
    assert [c["kind"] for c in fake_llm.calls] == ["text", "json"] + ["text"] * 12 + ["json"]
    assert all(c["model"] == "gpt-4o-mini" for c in fake_llm.calls)

    category_prompt = fake_llm.calls[0]["messages"][0]["content"]
    assert f"'{BIZ}' located in {CITY}?" in category_prompt
    assert "Lithuania" not in category_prompt
    assert '"queries"' in fake_llm.calls[1]["messages"][0]["content"]

    system, user = fake_llm.calls[2]["messages"]
    assert system["role"] == "system"
    assert system["content"].startswith(ENGINES[0]["persona"])
    assert system["content"].endswith(f"The user is asking about Barbershop businesses in {CITY}.")
    assert user == {"role": "user", "content": QUERIES[0]}
    assert fake_llm.calls[5]["messages"][0]["content"].startswith(ENGINES[1]["persona"])

    analysis_prompt = fake_llm.calls[14]["messages"][0]["content"]
    assert "Score: 42/100 — appeared in 5 of 12 AI responses." in analysis_prompt
    assert f"ChatGPT: {MENTION}" in analysis_prompt
    assert f"Gemini: {MENTION}" in analysis_prompt
    assert f"[Google AI] {NO_MENTION}" in analysis_prompt
    assert '"competitorReasons"' in analysis_prompt
    assert "Do NOT use generic SEO advice" in analysis_prompt


async def test_analyze_skips_category_detection_when_provided(client, fake_llm):
    _queue_analysis(fake_llm, detect_category=False)

    r = await client.post(ANALYZE_URL, json={"businessName": BIZ, "city": CITY, "category": "Barber Shop"})

    assert r.status_code == 200, r.text
    assert r.json()["category"] == "Barber Shop"
    assert len(fake_llm.calls) == 14
    assert fake_llm.calls[0]["kind"] == "json"
    assert "searching for a Barber Shop" in fake_llm.calls[0]["messages"][0]["content"]


async def test_analyze_falls_back_to_local_business_when_category_detection_is_empty(client, fake_llm):
    _queue_analysis(fake_llm, detect_category=False)
    fake_llm.text_responses.insert(0, '""')

    r = await client.post(ANALYZE_URL, json={"businessName": BIZ, "city": CITY})

    assert r.status_code == 200, r.text
    assert r.json()["category"] == "Local Business"


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (QUERIES[:10], QUERIES[:10] + ["best barbershop in Kaunas"] * 2),
        (QUERIES + ["extra 1", "extra 2"], QUERIES),
    ],
)
async def test_analyze_pads_and_truncates_queries_to_twelve(client, fake_llm, given, expected):
    _queue_analysis(fake_llm, detect_category=False, queries=given)

    r = await client.post(ANALYZE_URL, json={"businessName": BIZ, "city": CITY, "category": "Barbershop"})

    assert r.status_code == 200, r.text
    assert [q["text"] for q in r.json()["queries"]] == expected
    assert len(fake_llm.calls) == 14


@pytest.mark.parametrize("payload", [{"queries": "not a list"}, {"queries": []}, {"foo": "bar"}])
async def test_analyze_502_when_query_generation_returns_no_list(client, fake_llm, payload):
    fake_llm.json_responses.append(payload)

    r = await client.post(ANALYZE_URL, json={"businessName": BIZ, "city": CITY, "category": "Barbershop"})

    assert r.status_code == 502
    assert r.json() == {"error": "Query generation failed. Please try again.", "code": "llm_bad_json"}
    assert len(fake_llm.calls) == 1


async def test_analyze_excludes_failed_engine_calls_from_the_score(client, fake_llm):
    # Only 10 answers queued: the fake raises for the last two simulations, which are excluded, not counted as misses.
    _queue_analysis(fake_llm, detect_category=False, engine_texts=[MENTION] * 10)

    r = await client.post(ANALYZE_URL, json={"businessName": BIZ, "city": CITY, "category": "Barbershop"})

    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["totalMentions"], d["totalQueries"], d["failedQueries"], d["score"]) == (10, 10, 2, 100)
    assert d["engines"]["googleai"] == {"mentions": 1, "queries": 1, "confidence": "High", "avgPosition": 1}
    assert [q["failed"] for q in d["queries"]][-2:] == [True, True]
    assert all(q["mentioned"] is False for q in d["queries"][-2:])


async def test_analyze_503_when_most_engine_calls_fail(client, fake_llm):
    # 5 of 12 simulations answer (< half) → the run is reported as busy instead of a fake 0 score.
    _queue_analysis(fake_llm, detect_category=False, engine_texts=[MENTION] * 5)

    r = await client.post(ANALYZE_URL, json={"businessName": BIZ, "city": CITY, "category": "Barbershop"})

    assert r.status_code == 503
    assert r.json()["code"] == "llm_busy"


async def test_analyze_tolerates_missing_analysis_keys(client, fake_llm):
    _queue_analysis(fake_llm, detect_category=False, analysis={"businesses": ["Fade Lab", "fade lab", BIZ.lower()]})

    r = await client.post(ANALYZE_URL, json={"businessName": BIZ, "city": CITY, "category": "Barbershop"})

    assert r.status_code == 200, r.text
    d = r.json()
    assert d["competitors"] == [{"name": "Fade Lab", "score": 73, "reasons": []}]
    assert d["missing"] == [] and d["actions"] == []


@pytest.mark.parametrize(
    "body",
    [
        {"businessName": BIZ},
        {"businessName": BIZ, "city": ""},
        {"businessName": BIZ, "city": "   "},
        {"city": CITY},
        {"businessName": ", Kaunas", "city": CITY},
        {"businessName": BIZ, "city": CITY, "category": "x" * 81},
    ],
)
async def test_analyze_rejects_invalid_requests(client, fake_llm, body):
    r = await client.post(ANALYZE_URL, json=body)

    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"
    assert fake_llm.calls == []


# --- chat endpoint ----------------------------------------------------------


async def test_chat_returns_reply(client, fake_llm):
    fake_llm.text_responses.append("Focus on Smile Cuts' review volume first.")

    r = await client.post(CHAT_URL, json=CHAT_BODY)

    assert r.status_code == 200, r.text
    assert r.json() == {"reply": "Focus on Smile Cuts' review volume first."}
    assert len(fake_llm.calls) == 1
    assert fake_llm.calls[0]["model"] == "gpt-4o-mini"
    system, user = fake_llm.calls[0]["messages"]
    assert system["role"] == "system"
    assert system["content"].startswith(
        "You are Locan AI, an expert in AI-driven local visibility for Barbershop businesses. "
        f"You analyzed '{BIZ}' in {CITY}."
    )
    assert "- AI visibility score: 42/100\n- Top competitor: Smile Cuts\n" in system["content"]
    assert "- m1\n- m2" in system["content"]
    assert "1. Collect reviews\n2. Add photos" in system["content"]
    assert system["content"].endswith("Max 180 words.")
    assert user == {"role": "user", "content": "What should I do first?"}


@pytest.mark.parametrize("override", [{"message": ""}, {"message": "x" * 1001}, {"score": "high"}, {"missing": None}])
async def test_chat_rejects_invalid_requests(client, fake_llm, override):
    r = await client.post(CHAT_URL, json={**CHAT_BODY, **override})

    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"
    assert fake_llm.calls == []


# --- quota ------------------------------------------------------------------


async def test_ai_visibility_429_after_per_ip_quota(fake_llm):
    cfg = Settings(
        env="test",
        openai_api_key="test-openai",
        allowed_origins=["http://testserver"],
        quota_limits={"autocomplete_ip": 10, "details_ip": 10, "tool_ip": 1, "tools_global": 10, "autocomplete_global": 10},
    )
    app = create_app(cfg)
    _queue_analysis(fake_llm)
    _queue_analysis(fake_llm)
    fake_llm.text_responses.append("chat reply")
    body = {"businessName": BIZ, "city": CITY}
    headers = {"x-forwarded-for": "9.9.9.9, 10.0.0.1"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        ok = await c.post(ANALYZE_URL, json=body, headers=headers)
        assert ok.status_code == 200, ok.text
        blocked = await c.post(ANALYZE_URL, json=body, headers=headers)
        assert blocked.status_code == 429
        assert blocked.json()["code"] == "quota_exceeded"
        assert len(fake_llm.calls) == 15  # the blocked request never reached the model
        other = await c.post(ANALYZE_URL, json=body, headers={"x-forwarded-for": "8.8.8.8"})
        assert other.status_code == 200, other.text
        # chat has its own per-IP scope, so the analyze limit does not block it
        chat = await c.post(CHAT_URL, json=CHAT_BODY, headers=headers)
        assert chat.status_code == 200, chat.text
        blocked_chat = await c.post(CHAT_URL, json=CHAT_BODY, headers=headers)
        assert blocked_chat.status_code == 429
