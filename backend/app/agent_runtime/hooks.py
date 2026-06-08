from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from .memory import run_after_coach_response_hook


@dataclass(frozen=True)
class AfterCoachResponseEvent:
    user_id: str
    task_id: str
    command: str
    problem: dict[str, Any]
    user_content: str
    assistant_text: str
    user_message_id: int
    assistant_message_id: int


@dataclass(frozen=True)
class HookResult:
    name: str
    payload: dict[str, Any]
    ok: bool = True


class AgentHook(Protocol):
    name: str

    def after_coach_response(self, conn: sqlite3.Connection, event: AfterCoachResponseEvent) -> HookResult | None:
        ...


class MemoryCuratorHook:
    name = "memory_curator"

    def after_coach_response(self, conn: sqlite3.Connection, event: AfterCoachResponseEvent) -> HookResult | None:
        memory = run_after_coach_response_hook(
            conn,
            user_id=event.user_id,
            task_id=event.task_id,
            command=event.command,
            problem=event.problem,
            user_content=event.user_content,
            assistant_text=event.assistant_text,
            user_message_id=event.user_message_id,
            assistant_message_id=event.assistant_message_id,
        )
        return HookResult(
            name=self.name,
            payload={"proposed_memory_id": memory["id"] if memory else None},
        )


def default_agent_hooks() -> list[AgentHook]:
    return [MemoryCuratorHook()]


def run_after_coach_response_hooks(
    conn: sqlite3.Connection,
    event: AfterCoachResponseEvent,
    hooks: Sequence[AgentHook] | None = None,
) -> list[HookResult]:
    selected_hooks = default_agent_hooks() if hooks is None else hooks
    results: list[HookResult] = []
    for hook in selected_hooks:
        try:
            result = hook.after_coach_response(conn, event)
        except Exception as exc:
            results.append(_hook_error_result(hook, exc))
            continue
        if result:
            results.append(result)
    return results


def _hook_error_result(hook: AgentHook, exc: Exception) -> HookResult:
    name = str(getattr(hook, "name", hook.__class__.__name__))
    return HookResult(
        name=name,
        ok=False,
        payload={
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            }
        },
    )
