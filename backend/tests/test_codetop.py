import json
from pathlib import Path

from app import codetop
from app.codetop import normalize_question_item, sync_codetop, upsert_codetop_question
from app.db import get_connection, init_db


def _sample_item(value: int = 1141):
    return {
        "id": 1681,
        "value": value,
        "time": "2026-06-03T02:46:45.047000Z",
        "status": False,
        "note_status": True,
        "rate": 2,
        "leetcode": {
            "id": 1681,
            "frontend_question_id": "3",
            "question_id": 3,
            "title": "无重复字符的最长子串",
            "content": "<p>给定一个字符串 <code>s</code></p>",
            "level": 2,
            "slug_title": "longest-substring-without-repeating-characters",
            "expand": False,
        },
    }


def test_normalize_question_item_strips_content_by_default():
    row = normalize_question_item(_sample_item())

    assert row["codetop_id"] == 1681
    assert row["frontend_question_id"] == "3"
    assert row["difficulty"] == "Medium"
    assert row["content_markdown"] is None
    assert "content" not in json.loads(row["raw_json"])["leetcode"]


def test_normalize_question_item_can_include_markdown_content():
    row = normalize_question_item(_sample_item(), include_content=True)

    assert row["content_markdown"] == "给定一个字符串 `s`"
    assert "content" in json.loads(row["raw_json"])["leetcode"]


def test_upsert_codetop_question_updates_existing_row(tmp_path: Path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)

    with conn:
        upsert_codetop_question(conn, _sample_item(value=10))
        upsert_codetop_question(conn, _sample_item(value=20))

    row = conn.execute(
        "SELECT frequency, title, note_status FROM codetop_questions WHERE codetop_id = 1681"
    ).fetchone()
    count = conn.execute("SELECT COUNT(*) AS count FROM codetop_questions").fetchone()["count"]
    conn.close()

    assert count == 1
    assert row["frequency"] == 20
    assert row["title"] == "无重复字符的最长子串"
    assert row["note_status"] == 1


def test_sync_codetop_counts_only_fetched_pages(tmp_path: Path, monkeypatch):
    def fake_get_json(endpoint, params=None):
        if endpoint == codetop.QUESTION_ENDPOINT:
            return {"count": 40, "list": [_sample_item()]}
        return []

    monkeypatch.setattr(codetop, "_get_json", fake_get_json)
    conn = get_connection(tmp_path / "test.db")

    stats = sync_codetop(max_pages=1, delay_seconds=0, conn=conn)
    count = conn.execute("SELECT COUNT(*) AS count FROM codetop_questions").fetchone()["count"]
    conn.close()

    assert stats.pages == 1
    assert stats.questions == 1
    assert count == 1


def test_codetop_problem_signals_falls_back_to_slug_title(tmp_path: Path):
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
            (
                "sort-an-array",
                912,
                "Medium",
                "[]",
                "Sort an array.",
                "",
                "sortArray",
                "",
                "[]",
                "",
                "",
            ),
        )
        upsert_codetop_question(
            conn,
            {
                **_sample_item(value=353),
                "id": 1906,
                "leetcode": {
                    **_sample_item()["leetcode"],
                    "frontend_question_id": "补充题4",
                    "question_id": None,
                    "title": "手撕快速排序",
                    "slug_title": "sort-an-array",
                },
            },
        )

    row = conn.execute(
        "SELECT frequency, match_count FROM codetop_problem_signals WHERE task_id = ?",
        ("sort-an-array",),
    ).fetchone()
    conn.close()

    assert row["frequency"] == 353
    assert row["match_count"] == 1
