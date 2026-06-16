from fastapi.testclient import TestClient

from app.db import get_connection, init_db


def _insert_problem(conn, task_id: str, question_id: int, title: str, tags: str = '["Array"]') -> None:
    conn.execute(
        """
        INSERT INTO problems (
            task_id, question_id, difficulty, tags_json, problem_description,
            title_zh, starter_code, entry_point, test_code, input_output_json, prompt, completion
        ) VALUES (?, ?, 'Easy', ?, 'description', ?, 'code', 'Solution().solve',
                  'def check(candidate):\n    assert True', '[]', 'from typing import *', '')
        """,
        (task_id, question_id, tags, title),
    )


def _insert_plan(conn) -> None:
    conn.execute(
        """
        INSERT INTO study_plans (slug, title, source_type, source_url)
        VALUES ('top-interview-150', '面试经典 150 题', 'leetcode_study_plan', 'https://leetcode.cn/studyplan/top-interview-150/')
        """
    )
    plan_id = conn.execute("SELECT id FROM study_plans WHERE slug = 'top-interview-150'").fetchone()["id"]
    items = [
        ("two-sum", 1, "两数之和", "Easy", "数组 / 字符串", "array-string", 1, 1, 1),
        ("three-sum", 15, "三数之和", "Medium", "数组 / 字符串", "array-string", 1, 2, 2),
        ("missing-design", 999, "缺失设计题", "Medium", "设计", "design", 2, 1, 3),
    ]
    for slug, question_id, title, difficulty, group_name, group_slug, group_position, item_position, plan_position in items:
        conn.execute(
            """
            INSERT INTO study_plan_items (
              plan_id, task_id, external_slug, question_id, title, difficulty,
              group_name, group_slug, group_position, item_position, plan_position
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id,
                slug,
                slug,
                question_id,
                title,
                difficulty,
                group_name,
                group_slug,
                group_position,
                item_position,
                plan_position,
            ),
        )


def test_study_plan_endpoint_counts_groups_and_missing_items(tmp_path, monkeypatch):
    db_path = tmp_path / "catalog.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn, "two-sum", 1, "两数之和", '["Array", "Hash Table"]')
        _insert_problem(conn, "three-sum", 15, "三数之和", '["Array", "Two Pointers"]')
        conn.execute(
            """
            INSERT INTO user_problem_state (task_id, status, submit_count, pass_count)
            VALUES ('two-sum', 'passed', 1, 1)
            """
        )
        _insert_plan(conn)
    conn.close()

    from app.main import app

    client = TestClient(app)
    response = client.get("/api/study-plans")
    assert response.status_code == 200
    plan = response.json()["plans"][0]
    assert plan["total_count"] == 3
    assert plan["available_count"] == 2
    assert plan["missing_count"] == 1
    assert plan["passed_count"] == 1

    response = client.get("/api/study-plans/top-interview-150")
    assert response.status_code == 200
    payload = response.json()
    assert [group["group_slug"] for group in payload["groups"]] == ["array-string", "design"]
    assert payload["groups"][1]["missing_count"] == 1
    assert [item["task_id"] for item in payload["items"]] == ["two-sum", "three-sum", "missing-design"]
    assert payload["items"][0]["available"] is True
    assert payload["items"][2]["available"] is False
    assert payload["items"][2]["status"] == "missing"
    assert payload["next_task_id"] == "three-sum"

    response = client.get("/api/study-plans/top-interview-150", params={"tags": "Two Pointers"})
    assert response.status_code == 200
    assert [item["task_id"] for item in response.json()["items"]] == ["three-sum"]
