from __future__ import annotations

import httpx
import pytest
import respx

from app.config import Settings
from app.errors import ApiError
from app.services import llm
from app.services.llm import REPLICATE_API, ReplicateProvider


def _settings(**kw) -> Settings:
    base = dict(env="test", replicate_api_token="r8_test", llm_provider="replicate", llm_model="openai/gpt-5-nano")
    base.update(kw)
    return Settings(**base)


def test_build_input_maps_system_and_json_instruction():
    payload = ReplicateProvider.build_input(
        [{"role": "system", "content": "Be terse."}, {"role": "user", "content": "Hi"}],
        max_tokens=300,
        json_mode=True,
        reasoning="minimal",
        verbosity="low",
    )
    assert payload["messages"] == [{"role": "user", "content": "Hi"}]
    assert payload["system_prompt"].startswith("Be terse.") and "valid JSON object" in payload["system_prompt"]
    assert payload["max_completion_tokens"] == 428
    assert payload["reasoning_effort"] == "minimal" and payload["verbosity"] == "low"


def test_build_input_without_system_or_user():
    payload = ReplicateProvider.build_input([{"role": "system", "content": "x"}], max_tokens=10, json_mode=False, reasoning="low", verbosity="medium")
    assert payload["messages"] == [{"role": "user", "content": "Proceed."}]
    assert "system_prompt" in payload and "valid JSON" not in payload["system_prompt"]


@pytest.fixture
def replicate_mock():
    with respx.mock(base_url=REPLICATE_API, assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def provider():
    llm.configure(_settings(), httpx.AsyncClient())
    yield
    llm.configure(_settings(replicate_api_token=""))


async def test_chat_json_joins_chunks_and_parses(replicate_mock, provider):
    route = replicate_mock.post("/models/openai/gpt-5-nano/predictions").mock(
        return_value=httpx.Response(201, json={"status": "succeeded", "output": ['{"a": ', "[1, 2]", "}"]})
    )
    data = await llm.chat_json([{"role": "user", "content": "give json"}], max_tokens=200)
    assert data == {"a": [1, 2]}
    req = route.calls.last.request
    assert req.headers["Authorization"] == "Bearer r8_test"
    assert req.headers["Prefer"].startswith("wait=")
    body = req.read().decode()
    assert '"reasoning_effort": "minimal"' in body or '"reasoning_effort":"minimal"' in body


async def test_chat_text_polls_until_succeeded(replicate_mock, provider, monkeypatch):
    async def no_sleep(_):
        return None

    monkeypatch.setattr(llm.asyncio, "sleep", no_sleep)
    replicate_mock.post("/models/openai/gpt-5-nano/predictions").mock(
        return_value=httpx.Response(201, json={"status": "processing", "urls": {"get": f"{REPLICATE_API}/predictions/p1"}})
    )
    replicate_mock.get("/predictions/p1").mock(
        side_effect=[
            httpx.Response(200, json={"status": "processing", "urls": {"get": f"{REPLICATE_API}/predictions/p1"}}),
            httpx.Response(200, json={"status": "succeeded", "output": ["Hello", " world"]}),
        ]
    )
    assert await llm.chat_text([{"role": "user", "content": "hi"}]) == "Hello world"


async def test_failed_prediction_is_502(replicate_mock, provider):
    replicate_mock.post("/models/openai/gpt-5-nano/predictions").mock(
        return_value=httpx.Response(201, json={"status": "failed", "error": "boom"})
    )
    with pytest.raises(ApiError) as exc:
        await llm.chat_text([{"role": "user", "content": "hi"}])
    assert exc.value.status == 502 and exc.value.code == "llm_upstream"


async def test_http_error_is_502(replicate_mock, provider):
    replicate_mock.post("/models/openai/gpt-5-nano/predictions").mock(return_value=httpx.Response(401, json={"detail": "bad token"}))
    with pytest.raises(ApiError) as exc:
        await llm.chat_json([{"role": "user", "content": "hi"}])
    assert exc.value.status == 502


async def test_429_is_retried_after_retry_after(replicate_mock, provider, monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(llm.asyncio, "sleep", fake_sleep)
    replicate_mock.post("/models/openai/gpt-5-nano/predictions").mock(
        side_effect=[
            httpx.Response(429, json={"detail": "throttled", "status": 429, "retry_after": 3}),
            httpx.Response(201, json={"status": "succeeded", "output": ["OK"]}),
        ]
    )
    assert await llm.chat_text([{"role": "user", "content": "hi"}]) == "OK"
    assert sleeps == [3.0]


async def test_429_past_deadline_is_503_busy(replicate_mock, monkeypatch):
    async def fake_sleep(_):
        return None

    monkeypatch.setattr(llm.asyncio, "sleep", fake_sleep)
    llm._provider = ReplicateProvider("r8_test", "openai/gpt-5-nano", httpx.AsyncClient(), deadline_s=1.0)
    replicate_mock.post("/models/openai/gpt-5-nano/predictions").mock(
        return_value=httpx.Response(429, json={"detail": "throttled", "status": 429, "retry_after": 10})
    )
    with pytest.raises(ApiError) as exc:
        await llm.chat_text([{"role": "user", "content": "hi"}])
    assert exc.value.status == 503 and exc.value.code == "llm_busy"
    llm.configure(_settings(replicate_api_token=""))


async def test_bad_json_is_llm_bad_json(replicate_mock, provider):
    replicate_mock.post("/models/openai/gpt-5-nano/predictions").mock(
        return_value=httpx.Response(201, json={"status": "succeeded", "output": ["not json at all"]})
    )
    with pytest.raises(ApiError) as exc:
        await llm.chat_json([{"role": "user", "content": "hi"}])
    assert exc.value.code == "llm_bad_json"


async def test_not_configured_when_token_missing():
    llm.configure(_settings(replicate_api_token=""))
    with pytest.raises(ApiError) as exc:
        await llm.chat_text([{"role": "user", "content": "hi"}])
    assert exc.value.status == 503 and exc.value.code == "llm_not_configured"


def test_disabled_sentinel_means_not_configured(monkeypatch):
    monkeypatch.setenv("REPLICATE_API_TOKEN", "disabled")
    monkeypatch.setenv("LLM_PROVIDER", "replicate")
    assert Settings.from_env().replicate_api_token == ""
