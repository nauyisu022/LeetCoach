from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import json
import sqlite3

from .topic_taxonomy import TOPIC_BY_NAME, normalize_topic_name, topic_aliases, topic_label


@dataclass(frozen=True)
class PracticeFilters:
    user_id: str = "local"
    topics: tuple[str, ...] = ()
    difficulty: str | None = None
    status: str | None = None
    search: str | None = None
    current_task_id: str | None = None
    exclude_current: bool = False
    match_any_topic: bool = False
    limit: int = 80


@dataclass(frozen=True)
class PracticeQueue:
    rows: list[sqlite3.Row]
    active_topics: list[str]


@dataclass(frozen=True)
class PracticeTopicInsight:
    name: str
    label: str
    category: str
    category_label: str
    total_problem_count: int
    unseen_count: int
    attempted_count: int
    needs_review_count: int
    passed_count: int
    submit_count: int
    pass_count: int
    codetop_frequency: int
    progress: float
    priority_score: float
    recommendation: str
    next_task_id: str | None


def topic_names_for_problem(conn: sqlite3.Connection, task_id: str | None) -> tuple[str, ...]:
    if not task_id:
        return ()
    row = conn.execute("SELECT tags_json FROM problems WHERE task_id = ?", (task_id,)).fetchone()
    if not row:
        return ()
    names: list[str] = []
    seen: set[str] = set()
    for raw_name in json.loads(row["tags_json"]):
        canonical = normalize_topic_name(raw_name)
        if canonical in seen:
            continue
        seen.add(canonical)
        names.append(canonical)
    return tuple(names)


def fetch_practice_queue(conn: sqlite3.Connection, filters: PracticeFilters) -> PracticeQueue:
    topics = filters.topics or topic_names_for_problem(conn, filters.current_task_id)
    clauses: list[str] = []
    params: list[Any] = []

    if filters.match_any_topic and topics:
        aliases = [alias for topic in dict.fromkeys(topics) for alias in topic_aliases(topic)]
        placeholders = ", ".join("?" for _ in aliases)
        clauses.append(f"EXISTS (SELECT 1 FROM json_each(p.tags_json) WHERE value IN ({placeholders}))")
        params.extend(aliases)
    else:
        for topic in dict.fromkeys(topics):
            aliases = topic_aliases(topic)
            placeholders = ", ".join("?" for _ in aliases)
            clauses.append(f"EXISTS (SELECT 1 FROM json_each(p.tags_json) WHERE value IN ({placeholders}))")
            params.extend(aliases)

    if filters.difficulty:
        clauses.append("p.difficulty = ?")
        params.append(filters.difficulty)

    if filters.status:
        clauses.append("COALESCE(s.status, 'unseen') = ?")
        params.append(filters.status)

    if filters.search:
        clauses.append("(p.task_id LIKE ? OR p.title_zh LIKE ? OR CAST(p.question_id AS TEXT) LIKE ?)")
        params.extend([f"%{filters.search}%", f"%{filters.search}%", f"%{filters.search}%"])

    if filters.exclude_current and filters.current_task_id:
        clauses.append("p.task_id <> ?")
        params.append(filters.current_task_id)

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    rows = conn.execute(
        f"""
        SELECT p.task_id, p.question_id, p.title_zh, p.difficulty, p.tags_json,
               COALESCE(s.status, 'unseen') AS status,
               COALESCE(s.submit_count, 0) AS submit_count,
               COALESCE(s.pass_count, 0) AS pass_count,
               s.last_submitted_at,
               c.frequency AS codetop_frequency,
               c.last_asked_at AS codetop_last_asked_at
        FROM problems p
        LEFT JOIN user_problem_state s ON s.user_id = ? AND s.task_id = p.task_id
        LEFT JOIN codetop_problem_signals c ON c.task_id = p.task_id
        {where}
        ORDER BY
          CASE COALESCE(s.status, 'unseen')
            WHEN 'needs_review' THEN 0
            WHEN 'attempted' THEN 1
            WHEN 'unseen' THEN 2
            WHEN 'passed' THEN 3
            ELSE 4
          END,
          COALESCE(c.frequency, 0) DESC,
          CASE p.difficulty WHEN 'Easy' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END,
          COALESCE(s.submit_count, 0) ASC,
          p.question_id
        LIMIT ?
        """,
        [filters.user_id, *params, filters.limit],
    ).fetchall()
    return PracticeQueue(rows=rows, active_topics=[topic_label(topic) for topic in topics])


def practice_reason(row: sqlite3.Row, active_topics: list[str]) -> str:
    status = row["status"]
    frequency = row["codetop_frequency"] or 0
    topic_text = "、".join(active_topics[:3])
    if status == "needs_review":
        return "待复习题，优先巩固错题"
    if row["submit_count"] > 0 and row["pass_count"] == 0:
        return "做过但还没通过，适合继续突破"
    if topic_text and frequency:
        return f"同考点：{topic_text}；CodeTop 热度 {frequency}"
    if topic_text:
        return f"同考点：{topic_text}"
    if frequency:
        return f"CodeTop 高频题，热度 {frequency}"
    return "按当前队列策略推荐"


def fetch_topic_insights(
    conn: sqlite3.Connection,
    *,
    user_id: str = "local",
    limit: int = 8,
) -> list[PracticeTopicInsight]:
    rows = conn.execute(
        """
        SELECT p.task_id, p.tags_json,
               COALESCE(s.status, 'unseen') AS status,
               COALESCE(s.submit_count, 0) AS submit_count,
               COALESCE(s.pass_count, 0) AS pass_count,
               COALESCE(c.frequency, 0) AS codetop_frequency
        FROM problems p
        LEFT JOIN user_problem_state s ON s.user_id = ? AND s.task_id = p.task_id
        LEFT JOIN codetop_problem_signals c ON c.task_id = p.task_id
        """,
        (user_id,),
    ).fetchall()

    stats: dict[str, dict[str, Any]] = {}
    for row in rows:
        seen_topics: set[str] = set()
        for raw_name in json.loads(row["tags_json"]):
            name = normalize_topic_name(raw_name)
            if name in seen_topics:
                continue
            seen_topics.add(name)
            topic = TOPIC_BY_NAME.get(name)
            bucket = stats.setdefault(
                name,
                {
                    "name": name,
                    "label": topic.label if topic else name,
                    "category": topic.category if topic else "other",
                    "category_label": topic.category_label if topic else "其他",
                    "total_problem_count": 0,
                    "unseen_count": 0,
                    "attempted_count": 0,
                    "needs_review_count": 0,
                    "passed_count": 0,
                    "submit_count": 0,
                    "pass_count": 0,
                    "codetop_frequency": 0,
                },
            )
            status = row["status"]
            bucket["total_problem_count"] += 1
            bucket["submit_count"] += row["submit_count"]
            bucket["pass_count"] += row["pass_count"]
            bucket["codetop_frequency"] += row["codetop_frequency"]
            if status == "passed":
                bucket["passed_count"] += 1
            elif status == "needs_review":
                bucket["needs_review_count"] += 1
            elif status == "attempted":
                bucket["attempted_count"] += 1
            else:
                bucket["unseen_count"] += 1

    insights: list[PracticeTopicInsight] = []
    for name, bucket in stats.items():
        total = bucket["total_problem_count"]
        progress = bucket["passed_count"] / total if total else 0.0
        frequency_density = bucket["codetop_frequency"] / total if total else 0
        priority_score = (
            bucket["needs_review_count"] * 50
            + bucket["attempted_count"] * 35
            + min(bucket["unseen_count"], 5) * 0.5
            + min(frequency_density / 15, 8)
            + (1 - progress) * 12
        )
        next_queue = fetch_practice_queue(
            conn,
            PracticeFilters(user_id=user_id, topics=(name,), limit=1),
        )
        insights.append(
            PracticeTopicInsight(
                **bucket,
                progress=round(progress, 4),
                priority_score=round(priority_score, 2),
                recommendation=_topic_recommendation(bucket),
                next_task_id=next_queue.rows[0]["task_id"] if next_queue.rows else None,
            )
        )

    return sorted(
        insights,
        key=lambda item: (
            -item.priority_score,
            item.progress,
            -item.codetop_frequency,
            item.label,
        ),
    )[:limit]


def _topic_recommendation(bucket: dict[str, Any]) -> str:
    if bucket["needs_review_count"]:
        return f"{bucket['needs_review_count']} 道待复习，先回到错题"
    if bucket["attempted_count"]:
        return f"{bucket['attempted_count']} 道做过未通过，适合继续突破"
    if bucket["passed_count"] == 0:
        return "尚未通过，优先建立基本题感"
    if bucket["passed_count"] < bucket["total_problem_count"]:
        return "继续补齐未做题，形成稳定题型识别"
    return "已通过，后续用于间隔复习"
