from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator
from typing import Any, Protocol

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from .agent_api import AgentApiService
from .agent_memory_api import AgentMemoryApiService, AgentMemoryNotFoundError
from .agent_thread_api import AgentThreadApiService
from .schemas import (
    AgentCommandListResponse,
    AgentCommandPreviewResponse,
    AgentCommandRequest,
    AgentMemoryItem,
    AgentMemoryListResponse,
    AgentMemoryUpdateRequest,
    AgentProfileResponse,
    AgentProblemSearchResponse,
    AgentRecommendationSetResponse,
    AgentThreadResponse,
    AgentThreadSummaryResponse,
    AgentToolListResponse,
    AssistantRunRequest,
    PracticeNoteDraftRequest,
)


class ConnectionFactory(Protocol):
    def __call__(self) -> sqlite3.Connection:
        ...


ProblemLoader = Callable[[str], Any]
AIStreamerProvider = Callable[[], Callable[[list[dict[str, str]]], Iterator[str]]]


def create_agent_router(
    *,
    user_id: str,
    connection_factory: ConnectionFactory,
    problem_loader: ProblemLoader,
    ai_streamer_provider: AIStreamerProvider,
) -> APIRouter:
    router = APIRouter()

    def agent_api_service() -> AgentApiService:
        return AgentApiService(
            user_id=user_id,
            connection_factory=connection_factory,
            problem_loader=problem_loader,
            ai_streamer=ai_streamer_provider(),
        )

    def agent_memory_api_service() -> AgentMemoryApiService:
        return AgentMemoryApiService(user_id=user_id, connection_factory=connection_factory)

    def agent_thread_api_service() -> AgentThreadApiService:
        return AgentThreadApiService(user_id=user_id, connection_factory=connection_factory)

    def stream_response(content: Iterator[str]) -> StreamingResponse:
        return StreamingResponse(content, media_type="text/plain; charset=utf-8")

    def assistant_event_response(request: AssistantRunRequest) -> StreamingResponse:
        def events() -> Iterator[str]:
            try:
                for chunk in agent_api_service().stream_command(request):
                    if chunk:
                        yield _assistant_stream_event("text-delta", delta=chunk)
                thread = agent_thread_api_service().thread_messages(request.task_id)
                yield _assistant_stream_event(
                    "thread-snapshot",
                    messages=[_model_dump(message) for message in thread.messages],
                )
                yield _assistant_stream_event("done")
            except Exception as exc:
                yield _assistant_stream_event("error", message=str(exc))

        return StreamingResponse(events(), media_type="application/x-ndjson; charset=utf-8")

    def set_memory_status_response(memory_id: int, status: str) -> AgentMemoryItem:
        try:
            return agent_memory_api_service().set_memory_status(memory_id, status)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except AgentMemoryNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Memory not found") from exc

    @router.get("/api/agent/tools", response_model=AgentToolListResponse)
    def agent_tools() -> AgentToolListResponse:
        return agent_api_service().tools_response()

    @router.get("/api/agent/commands", response_model=AgentCommandListResponse)
    def agent_commands() -> AgentCommandListResponse:
        return agent_api_service().commands_response()

    @router.get("/api/agent/profile", response_model=AgentProfileResponse)
    def agent_profile() -> AgentProfileResponse:
        return agent_api_service().profile_response()

    @router.get("/api/agent/tools/problem-search", response_model=AgentProblemSearchResponse)
    def agent_problem_search(
        q: str,
        current_task_id: str | None = None,
        limit: int = Query(8, ge=1, le=20),
    ) -> AgentProblemSearchResponse:
        return agent_api_service().problem_search_response(
            query=q,
            current_task_id=current_task_id,
            limit=limit,
        )

    @router.get("/api/agent/recommendation-sets/latest", response_model=AgentRecommendationSetResponse)
    def latest_recommendation_set(source_task_id: str | None = None) -> AgentRecommendationSetResponse:
        return agent_api_service().latest_recommendation_set_response(source_task_id=source_task_id)

    @router.get("/api/agent/memories", response_model=AgentMemoryListResponse)
    def agent_memories(
        status: str | None = None,
        task_id: str | None = None,
        limit: int = Query(80, ge=1, le=200),
    ) -> AgentMemoryListResponse:
        try:
            return agent_memory_api_service().list_memories(status=status, task_id=task_id, limit=limit)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.put("/api/agent/memories/{memory_id}", response_model=AgentMemoryItem)
    def update_agent_memory(memory_id: int, request: AgentMemoryUpdateRequest) -> AgentMemoryItem:
        try:
            return agent_memory_api_service().update_memory(memory_id, request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except AgentMemoryNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Memory not found") from exc

    @router.post("/api/agent/memories/{memory_id}/accept", response_model=AgentMemoryItem)
    def accept_agent_memory(memory_id: int) -> AgentMemoryItem:
        return set_memory_status_response(memory_id, "accepted")

    @router.post("/api/agent/memories/{memory_id}/reject", response_model=AgentMemoryItem)
    def reject_agent_memory(memory_id: int) -> AgentMemoryItem:
        return set_memory_status_response(memory_id, "rejected")

    @router.get("/api/agent/thread-summary/{task_id}", response_model=AgentThreadSummaryResponse)
    def get_agent_thread_summary(task_id: str) -> AgentThreadSummaryResponse:
        problem_loader(task_id)
        return agent_memory_api_service().thread_summary(task_id)

    @router.get("/api/agent/thread/{task_id}", response_model=AgentThreadResponse)
    def get_agent_thread(task_id: str) -> AgentThreadResponse:
        problem_loader(task_id)
        return agent_thread_api_service().thread_messages(task_id)

    @router.delete("/api/agent/thread/{task_id}")
    def clear_agent_thread(task_id: str) -> dict[str, str]:
        problem_loader(task_id)
        return agent_thread_api_service().clear_thread(task_id)

    @router.get("/api/assistant/thread/{task_id}", response_model=AgentThreadResponse)
    def get_assistant_thread(task_id: str) -> AgentThreadResponse:
        return get_agent_thread(task_id)

    @router.delete("/api/assistant/thread/{task_id}")
    def clear_assistant_thread(task_id: str) -> dict[str, str]:
        return clear_agent_thread(task_id)

    @router.post("/api/assistant/run")
    def assistant_run(request: AssistantRunRequest) -> StreamingResponse:
        return assistant_event_response(request)

    @router.post("/api/agent/command/stream")
    def agent_command_stream(request: AgentCommandRequest) -> StreamingResponse:
        return stream_response(agent_api_service().stream_command(request))

    @router.post("/api/agent/command/preview", response_model=AgentCommandPreviewResponse)
    def agent_command_preview(request: AgentCommandRequest) -> AgentCommandPreviewResponse:
        return agent_api_service().preview_command(request)

    @router.post("/api/problems/{task_id}/note/draft/stream")
    def draft_practice_note_stream(task_id: str, request: PracticeNoteDraftRequest) -> StreamingResponse:
        return stream_response(
            agent_api_service().stream_note_draft(
                AgentCommandRequest(
                    task_id=task_id,
                    command="/note-draft",
                    code=request.code,
                    submission_id=request.submission_id,
                    current_result=request.current_result,
                    thinking_mode=request.thinking_mode,
                )
            )
        )

    return router


def _assistant_stream_event(event_type: str, **payload: Any) -> str:
    return f"{json.dumps({'type': event_type, **payload}, ensure_ascii=False)}\n"


def _model_dump(item: Any) -> dict[str, Any]:
    if hasattr(item, "model_dump"):
        return item.model_dump()
    return item.dict()
