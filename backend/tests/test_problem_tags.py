from fastapi.testclient import TestClient

from app.db import get_connection, init_db


def _insert_problem(conn, task_id: str, question_id: int, tags: str) -> None:
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
            "Easy",
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


def test_problem_tags_endpoint_and_multi_tag_filter(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn, "array-hash", 1, '["Array", "Hash Table"]')
        _insert_problem(conn, "array-only", 2, '["Array"]')
        _insert_problem(conn, "string-only", 3, '["String"]')
        _insert_problem(conn, "chinese-array", 4, '["数组"]')
    conn.close()

    from app.main import app

    client = TestClient(app)
    tags = client.get("/api/problem-tags").json()
    assert tags[:3] == [
        {
            "name": "Array",
            "label": "数组",
            "category": "core-structures",
            "category_label": "基础数据结构",
            "aliases": ["Array", "数组"],
            "count": 3,
        },
        {
            "name": "Hash Table",
            "label": "哈希表",
            "category": "core-structures",
            "category_label": "基础数据结构",
            "aliases": ["Hash Table", "哈希表"],
            "count": 1,
        },
        {
            "name": "String",
            "label": "字符串",
            "category": "core-structures",
            "category_label": "基础数据结构",
            "aliases": ["String", "字符串"],
            "count": 1,
        },
    ]

    response = client.get("/api/problems", params=[("tags", "Array"), ("tags", "Hash Table")])
    assert response.status_code == 200
    assert [item["task_id"] for item in response.json()] == ["array-hash"]

    response = client.get("/api/problems", params={"tags": "Array"})
    assert response.status_code == 200
    assert [item["task_id"] for item in response.json()] == ["array-hash", "array-only", "chinese-array"]
