from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from .topic_taxonomy import TOPIC_BY_NAME, display_topic_labels, normalize_topic_name, topic_label


def note_topic_names_for_problem(conn: sqlite3.Connection, task_id: str) -> list[str]:
    row = conn.execute("SELECT tags_json FROM problems WHERE task_id = ?", (task_id,)).fetchone()
    if not row:
        return []
    names: list[str] = []
    seen: set[str] = set()
    for raw_name in json.loads(row["tags_json"]):
        name = normalize_topic_name(raw_name)
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def fetch_note(conn: sqlite3.Connection, *, user_id: str, task_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM practice_notes
        WHERE user_id = ? AND task_id = ?
        """,
        (user_id, task_id),
    ).fetchone()


def fetch_note_topics(conn: sqlite3.Connection, note_id: int) -> list[str]:
    rows = conn.execute(
        """
        SELECT topic_name
        FROM practice_note_topics
        WHERE note_id = ?
        ORDER BY topic_name
        """,
        (note_id,),
    ).fetchall()
    return [row["topic_name"] for row in rows]


def upsert_note(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    task_id: str,
    content_markdown: str,
    ai_summary: str | None = None,
    mistake_summary: str | None = None,
    invariant_summary: str | None = None,
    solution_pattern: str | None = None,
    source_submission_id: int | None = None,
    review_at: str | None = None,
    topics: list[str] | None = None,
) -> sqlite3.Row:
    conn.execute(
        """
        INSERT INTO practice_notes (
            user_id, task_id, content_markdown, ai_summary, mistake_summary,
            invariant_summary, solution_pattern, source_submission_id, review_at,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id, task_id) DO UPDATE SET
            content_markdown=excluded.content_markdown,
            ai_summary=excluded.ai_summary,
            mistake_summary=excluded.mistake_summary,
            invariant_summary=excluded.invariant_summary,
            solution_pattern=excluded.solution_pattern,
            source_submission_id=excluded.source_submission_id,
            review_at=excluded.review_at,
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            user_id,
            task_id,
            content_markdown,
            ai_summary,
            mistake_summary,
            invariant_summary,
            solution_pattern,
            source_submission_id,
            review_at,
        ),
    )
    note = fetch_note(conn, user_id=user_id, task_id=task_id)
    topic_names = normalize_note_topics(topics) if topics else note_topic_names_for_problem(conn, task_id)
    replace_note_topics(conn, note_id=note["id"], topics=topic_names)
    refresh_topic_memories(conn, user_id=user_id, topics=topic_names)
    return fetch_note(conn, user_id=user_id, task_id=task_id)


def replace_note_topics(conn: sqlite3.Connection, *, note_id: int, topics: list[str]) -> None:
    conn.execute("DELETE FROM practice_note_topics WHERE note_id = ?", (note_id,))
    conn.executemany(
        """
        INSERT OR IGNORE INTO practice_note_topics (note_id, topic_name)
        VALUES (?, ?)
        """,
        [(note_id, topic) for topic in normalize_note_topics(topics)],
    )


def normalize_note_topics(topics: list[str]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for topic in topics:
        name = normalize_topic_name(topic)
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def fetch_topic_memories(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    limit: int = 20,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM topic_memories
        WHERE user_id = ?
        ORDER BY updated_at DESC, topic_name
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()


def fetch_topic_memory(conn: sqlite3.Connection, *, user_id: str, topic_name: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM topic_memories
        WHERE user_id = ? AND topic_name = ?
        """,
        (user_id, normalize_topic_name(topic_name)),
    ).fetchone()


def refresh_topic_memories(conn: sqlite3.Connection, *, user_id: str, topics: list[str]) -> None:
    for topic_name in normalize_note_topics(topics):
        memory = build_topic_memory(conn, user_id=user_id, topic_name=topic_name)
        conn.execute(
            """
            INSERT INTO topic_memories (
                user_id, topic_name, memory_markdown, common_mistakes_json,
                recognition_cues_json, template_notes_json, mastery_level,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, topic_name) DO UPDATE SET
                memory_markdown=excluded.memory_markdown,
                common_mistakes_json=excluded.common_mistakes_json,
                recognition_cues_json=excluded.recognition_cues_json,
                template_notes_json=excluded.template_notes_json,
                mastery_level=excluded.mastery_level,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                user_id,
                topic_name,
                memory["memory_markdown"],
                json.dumps(memory["common_mistakes"], ensure_ascii=False),
                json.dumps(memory["recognition_cues"], ensure_ascii=False),
                json.dumps(memory["template_notes"], ensure_ascii=False),
                memory["mastery_level"],
            ),
        )


def build_topic_memory(conn: sqlite3.Connection, *, user_id: str, topic_name: str) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT n.*, p.question_id, p.title_zh, p.task_id
        FROM practice_notes n
        JOIN practice_note_topics nt ON nt.note_id = n.id
        JOIN problems p ON p.task_id = n.task_id
        WHERE n.user_id = ? AND nt.topic_name = ?
        ORDER BY n.updated_at DESC
        LIMIT 12
        """,
        (user_id, topic_name),
    ).fetchall()
    topic = TOPIC_BY_NAME.get(topic_name)
    label = topic.label if topic else topic_label(topic_name)
    mistakes = compact_unique([row["mistake_summary"] for row in rows if row["mistake_summary"]])
    invariants = compact_unique([row["invariant_summary"] for row in rows if row["invariant_summary"]])
    patterns = compact_unique([row["solution_pattern"] for row in rows if row["solution_pattern"]])
    passed_count = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM user_problem_state s
        JOIN problems p ON p.task_id = s.task_id
        WHERE s.user_id = ?
          AND s.status = 'passed'
          AND EXISTS (SELECT 1 FROM json_each(p.tags_json) WHERE value = ?)
        """,
        (user_id, topic_name),
    ).fetchone()["count"]
    mastery_level = "reviewing" if mistakes else "learning"
    if passed_count >= 5 and not mistakes:
        mastery_level = "solid"

    lines = [f"# {label}", "", "## 代表题笔记"]
    if rows:
        for row in rows[:8]:
            title = row["title_zh"] or row["task_id"]
            summary = row["ai_summary"] or first_note_line(row["content_markdown"]) or "已保存笔记"
            lines.append(f"- #{row['question_id']} {title}: {summary}")
    else:
        lines.append("- 暂无笔记")
    if mistakes:
        lines.extend(["", "## 常见错误", *[f"- {item}" for item in mistakes[:8]]])
    if invariants:
        lines.extend(["", "## 关键不变量", *[f"- {item}" for item in invariants[:8]]])
    if patterns:
        lines.extend(["", "## 解法范式", *[f"- {item}" for item in patterns[:8]]])

    return {
        "memory_markdown": "\n".join(lines),
        "common_mistakes": mistakes,
        "recognition_cues": invariants,
        "template_notes": patterns,
        "mastery_level": mastery_level,
    }


def compact_unique(items: list[str]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = " ".join(item.split())
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


def first_note_line(content: str | None) -> str | None:
    if not content:
        return None
    for line in content.splitlines():
        cleaned = line.strip().lstrip("#").strip()
        if cleaned:
            return cleaned[:120]
    return None


def create_review_event(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    note_id: int,
    rating: int,
) -> sqlite3.Row:
    cursor = conn.execute(
        """
        INSERT INTO review_events (user_id, note_id, rating)
        VALUES (?, ?, ?)
        """,
        (user_id, note_id, rating),
    )
    conn.execute(
        """
        UPDATE practice_notes
        SET review_at = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        (next_review_at(rating), note_id, user_id),
    )
    return conn.execute("SELECT * FROM review_events WHERE id = ?", (cursor.lastrowid,)).fetchone()


def next_review_at(rating: int) -> str:
    days = 1
    if rating >= 5:
        days = 14
    elif rating >= 4:
        days = 7
    elif rating >= 3:
        days = 3
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def topic_labels_for_names(names: list[str]) -> list[str]:
    return display_topic_labels(names)
