from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .context import AgentContext, build_agent_context
from .commands import command_definition, normalize_registered_command
from .hooks import AgentHook, default_agent_hooks
from .prompts import build_chat_context, build_diagnose_prompt, build_explain_prompt, build_note_draft_prompt
from .skills import skill_prompt_section
from .tools import AgentTool, ToolResult, default_agent_tools, judge_context_from_results, note_content_from_results
from .turn import AgentTurnInput


CommandPlanHandler = Callable[["CommandPlanInput"], "AgentCommandPlan"]


@dataclass(frozen=True)
class AgentCommandPlan:
    command: str
    user_content: str
    messages: list[dict[str, str]]


@dataclass(frozen=True)
class CommandPlanInput:
    command: str
    definition: Any
    task_id: str
    problem: dict[str, Any]
    code: str | None
    failure: dict[str, Any] | None
    message: str | None
    history: list[dict[str, str]]
    tool_results: list[ToolResult]
    skill_section: str
    tool_section: str


@dataclass(frozen=True)
class AgentInvocation:
    turn: AgentTurnInput
    problem: dict[str, Any]
    context: AgentContext
    code: str
    failure: dict[str, Any] | None
    plan: AgentCommandPlan
    config: "AgentRuntimeConfig"


@dataclass(frozen=True)
class AgentRuntimeConfig:
    tools: Sequence[AgentTool] | None = None
    route_handlers: Mapping[str, CommandPlanHandler] | None = None
    hooks: Sequence[AgentHook] | None = None


@dataclass(frozen=True)
class AgentRuntimeProfile:
    name: str
    description: str
    config: AgentRuntimeConfig
    stream_only: bool = True
    state_backends: tuple[str, ...] = (
        "coach_messages",
        "submissions.ai_diagnosis_summary",
        "user_memory_items",
        "practice_notes",
    )


def default_agent_runtime_config() -> AgentRuntimeConfig:
    return AgentRuntimeConfig(
        tools=default_agent_tools(),
        route_handlers=default_command_plan_handlers(),
        hooks=default_agent_hooks(),
    )


def default_agent_runtime_profile() -> AgentRuntimeProfile:
    return AgentRuntimeProfile(
        name="teaching-agent-v1",
        description="Default coding-practice teaching agent with command routing, local context tools, and memory curation.",
        config=default_agent_runtime_config(),
    )


def build_agent_invocation(
    conn: sqlite3.Connection,
    *,
    request: Any,
    user_id: str,
    problem: dict[str, Any],
    tools: Sequence[AgentTool] | None = None,
    config: AgentRuntimeConfig | None = None,
) -> AgentInvocation:
    runtime_config = config or default_agent_runtime_config()
    if tools is not None and config is None:
        runtime_config = AgentRuntimeConfig(
            tools=tools,
            route_handlers=runtime_config.route_handlers,
            hooks=runtime_config.hooks,
        )
    command = normalize_command(request.command, request.message)
    turn = AgentTurnInput.from_command_request(request, user_id=user_id, command=command)
    context = build_agent_context(conn, turn=turn, problem=problem, tools=runtime_config.tools)
    code, failure = judge_context_from_results(context.tool_results, fallback_code=turn.code)
    enriched_problem = enrich_problem_with_memories(problem, context.memories)
    plan = build_command_plan(
        command=command,
        task_id=turn.task_id,
        problem=enriched_problem,
        code=code,
        failure=failure,
        message=turn.message,
        history=context.history,
        tool_results=context.tool_results,
        route_handlers=runtime_config.route_handlers,
    )
    return AgentInvocation(
        turn=turn,
        problem=enriched_problem,
        context=context,
        code=code,
        failure=failure,
        plan=plan,
        config=runtime_config,
    )


def normalize_command(command: str | None, message: str | None = None) -> str:
    raw = (command or "auto").strip()
    if raw == "auto" and message:
        first = message.strip().split(maxsplit=1)[0] if message.strip() else ""
        normalized = normalize_registered_command(first)
        if normalized:
            return normalized
    normalized = normalize_registered_command(raw)
    if normalized:
        return normalized
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
    tool_results: list[ToolResult] | None = None,
    route_handlers: Mapping[str, CommandPlanHandler] | None = None,
) -> AgentCommandPlan:
    resolved_tool_results = tool_results or []
    tool_section = _tool_section(resolved_tool_results)
    definition = command_definition(command)
    skill_section = skill_prompt_section(definition.skill_name if definition else None)
    handlers = route_handlers or default_command_plan_handlers()
    if definition:
        handler = handlers.get(definition.route)
        if handler:
            return handler(
                CommandPlanInput(
                    command=command,
                    definition=definition,
                    task_id=task_id,
                    problem=problem,
                    code=code,
                    failure=failure,
                    message=message,
                    history=history,
                    tool_results=resolved_tool_results,
                    skill_section=skill_section,
                    tool_section=tool_section,
                )
            )

    user_content = message or ""
    if not user_content:
        raise ValueError("Chat message is required")
    if tool_section:
        search_skill_section = skill_prompt_section("problem_search")
        return AgentCommandPlan(
            command="/search-problems",
            user_content=user_content,
            messages=[
                *history,
                {
                    "role": "user",
                    "content": (
                        f"{_join_sections(search_skill_section, build_chat_context(problem, code, failure), tool_section)}\n\n"
                        "用户问题触发了本地题库搜索。请基于工具结果回答，不要编造未搜索到的题目。\n"
                        f"用户问题：{user_content}"
                    ),
                },
            ],
        )
    return AgentCommandPlan(
        command="auto",
        user_content=user_content,
        messages=[
            *history,
            {"role": "user", "content": f"{_join_sections(skill_prompt_section('guided_chat'), build_chat_context(problem, code, failure))}\n\n用户问题：{user_content}"},
        ],
    )


def default_command_plan_handlers() -> Mapping[str, CommandPlanHandler]:
    return {
        "diagnose": _plan_diagnose_command,
        "explain": _plan_explain_command,
        "search": _plan_search_command,
        "note_draft": _plan_note_draft_command,
        "chat": _plan_chat_command,
    }


def _plan_diagnose_command(plan_input: CommandPlanInput) -> AgentCommandPlan:
    user_content = plan_input.message or plan_input.definition.default_message
    return AgentCommandPlan(
        command=plan_input.command,
        user_content=user_content,
        messages=[
            {
                "role": "user",
                "content": _join_sections(
                    plan_input.skill_section,
                    build_diagnose_prompt(plan_input.problem, plan_input.code or "", plan_input.failure),
                ),
            }
        ],
    )


def _plan_explain_command(plan_input: CommandPlanInput) -> AgentCommandPlan:
    user_content = plan_input.message or plan_input.definition.default_message
    return AgentCommandPlan(
        command=plan_input.command,
        user_content=user_content,
        messages=[{"role": "user", "content": _join_sections(plan_input.skill_section, build_explain_prompt(plan_input.problem))}],
    )


def _plan_search_command(plan_input: CommandPlanInput) -> AgentCommandPlan:
    user_content = plan_input.message or plan_input.definition.default_message
    context = build_chat_context(plan_input.problem, plan_input.code, plan_input.failure)
    return AgentCommandPlan(
        command=plan_input.command,
        user_content=user_content,
        messages=[
            *plan_input.history,
            {
                "role": "user",
                "content": (
                    f"{_join_sections(plan_input.skill_section, context, plan_input.tool_section)}\n\n"
                    "用户正在让你找题或推荐题。必须优先基于上面的本地题库工具结果回答；"
                    "不要编造工具结果里没有的题目。请说明每道题为什么相关，并建议先做哪一道。\n"
                    f"用户问题：{user_content}"
                ),
            },
        ],
    )


def _plan_note_draft_command(plan_input: CommandPlanInput) -> AgentCommandPlan:
    user_content = plan_input.message or plan_input.definition.default_message
    existing_note = note_content_from_results(plan_input.tool_results)
    return AgentCommandPlan(
        command=plan_input.command,
        user_content=user_content,
        messages=[
            {
                "role": "user",
                "content": _join_sections(
                    plan_input.skill_section,
                    build_note_draft_prompt(plan_input.problem, plan_input.code, plan_input.failure, existing_note),
                ),
            }
        ],
    )


def _plan_chat_command(plan_input: CommandPlanInput) -> AgentCommandPlan:
    user_content = plan_input.message or plan_input.definition.default_message
    context = build_chat_context(plan_input.problem, plan_input.code, plan_input.failure)
    return AgentCommandPlan(
        command=plan_input.command,
        user_content=user_content,
        messages=[
            *plan_input.history,
            {
                "role": "user",
                "content": (
                    f"{_join_sections(plan_input.skill_section, context, plan_input.tool_section)}\n\n"
                    f"用户命令：{plan_input.command}\n用户问题：{user_content}"
                ),
            },
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


def _tool_section(tool_results: list[ToolResult]) -> str:
    if not tool_results:
        return ""
    sections = [result.as_prompt_section() for result in tool_results]
    return "\n\n".join(section for section in sections if section)


def _join_sections(*sections: str) -> str:
    return "\n\n".join(section for section in sections if section)
