from __future__ import annotations

import sqlite3
from dataclasses import asdict
from typing import Protocol

from .agent_runtime.memory import (
    fetch_memory_records,
    fetch_thread_summary_record,
    set_memory_record_status,
    update_memory_record,
)
from .schemas import (
    AgentMemoryItem,
    AgentMemoryListResponse,
    AgentMemoryUpdateRequest,
    AgentThreadSummaryResponse,
)


class ConnectionFactory(Protocol):
    def __call__(self) -> sqlite3.Connection:
        ...


class AgentMemoryNotFoundError(LookupError):
    pass


class AgentMemoryApiService:
    def __init__(self, *, user_id: str, connection_factory: ConnectionFactory) -> None:
        self.user_id = user_id
        self.connection_factory = connection_factory

    def list_memories(
        self,
        *,
        status: str | None = None,
        task_id: str | None = None,
        limit: int = 80,
    ) -> AgentMemoryListResponse:
        conn = self.connection_factory()
        try:
            records = fetch_memory_records(conn, user_id=self.user_id, status=status, task_id=task_id, limit=limit)
        finally:
            conn.close()
        return AgentMemoryListResponse(memories=[AgentMemoryItem(**asdict(record)) for record in records])

    def update_memory(self, memory_id: int, request: AgentMemoryUpdateRequest) -> AgentMemoryItem:
        conn = self.connection_factory()
        try:
            with conn:
                record = update_memory_record(
                    conn,
                    user_id=self.user_id,
                    memory_id=memory_id,
                    content=request.content,
                    status=request.status,
                )
        finally:
            conn.close()
        if not record:
            raise AgentMemoryNotFoundError("Memory not found")
        return AgentMemoryItem(**asdict(record))

    def set_memory_status(self, memory_id: int, status: str) -> AgentMemoryItem:
        conn = self.connection_factory()
        try:
            with conn:
                record = set_memory_record_status(conn, user_id=self.user_id, memory_id=memory_id, status=status)
        finally:
            conn.close()
        if not record:
            raise AgentMemoryNotFoundError("Memory not found")
        return AgentMemoryItem(**asdict(record))

    def thread_summary(self, task_id: str) -> AgentThreadSummaryResponse:
        conn = self.connection_factory()
        try:
            record = fetch_thread_summary_record(conn, user_id=self.user_id, task_id=task_id)
        finally:
            conn.close()
        if not record:
            return AgentThreadSummaryResponse(task_id=task_id, summary=None)
        return AgentThreadSummaryResponse(**asdict(record))
