from __future__ import annotations

from collections.abc import Iterator

from .agent_runtime.model import stream_agent_model_messages


def call_claude_messages_stream(messages: list[dict[str, str]], thinking_mode: str | None = None) -> Iterator[str]:
    return stream_agent_model_messages(messages, thinking_mode=thinking_mode)
