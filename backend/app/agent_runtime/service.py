from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Sequence
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
    text_transform: Callable[[str], str] | None = None,
    emit_chunks: bool = True,
) -> Iterator[str]:
    chunks: list[str] = []
    for chunk in ai_streamer(turn.messages, thinking_mode=turn.thinking_mode):
        chunks.append(chunk)
        if emit_chunks:
            yield chunk

    text = "".join(chunks).strip()
    if not text:
        text = AI_EMPTY_RESPONSE_TEXT
        if emit_chunks:
            yield text

    if text_transform:
        text = text_transform(text)

    if not emit_chunks:
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


def stream_agent_invocation(
    invocation: AgentInvocation,
    *,
    ai_streamer: AIStreamer = stream_agent_model_messages,
) -> Iterator[str]:
    search_result = _successful_problem_search_result(invocation)
    text_transform = None
    emit_chunks = True
    if invocation.plan.command == "/search-problems" and search_result:
        text_transform = lambda text: link_problem_references_as_markdown_urls(
            text,
            search_result.payload.get("results") or [],
        )
        emit_chunks = False

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
        text_transform=text_transform,
        emit_chunks=emit_chunks,
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


def update_submission_ai_summary(user_id: str, submission_id: int, text: str) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE submissions SET ai_diagnosis_summary = ? WHERE user_id = ? AND id = ?",
            (text[:1000], user_id, submission_id),
        )
    conn.close()


def _successful_problem_search_result(invocation: AgentInvocation):
    return next(
        (result for result in invocation.context.tool_results if result.name == "problem_search" and result.ok),
        None,
    )


def link_problem_references_as_markdown_urls(text: str, results: list[dict[str, Any]]) -> str:
    problem_by_question_id: dict[int, dict[str, Any]] = {}
    for item in results:
        try:
            question_id = int(item.get("question_id"))
        except (TypeError, ValueError):
            continue
        problem_by_question_id[question_id] = item

    if not problem_by_question_id:
        return text

    pattern = re.compile(r"\b(\d{1,5})\.(?!\d)")
    output: list[str] = []
    last_index = 0

    for match in pattern.finditer(text):
        problem = problem_by_question_id.get(int(match.group(1)))
        if not problem or _already_markdown_linked(text, match.start()):
            continue

        match_end = match.end()
        extra_length = _problem_title_match_length(text[match_end:], str(problem.get("title") or ""))
        if extra_length is None:
            continue

        output.append(text[last_index:match.start()])
        link_end = match_end + extra_length
        label = text[match.start():link_end]
        output.append(_markdown_link_from_tool_result(problem, label))
        last_index = link_end

    if last_index == 0:
        return text
    output.append(text[last_index:])
    return "".join(output)


def _already_markdown_linked(text: str, match_start: int) -> bool:
    if match_start > 0 and text[match_start - 1] == "[":
        return True
    line_start = text.rfind("\n", 0, match_start) + 1
    preceding_line = text[line_start:match_start]
    return "[" in preceding_line and "](" not in preceding_line


def _markdown_link_from_tool_result(problem: dict[str, Any], fallback_label: str) -> str:
    markdown_link = problem.get("markdown_link")
    if isinstance(markdown_link, str) and markdown_link.strip():
        return markdown_link

    url = problem.get("url")
    if isinstance(url, str) and url.strip():
        title = str(problem.get("title") or "").strip()
        label = f"{problem.get('question_id')}. {title}" if title else fallback_label
        return f"[{label}]({url})"

    return fallback_label


def _problem_title_match_length(text_after_number: str, title: str) -> int | None:
    if re.match(r"\s+\d{1,5}\.(?!\d)", text_after_number):
        return None

    leading_whitespace_match = re.match(r"\s*", text_after_number)
    leading_whitespace = leading_whitespace_match.group(0) if leading_whitespace_match else ""
    candidate = text_after_number[len(leading_whitespace):]
    if title and candidate.startswith(title):
        return len(leading_whitespace) + len(title)
    return 0


def persist_agent_artifacts(invocation: AgentInvocation) -> None:
    if invocation.plan.command != "/search-problems":
        return
    search_result = _successful_problem_search_result(invocation)
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
