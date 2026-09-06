"""LLM access. Every model call in the API goes through chat_text()/chat_json() so tests can monkeypatch them.

Providers (chosen by Settings.llm_provider):
  - replicate: OpenAI models hosted on Replicate (default openai/gpt-5-nano) via the predictions API
  - openai:    OpenAI API directly (legacy fallback)
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Protocol

import httpx

from ..config import Settings
from ..errors import ApiError

DEFAULT_MODEL = "gpt-4o-mini"  # only meaningful for the openai provider; replicate uses Settings.llm_model
REPLICATE_API = "https://api.replicate.com/v1"
JSON_INSTRUCTION = "Respond with a single valid JSON object only. No prose before or after it, no code fences."


class LlmProvider(Protocol):
    async def complete(self, messages: list[dict[str, str]], *, max_tokens: int, temperature: float, json_mode: bool) -> str: ...


class OpenAIProvider:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def complete(self, messages, *, max_tokens, temperature, json_mode) -> str:
        from openai import OpenAIError

        kwargs: dict[str, Any] = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = await self._client.chat.completions.create(
                model=self._model, messages=messages, temperature=temperature, max_tokens=max_tokens, **kwargs
            )
        except OpenAIError as exc:
            raise ApiError(502, "llm_upstream", f"AI request failed: {exc.__class__.__name__}") from exc
        return (resp.choices[0].message.content or "").strip()


class ReplicateProvider:
    """Runs `owner/name` models on Replicate. Blocks with `Prefer: wait`, then polls until done or deadline."""

    def __init__(
        self,
        token: str,
        model: str,
        http: httpx.AsyncClient,
        reasoning_effort: str = "minimal",
        verbosity: str = "low",
        wait_s: int = 30,
        deadline_s: float = 45.0,
        max_concurrency: int = 8,
    ) -> None:
        self._token = token
        self._model = model
        self._http = http
        self._reasoning = reasoning_effort
        self._verbosity = verbosity
        self._wait = wait_s
        self._deadline = deadline_s
        self._sem = asyncio.Semaphore(max_concurrency)

    def _headers(self, wait: bool) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}
        if wait:
            h["Prefer"] = f"wait={self._wait}"
        return h

    @staticmethod
    def build_input(
        messages: list[dict[str, str]], *, max_tokens: int, json_mode: bool, reasoning: str, verbosity: str
    ) -> dict:
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        convo = [{"role": m["role"], "content": m["content"]} for m in messages if m.get("role") != "system"]
        if json_mode:
            system_parts.append(JSON_INSTRUCTION)
        if not convo:  # a system-only prompt still needs a user turn
            convo = [{"role": "user", "content": "Proceed."}]
        payload: dict[str, Any] = {
            "messages": convo,
            # GPT-5 counts reasoning tokens against the completion budget; keep headroom even at minimal effort.
            "max_completion_tokens": max(128, max_tokens + 128),
            "reasoning_effort": reasoning,
            "verbosity": verbosity,
        }
        if system_parts:
            payload["system_prompt"] = "\n\n".join(system_parts)
        return payload

    async def _create(self, body: dict, started: float) -> httpx.Response:
        """POST the prediction; on 429 wait for `retry_after` (bounded by the deadline) and retry."""
        while True:
            try:
                resp = await self._http.post(
                    f"{REPLICATE_API}/models/{self._model}/predictions", json=body, headers=self._headers(wait=True)
                )
            except httpx.HTTPError as exc:
                raise ApiError(502, "llm_upstream", f"AI request failed: {exc.__class__.__name__}") from exc
            if resp.status_code != 429:
                return resp
            try:
                retry_after = float(resp.json().get("retry_after", 2))
            except ValueError:
                retry_after = 2.0
            retry_after = min(max(retry_after, 0.5), 12.0)
            if time.monotonic() - started + retry_after > self._deadline:
                raise ApiError(503, "llm_busy", "AI is busy right now. Please try again in a minute.")
            await asyncio.sleep(retry_after)

    async def complete(self, messages, *, max_tokens, temperature, json_mode) -> str:
        body = {
            "input": self.build_input(
                messages, max_tokens=max_tokens, json_mode=json_mode, reasoning=self._reasoning, verbosity=self._verbosity
            )
        }
        started = time.monotonic()
        async with self._sem:
            resp = await self._create(body, started)
        if resp.status_code >= 400:
            raise ApiError(502, "llm_upstream", f"AI provider returned HTTP {resp.status_code}.")
        pred = resp.json()

        while pred.get("status") in ("starting", "processing"):
            if time.monotonic() - started > self._deadline:
                raise ApiError(504, "llm_timeout", "AI is taking too long right now. Please try again.")
            await asyncio.sleep(1.0)
            get_url = (pred.get("urls") or {}).get("get")
            if not get_url:
                raise ApiError(502, "llm_upstream", "AI provider returned an incomplete prediction.")
            try:
                poll = await self._http.get(get_url, headers=self._headers(wait=False))
            except httpx.HTTPError as exc:
                raise ApiError(502, "llm_upstream", f"AI request failed: {exc.__class__.__name__}") from exc
            if poll.status_code >= 400:
                raise ApiError(502, "llm_upstream", f"AI provider returned HTTP {poll.status_code}.")
            pred = poll.json()

        if pred.get("status") != "succeeded":
            raise ApiError(502, "llm_upstream", f"AI prediction {pred.get('status', 'failed')}.")
        output = pred.get("output")
        text = "".join(str(chunk) for chunk in output) if isinstance(output, list) else str(output or "")
        return text.strip()


_provider: LlmProvider | None = None


def configure(settings: Settings, http: httpx.AsyncClient | None = None) -> None:
    global _provider
    _provider = None
    if settings.llm_provider == "replicate" and settings.replicate_api_token:
        client = http or httpx.AsyncClient(timeout=httpx.Timeout(70.0))
        _provider = ReplicateProvider(
            settings.replicate_api_token,
            settings.llm_model,
            client,
            reasoning_effort=settings.llm_reasoning_effort,
            verbosity=settings.llm_verbosity,
        )
    elif settings.llm_provider == "openai" and settings.openai_api_key:
        _provider = OpenAIProvider(settings.openai_api_key)


def _require_provider() -> LlmProvider:
    if _provider is None:
        raise ApiError(503, "llm_not_configured", "AI features are temporarily unavailable. Please try again later.")
    return _provider


def extract_json(text: str) -> Any:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", text)
        if m:
            return json.loads(m.group())
        raise


async def chat_text(
    messages: list[dict[str, str]],
    model: str = DEFAULT_MODEL,
    temperature: float = 0.4,
    max_tokens: int = 800,
) -> str:
    return await _require_provider().complete(messages, max_tokens=max_tokens, temperature=temperature, json_mode=False)


async def chat_json(
    messages: list[dict[str, str]],
    model: str = DEFAULT_MODEL,
    temperature: float = 0.4,
    max_tokens: int = 1500,
) -> dict:
    content = await _require_provider().complete(messages, max_tokens=max_tokens, temperature=temperature, json_mode=True)
    try:
        data = extract_json(content or "{}")
    except (json.JSONDecodeError, ValueError) as exc:
        raise ApiError(502, "llm_bad_json", "AI returned an unreadable response. Please try again.") from exc
    if not isinstance(data, dict):
        raise ApiError(502, "llm_bad_json", "AI returned an unexpected response. Please try again.")
    return data
