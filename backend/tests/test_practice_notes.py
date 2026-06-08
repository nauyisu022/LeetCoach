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


def test_save_note_creates_topic_memory(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
    conn.close()

    from app.main import app

    client = TestClient(app)
    response = client.put(
        "/api/problems/two-sum/note",
        json={
            "content_markdown": "# Two Sum\n\n用哈希表记录补数。",
            "ai_summary": "哈希表补数",
            "mistake_summary": "先返回了值而不是下标",
            "invariant_summary": "遍历到 i 时，哈希表只保存 i 左侧元素",
            "solution_pattern": "一遍扫描 + 哈希表",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["topics"] == ["数组", "哈希表"]
    assert payload["mistake_summary"] == "先返回了值而不是下标"

    memories = client.get("/api/topic-memories").json()["memories"]
    labels = [memory["topic_label"] for memory in memories]
    assert "哈希表" in labels
    hash_memory = next(memory for memory in memories if memory["topic_label"] == "哈希表")
    assert "先返回了值而不是下标" in hash_memory["memory_markdown"]
    assert hash_memory["common_mistakes"] == ["先返回了值而不是下标"]


def test_note_draft_requires_stream_endpoint(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
    conn.close()

    from app import main

    client = TestClient(main.app)
    response = client.post("/api/problems/two-sum/note/draft", json={"code": "class Solution: pass"})
    assert response.status_code == 410


def test_note_draft_stream_does_not_persist_until_saved(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
    conn.close()

    from app import main

    captured_messages = {}

    def fake_stream(messages, **kwargs):
        captured_messages["text"] = "\n".join(message["content"] for message in messages)
        yield "# 1. two-sum\n\n"
        yield "## 考点\n哈希表"

    monkeypatch.setattr(main, "agent_model_streamer", fake_stream)
    client = TestClient(main.app)
    response = client.post("/api/problems/two-sum/note/draft/stream", json={"code": "class Solution: pass"})
    assert response.status_code == 200
    assert response.text.startswith("# 1. two-sum")
    assert "Agent Skill: note_draft" in captured_messages["text"]

    note_response = client.get("/api/problems/two-sum/note")
    assert note_response.status_code == 200
    assert note_response.json()["note"] is None
    thread_response = client.get("/api/coach/thread/two-sum")
    assert thread_response.status_code == 200
    assert thread_response.json()["messages"] == []


def test_review_note_records_event_and_sets_next_review(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
    conn.close()

    from app.main import app

    client = TestClient(app)
    client.put("/api/problems/two-sum/note", json={"content_markdown": "note"})
    response = client.post("/api/problems/two-sum/note/review", json={"rating": 4})
    assert response.status_code == 200
    event = response.json()
    assert event["rating"] == 4

    note = client.get("/api/problems/two-sum/note").json()["note"]
    assert note["review_at"] is not None
