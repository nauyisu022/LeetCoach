from __future__ import annotations

from collections.abc import Iterator

from ..ai_client import stream_chat_messages
from .prompts import SYSTEM_PROMPT


def stream_agent_model_messages(messages: list[dict[str, str]], thinking_mode: str | None = None) -> Iterator[str]:
    return stream_chat_messages(
        messages,
        system=SYSTEM_PROMPT,
        max_tokens=1800,
        thinking_mode=thinking_mode,
    )
