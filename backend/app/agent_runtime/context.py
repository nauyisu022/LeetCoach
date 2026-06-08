from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..practice import topic_names_for_problem
from ..topic_taxonomy import normalize_topic_name
from .memory import fetch_thread_summary
from .tools import AgentTool, AgentToolRequest, ToolResult, memory_context_from_results, run_agent_tools
from .turn import AgentTurnInput


@dataclass(frozen=True)
class AgentContext:
    problem: dict[str, Any]
    history: list[dict[str, str]]
    memories: list[dict[str, str]]
    current_topics: list[str]
    tool_results: list[ToolResult]


def build_agent_context(
    conn: sqlite3.Connection,
    *,
    turn: AgentTurnInput,
    problem: dict[str, Any],
    tools: Sequence[AgentTool] | None = None,
) -> AgentContext:
    current_topics = _current_topics(conn, turn.task_id, problem)
    history = fetch_coach_history_for_context(conn, user_id=turn.user_id, task_id=turn.task_id)
    tool_results = run_agent_tools(
        AgentToolRequest(
            conn=conn,
            turn=turn,
            problem=problem,
            current_topics=current_topics,
        ),
        tools=tools,
    )
    memories = memory_context_from_results(tool_results)
    return AgentContext(
        problem=problem,
        history=history,
        memories=memories,
        current_topics=current_topics,
        tool_results=tool_results,
    )


def fetch_coach_history_for_context(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    task_id: str,
    limit: int = 4,
) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    summary = fetch_thread_summary(conn, user_id=user_id, task_id=task_id)
    if summary and summary["summary"]:
        history.append(
            {
                "role": "user",
                "content": f"本题对话摘要：{summary['summary']}",
            }
        )
    rows = conn.execute(
        """
        SELECT role, content
        FROM coach_messages
        WHERE user_id = ? AND task_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (user_id, task_id, limit),
    ).fetchall()
    history.extend({"role": row["role"], "content": row["content"]} for row in reversed(rows))
    return history


def _current_topics(conn: sqlite3.Connection, task_id: str, problem: dict[str, Any]) -> list[str]:
    topics: list[str] = []
    seen: set[str] = set()
    for raw_topic in [*topic_names_for_problem(conn, task_id), *(problem.get("tags") or [])]:
        if not raw_topic:
            continue
        topic = normalize_topic_name(raw_topic)
        if topic in seen:
            continue
        seen.add(topic)
        topics.append(topic)
    return topics
