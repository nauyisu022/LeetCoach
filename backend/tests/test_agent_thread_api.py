from fastapi.testclient import TestClient

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


def test_agent_thread_routes_preferred_path_and_coach_compatibility(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    _init_thread_db(db_path)
    conn = get_connection(db_path)
    with conn:
        _insert_problem(conn)
    conn.close()

    from app.main import app

    client = TestClient(app)
    agent_response = client.get("/api/agent/thread/two-sum")
    coach_response = client.get("/api/coach/thread/two-sum")
    clear_response = client.delete("/api/agent/thread/two-sum")
    empty_response = client.get("/api/agent/thread/two-sum")

    assert agent_response.status_code == 200
    assert [message["content"] for message in agent_response.json()["messages"]] == ["first", "second"]
    assert coach_response.status_code == 200
    assert coach_response.json() == agent_response.json()
    assert clear_response.status_code == 200
    assert clear_response.json() == {"status": "cleared"}
    assert empty_response.json()["messages"] == []
