from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentTurnInput:
    user_id: str
    task_id: str
    command: str
    message: str | None
    code: str | None
    submission_id: int | None
    current_result: Any | None
    thinking_mode: str | None
    html_visual_mode: str | None = None

    @classmethod
    def from_command_request(cls, request: Any, *, user_id: str, command: str) -> "AgentTurnInput":
        return cls(
            user_id=user_id,
            task_id=request.task_id,
            command=command,
            message=request.message,
            code=request.code,
            submission_id=request.submission_id,
            current_result=request.current_result,
            thinking_mode=request.thinking_mode,
            html_visual_mode=getattr(request, "html_visual_mode", None),
        )
