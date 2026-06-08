from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, Protocol

from anthropic import Anthropic

from .config import ai_thinking_mode, anthropic_api_key, anthropic_auth_token, anthropic_base_url, anthropic_model


@dataclass(frozen=True)
class AIChatRequest:
    messages: list[dict[str, str]]
    system: str
    max_tokens: int
    thinking_mode: str | None = None


class AIChatClient(Protocol):
    def stream_messages(self, request: AIChatRequest) -> Iterator[str]:
        ...

    def complete_messages(self, request: AIChatRequest) -> str:
        ...


class AnthropicMessagesClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        auth_token: str | None,
        base_url: str | None,
        model: str,
        client_factory: Callable[..., Any] = Anthropic,
    ) -> None:
        self.api_key = api_key
        self.auth_token = auth_token
        self.base_url = base_url
        self.model = model
        self.client_factory = client_factory

    def stream_messages(self, request: AIChatRequest) -> Iterator[str]:
        if not self._has_credentials():
            yield "未配置 ANTHROPIC_API_KEY 或 ANTHROPIC_AUTH_TOKEN。已跳过 Claude 调用；你仍然可以使用本地判题。"
            return

        client = self._client()
        with client.messages.stream(
            model=self.model,
            max_tokens=request.max_tokens,
            system=request.system,
            messages=request.messages,
            extra_body=provider_extra_body(self.base_url, request.thinking_mode),
        ) as stream:
            for text in stream.text_stream:
                if text:
                    yield text

    def complete_messages(self, request: AIChatRequest) -> str:
        if not self._has_credentials():
            raise RuntimeError("ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN is required for AI generation")

        client = self._client()
        response = client.messages.create(
            model=self.model,
            max_tokens=request.max_tokens,
            system=request.system,
            messages=request.messages,
            extra_body=provider_extra_body(self.base_url, request.thinking_mode),
        )
        return "\n".join(block.text for block in response.content if getattr(block, "type", None) == "text")

    def _has_credentials(self) -> bool:
        return bool(self.api_key or self.auth_token)

    def _client(self) -> Any:
        return self.client_factory(api_key=self.api_key, auth_token=self.auth_token, base_url=self.base_url)


def default_ai_client() -> AIChatClient:
    return AnthropicMessagesClient(
        api_key=anthropic_api_key(),
        auth_token=anthropic_auth_token(),
        base_url=anthropic_base_url(),
        model=anthropic_model(),
    )


def stream_chat_messages(
    messages: list[dict[str, str]],
    *,
    system: str,
    max_tokens: int,
    thinking_mode: str | None = None,
    client: AIChatClient | None = None,
) -> Iterator[str]:
    selected_client = client or default_ai_client()
    return selected_client.stream_messages(
        AIChatRequest(
            messages=messages,
            system=system,
            max_tokens=max_tokens,
            thinking_mode=thinking_mode,
        )
    )


def complete_chat_messages(
    messages: list[dict[str, str]],
    *,
    system: str,
    max_tokens: int,
    thinking_mode: str | None = None,
    client: AIChatClient | None = None,
) -> str:
    selected_client = client or default_ai_client()
    return selected_client.complete_messages(
        AIChatRequest(
            messages=messages,
            system=system,
            max_tokens=max_tokens,
            thinking_mode=thinking_mode,
        )
    )


def provider_extra_body(base_url: str | None, thinking_mode: str | None = None) -> dict[str, Any] | None:
    if "deepseek" not in (base_url or "").lower():
        return None

    mode = (thinking_mode or ai_thinking_mode()).strip().lower()
    if mode in {"off", "false", "0"}:
        mode = "disabled"
    if mode in {"on", "true", "1"}:
        mode = "enabled"
    if mode == "auto":
        mode = "enabled"
    if mode in {"enabled", "disabled"}:
        return {"thinking": {"type": mode}}
    return None
