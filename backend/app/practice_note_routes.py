from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Any, Protocol

from fastapi import APIRouter, HTTPException

from .practice_note_api import PracticeNoteApiService, PracticeNoteNotFoundError
from .schemas import (
    PracticeNote,
    PracticeNoteDraftRequest,
    PracticeNoteDraftResponse,
    PracticeNoteResponse,
    PracticeNoteSaveRequest,
    ReviewEvent,
    ReviewEventRequest,
)


class ConnectionFactory(Protocol):
    def __call__(self) -> sqlite3.Connection:
        ...


ProblemLoader = Callable[[str], Any]


def create_practice_note_router(
    *,
    user_id: str,
    connection_factory: ConnectionFactory,
    problem_loader: ProblemLoader,
) -> APIRouter:
    router = APIRouter()

    def note_service() -> PracticeNoteApiService:
        return PracticeNoteApiService(user_id=user_id, connection_factory=connection_factory)

    @router.get("/api/problems/{task_id}/note", response_model=PracticeNoteResponse)
    def get_practice_note(task_id: str) -> PracticeNoteResponse:
        problem_loader(task_id)
        return note_service().get_note(task_id)

    @router.put("/api/problems/{task_id}/note", response_model=PracticeNote)
    def save_practice_note(task_id: str, request: PracticeNoteSaveRequest) -> PracticeNote:
        problem_loader(task_id)
        return note_service().save_note(task_id, request)

    @router.post("/api/problems/{task_id}/note/draft", response_model=PracticeNoteDraftResponse)
    def draft_practice_note(task_id: str, request: PracticeNoteDraftRequest) -> PracticeNoteDraftResponse:
        raise HTTPException(status_code=410, detail=f"Use /api/problems/{task_id}/note/draft/stream")

    @router.post("/api/problems/{task_id}/note/review", response_model=ReviewEvent)
    def review_practice_note(task_id: str, request: ReviewEventRequest) -> ReviewEvent:
        problem_loader(task_id)
        try:
            return note_service().review_note(task_id, request.rating)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PracticeNoteNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Practice note not found") from exc

    return router
