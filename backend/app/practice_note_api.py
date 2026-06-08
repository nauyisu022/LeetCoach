from __future__ import annotations

import sqlite3
from typing import Protocol

from .notes import (
    create_review_event,
    fetch_note,
    fetch_note_topics,
    note_topic_names_for_problem,
    topic_labels_for_names,
    upsert_note,
)
from .schemas import PracticeNote, PracticeNoteResponse, PracticeNoteSaveRequest, ReviewEvent


class ConnectionFactory(Protocol):
    def __call__(self) -> sqlite3.Connection:
        ...


class PracticeNoteNotFoundError(LookupError):
    pass


class PracticeNoteApiService:
    def __init__(self, *, user_id: str, connection_factory: ConnectionFactory) -> None:
        self.user_id = user_id
        self.connection_factory = connection_factory

    def get_note(self, task_id: str) -> PracticeNoteResponse:
        conn = self.connection_factory()
        try:
            row = fetch_note(conn, user_id=self.user_id, task_id=task_id)
            suggested_topics = topic_labels_for_names(note_topic_names_for_problem(conn, task_id))
            note = practice_note_from_row(conn, row) if row else None
            return PracticeNoteResponse(note=note, suggested_topics=suggested_topics)
        finally:
            conn.close()

    def save_note(self, task_id: str, request: PracticeNoteSaveRequest) -> PracticeNote:
        conn = self.connection_factory()
        try:
            with conn:
                row = upsert_note(
                    conn,
                    user_id=self.user_id,
                    task_id=task_id,
                    content_markdown=request.content_markdown,
                    ai_summary=request.ai_summary,
                    mistake_summary=request.mistake_summary,
                    invariant_summary=request.invariant_summary,
                    solution_pattern=request.solution_pattern,
                    source_submission_id=request.source_submission_id,
                    review_at=request.review_at,
                    topics=request.topics,
                )
                return practice_note_from_row(conn, row)
        finally:
            conn.close()

    def review_note(self, task_id: str, rating: int) -> ReviewEvent:
        if rating < 1 or rating > 5:
            raise ValueError("rating must be between 1 and 5")
        conn = self.connection_factory()
        try:
            note = fetch_note(conn, user_id=self.user_id, task_id=task_id)
            if not note:
                raise PracticeNoteNotFoundError("Practice note not found")
            with conn:
                event = create_review_event(conn, user_id=self.user_id, note_id=note["id"], rating=rating)
            return ReviewEvent(
                id=event["id"],
                user_id=event["user_id"],
                note_id=event["note_id"],
                rating=event["rating"],
                reviewed_at=event["reviewed_at"],
            )
        finally:
            conn.close()


def practice_note_from_row(conn: sqlite3.Connection, row: sqlite3.Row) -> PracticeNote:
    topics = topic_labels_for_names(fetch_note_topics(conn, row["id"]))
    return PracticeNote(
        id=row["id"],
        user_id=row["user_id"],
        task_id=row["task_id"],
        content_markdown=row["content_markdown"],
        ai_summary=row["ai_summary"],
        mistake_summary=row["mistake_summary"],
        invariant_summary=row["invariant_summary"],
        solution_pattern=row["solution_pattern"],
        source_submission_id=row["source_submission_id"],
        review_at=row["review_at"],
        topics=topics,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
