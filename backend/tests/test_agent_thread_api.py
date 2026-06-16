from fastapi.testclient import TestClient
import json

from app.agent_thread_api import AgentThreadApiService
from app.db import get_connection, init_db


def _service(db_path) -> AgentThreadApiService:
    return AgentThreadApiService(
        user_id="local",
        connection_factory=lambda: get_connection(db_path),
    )


def _init_thread_db(db_path) -> None:
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        conn.execute("INSERT OR IGNORE INTO users (id, display_name) VALUES ('other', 'Other')")
        conn.execute(
            """
            INSERT INTO coach_messages (user_id, task_id, role, content)
            VALUES
              ('local', 'two-sum', 'user', 'first'),
              ('local', 'two-sum', 'assistant', 'second'),
              ('other', 'two-sum', 'user', 'other user message'),
              ('local', 'three-sum', 'user', 'other task message')
            """
        )
        conn.execute(
            """
            INSERT INTO coach_thread_summaries (user_id, task_id, summary, last_message_id)
            VALUES
              ('local', 'two-sum', 'summary', 2),
              ('other', 'two-sum', 'other summary', 3),
              ('local', 'three-sum', 'other task summary', 4)
            """
        )
    conn.close()


def _insert_problem(conn, task_id: str = "two-sum") -> None:
    conn.execute(
        """
        INSERT INTO problems (
            task_id, question_id, difficulty, tags_json, problem_description,
            title_zh, starter_code, entry_point, test_code, input_output_json, prompt, completion
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task_id,
            1,
            "Easy",
            '["Array", "Hash Table"]',
            "description",
            "两数之和",
            "code",
            "Solution().twoSum",
            "def check(candidate):\n    assert True",
            "[]",
            "from typing import *",
            "",
        ),
    )


def test_agent_thread_api_reads_ordered_messages_and_clears_only_selected_thread(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    _init_thread_db(db_path)
    service = _service(db_path)

    thread = service.thread_messages("two-sum")
    cleared = service.clear_thread("two-sum")
    empty_thread = service.thread_messages("two-sum")

    conn = get_connection(db_path)
    remaining_messages = conn.execute(
        "SELECT user_id, task_id, content FROM coach_messages ORDER BY id"
    ).fetchall()
    remaining_summaries = conn.execute(
        "SELECT user_id, task_id, summary FROM coach_thread_summaries ORDER BY id"
    ).fetchall()
    conn.close()

    assert [message.content for message in thread.messages] == ["first", "second"]
    assert cleared == {"status": "cleared"}
    assert empty_thread.messages == []
    assert [(row["user_id"], row["task_id"], row["content"]) for row in remaining_messages] == [
        ("other", "two-sum", "other user message"),
        ("local", "three-sum", "other task message"),
    ]
    assert [(row["user_id"], row["task_id"], row["summary"]) for row in remaining_summaries] == [
        ("other", "two-sum", "other summary"),
        ("local", "three-sum", "other task summary"),
    ]


def test_agent_thread_routes_preferred_path_and_coach_legacy_removed(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    _init_thread_db(db_path)
    conn = get_connection(db_path)
    with conn:
        _insert_problem(conn)
    conn.close()

    from app.main import app

    with TestClient(app) as client:
        agent_response = client.get("/api/agent/thread/two-sum")
        coach_response = client.get("/api/coach/thread/two-sum")
        coach_stream_response = client.post(
            "/api/coach/chat/stream",
            json={"task_id": "two-sum", "message": "hi"},
        )
        clear_response = client.delete("/api/agent/thread/two-sum")
        empty_response = client.get("/api/agent/thread/two-sum")

    assert agent_response.status_code == 200
    assert [message["content"] for message in agent_response.json()["messages"]] == ["first", "second"]
    assert coach_response.status_code == 404
    assert coach_stream_response.status_code == 404
    assert clear_response.status_code == 200
    assert clear_response.json() == {"status": "cleared"}
    assert empty_response.json()["messages"] == []


def test_assistant_thread_routes_stream_runtime_events_and_persist_turn(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    _init_thread_db(db_path)
    conn = get_connection(db_path)
    with conn:
        _insert_problem(conn)
    conn.close()

    from app import main
    from app.main import app

    def fake_stream(messages, **kwargs):
        assert kwargs["thinking_mode"] == "disabled"
        assert messages[-1]["role"] == "user"
        yield "hello"
        yield " world"

    monkeypatch.setattr(main, "agent_model_streamer", fake_stream)

    with TestClient(app) as client:
        thread_response = client.get("/api/assistant/thread/two-sum")
        stream_response = client.post(
            "/api/assistant/run",
            json={
                "task_id": "two-sum",
                "command": "auto",
                "message": "hi",
                "thinking_mode": "disabled",
            },
        )
        persisted_response = client.get("/api/assistant/thread/two-sum")
        clear_response = client.delete("/api/assistant/thread/two-sum")

    assert thread_response.status_code == 200
    assert [message["content"] for message in thread_response.json()["messages"]] == ["first", "second"]
    assert stream_response.status_code == 200
    events = [json.loads(line) for line in stream_response.text.splitlines()]
    assert events[0] == {"type": "text-delta", "delta": "hello"}
    assert events[1] == {"type": "text-delta", "delta": " world"}
    assert events[-1] == {"type": "done"}
    assert events[-2]["type"] == "thread-snapshot"
    assert [message["content"] for message in persisted_response.json()["messages"]][-2:] == ["hi", "hello world"]
    assert clear_response.json() == {"status": "cleared"}
