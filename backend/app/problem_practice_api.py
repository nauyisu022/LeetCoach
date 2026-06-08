from __future__ import annotations

import json
import sqlite3
from typing import Any, Protocol

from .leetcode_cn import fetch_chinese_problem, fetch_chinese_titles
from .practice import PracticeFilters, fetch_practice_queue, fetch_topic_insights, practice_reason
from .schemas import (
    PracticeInsightsResponse,
    PracticeQueueItem,
    PracticeQueueResponse,
    PracticeTopicInsight,
    ProblemDetail,
    ProblemSummary,
    ProblemTag,
    ProgressSummary,
    SavedSolution,
)
from .semantic_tests import effective_input_output_for_problem
from .topic_taxonomy import CATEGORY_ORDER, TOPIC_BY_NAME, display_topic_labels, normalize_topic_name, topic_aliases


class ConnectionFactory(Protocol):
    def __call__(self) -> sqlite3.Connection:
        ...


class ProblemNotFoundError(LookupError):
    pass


class ProblemPracticeApiService:
    def __init__(self, *, user_id: str, connection_factory: ConnectionFactory) -> None:
        self.user_id = user_id
        self.connection_factory = connection_factory

    def list_problems(
        self,
        *,
        difficulty: str | None = None,
        tag: str | None = None,
        tags: list[str] | None = None,
        status: str | None = None,
        search: str | None = None,
        limit: int = 3000,
    ) -> list[ProblemSummary]:
        clauses: list[str] = []
        params: list[Any] = []
        if difficulty:
            clauses.append("p.difficulty = ?")
            params.append(difficulty)
        selected_tags = [item for item in [*(tags or []), *([tag] if tag else [])] if item]
        for selected_tag in dict.fromkeys(selected_tags):
            aliases = topic_aliases(selected_tag)
            placeholders = ", ".join("?" for _ in aliases)
            clauses.append(f"EXISTS (SELECT 1 FROM json_each(p.tags_json) WHERE value IN ({placeholders}))")
            params.extend(aliases)
        if status:
            clauses.append("COALESCE(s.status, 'unseen') = ?")
            params.append(status)
        if search:
            clauses.append("(p.task_id LIKE ? OR p.title_zh LIKE ? OR CAST(p.question_id AS TEXT) LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        conn = self.connection_factory()
        try:
            rows = _problem_summary_rows(conn, user_id=self.user_id, where=where, params=params, limit=limit)
            ensure_chinese_titles(conn, rows)
            rows = _problem_summary_rows(conn, user_id=self.user_id, where=where, params=params, limit=limit)
            return [problem_summary_from_row(row) for row in rows]
        finally:
            conn.close()

    def progress_summary(self) -> ProgressSummary:
        conn = self.connection_factory()
        try:
            row = conn.execute(
                """
                SELECT
                  COUNT(*) AS total,
                  SUM(CASE WHEN COALESCE(s.status, 'unseen') = 'passed' THEN 1 ELSE 0 END) AS passed,
                  SUM(CASE WHEN COALESCE(s.status, 'unseen') = 'needs_review' THEN 1 ELSE 0 END) AS needs_review,
                  SUM(CASE WHEN COALESCE(s.status, 'unseen') = 'unseen' THEN 1 ELSE 0 END) AS unseen
                FROM problems p
                LEFT JOIN user_problem_state s ON s.user_id = ? AND s.task_id = p.task_id
                """,
                (self.user_id,),
            ).fetchone()
            today_row = conn.execute(
                """
                SELECT COUNT(DISTINCT task_id) AS today_passed
                FROM submissions
                WHERE user_id = ?
                  AND passed = 1
                  AND date(datetime(created_at, '+8 hours')) = date(datetime('now', '+8 hours'))
                """,
                (self.user_id,),
            ).fetchone()
        finally:
            conn.close()
        return ProgressSummary(
            total=int(row["total"] or 0),
            passed=int(row["passed"] or 0),
            needs_review=int(row["needs_review"] or 0),
            unseen=int(row["unseen"] or 0),
            today_passed=int(today_row["today_passed"] or 0),
        )

    def problem_tags(self) -> list[ProblemTag]:
        conn = self.connection_factory()
        try:
            rows = conn.execute(
                """
                SELECT value AS name, COUNT(*) AS count
                FROM problems, json_each(problems.tags_json)
                GROUP BY value
                ORDER BY count DESC, name
                """
            ).fetchall()
        finally:
            conn.close()
        totals: dict[str, int] = {}
        for row in rows:
            canonical_name = normalize_topic_name(row["name"])
            totals[canonical_name] = totals.get(canonical_name, 0) + row["count"]
        tags: list[ProblemTag] = []
        for name, count in totals.items():
            topic = TOPIC_BY_NAME.get(name)
            if topic:
                tags.append(
                    ProblemTag(
                        name=topic.name,
                        label=topic.label,
                        category=topic.category,
                        category_label=topic.category_label,
                        aliases=list(topic.aliases),
                        count=count,
                    )
                )
            else:
                tags.append(
                    ProblemTag(
                        name=name,
                        label=name,
                        category="other",
                        category_label="其他",
                        aliases=[name],
                        count=count,
                    )
                )
        return sorted(
            tags,
            key=lambda item: (
                CATEGORY_ORDER.get(item.category, 999),
                -item.count,
                item.label,
            ),
        )

    def practice_queue(self, filters: PracticeFilters) -> PracticeQueueResponse:
        conn = self.connection_factory()
        try:
            queue = fetch_practice_queue(conn, filters)
            ensure_chinese_titles(conn, queue.rows)
            queue = fetch_practice_queue(conn, filters)
            items = [
                PracticeQueueItem(
                    **problem_summary_from_row(row).model_dump(),
                    recommendation_reason=practice_reason(row, queue.active_topics),
                )
                for row in queue.rows
            ]
        finally:
            conn.close()
        return PracticeQueueResponse(
            active_topics=queue.active_topics,
            strategy="待复习 > 做过未通过 > 未做高频 > 难度递进 > 已通过巩固",
            items=items,
            next_task_id=items[0].task_id if items else None,
        )

    def practice_insights(self, *, limit: int = 8) -> PracticeInsightsResponse:
        conn = self.connection_factory()
        try:
            insights = fetch_topic_insights(conn, user_id=self.user_id, limit=limit)
        finally:
            conn.close()
        return PracticeInsightsResponse(
            strategy="优先看待复习和做过未通过的考点，再结合高频未做题补齐覆盖",
            topics=[PracticeTopicInsight(**insight.__dict__) for insight in insights],
        )

    def problem_detail(self, task_id: str) -> ProblemDetail:
        return problem_detail_from_row(self.fetch_problem_row(task_id))

    def fetch_problem_row(self, task_id: str) -> sqlite3.Row:
        conn = self.connection_factory()
        try:
            row = _fetch_problem_row(conn, user_id=self.user_id, task_id=task_id)
            if not row:
                raise ProblemNotFoundError(f"Problem not found: {task_id}")
            if not row["problem_description_zh"]:
                try:
                    title_zh, description_zh = fetch_chinese_problem(task_id)
                except Exception:
                    title_zh, description_zh = None, None
                if title_zh or description_zh:
                    with conn:
                        conn.execute(
                            """
                            UPDATE problems
                            SET title_zh = COALESCE(?, title_zh),
                                problem_description_zh = COALESCE(?, problem_description_zh)
                            WHERE task_id = ?
                            """,
                            (title_zh, description_zh, task_id),
                        )
                    row = _fetch_problem_row(conn, user_id=self.user_id, task_id=task_id)
            return row
        finally:
            conn.close()


def _problem_summary_rows(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    where: str,
    params: list[Any],
    limit: int,
) -> list[sqlite3.Row]:
    return conn.execute(
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
        [user_id, *params, limit],
    ).fetchall()


def _fetch_problem_row(conn: sqlite3.Connection, *, user_id: str, task_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT p.*, COALESCE(s.status, 'unseen') AS status,
               COALESCE(s.submit_count, 0) AS submit_count,
               COALESCE(s.pass_count, 0) AS pass_count,
               s.last_submitted_at,
               c.frequency AS codetop_frequency,
               c.last_asked_at AS codetop_last_asked_at,
               us.id AS saved_solution_id,
               us.user_id AS saved_solution_user_id,
               us.code AS saved_solution_code,
               us.language AS saved_solution_language,
               us.notes AS saved_solution_notes,
               us.created_at AS saved_solution_created_at,
               us.updated_at AS saved_solution_updated_at
        FROM problems p
        LEFT JOIN user_problem_state s ON s.user_id = ? AND s.task_id = p.task_id
        LEFT JOIN codetop_problem_signals c ON c.task_id = p.task_id
        LEFT JOIN user_solutions us ON us.task_id = p.task_id AND us.user_id = ?
        WHERE p.task_id = ?
        """,
        (user_id, user_id, task_id),
    ).fetchone()


def ensure_chinese_titles(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> None:
    missing = [row["task_id"] for row in rows if not row["title_zh"]]
    if not missing:
        return
    try:
        titles = fetch_chinese_titles(missing)
    except Exception:
        return
    if not titles:
        return
    with conn:
        conn.executemany(
            "UPDATE problems SET title_zh = ? WHERE task_id = ? AND title_zh IS NULL",
            [(title, task_id) for task_id, title in titles.items()],
        )


def problem_summary_from_row(row: sqlite3.Row) -> ProblemSummary:
    return ProblemSummary(
        task_id=row["task_id"],
        question_id=row["question_id"],
        title=row["title_zh"] or row["task_id"],
        difficulty=row["difficulty"],
        tags=display_topic_labels(json.loads(row["tags_json"])),
        status=row["status"],
        submit_count=row["submit_count"],
        pass_count=row["pass_count"],
        last_submitted_at=row["last_submitted_at"],
        codetop_frequency=row["codetop_frequency"],
        codetop_last_asked_at=row["codetop_last_asked_at"],
    )


def problem_detail_from_row(row: sqlite3.Row) -> ProblemDetail:
    base = problem_summary_from_row(row).model_dump()
    base["title"] = row["title_zh"] or row["task_id"]
    return ProblemDetail(
        **base,
        problem_description=row["problem_description_zh"] or row["problem_description"],
        starter_code=row["starter_code"],
        entry_point=row["entry_point"],
        input_output=effective_input_output_for_problem(row["task_id"], row["input_output_json"]),
        saved_solution=saved_solution_from_problem_row(row),
    )


def saved_solution_from_problem_row(row: sqlite3.Row) -> SavedSolution | None:
    if row["saved_solution_id"] is None:
        return None
    return SavedSolution(
        id=row["saved_solution_id"],
        user_id=row["saved_solution_user_id"],
        task_id=row["task_id"],
        code=row["saved_solution_code"],
        language=row["saved_solution_language"],
        notes=row["saved_solution_notes"],
        created_at=row["saved_solution_created_at"],
        updated_at=row["saved_solution_updated_at"],
    )
