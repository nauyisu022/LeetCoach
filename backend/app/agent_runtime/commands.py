from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CommandRoute = Literal["diagnose", "explain", "search", "chat", "note_draft"]


@dataclass(frozen=True)
class AgentCommandDefinition:
    name: str
    route: CommandRoute
    default_message: str
    skill_name: str
    aliases: tuple[str, ...] = ()
    display_name: str | None = None
    toolbar_icon: str | None = None
    toolbar_order: int | None = None


COMMAND_DEFINITIONS: tuple[AgentCommandDefinition, ...] = (
    AgentCommandDefinition(
        name="/diagnose",
        route="diagnose",
        default_message="请诊断我这次提交为什么失败。",
        skill_name="diagnose_failure",
        aliases=("diagnose", "诊断"),
        display_name="诊断",
        toolbar_icon="diagnose",
        toolbar_order=20,
    ),
    AgentCommandDefinition(
        name="/explain",
        route="explain",
        default_message="请完整讲解这道题，并总结解法范式。",
        skill_name="explain_algorithm",
        aliases=("explain", "讲解"),
        display_name="讲解",
        toolbar_icon="explain",
        toolbar_order=10,
    ),
    AgentCommandDefinition(
        name="/hint",
        route="chat",
        default_message="请给我一个有限提示，不要直接给完整答案。",
        skill_name="guided_chat",
    ),
    AgentCommandDefinition(
        name="/code-review",
        route="chat",
        default_message="请 review 当前代码，指出逻辑、边界和复杂度问题。",
        skill_name="guided_chat",
    ),
    AgentCommandDefinition(
        name="/note",
        route="chat",
        default_message="请帮我把当前练习整理成复习笔记草稿。",
        skill_name="guided_chat",
    ),
    AgentCommandDefinition(
        name="/note-draft",
        route="note_draft",
        default_message="请把这次算法练习整理成可复习的 Markdown 笔记草稿。",
        skill_name="note_draft",
        aliases=("note-draft", "draft-note", "笔记草稿"),
    ),
    AgentCommandDefinition(
        name="/memory",
        route="chat",
        default_message="请从最近练习中提炼可以长期记住的学习点。",
        skill_name="guided_chat",
    ),
    AgentCommandDefinition(
        name="/review",
        route="chat",
        default_message="请基于当前题和我的记录安排复习重点。",
        skill_name="guided_chat",
    ),
    AgentCommandDefinition(
        name="/next",
        route="chat",
        default_message="请推荐下一道适合继续练的题。",
        skill_name="guided_chat",
    ),
    AgentCommandDefinition(
        name="/search-problems",
        route="search",
        default_message="请搜索本地题库，推荐相关题目。",
        skill_name="problem_search",
        aliases=("search-problems", "search", "搜索", "搜题", "找题"),
        display_name="找题",
        toolbar_icon="search",
        toolbar_order=30,
    ),
)

COMMANDS_BY_NAME = {definition.name: definition for definition in COMMAND_DEFINITIONS}
COMMANDS_BY_ALIAS = {
    alias: definition
    for definition in COMMAND_DEFINITIONS
    for alias in definition.aliases
}


def command_definition(command: str) -> AgentCommandDefinition | None:
    return COMMANDS_BY_NAME.get(command)


def command_names() -> set[str]:
    return set(COMMANDS_BY_NAME)


def command_manifest() -> list[dict[str, object]]:
    return [
        {
            "name": definition.name,
            "route": definition.route,
            "default_message": definition.default_message,
            "skill_name": definition.skill_name,
            "aliases": list(definition.aliases),
            "display_name": definition.display_name,
            "toolbar_icon": definition.toolbar_icon,
            "toolbar_order": definition.toolbar_order,
        }
        for definition in COMMAND_DEFINITIONS
    ]


def normalize_registered_command(raw: str) -> str | None:
    if raw in COMMANDS_BY_NAME:
        return raw
    if raw in COMMANDS_BY_ALIAS:
        return COMMANDS_BY_ALIAS[raw].name
    if raw.startswith("/") and raw[1:] in COMMANDS_BY_ALIAS:
        return COMMANDS_BY_ALIAS[raw[1:]].name
    return None
