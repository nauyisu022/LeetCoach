from fastapi.testclient import TestClient

from app.db import get_connection, init_db


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


def test_agent_stream_creates_proposed_memory_and_summary(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
    conn.close()

    from app import main

    monkeypatch.setattr(
        main,
        "call_claude_messages_stream",
        lambda messages, **kwargs: iter(["## 结论\n你的代码应该维护哈希表只保存左侧元素。"]),
    )
    client = TestClient(main.app)

    response = client.post(
        "/api/agent/command/stream",
        json={"task_id": "two-sum", "command": "/diagnose", "code": "class Solution: pass"},
    )
    assert response.status_code == 200
    assert "左侧元素" in response.text

    memories = client.get("/api/agent/memories?status=proposed").json()["memories"]
    assert len(memories) == 1
    assert memories[0]["memory_type"] == "weakness"
    assert memories[0]["status"] == "proposed"
    assert "左侧元素" in memories[0]["content"]

    summary = client.get("/api/agent/thread-summary/two-sum").json()
    assert summary["summary"]
    assert "左侧元素" in summary["summary"]


def test_accepted_memory_is_injected_and_rejected_memory_is_excluded(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
        conn.execute(
            """
            INSERT INTO user_memory_items (
                user_id, memory_type, scope, topic, task_id, content, source, confidence, status
            ) VALUES
              ('local', 'strategy', 'task', '哈希表', 'two-sum', '优先想补数映射，不要先排序。', 'test', 0.9, 'accepted'),
              ('local', 'strategy', 'task', '哈希表', 'two-sum', '这条被拒绝，不能进入 prompt。', 'test', 0.9, 'rejected')
            """
        )
    conn.close()

    from app import main

    captured_messages = {}

    def fake_stream(messages, **kwargs):
        captured_messages["text"] = "\n".join(message["content"] for message in messages)
        return iter(["ok"])

    monkeypatch.setattr(main, "call_claude_messages_stream", fake_stream)
    client = TestClient(main.app)

    response = client.post(
        "/api/agent/command/stream",
        json={"task_id": "two-sum", "command": "/explain"},
    )
    assert response.status_code == 200
    assert "优先想补数映射" in captured_messages["text"]
    assert "这条被拒绝" not in captured_messages["text"]


def test_memory_accept_edit_reject_flow(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
        cursor = conn.execute(
            """
            INSERT INTO user_memory_items (
                user_id, memory_type, scope, topic, task_id, content, source, confidence, status
            ) VALUES ('local', 'strategy', 'task', '哈希表', 'two-sum', 'old', 'test', 0.8, 'proposed')
            """
        )
        memory_id = cursor.lastrowid
    conn.close()

    from app.main import app

    client = TestClient(app)
    edited = client.put(f"/api/agent/memories/{memory_id}", json={"content": "edited"}).json()
    assert edited["content"] == "edited"
    accepted = client.post(f"/api/agent/memories/{memory_id}/accept").json()
    assert accepted["status"] == "accepted"
    rejected = client.post(f"/api/agent/memories/{memory_id}/reject").json()
    assert rejected["status"] == "rejected"
