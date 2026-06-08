import pytest

from app.agent_memory_api import AgentMemoryApiService, AgentMemoryNotFoundError
from app.db import get_connection, init_db
from app.schemas import AgentMemoryUpdateRequest


def _service(db_path) -> AgentMemoryApiService:
    return AgentMemoryApiService(
        user_id="local",
        connection_factory=lambda: get_connection(db_path),
    )


def _init_memory_db(db_path) -> int:
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        conn.execute("INSERT OR IGNORE INTO users (id, display_name) VALUES ('other', 'Other')")
        cursor = conn.execute(
            """
            INSERT INTO user_memory_items (
                user_id, memory_type, scope, topic, task_id, content, source, confidence, status
            ) VALUES ('local', 'strategy', 'task', 'Hash Table', 'two-sum', 'old memory', 'test', 0.8, 'proposed')
            """
        )
        memory_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO user_memory_items (
                user_id, memory_type, scope, topic, task_id, content, source, confidence, status
            ) VALUES ('other', 'strategy', 'task', 'Hash Table', 'two-sum', 'other user memory', 'test', 0.8, 'proposed')
            """
        )
        conn.execute(
            """
            INSERT INTO coach_thread_summaries (
                user_id, task_id, summary, last_message_id
            ) VALUES ('local', 'two-sum', 'thread summary', 12)
            """
        )
    conn.close()
    return memory_id


def test_agent_memory_api_lists_updates_status_and_summary(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    memory_id = _init_memory_db(db_path)
    service = _service(db_path)

    listed = service.list_memories(task_id="two-sum")
    edited = service.update_memory(memory_id, AgentMemoryUpdateRequest(content="  edited memory  "))
    accepted = service.set_memory_status(memory_id, "accepted")
    summary = service.thread_summary("two-sum")
    missing_summary = service.thread_summary("missing")

    assert [item.content for item in listed.memories] == ["old memory"]
    assert edited.content == "edited memory"
    assert accepted.status == "accepted"
    assert summary.summary == "thread summary"
    assert summary.last_message_id == 12
    assert missing_summary.task_id == "missing"
    assert missing_summary.summary is None


def test_agent_memory_api_maps_validation_and_missing_errors(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    memory_id = _init_memory_db(db_path)
    service = _service(db_path)

    with pytest.raises(ValueError, match="Invalid memory status"):
        service.list_memories(status="unknown")
    with pytest.raises(ValueError, match="Memory content cannot be empty"):
        service.update_memory(memory_id, AgentMemoryUpdateRequest(content="   "))
    with pytest.raises(AgentMemoryNotFoundError, match="Memory not found"):
        service.update_memory(9999, AgentMemoryUpdateRequest(content="missing"))
    with pytest.raises(AgentMemoryNotFoundError, match="Memory not found"):
        service.set_memory_status(9999, "accepted")
