from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..db import get_connection
from ..practice import PracticeFilters, fetch_practice_queue, fetch_topic_insights, practice_reason, topic_names_for_problem
from ..topic_taxonomy import display_topic_labels


def build_agent_problem_payload(row: sqlite3.Row, *, user_id: str) -> dict[str, Any]:
    return {
        "task_id": row["task_id"],
        "question_id": row["question_id"],
        "difficulty": row["difficulty"],
        "tags": display_topic_labels(json.loads(row["tags_json"])),
        "problem_description": row["problem_description_zh"] or row["problem_description"],
        "practice_context": build_practice_context(row["task_id"], user_id=user_id),
    }


def build_practice_context(task_id: str, *, user_id: str) -> dict[str, Any]:
    conn = get_connection()
    try:
        current_topics = set(topic_names_for_problem(conn, task_id))
        insights = fetch_topic_insights(conn, user_id=user_id, limit=8)
        relevant_insights = [insight for insight in insights if insight.name in current_topics] or insights[:3]
        queue = fetch_practice_queue(
            conn,
            PracticeFilters(
                user_id=user_id,
                current_task_id=task_id,
                exclude_current=True,
                match_any_topic=True,
                limit=3,
            ),
        )
    finally:
        conn.close()

    return {
        "weak_topics": [
            {
                "label": insight.label,
                "passed_count": insight.passed_count,
                "total_problem_count": insight.total_problem_count,
                "recommendation": insight.recommendation,
            }
            for insight in relevant_insights[:3]
        ],
        "same_topic_next": [
            {
                "question_id": row["question_id"],
                "title": row["title_zh"] or row["task_id"],
                "reason": practice_reason(row, queue.active_topics),
            }
            for row in queue.rows[:3]
        ],
    }
