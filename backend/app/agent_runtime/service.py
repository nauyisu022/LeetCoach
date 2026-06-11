from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from ..db import get_connection
from .artifacts import create_recommendation_set
from .hooks import AfterCoachResponseEvent, AgentHook, run_after_coach_response_hooks
from .model import stream_agent_model_messages
from .runtime import AgentInvocation

AI_EMPTY_RESPONSE_TEXT = "AI 没有返回内容。请稍后重试，或检查当前模型/API 配置。"


class AIStreamer(Protocol):
    def __call__(self, messages: list[dict[str, str]], *, thinking_mode: str | None = None) -> Iterator[str]:
        ...


@dataclass(frozen=True)
class AgentStreamTurn:
    user_id: str
    task_id: str
    user_content: str
    messages: list[dict[str, str]]
    command: str = "auto"
    problem: dict[str, Any] | None = None
    submission_id: int | None = None
    thinking_mode: str | None = None
    hooks: Sequence[AgentHook] | None = None


def stream_ai_text(
    messages: list[dict[str, str]],
    *,
    thinking_mode: str | None = None,
    ai_streamer: AIStreamer = stream_agent_model_messages,
) -> Iterator[str]:
    chunks: list[str] = []
    for chunk in ai_streamer(messages, thinking_mode=thinking_mode):
        chunks.append(chunk)
        yield chunk

    if not "".join(chunks).strip():
        yield AI_EMPTY_RESPONSE_TEXT


def stream_agent_turn(
    turn: AgentStreamTurn,
    *,
    ai_streamer: AIStreamer = stream_agent_model_messages,
) -> Iterator[str]:
    chunks: list[str] = []
    for chunk in ai_streamer(turn.messages, thinking_mode=turn.thinking_mode):
        chunks.append(chunk)
        yield chunk

    text = "".join(chunks).strip()
    if not text:
        text = AI_EMPTY_RESPONSE_TEXT
        yield text

    user_message_id = append_coach_message(turn.user_id, turn.task_id, "user", turn.user_content)
    assistant_message_id = append_coach_message(turn.user_id, turn.task_id, "assistant", text)
    run_after_agent_turn_hooks(
        user_id=turn.user_id,
        task_id=turn.task_id,
        command=turn.command,
        problem=turn.problem or {"task_id": turn.task_id},
        user_content=turn.user_content,
        assistant_text=text,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        hooks=turn.hooks,
    )
    if turn.submission_id:
        update_submission_ai_summary(turn.user_id, turn.submission_id, text)


CoachStreamTurn = AgentStreamTurn


def stream_coach_turn(
    turn: AgentStreamTurn,
    *,
    ai_streamer: AIStreamer = stream_agent_model_messages,
) -> Iterator[str]:
    return stream_agent_turn(turn, ai_streamer=ai_streamer)


def stream_agent_invocation(
    invocation: AgentInvocation,
    *,
    ai_streamer: AIStreamer = stream_agent_model_messages,
) -> Iterator[str]:
    yield from stream_agent_turn(
        AgentStreamTurn(
            user_id=invocation.turn.user_id,
            task_id=invocation.turn.task_id,
            user_content=invocation.plan.user_content,
            messages=invocation.plan.messages,
            command=invocation.plan.command,
            problem=invocation.problem,
            submission_id=invocation.turn.submission_id,
            thinking_mode=invocation.turn.thinking_mode,
            hooks=invocation.config.hooks,
        ),
        ai_streamer=ai_streamer,
    )
    persist_agent_artifacts(invocation)


def stream_note_draft_invocation(
    invocation: AgentInvocation,
    *,
    ai_streamer: AIStreamer = stream_agent_model_messages,
) -> Iterator[str]:
    return stream_ai_text(
        invocation.plan.messages,
        thinking_mode=invocation.turn.thinking_mode,
        ai_streamer=ai_streamer,
    )


def append_coach_message(user_id: str, task_id: str, role: str, content: str) -> int:
    conn = get_connection()
    with conn:
        cursor = conn.execute(
            "INSERT INTO coach_messages (user_id, task_id, role, content) VALUES (?, ?, ?, ?)",
            (user_id, task_id, role, content),
        )
        message_id = int(cursor.lastrowid)
    conn.close()
    return message_id


def run_after_agent_turn_hooks(
    *,
    user_id: str,
    task_id: str,
    command: str,
    problem: dict[str, Any],
    user_content: str,
    assistant_text: str,
    user_message_id: int,
    assistant_message_id: int,
    hooks: Sequence[AgentHook] | None = None,
) -> None:
    conn = get_connection()
    with conn:
        run_after_coach_response_hooks(
            conn,
            AfterCoachResponseEvent(
                user_id=user_id,
                task_id=task_id,
                command=command,
                problem=problem,
                user_content=user_content,
                assistant_text=assistant_text,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
            ),
            hooks=hooks,
        )
    conn.close()


def run_after_coach_turn_hooks(
    *,
    user_id: str,
    task_id: str,
    command: str,
    problem: dict[str, Any],
    user_content: str,
    assistant_text: str,
    user_message_id: int,
    assistant_message_id: int,
    hooks: Sequence[AgentHook] | None = None,
) -> None:
    run_after_agent_turn_hooks(
        user_id=user_id,
        task_id=task_id,
        command=command,
        problem=problem,
        user_content=user_content,
        assistant_text=assistant_text,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        hooks=hooks,
    )


def update_submission_ai_summary(user_id: str, submission_id: int, text: str) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE submissions SET ai_diagnosis_summary = ? WHERE user_id = ? AND id = ?",
            (text[:1000], user_id, submission_id),
        )
    conn.close()


def persist_agent_artifacts(invocation: AgentInvocation) -> None:
    if invocation.plan.command != "/search-problems":
        return
    search_result = next(
        (result for result in invocation.context.tool_results if result.name == "problem_search" and result.ok),
        None,
    )
    if not search_result:
        return
    payload = search_result.payload
    results = payload.get("results") or []
    if not results:
        return
    conn = get_connection()
    with conn:
        create_recommendation_set(
            conn,
            user_id=invocation.turn.user_id,
            source_task_id=invocation.turn.task_id,
            query=payload.get("query") or invocation.plan.user_content,
            interpreted_topics=list(payload.get("interpreted_topics") or []),
            results=results,
        )
    conn.close()
