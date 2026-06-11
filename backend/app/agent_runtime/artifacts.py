from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any


RECOMMENDATION_SET_TYPE = "recommendation_set"


@dataclass(frozen=True)
class AgentArtifactRecord:
    id: int
    user_id: str
    artifact_type: str
    source_task_id: str | None
    title: str
    payload: dict[str, Any]
    status: str
    created_at: str
    updated_at: str


def create_recommendation_set(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    source_task_id: str,
    query: str,
    interpreted_topics: list[str],
    results: list[dict[str, Any]],
) -> AgentArtifactRecord | None:
    if not results:
        return None
    title = _recommendation_title(source_task_id, interpreted_topics)
    payload = {
        "query": query,
        "source_task_id": source_task_id,
        "interpreted_topics": interpreted_topics,
        "items": [
            {
                "order": index,
                "task_id": item["task_id"],
                "question_id": item["question_id"],
                "title": item["title"],
                "difficulty": item["difficulty"],
                "tags": item.get("tags") or [],
                "codetop_frequency": item.get("codetop_frequency"),
                "status": "not_started",
            }
            for index, item in enumerate(results, start=1)
        ],
    }
    cursor = conn.execute(
        """
        INSERT INTO agent_artifacts (
          user_id, artifact_type, source_task_id, title, payload_json, status, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)
        """,
        (
            user_id,
            RECOMMENDATION_SET_TYPE,
            source_task_id,
            title,
            json.dumps(payload, ensure_ascii=False),
        ),
    )
    record = fetch_agent_artifact(conn, user_id=user_id, artifact_id=int(cursor.lastrowid))
    return record


def latest_recommendation_set(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    source_task_id: str | None = None,
) -> AgentArtifactRecord | None:
    params: list[Any] = [user_id, RECOMMENDATION_SET_TYPE]
    source_filter = ""
    if source_task_id:
        source_filter = "AND source_task_id = ?"
        params.append(source_task_id)
    row = conn.execute(
        f"""
        SELECT *
        FROM agent_artifacts
        WHERE user_id = ?
          AND artifact_type = ?
          AND status = 'active'
          {source_filter}
        ORDER BY id DESC
        LIMIT 1
        """,
        params,
    ).fetchone()
    return agent_artifact_from_row(row)


def fetch_agent_artifact(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    artifact_id: int,
) -> AgentArtifactRecord | None:
    row = conn.execute(
        """
        SELECT *
        FROM agent_artifacts
        WHERE user_id = ? AND id = ?
        """,
        (user_id, artifact_id),
    ).fetchone()
    return agent_artifact_from_row(row)


def agent_artifact_from_row(row: sqlite3.Row | None) -> AgentArtifactRecord | None:
    if row is None:
        return None
    return AgentArtifactRecord(
        id=row["id"],
        user_id=row["user_id"],
        artifact_type=row["artifact_type"],
        source_task_id=row["source_task_id"],
        title=row["title"],
        payload=json.loads(row["payload_json"]),
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _recommendation_title(source_task_id: str, interpreted_topics: list[str]) -> str:
    topic_text = "、".join(interpreted_topics[:3])
    if topic_text:
        return f"{source_task_id} 的相似题单：{topic_text}"
    return f"{source_task_id} 的相似题单"
