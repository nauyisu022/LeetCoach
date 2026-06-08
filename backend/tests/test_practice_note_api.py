import pytest

from app.db import get_connection, init_db
from app.practice_note_api import PracticeNoteApiService, PracticeNoteNotFoundError
from app.schemas import PracticeNoteSaveRequest


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


def _service(db_path) -> PracticeNoteApiService:
    return PracticeNoteApiService(user_id="local", connection_factory=lambda: get_connection(db_path))


def test_practice_note_api_get_save_and_review(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
    conn.close()
    service = _service(db_path)

    empty = service.get_note("two-sum")
    saved = service.save_note(
        "two-sum",
        PracticeNoteSaveRequest(
            content_markdown="# Two Sum",
            mistake_summary="返回了值不是下标",
            invariant_summary="哈希表只保存左侧元素",
            solution_pattern="一次遍历",
        ),
    )
    loaded = service.get_note("two-sum")
    review = service.review_note("two-sum", 4)

    assert empty.note is None
    assert empty.suggested_topics == ["数组", "哈希表"]
    assert saved.topics == ["数组", "哈希表"]
    assert saved.mistake_summary == "返回了值不是下标"
    assert loaded.note is not None
    assert loaded.note.content_markdown == "# Two Sum"
    assert review.rating == 4
    assert review.note_id == saved.id


def test_practice_note_api_review_validation_and_missing_note(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
    conn.close()
    service = _service(db_path)

    with pytest.raises(ValueError, match="rating must be between 1 and 5"):
        service.review_note("two-sum", 0)
    with pytest.raises(PracticeNoteNotFoundError, match="Practice note not found"):
        service.review_note("two-sum", 3)
