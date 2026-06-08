from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


SKILL_SPEC_DIR = Path(__file__).with_name("skill_specs")


@dataclass(frozen=True)
class AgentSkill:
    name: str
    body: str

    def as_prompt_section(self) -> str:
        return f"Agent Skill: {self.name}\n{self.body}"


@lru_cache(maxsize=32)
def load_skill(name: str) -> AgentSkill:
    path = SKILL_SPEC_DIR / f"{name}.md"
    if not path.exists():
        raise ValueError(f"Unknown agent skill: {name}")
    return AgentSkill(name=name, body=path.read_text(encoding="utf-8").strip())


def skill_prompt_section(name: str | None) -> str:
    if not name:
        return ""
    return load_skill(name).as_prompt_section()

