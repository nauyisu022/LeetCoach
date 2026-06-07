from fastapi.testclient import TestClient

from app.db import get_connection, init_db


def _insert_problem(conn, task_id: str, question_id: int) -> None:
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
            "Medium",
            "[]",
            "description",
            "code",
            "Solution().solve",
            "def check(candidate):\n    assert True",
            "[]",
            "from typing import *",
            "",
        ),
    )


def _insert_submission(conn, task_id: str, passed: int, created_at: str = "CURRENT_TIMESTAMP") -> None:
    if created_at == "CURRENT_TIMESTAMP":
        conn.execute(
            """
            INSERT INTO submissions (
                user_id, task_id, code, passed, runtime_ms, test_count_estimate, passed_test_count
            ) VALUES ('local', ?, 'code', ?, 1, 1, ?)
            """,
            (task_id, passed, passed),
        )
        return

    conn.execute(
        """
        INSERT INTO submissions (
            user_id, task_id, code, passed, runtime_ms, test_count_estimate, passed_test_count, created_at
        ) VALUES ('local', ?, 'code', ?, 1, 1, ?, ?)
        """,
        (task_id, passed, passed, created_at),
    )


def test_progress_summary_is_global_and_counts_today_distinct_passed_tasks(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn, "passed-one", 1)
        _insert_problem(conn, "review-one", 2)
        _insert_problem(conn, "unseen-one", 3)
        conn.execute(
            """
            INSERT INTO user_problem_state (task_id, status, submit_count, pass_count)
            VALUES ('passed-one', 'passed', 2, 2)
            """
        )
        conn.execute(
            """
            INSERT INTO user_problem_state (task_id, status, submit_count, pass_count)
            VALUES ('review-one', 'needs_review', 1, 0)
            """
        )
        _insert_submission(conn, "passed-one", 1)
        _insert_submission(conn, "passed-one", 1)
        _insert_submission(conn, "review-one", 0)
        _insert_submission(conn, "review-one", 1, "2000-01-01 00:00:00")
    conn.close()

    from app.main import app

    response = TestClient(app).get("/api/progress/summary")

    assert response.status_code == 200
    assert response.json() == {
        "total": 3,
        "passed": 1,
        "needs_review": 1,
        "unseen": 1,
        "today_passed": 1,
    }
