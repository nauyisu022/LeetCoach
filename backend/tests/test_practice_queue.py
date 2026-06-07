from fastapi.testclient import TestClient

from app.db import get_connection, init_db


def _insert_problem(conn, task_id: str, question_id: int, tags: str, difficulty: str = "Medium") -> None:
    conn.execute(
        """
        INSERT INTO problems (
            task_id, question_id, difficulty, tags_json, problem_description,
            starter_code, entry_point, test_code, input_output_json, prompt, completion
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task_id,
            question_id,
            difficulty,
            tags,
            "description",
            "code",
            "Solution().solve",
            "def check(candidate):\n    assert True",
            "[]",
            "from typing import *",
            "",
        ),
    )


def _insert_codetop(conn, question_id: int, title: str, slug: str, frequency: int) -> None:
    conn.execute(
        """
        INSERT INTO codetop_questions (
            codetop_id, frontend_question_id, question_id, title,
            slug_title, difficulty, frequency, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            question_id,
            str(question_id),
            question_id,
            title,
            slug,
            "Medium",
            frequency,
            "{}",
        ),
    )


def test_practice_queue_prioritizes_review_inside_selected_topic(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn, "review-hash", 1, '["Array", "Hash Table"]')
        _insert_problem(conn, "hot-hash", 2, '["Array", "Hash Table"]')
        _insert_problem(conn, "other-string", 3, '["String"]')
        _insert_codetop(conn, 1, "review hash", "review-hash", 10)
        _insert_codetop(conn, 2, "hot hash", "hot-hash", 900)
        conn.execute("INSERT INTO users (id, display_name) VALUES ('other', 'Other User')")
        conn.execute(
            """
            INSERT INTO user_problem_state (task_id, status, submit_count, pass_count)
            VALUES ('review-hash', 'needs_review', 2, 0)
            """
        )
        conn.execute(
            """
            INSERT INTO user_problem_state (user_id, task_id, status, submit_count, pass_count)
            VALUES ('other', 'hot-hash', 'needs_review', 3, 0)
            """
        )
    conn.close()

    from app.main import app

    client = TestClient(app)
    response = client.get("/api/practice/queue", params={"tags": "Hash Table"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["active_topics"] == ["哈希表"]
    assert payload["strategy"].startswith("待复习")
    assert [item["task_id"] for item in payload["items"]] == ["review-hash", "hot-hash"]
    assert payload["items"][0]["recommendation_reason"] == "待复习题，优先巩固错题"
    assert payload["next_task_id"] == "review-hash"
    assert payload["items"][1]["status"] == "unseen"


def test_practice_next_uses_current_problem_topics_and_excludes_current(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn, "current", 1, '["Sliding Window", "String"]')
        _insert_problem(conn, "same-topic", 2, '["Sliding Window"]')
        _insert_problem(conn, "different-topic", 3, '["Graph"]')
        _insert_codetop(conn, 1, "current", "current", 1000)
        _insert_codetop(conn, 2, "same topic", "same-topic", 20)
        _insert_codetop(conn, 3, "different topic", "different-topic", 900)
    conn.close()

    from app.main import app

    client = TestClient(app)
    response = client.get("/api/practice/next", params={"current_task_id": "current"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["active_topics"] == ["滑动窗口", "字符串"]
    assert [item["task_id"] for item in payload["items"]] == ["same-topic"]
    assert payload["next_task_id"] == "same-topic"


def test_practice_insights_rank_weak_topics(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn, "hash-review", 1, '["Array", "Hash Table"]')
        _insert_problem(conn, "hash-unseen", 2, '["Hash Table"]')
        _insert_problem(conn, "graph-passed", 3, '["Graph"]')
        _insert_codetop(conn, 1, "hash review", "hash-review", 100)
        _insert_codetop(conn, 2, "hash unseen", "hash-unseen", 800)
        _insert_codetop(conn, 3, "graph passed", "graph-passed", 900)
        conn.execute(
            """
            INSERT INTO user_problem_state (task_id, status, submit_count, pass_count)
            VALUES ('hash-review', 'needs_review', 2, 0)
            """
        )
        conn.execute(
            """
            INSERT INTO user_problem_state (task_id, status, submit_count, pass_count)
            VALUES ('graph-passed', 'passed', 1, 1)
            """
        )
    conn.close()

    from app.main import app

    client = TestClient(app)
    response = client.get("/api/practice/insights", params={"limit": 3})
    assert response.status_code == 200
    payload = response.json()
    assert payload["strategy"].startswith("优先看待复习")
    top_topic = payload["topics"][0]
    assert top_topic["label"] == "哈希表"
    assert top_topic["needs_review_count"] == 1
    assert top_topic["unseen_count"] == 1
    assert top_topic["passed_count"] == 0
    assert top_topic["next_task_id"] == "hash-review"
    assert "待复习" in top_topic["recommendation"]
