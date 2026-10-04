"""The model layer is provider-agnostic; the safety guarantees do not live here.

These check the dispatch and the fail-closed behaviour, without calling any API.
"""
import pytest

from app import llm
from app.config import settings
from app.llm import LLMUnavailable


def test_missing_key_is_unavailable_not_a_crash(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    with pytest.raises(LLMUnavailable):
        llm._complete("sys", [{"role": "user", "content": "hi"}], 100, want_json=False)


def test_openai_missing_key_is_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "")
    with pytest.raises(LLMUnavailable):
        llm._complete("sys", [{"role": "user", "content": "hi"}], 100, want_json=True)


def test_openai_path_calls_chat_completions(monkeypatch):
    """With a key, the OpenAI branch builds a chat call and returns its text."""
    captured = {}

    class FakeChoice:
        def __init__(self, text):
            self.message = type("M", (), {"content": text})

    class FakeResp:
        def __init__(self, text):
            self.choices = [FakeChoice(text)]

    class FakeChat:
        class completions:
            @staticmethod
            def create(**kwargs):
                captured.update(kwargs)
                return FakeResp('{"ok": true}')

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "openai_model", "gpt-4o-mini")
    monkeypatch.setattr(llm, "_openai_client", lambda k: FakeClient())

    out = llm._complete("system here", [{"role": "user", "content": "hi"}], 200, want_json=True)
    assert out == '{"ok": true}'
    assert captured["model"] == "gpt-4o-mini"
    assert captured["response_format"] == {"type": "json_object"}
    # system prompt is prepended as a system message
    assert captured["messages"][0] == {"role": "system", "content": "system here"}


def test_classify_and_compose_work_over_openai(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(llm, "_complete",
                        lambda system, messages, max_tokens, want_json, model=None:
                        '{"intent":"info","language":"en"}' if want_json else "Hello there.")
    assert llm.classify("hi", ["oil_change"])["intent"] == "info"
    assert llm.compose("Garage", "- fact", "hi") == "Hello there."
