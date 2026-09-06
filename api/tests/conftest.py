from __future__ import annotations

import pytest
import respx
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def cfg() -> Settings:
    return Settings(
        env="test",
        openai_api_key="test-openai",
        google_places_api_key="test-places",
        allowed_origins=["http://testserver"],
        quota_table=None,
    )


@pytest.fixture
def app(cfg: Settings):
    return create_app(cfg)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.fixture
def places_mock():
    with respx.mock(base_url="https://places.googleapis.com", assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def fake_llm(monkeypatch):
    """Replace both LLM entry points; tests set .json_responses / .text_responses queues."""
    from app.services import llm

    class Fake:
        def __init__(self) -> None:
            self.json_responses: list[dict] = []
            self.text_responses: list[str] = []
            self.calls: list[dict] = []

        async def chat_json(self, messages, model="gpt-4o-mini", temperature=0.4, max_tokens=1500):
            self.calls.append({"kind": "json", "messages": messages, "model": model})
            if not self.json_responses:
                raise AssertionError("fake_llm.json_responses exhausted")
            return self.json_responses.pop(0)

        async def chat_text(self, messages, model="gpt-4o-mini", temperature=0.4, max_tokens=800):
            self.calls.append({"kind": "text", "messages": messages, "model": model})
            if not self.text_responses:
                raise AssertionError("fake_llm.text_responses exhausted")
            return self.text_responses.pop(0)

    fake = Fake()
    monkeypatch.setattr(llm, "chat_json", fake.chat_json)
    monkeypatch.setattr(llm, "chat_text", fake.chat_text)
    return fake
