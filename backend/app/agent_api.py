from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import asdict
from typing import Any, Protocol

from fastapi import HTTPException

from .agent_runtime.inspection import (
    agent_command_manifest_items,
    agent_profile_manifest_item,
    agent_tool_manifest_items,
    inspect_agent_invocation,
)
from .agent_runtime.artifacts import (
    AgentArtifactRecord,
    create_recommendation_set,
    latest_recommendation_set,
)
from .agent_runtime.model import stream_agent_model_messages
from .agent_runtime.problem_context import build_agent_problem_payload
from .agent_runtime.runtime import AgentInvocation, build_agent_invocation
from .agent_runtime.service import AIStreamer, stream_agent_invocation, stream_note_draft_invocation
from .agent_runtime.tools import search_problem_catalog
from .schemas import (
    AgentCommandInfo,
    AgentCommandListResponse,
    AgentCommandPreviewResponse,
    AgentCommandRequest,
    AgentProblemSearchResponse,
    AgentRecommendationItem,
    AgentRecommendationSet,
    AgentRecommendationSetResponse,
    AgentProfileInfo,
    AgentProfileResponse,
    AgentToolInfo,
    AgentToolListResponse,
)


class ConnectionFactory(Protocol):
    def __call__(self) -> sqlite3.Connection:
        ...


ProblemRowLoader = Callable[[str], Any]


class AgentApiService:
    def __init__(
        self,
        *,
        user_id: str,
        connection_factory: ConnectionFactory,
        problem_loader: ProblemRowLoader,
        ai_streamer: AIStreamer = stream_agent_model_messages,
    ) -> None:
        self.user_id = user_id
        self.connection_factory = connection_factory
        self.problem_loader = problem_loader
        self.ai_streamer = ai_streamer

    def tools_response(self) -> AgentToolListResponse:
        return AgentToolListResponse(
            tools=[
                AgentToolInfo(**asdict(item))
                for item in agent_tool_manifest_items()
            ]
        )

    def commands_response(self) -> AgentCommandListResponse:
        return AgentCommandListResponse(
            commands=[
                AgentCommandInfo(**asdict(item))
                for item in agent_command_manifest_items()
            ]
        )

    def profile_response(self) -> AgentProfileResponse:
        item = agent_profile_manifest_item()
        return AgentProfileResponse(profile=AgentProfileInfo(**asdict(item)))

    def problem_search_response(
        self,
        *,
        query: str,
        current_task_id: str | None = None,
        limit: int = 8,
    ) -> AgentProblemSearchResponse:
        conn = self.connection_factory()
        try:
            result = search_problem_catalog(
                conn,
                query=query,
                current_task_id=current_task_id,
                limit=limit,
            )
            record = None
            if current_task_id:
                with conn:
                    record = create_recommendation_set(
                        conn,
                        user_id=self.user_id,
                        source_task_id=current_task_id,
                        query=result.payload["query"],
                        interpreted_topics=result.payload["interpreted_topics"],
                        results=result.payload["results"],
                    )
        finally:
            conn.close()
        return AgentProblemSearchResponse(**result.payload, recommendation_set_id=record.id if record else None)

    def latest_recommendation_set_response(
        self,
        *,
        source_task_id: str | None = None,
    ) -> AgentRecommendationSetResponse:
        conn = self.connection_factory()
        try:
            record = latest_recommendation_set(conn, user_id=self.user_id, source_task_id=source_task_id)
        finally:
            conn.close()
        return AgentRecommendationSetResponse(recommendation_set=_recommendation_set_from_record(record))

    def preview_command(self, request: AgentCommandRequest) -> AgentCommandPreviewResponse:
        invocation = self.invocation_from_request(request)
        return AgentCommandPreviewResponse(**asdict(inspect_agent_invocation(invocation)))

    def stream_command(self, request: AgentCommandRequest) -> Iterator[str]:
        invocation = self.invocation_from_request(request)
        return stream_agent_invocation(invocation, ai_streamer=self.ai_streamer)

    def stream_note_draft(self, request: AgentCommandRequest) -> Iterator[str]:
        invocation = self.invocation_from_request(request)
        return stream_note_draft_invocation(invocation, ai_streamer=self.ai_streamer)

    def invocation_from_request(self, request: AgentCommandRequest) -> AgentInvocation:
        row = self.problem_loader(request.task_id)
        problem = build_agent_problem_payload(row, user_id=self.user_id)
        conn = self.connection_factory()
        try:
            return build_agent_invocation(conn, request=request, user_id=self.user_id, problem=problem)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            conn.close()


def _recommendation_set_from_record(record: AgentArtifactRecord | None) -> AgentRecommendationSet | None:
    if record is None:
        return None
    payload = record.payload
    return AgentRecommendationSet(
        id=record.id,
        user_id=record.user_id,
        source_task_id=record.source_task_id,
        title=record.title,
        query=payload.get("query") or "",
        interpreted_topics=list(payload.get("interpreted_topics") or []),
        items=[AgentRecommendationItem(**item) for item in payload.get("items") or []],
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
