import json
from pathlib import Path

from app.importer import import_dataset
from app.db import get_connection, init_db


def test_schema_initializes(tmp_path: Path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert {
        "problems",
        "user_problem_state",
        "submissions",
        "users",
        "user_solutions",
        "practice_notes",
        "practice_note_topics",
        "topic_memories",
        "review_events",
    }.issubset(tables)
    user = conn.execute("SELECT id FROM users WHERE id = 'local'").fetchone()
    submission_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(submissions)").fetchall()
    }
    conn.close()
    assert user is not None
    assert "passed_test_count" in submission_columns


def test_user_solution_is_scoped_by_user_and_problem(tmp_path: Path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    with conn:
        conn.execute(
            """
            INSERT INTO problems (
                task_id, question_id, difficulty, tags_json, problem_description,
                starter_code, entry_point, test_code, input_output_json, prompt, completion
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("two-sum", 1, "Easy", "[]", "desc", "code", "twoSum", "test", "[]", "prompt", "completion"),
        )
        conn.execute(
            """
            INSERT INTO user_solutions (user_id, task_id, code, language)
            VALUES ('local', 'two-sum', 'first', 'python')
            ON CONFLICT(user_id, task_id) DO UPDATE SET code=excluded.code
            """
        )
        conn.execute(
            """
            INSERT INTO user_solutions (user_id, task_id, code, language)
            VALUES ('local', 'two-sum', 'second', 'python')
            ON CONFLICT(user_id, task_id) DO UPDATE SET code=excluded.code
            """
        )
    rows = conn.execute("SELECT code FROM user_solutions WHERE task_id = 'two-sum'").fetchall()
    conn.close()
    assert [row["code"] for row in rows] == ["second"]


def test_dataset_fixture_shape():
    dataset = Path("/Users/admin/Downloads/leetcode-dataset-check/LeetCodeDataset/LeetCodeDataset-test.jsonl")
    if not dataset.exists():
        return
    first = json.loads(dataset.read_text(encoding="utf-8").splitlines()[0])
    assert {"task_id", "entry_point", "test", "input_output", "starter_code"}.issubset(first)


def test_import_dataset_filters_error_outputs(tmp_path: Path, monkeypatch):
    source = tmp_path / "dataset"
    source.mkdir()
    (source / "LeetCodeDataset-test.jsonl").write_text(
        json.dumps(
            {
                "task_id": "sample-task",
                "question_id": 1,
                "difficulty": "Easy",
                "tags": [],
                "problem_description": "desc",
                "starter_code": "code",
                "entry_point": "Solution().solve",
                "test": "def check(candidate):\n    assert True\n",
                "input_output": [
                    {"input": "x = 1", "output": "Error: bad generated sample"},
                    {"input": "x = 2", "output": "3"},
                ],
                "prompt": "prompt",
                "completion": "completion",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_DB_PATH", str(db_file))

    import_dataset(source)

    conn = get_connection(db_file)
    row = conn.execute("SELECT input_output_json FROM problems WHERE task_id = 'sample-task'").fetchone()
    conn.close()
    assert json.loads(row["input_output_json"]) == [{"input": "x = 2", "output": "3"}]
