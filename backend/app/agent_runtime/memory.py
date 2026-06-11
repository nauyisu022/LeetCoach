from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from typing import Any

VALID_MEMORY_STATUSES = {"proposed", "accepted", "rejected", "archived"}
VALID_MEMORY_TYPES = {"preference", "weakness", "strength", "habit", "goal", "strategy"}


@dataclass(frozen=True)
class AgentMemoryRecord:
    id: int
    user_id: str
    memory_type: str
    scope: str
    topic: str | None
    task_id: str | None
    content: str
    source: str
    confidence: float
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class AgentThreadSummaryRecord:
    task_id: str
    summary: str
    last_message_id: int | None
    updated_at: str


@dataclass(frozen=True)
class LearningEventRecord:
    id: int
    user_id: str
    task_id: str | None
    topic: str | None
    event_type: str
    content: str
    evidence_message_ids: list[int]
    confidence: float
    created_at: str


def memory_record_from_row(row: sqlite3.Row) -> AgentMemoryRecord:
    return AgentMemoryRecord(
        id=row["id"],
        user_id=row["user_id"],
        memory_type=row["memory_type"],
        scope=row["scope"],
        topic=row["topic"],
        task_id=row["task_id"],
        content=row["content"],
        source=row["source"],
        confidence=row["confidence"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def thread_summary_record_from_row(row: sqlite3.Row) -> AgentThreadSummaryRecord:
    return AgentThreadSummaryRecord(
        task_id=row["task_id"],
        summary=row["summary"],
        last_message_id=row["last_message_id"],
        updated_at=row["updated_at"],
    )


def learning_event_record_from_row(row: sqlite3.Row) -> LearningEventRecord:
    return LearningEventRecord(
        id=row["id"],
        user_id=row["user_id"],
        task_id=row["task_id"],
        topic=row["topic"],
        event_type=row["event_type"],
        content=row["content"],
        evidence_message_ids=json.loads(row["evidence_message_ids"]),
        confidence=row["confidence"],
        created_at=row["created_at"],
    )


def fetch_memory_items(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    status: str | None = None,
    task_id: str | None = None,
    limit: int = 80,
) -> list[sqlite3.Row]:
    clauses = ["user_id = ?"]
    params: list[Any] = [user_id]
    if status:
        if status not in VALID_MEMORY_STATUSES:
            raise ValueError(f"Invalid memory status: {status}")
        clauses.append("status = ?")
        params.append(status)
    if task_id:
        clauses.append("(task_id = ? OR scope = 'global')")
        params.append(task_id)
    params.append(limit)
    return conn.execute(
        f"""
        SELECT *
        FROM user_memory_items
        WHERE {' AND '.join(clauses)}
        ORDER BY
          CASE status WHEN 'proposed' THEN 0 WHEN 'accepted' THEN 1 WHEN 'rejected' THEN 2 ELSE 3 END,
          updated_at DESC,
          id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()


def fetch_memory_records(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    status: str | None = None,
    task_id: str | None = None,
    limit: int = 80,
) -> list[AgentMemoryRecord]:
    return [
        memory_record_from_row(row)
        for row in fetch_memory_items(conn, user_id=user_id, status=status, task_id=task_id, limit=limit)
    ]


def fetch_memory_item(conn: sqlite3.Connection, *, user_id: str, memory_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM user_memory_items
        WHERE user_id = ? AND id = ?
        """,
        (user_id, memory_id),
    ).fetchone()


def update_memory_item(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    memory_id: int,
    content: str | None = None,
    status: str | None = None,
) -> sqlite3.Row | None:
    if status and status not in VALID_MEMORY_STATUSES:
        raise ValueError(f"Invalid memory status: {status}")
    assignments: list[str] = []
    params: list[Any] = []
    if content is not None:
        cleaned = content.strip()
        if not cleaned:
            raise ValueError("Memory content cannot be empty")
        assignments.append("content = ?")
        params.append(cleaned)
    if status is not None:
        assignments.append("status = ?")
        params.append(status)
    if not assignments:
        return fetch_memory_item(conn, user_id=user_id, memory_id=memory_id)

    assignments.append("updated_at = CURRENT_TIMESTAMP")
    params.extend([user_id, memory_id])
    conn.execute(
        f"""
        UPDATE user_memory_items
        SET {', '.join(assignments)}
        WHERE user_id = ? AND id = ?
        """,
        params,
    )
    return fetch_memory_item(conn, user_id=user_id, memory_id=memory_id)


def update_memory_record(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    memory_id: int,
    content: str | None = None,
    status: str | None = None,
) -> AgentMemoryRecord | None:
    row = update_memory_item(conn, user_id=user_id, memory_id=memory_id, content=content, status=status)
    return memory_record_from_row(row) if row else None


def set_memory_status(conn: sqlite3.Connection, *, user_id: str, memory_id: int, status: str) -> sqlite3.Row | None:
    return update_memory_item(conn, user_id=user_id, memory_id=memory_id, status=status)


def set_memory_record_status(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    memory_id: int,
    status: str,
) -> AgentMemoryRecord | None:
    row = set_memory_status(conn, user_id=user_id, memory_id=memory_id, status=status)
    return memory_record_from_row(row) if row else None


def fetch_accepted_memories_for_context(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    task_id: str,
    topics: list[str],
    limit: int = 6,
) -> list[sqlite3.Row]:
    topic_values = [topic for topic in dict.fromkeys(topics) if topic]
    topic_clause = ""
    params: list[Any] = [user_id, task_id]
    if topic_values:
        placeholders = ", ".join("?" for _ in topic_values)
        topic_clause = f" OR (scope = 'topic' AND topic IN ({placeholders}))"
        params.extend(topic_values)
    params.append(limit)
    return conn.execute(
        f"""
        SELECT *
        FROM user_memory_items
        WHERE user_id = ?
          AND status = 'accepted'
          AND (
            scope = 'global'
            OR (scope = 'task' AND task_id = ?)
            {topic_clause}
          )
        ORDER BY
          CASE scope WHEN 'task' THEN 0 WHEN 'topic' THEN 1 ELSE 2 END,
          confidence DESC,
          updated_at DESC
        LIMIT ?
        """,
        params,
    ).fetchall()


def create_learning_event(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    task_id: str | None,
    topic: str | None,
    event_type: str,
    content: str,
    evidence_message_ids: list[int],
    confidence: float,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO learning_events (
            user_id, task_id, topic, event_type, content, evidence_message_ids, confidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            task_id,
            topic,
            event_type,
            content,
            json.dumps(evidence_message_ids),
            confidence,
        ),
    )
    return int(cursor.lastrowid)


def fetch_recent_learning_events_for_context(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    task_id: str,
    topics: list[str],
    limit: int = 6,
) -> list[sqlite3.Row]:
    topic_values = [topic for topic in dict.fromkeys(topics) if topic]
    topic_clause = ""
    params: list[Any] = [user_id, task_id]
    if topic_values:
        placeholders = ", ".join("?" for _ in topic_values)
        topic_clause = f" OR topic IN ({placeholders})"
        params.extend(topic_values)
    params.append(limit)
    return conn.execute(
        f"""
        SELECT *
        FROM learning_events
        WHERE user_id = ?
          AND (
            task_id = ?
            {topic_clause}
          )
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()


def learning_event_rows_for_prompt(rows: list[sqlite3.Row]) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        key = (row["task_id"] or "", row["topic"] or "", row["event_type"])
        if key in seen:
            continue
        seen.add(key)
        events.append(
            {
                "type": row["event_type"],
                "task_id": row["task_id"] or "",
                "topic": row["topic"] or "",
                "content": row["content"],
                "created_at": row["created_at"],
            }
        )
    return events


def create_proposed_memory(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    task_id: str | None,
    topic: str | None,
    memory_type: str,
    scope: str,
    content: str,
    source: str,
    confidence: float,
) -> sqlite3.Row | None:
    if memory_type not in VALID_MEMORY_TYPES:
        raise ValueError(f"Invalid memory type: {memory_type}")
    cleaned = " ".join(content.split())
    if not cleaned:
        return None
    if _has_similar_open_memory(conn, user_id=user_id, task_id=task_id, content=cleaned):
        return None
    cursor = conn.execute(
        """
        INSERT INTO user_memory_items (
            user_id, memory_type, scope, topic, task_id, content, source, confidence, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'proposed')
        """,
        (user_id, memory_type, scope, topic, task_id, cleaned[:500], source, confidence),
    )
    return fetch_memory_item(conn, user_id=user_id, memory_id=int(cursor.lastrowid))


def upsert_thread_summary(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    task_id: str,
    summary: str,
    last_message_id: int,
) -> None:
    cleaned = summary.strip()
    if not cleaned:
        return
    conn.execute(
        """
        INSERT INTO coach_thread_summaries (
            user_id, task_id, summary, last_message_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id, task_id) DO UPDATE SET
            summary=excluded.summary,
            last_message_id=excluded.last_message_id,
            updated_at=CURRENT_TIMESTAMP
        """,
        (user_id, task_id, cleaned[:1200], last_message_id),
    )


def fetch_thread_summary(conn: sqlite3.Connection, *, user_id: str, task_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM coach_thread_summaries
        WHERE user_id = ? AND task_id = ?
        """,
        (user_id, task_id),
    ).fetchone()


def fetch_thread_summary_record(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    task_id: str,
) -> AgentThreadSummaryRecord | None:
    row = fetch_thread_summary(conn, user_id=user_id, task_id=task_id)
    return thread_summary_record_from_row(row) if row else None


def run_after_coach_response_hook(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    task_id: str,
    command: str,
    problem: dict[str, Any],
    user_content: str,
    assistant_text: str,
    user_message_id: int,
    assistant_message_id: int,
) -> sqlite3.Row | None:
    summary = _thread_summary_line(command=command, user_content=user_content, assistant_text=assistant_text)
    upsert_thread_summary(
        conn,
        user_id=user_id,
        task_id=task_id,
        summary=summary,
        last_message_id=assistant_message_id,
    )
    candidate = _memory_candidate(command=command, problem=problem, assistant_text=assistant_text)
    if not candidate:
        return None
    evidence_ids = [user_message_id, assistant_message_id]
    create_learning_event(
        conn,
        user_id=user_id,
        task_id=task_id,
        topic=candidate["topic"],
        event_type=candidate["event_type"],
        content=candidate["content"],
        evidence_message_ids=evidence_ids,
        confidence=candidate["confidence"],
    )
    return create_proposed_memory(
        conn,
        user_id=user_id,
        task_id=task_id,
        topic=candidate["topic"],
        memory_type=candidate["memory_type"],
        scope=candidate["scope"],
        content=candidate["content"],
        source=f"after_coach_response:{command}",
        confidence=candidate["confidence"],
    )


def memory_rows_for_prompt(rows: list[sqlite3.Row]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for row in rows:
        scope = row["scope"]
        if scope == "topic" and row["topic"]:
            label = f"topic:{row['topic']}"
        elif scope == "task" and row["task_id"]:
            label = f"task:{row['task_id']}"
        else:
            label = "global"
        items.append({"scope": label, "content": row["content"]})
    return items


def _memory_candidate(command: str, problem: dict[str, Any], assistant_text: str) -> dict[str, Any] | None:
    if _is_empty_or_config_error(assistant_text):
        return None
    summary = _extract_summary(assistant_text)
    if not summary:
        return None
    tags = problem.get("tags") or []
    topic = tags[0] if tags else None
    title = f"{problem.get('question_id')}. {problem.get('task_id')}"
    if command == "/diagnose":
        return {
            "memory_type": "weakness",
            "scope": "task",
            "topic": topic,
            "event_type": "mistake",
            "content": f"{title} 诊断线索：{summary}",
            "confidence": 0.72,
        }
    if command == "/explain":
        return {
            "memory_type": "strategy",
            "scope": "task",
            "topic": topic,
            "event_type": "insight",
            "content": f"{title} 解法记忆：{summary}",
            "confidence": 0.62,
        }
    if _looks_personal_learning_turn(assistant_text):
        return {
            "memory_type": "strategy",
            "scope": "task",
            "topic": topic,
            "event_type": "insight",
            "content": f"{title} 学习线索：{summary}",
            "confidence": 0.58,
        }
    return None


def _thread_summary_line(*, command: str, user_content: str, assistant_text: str) -> str:
    assistant_summary = _extract_summary(assistant_text) or assistant_text.strip()
    user_summary = " ".join(user_content.split())[:160]
    return f"{command}: 用户问「{user_summary}」；回答要点：{assistant_summary[:420]}"


def _extract_summary(text: str) -> str:
    cleaned_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^[-*]\s*", "", line)
        line = re.sub(r"^\d+[.)]\s*", "", line)
        if not line or line.startswith("```"):
            continue
        if line in {"结论", "最小错误点", "失败 case 怎么触发", "应该维护的不变量", "最小修改方向"}:
            continue
        cleaned_lines.append(line)
        if len(" ".join(cleaned_lines)) >= 260:
            break
    return " ".join(cleaned_lines)[:280]


def _is_empty_or_config_error(text: str) -> bool:
    stripped = text.strip()
    return not stripped or stripped.startswith("未配置 ANTHROPIC_API_KEY") or stripped.startswith("AI 没有返回内容")


def _looks_personal_learning_turn(text: str) -> bool:
    return any(keyword in text for keyword in ("你的代码", "你现在", "下次", "容易错", "记住", "不变量"))


def _has_similar_open_memory(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    task_id: str | None,
    content: str,
) -> bool:
    prefix = content[:96]
    row = conn.execute(
        """
        SELECT 1
        FROM user_memory_items
        WHERE user_id = ?
          AND status IN ('proposed', 'accepted')
          AND COALESCE(task_id, '') = COALESCE(?, '')
          AND content LIKE ?
        LIMIT 1
        """,
        (user_id, task_id, f"{prefix}%"),
    ).fetchone()
    return row is not None
