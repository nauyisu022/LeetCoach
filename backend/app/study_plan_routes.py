from __future__ import annotations

import sqlite3
from typing import Protocol

from fastapi import APIRouter, HTTPException, Query

from .schemas import StudyPlanItemsResponse, StudyPlanListResponse, StudyPlanSummary
from .study_plans import (
    StudyPlanNotFoundError,
    get_study_plan_items,
    list_study_plans,
    sync_leetcode_study_plan,
)


class ConnectionFactory(Protocol):
    def __call__(self) -> sqlite3.Connection:
        ...


def create_study_plan_router(*, user_id: str, connection_factory: ConnectionFactory) -> APIRouter:
    router = APIRouter()

    @router.get("/api/study-plans", response_model=StudyPlanListResponse)
    def study_plans() -> StudyPlanListResponse:
        conn = connection_factory()
        try:
            return list_study_plans(conn, user_id=user_id)
        finally:
            conn.close()

    @router.post("/api/study-plans/sync/{slug}", response_model=StudyPlanSummary)
    def sync_study_plan(slug: str) -> StudyPlanSummary:
        conn = connection_factory()
        try:
            return sync_leetcode_study_plan(conn, slug)
        except StudyPlanNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        finally:
            conn.close()

    @router.get("/api/study-plans/{slug}", response_model=StudyPlanItemsResponse)
    def study_plan_items(
        slug: str,
        group_slug: str | None = None,
        difficulty: str | None = None,
        tags: list[str] | None = Query(None),
        status: str | None = None,
        search: str | None = None,
        limit: int = Query(3000, ge=1, le=5000),
    ) -> StudyPlanItemsResponse:
        conn = connection_factory()
        try:
            return get_study_plan_items(
                conn,
                user_id=user_id,
                slug=slug,
                group_slug=group_slug,
                difficulty=difficulty,
                tags=tags,
                status=status,
                search=search,
                limit=limit,
            )
        except StudyPlanNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        finally:
            conn.close()

    return router
