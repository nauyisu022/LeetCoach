from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .commands import command_manifest
from .runtime import AgentInvocation, AgentRuntimeProfile, default_agent_runtime_profile
from .tools import default_agent_tool_specs


@dataclass(frozen=True)
class AgentToolManifestItem:
    name: str
    description: str
    trigger: str
    prompt_visibility: str


@dataclass(frozen=True)
class AgentCommandManifestItem:
    name: str
    route: str
    default_message: str
    skill_name: str
    aliases: list[str]
    display_name: str | None
    toolbar_icon: str | None
    toolbar_order: int | None


@dataclass(frozen=True)
class AgentProfileManifestItem:
    name: str
    description: str
    tool_names: list[str]
    command_routes: list[str]
    hook_names: list[str]
    stream_only: bool
    state_backends: list[str]


@dataclass(frozen=True)
class AgentToolRunInspection:
    name: str
    payload: dict[str, Any]
    prompt_section: str
    ok: bool


@dataclass(frozen=True)
class AgentInvocationInspection:
    task_id: str
    command: str
    user_content: str
    thinking_mode: str | None
    current_topics: list[str]
    history_count: int
    memory_count: int
    tool_results: list[AgentToolRunInspection]
    code_present: bool
    failure_present: bool
    failure: dict[str, Any] | None
    messages: list[dict[str, str]]


def agent_tool_manifest_items() -> list[AgentToolManifestItem]:
    return [
        AgentToolManifestItem(
            name=spec.name,
            description=spec.description,
            trigger=spec.trigger,
            prompt_visibility=spec.prompt_visibility,
        )
        for spec in default_agent_tool_specs()
    ]


def agent_command_manifest_items() -> list[AgentCommandManifestItem]:
    return [
        AgentCommandManifestItem(
            name=str(item["name"]),
            route=str(item["route"]),
            default_message=str(item["default_message"]),
            skill_name=str(item["skill_name"]),
            aliases=[str(alias) for alias in item["aliases"]],
            display_name=str(item["display_name"]) if item["display_name"] is not None else None,
            toolbar_icon=str(item["toolbar_icon"]) if item["toolbar_icon"] is not None else None,
            toolbar_order=int(item["toolbar_order"]) if item["toolbar_order"] is not None else None,
        )
        for item in command_manifest()
    ]


def agent_profile_manifest_item(profile: AgentRuntimeProfile | None = None) -> AgentProfileManifestItem:
    selected = profile or default_agent_runtime_profile()
    config = selected.config
    return AgentProfileManifestItem(
        name=selected.name,
        description=selected.description,
        tool_names=[str(getattr(tool, "name", tool.__class__.__name__)) for tool in config.tools or []],
        command_routes=sorted(str(route) for route in (config.route_handlers or {}).keys()),
        hook_names=[str(getattr(hook, "name", hook.__class__.__name__)) for hook in config.hooks or []],
        stream_only=selected.stream_only,
        state_backends=list(selected.state_backends),
    )


def inspect_agent_invocation(
    invocation: AgentInvocation,
    *,
    tool_prompt_limit: int = 2400,
    message_limit: int = 6000,
) -> AgentInvocationInspection:
    return AgentInvocationInspection(
        task_id=invocation.turn.task_id,
        command=invocation.plan.command,
        user_content=invocation.plan.user_content,
        thinking_mode=invocation.turn.thinking_mode,
        current_topics=invocation.context.current_topics,
        history_count=len(invocation.context.history),
        memory_count=len(invocation.context.memories),
        tool_results=[
            AgentToolRunInspection(
                name=result.name,
                payload=result.payload,
                prompt_section=truncate_preview_text(result.as_prompt_section(), tool_prompt_limit),
                ok=result.ok,
            )
            for result in invocation.context.tool_results
        ],
        code_present=bool(invocation.code),
        failure_present=invocation.failure is not None,
        failure=invocation.failure,
        messages=[
            {
                "role": message["role"],
                "content": truncate_preview_text(message["content"], message_limit),
            }
            for message in invocation.plan.messages
        ],
    )


def truncate_preview_text(value: Any, limit: int) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= limit else f"{text[:limit]}..."
