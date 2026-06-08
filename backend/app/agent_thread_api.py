from __future__ import annotations

import sqlite3
from typing import Protocol

from .schemas import AgentThreadMessage, AgentThreadResponse


class ConnectionFactory(Protocol):
    def __call__(self) -> sqlite3.Connection:
        ...


class AgentThreadApiService:
    def __init__(self, *, user_id: str, connection_factory: ConnectionFactory) -> None:
        self.user_id = user_id
        self.connection_factory = connection_factory

    def thread_messages(self, task_id: str) -> AgentThreadResponse:
        conn = self.connection_factory()
        try:
            rows = conn.execute(
                """
                SELECT id, role, content, created_at
                FROM coach_messages
                WHERE user_id = ? AND task_id = ?
                ORDER BY id
                """,
                (self.user_id, task_id),
            ).fetchall()
        finally:
            conn.close()
        return AgentThreadResponse(
            messages=[
                AgentThreadMessage(id=row["id"], role=row["role"], content=row["content"], created_at=row["created_at"])
                for row in rows
            ]
        )

    def clear_thread(self, task_id: str) -> dict[str, str]:
        conn = self.connection_factory()
        try:
            with conn:
                conn.execute("DELETE FROM coach_messages WHERE user_id = ? AND task_id = ?", (self.user_id, task_id))
                conn.execute("DELETE FROM coach_thread_summaries WHERE user_id = ? AND task_id = ?", (self.user_id, task_id))
        finally:
            conn.close()
        return {"status": "cleared"}
