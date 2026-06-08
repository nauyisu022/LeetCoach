from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..coach import build_chat_context, build_diagnose_prompt, build_explain_prompt


@dataclass(frozen=True)
class AgentCommandPlan:
    command: str
    user_content: str
    messages: list[dict[str, str]]


def normalize_command(command: str | None, message: str | None = None) -> str:
    raw = (command or "auto").strip()
    if raw == "auto" and message:
        first = message.strip().split(maxsplit=1)[0] if message.strip() else ""
        if first in {"/diagnose", "/explain", "/hint", "/code-review", "/note", "/memory", "/review", "/next"}:
            return first
    if raw in {"diagnose", "诊断"}:
        return "/diagnose"
    if raw in {"explain", "讲解"}:
        return "/explain"
    if raw in {"chat", "auto", ""}:
        return "auto"
    return raw if raw.startswith("/") else f"/{raw}"


def build_command_plan(
    *,
    command: str,
    task_id: str,
    problem: dict[str, Any],
    code: str | None,
    failure: dict[str, Any] | None,
    message: str | None,
    history: list[dict[str, str]],
) -> AgentCommandPlan:
    if command == "/diagnose":
        user_content = message or "请诊断我这次提交为什么失败。"
        return AgentCommandPlan(
            command=command,
            user_content=user_content,
            messages=[{"role": "user", "content": build_diagnose_prompt(problem, code or "", failure)}],
        )
    if command == "/explain":
        user_content = message or "请完整讲解这道题，并总结解法范式。"
        return AgentCommandPlan(
            command=command,
            user_content=user_content,
            messages=[{"role": "user", "content": build_explain_prompt(problem)}],
        )
    if command in {"/hint", "/code-review", "/note", "/memory", "/review", "/next"}:
        user_content = message or _default_command_message(command)
        context = build_chat_context(problem, code, failure)
        return AgentCommandPlan(
            command=command,
            user_content=user_content,
            messages=[
                *history,
                {"role": "user", "content": f"{context}\n\n用户命令：{command}\n用户问题：{user_content}"},
            ],
        )

    user_content = message or ""
    if not user_content:
        raise ValueError("Chat message is required")
    return AgentCommandPlan(
        command="auto",
        user_content=user_content,
        messages=[
            *history,
            {"role": "user", "content": f"{build_chat_context(problem, code, failure)}\n\n用户问题：{user_content}"},
        ],
    )


def enrich_problem_with_memories(problem: dict[str, Any], memories: list[dict[str, str]]) -> dict[str, Any]:
    if not memories:
        return problem
    enriched = dict(problem)
    practice_context = dict(enriched.get("practice_context") or {})
    practice_context["accepted_memories"] = memories
    enriched["practice_context"] = practice_context
    return enriched


def _default_command_message(command: str) -> str:
    return {
        "/hint": "请给我一个有限提示，不要直接给完整答案。",
        "/code-review": "请 review 当前代码，指出逻辑、边界和复杂度问题。",
        "/note": "请帮我把当前练习整理成复习笔记草稿。",
        "/memory": "请从最近练习中提炼可以长期记住的学习点。",
        "/review": "请基于当前题和我的记录安排复习重点。",
        "/next": "请推荐下一道适合继续练的题。",
    }.get(command, command)
