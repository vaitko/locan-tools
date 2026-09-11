from __future__ import annotations

from app.config import Settings
from app.services import llm


class _FakeAsyncOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_openai_provider_passes_base_url_and_api_key(monkeypatch):
    import openai

    monkeypatch.setattr(openai, "AsyncOpenAI", _FakeAsyncOpenAI)
    provider = llm.OpenAIProvider("local", "llama3.1", "http://localhost:11434/v1")
    assert provider._client.kwargs == {"api_key": "local", "base_url": "http://localhost:11434/v1"}
    assert provider._model == "llama3.1"


def test_openai_provider_base_url_none_when_empty(monkeypatch):
    import openai

    monkeypatch.setattr(openai, "AsyncOpenAI", _FakeAsyncOpenAI)
    provider = llm.OpenAIProvider("sk-test")
    assert provider._client.kwargs == {"api_key": "sk-test", "base_url": None}


def test_configure_openai_uses_local_key_and_llm_model_when_base_url_set_and_no_key(monkeypatch):
    import openai

    monkeypatch.setattr(openai, "AsyncOpenAI", _FakeAsyncOpenAI)
    cfg = Settings(
        llm_provider="openai", openai_api_key="", openai_base_url="http://localhost:11434/v1", llm_model="llama3.1"
    )
    llm.configure(cfg)
    provider = llm._provider
    assert isinstance(provider, llm.OpenAIProvider)
    assert provider._client.kwargs == {"api_key": "local", "base_url": "http://localhost:11434/v1"}
    assert provider._model == "llama3.1"


def test_configure_openai_passes_llm_model_through_unchanged(monkeypatch):
    import openai

    monkeypatch.setattr(openai, "AsyncOpenAI", _FakeAsyncOpenAI)
    cfg = Settings(llm_provider="openai", openai_api_key="sk-test")
    llm.configure(cfg)
    assert llm._provider._model == cfg.llm_model
    assert llm._provider._model != llm.DEFAULT_MODEL

    cfg = Settings(llm_provider="openai", openai_api_key="sk-test", llm_model="gpt-4o-mini")
    llm.configure(cfg)
    assert llm._provider._model == "gpt-4o-mini"


def test_configure_openai_stays_unconfigured_without_key_or_base_url(monkeypatch):
    import openai

    monkeypatch.setattr(openai, "AsyncOpenAI", _FakeAsyncOpenAI)
    cfg = Settings(llm_provider="openai", openai_api_key="", openai_base_url="")
    llm.configure(cfg)
    assert llm._provider is None
