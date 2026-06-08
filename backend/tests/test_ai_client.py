from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ai_client import AIChatRequest, AnthropicMessagesClient, provider_extra_body


def test_agent_model_stream_uses_teaching_system_prompt(monkeypatch):
    from app.agent_runtime import model

    calls = {}

    def fake_stream_chat_messages(messages, *, system, max_tokens, thinking_mode=None, client=None):
        calls["messages"] = messages
        calls["system"] = system
        calls["max_tokens"] = max_tokens
        calls["thinking_mode"] = thinking_mode
        calls["client"] = client
        return iter(["ok"])

    monkeypatch.setattr(model, "stream_chat_messages", fake_stream_chat_messages)

    chunks = list(model.stream_agent_model_messages([{"role": "user", "content": "hi"}], thinking_mode="enabled"))

    assert chunks == ["ok"]
    assert calls["messages"] == [{"role": "user", "content": "hi"}]
    assert "算法题学习教练" in calls["system"]
    assert calls["max_tokens"] == 1800
    assert calls["thinking_mode"] == "enabled"
    assert calls["client"] is None


def test_legacy_coach_stream_wrapper_delegates_to_agent_model(monkeypatch):
    from app import coach

    calls = {}

    def fake_stream_agent_model_messages(messages, *, thinking_mode=None):
        calls["messages"] = messages
        calls["thinking_mode"] = thinking_mode
        return iter(["compat"])

    monkeypatch.setattr(coach, "stream_agent_model_messages", fake_stream_agent_model_messages)

    chunks = list(coach.call_claude_messages_stream([{"role": "user", "content": "hi"}], thinking_mode="disabled"))

    assert chunks == ["compat"]
    assert calls == {
        "messages": [{"role": "user", "content": "hi"}],
        "thinking_mode": "disabled",
    }


def test_provider_extra_body_enables_deepseek_auto_thinking(monkeypatch):
    monkeypatch.setenv("LEETCOACH_AI_THINKING", "auto")

    assert provider_extra_body("https://api.deepseek.com", None) == {"thinking": {"type": "enabled"}}
    assert provider_extra_body("https://api.anthropic.com", "enabled") is None


def test_anthropic_client_streams_messages_with_provider_options():
    calls = {}

    class FakeStream:
        text_stream = ["hello", "", " world"]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeMessages:
        def stream(self, **kwargs):
            calls["stream"] = kwargs
            return FakeStream()

    class FakeClient:
        def __init__(self, **kwargs):
            calls["client"] = kwargs
            self.messages = FakeMessages()

    client = AnthropicMessagesClient(
        api_key="key",
        auth_token=None,
        base_url="https://api.deepseek.com",
        model="deepseek-test",
        client_factory=FakeClient,
    )

    chunks = list(
        client.stream_messages(
            AIChatRequest(
                messages=[{"role": "user", "content": "hi"}],
                system="system prompt",
                max_tokens=123,
                thinking_mode="off",
            )
        )
    )

    assert chunks == ["hello", " world"]
    assert calls["client"] == {"api_key": "key", "auth_token": None, "base_url": "https://api.deepseek.com"}
    assert calls["stream"]["model"] == "deepseek-test"
    assert calls["stream"]["max_tokens"] == 123
    assert calls["stream"]["extra_body"] == {"thinking": {"type": "disabled"}}


def test_anthropic_client_completes_text_response():
    class FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(
                content=[
                    SimpleNamespace(type="text", text='{"ok": true}'),
                    SimpleNamespace(type="tool_use", text="ignored"),
                    SimpleNamespace(type="text", text="\n"),
                ]
            )

    class FakeClient:
        def __init__(self, **kwargs):
            self.messages = FakeMessages()

    client = AnthropicMessagesClient(
        api_key=None,
        auth_token="token",
        base_url=None,
        model="claude-test",
        client_factory=FakeClient,
    )

    assert (
        client.complete_messages(
            AIChatRequest(
                messages=[{"role": "user", "content": "json"}],
                system="system prompt",
                max_tokens=4000,
            )
        )
        == '{"ok": true}\n\n'
    )


def test_anthropic_client_requires_credentials_for_completion():
    client = AnthropicMessagesClient(
        api_key=None,
        auth_token=None,
        base_url=None,
        model="claude-test",
    )

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        client.complete_messages(
            AIChatRequest(
                messages=[{"role": "user", "content": "json"}],
                system="system prompt",
                max_tokens=4000,
            )
        )
