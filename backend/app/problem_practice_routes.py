from __future__ import annotations

import sqlite3
from typing import Protocol

from fastapi import APIRouter, HTTPException, Query

from .practice import PracticeFilters
from .problem_practice_api import ProblemNotFoundError, ProblemPracticeApiService
from .schemas import (
    PracticeInsightsResponse,
    PracticeQueueResponse,
    ProblemDetail,
    ProblemSummary,
    ProblemTag,
    ProgressSummary,
)


class ConnectionFactory(Protocol):
    def __call__(self) -> sqlite3.Connection:
        ...


def create_problem_practice_router(*, user_id: str, connection_factory: ConnectionFactory) -> APIRouter:
    router = APIRouter()

    def problem_service() -> ProblemPracticeApiService:
        return ProblemPracticeApiService(user_id=user_id, connection_factory=connection_factory)

    @router.get("/api/problems", response_model=list[ProblemSummary])
    def list_problems(
        difficulty: str | None = None,
        tag: str | None = None,
        tags: list[str] | None = Query(None),
        status: str | None = None,
        search: str | None = None,
        limit: int = Query(3000, ge=1, le=5000),
    ) -> list[ProblemSummary]:
        return problem_service().list_problems(
            difficulty=difficulty,
            tag=tag,
            tags=tags,
            status=status,
            search=search,
            limit=limit,
        )

    @router.get("/api/progress/summary", response_model=ProgressSummary)
    def progress_summary() -> ProgressSummary:
        return problem_service().progress_summary()

    @router.get("/api/problem-tags", response_model=list[ProblemTag])
    def list_problem_tags() -> list[ProblemTag]:
        return problem_service().problem_tags()

    @router.get("/api/practice/queue", response_model=PracticeQueueResponse)
    def practice_queue(
        tags: list[str] | None = Query(None),
        current_task_id: str | None = None,
        difficulty: str | None = None,
        status: str | None = None,
        search: str | None = None,
        limit: int = Query(30, ge=1, le=100),
    ) -> PracticeQueueResponse:
        filters = PracticeFilters(
            user_id=user_id,
            topics=tuple(tags or ()),
            difficulty=difficulty,
            status=status,
            search=search,
            current_task_id=current_task_id,
            limit=limit,
        )
        return problem_service().practice_queue(filters)

    @router.get("/api/practice/next", response_model=PracticeQueueResponse)
    def practice_next(
        current_task_id: str,
        tags: list[str] | None = Query(None),
        difficulty: str | None = None,
    ) -> PracticeQueueResponse:
        filters = PracticeFilters(
            user_id=user_id,
            topics=tuple(tags or ()),
            difficulty=difficulty,
            current_task_id=current_task_id,
            exclude_current=True,
            match_any_topic=not tags,
            limit=1,
        )
        return problem_service().practice_queue(filters)

    @router.get("/api/practice/insights", response_model=PracticeInsightsResponse)
    def practice_insights(limit: int = Query(8, ge=1, le=30)) -> PracticeInsightsResponse:
        return problem_service().practice_insights(limit=limit)

    @router.get("/api/problems/{task_id}", response_model=ProblemDetail)
    def get_problem(task_id: str) -> ProblemDetail:
        try:
            return problem_service().problem_detail(task_id)
        except ProblemNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router
