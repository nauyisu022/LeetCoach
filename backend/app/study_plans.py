from __future__ import annotations

import argparse
import json
import sqlite3
import urllib.request
from typing import Any

from .db import get_connection, init_db
from .problem_practice_api import problem_summary_from_row
from .schemas import (
    StudyPlanGroupSummary,
    StudyPlanItemsResponse,
    StudyPlanListResponse,
    StudyPlanProblemSummary,
    StudyPlanSummary,
)
from .topic_taxonomy import topic_aliases

LEETCODE_GRAPHQL_URL = "https://leetcode.cn/graphql/"
LEETCODE_STUDY_PLAN_URL = "https://leetcode.cn/studyplan/{slug}/"
LEETCODE_PROBLEM_URL = "https://leetcode.cn/problems/{slug}/"


class StudyPlanNotFoundError(LookupError):
    pass


def fetch_leetcode_study_plan(slug: str) -> dict[str, Any]:
    body = json.dumps(
        {
            "query": """
            query studyPlanDetail($slug: String!) {
              studyPlanV2Detail(planSlug: $slug) {
                name
                slug
                description
                planSubGroups {
                  name
                  slug
                  questions {
                    titleSlug
                    questionFrontendId
                    translatedTitle
                    difficulty
                    paidOnly
                  }
                }
              }
            }
            """,
            "variables": {"slug": slug},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        LEETCODE_GRAPHQL_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
            "Referer": LEETCODE_STUDY_PLAN_URL.format(slug=slug),
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    errors = payload.get("errors")
    if errors:
        raise StudyPlanNotFoundError(f"LeetCode study plan query failed: {errors[0].get('message', errors[0])}")
    plan = payload.get("data", {}).get("studyPlanV2Detail")
    if not plan:
        raise StudyPlanNotFoundError(f"LeetCode study plan not found: {slug}")
    return plan


def sync_leetcode_study_plan(conn: sqlite3.Connection, slug: str) -> StudyPlanSummary:
    plan = fetch_leetcode_study_plan(slug)
    source_url = LEETCODE_STUDY_PLAN_URL.format(slug=slug)
    with conn:
        conn.execute(
            """
            INSERT INTO study_plans (
              slug, title, source_type, source_url, description, fetched_at, created_at, updated_at
            ) VALUES (?, ?, 'leetcode_study_plan', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(slug) DO UPDATE SET
              title=excluded.title,
              source_url=excluded.source_url,
              description=excluded.description,
              fetched_at=CURRENT_TIMESTAMP,
              updated_at=CURRENT_TIMESTAMP
            """,
            (plan["slug"], plan["name"], source_url, plan.get("description")),
        )
        plan_id = conn.execute("SELECT id FROM study_plans WHERE slug = ?", (plan["slug"],)).fetchone()["id"]
        conn.execute("DELETE FROM study_plan_items WHERE plan_id = ?", (plan_id,))
        plan_position = 0
        for group_position, group in enumerate(plan.get("planSubGroups") or [], start=1):
            for item_position, question in enumerate(group.get("questions") or [], start=1):
                plan_position += 1
                external_slug = question["titleSlug"]
                conn.execute(
                    """
                    INSERT INTO study_plan_items (
                      plan_id, task_id, external_slug, question_id, title, difficulty,
                      group_name, group_slug, group_position, item_position, plan_position,
                      paid_only, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (
                        plan_id,
                        external_slug,
                        external_slug,
                        int(question["questionFrontendId"]),
                        question.get("translatedTitle") or external_slug,
                        normalize_difficulty(question.get("difficulty")),
                        group["name"],
                        group["slug"],
                        group_position,
                        item_position,
                        plan_position,
                        1 if question.get("paidOnly") else 0,
                    ),
                )
    return get_study_plan_summary(conn, user_id="local", slug=plan["slug"])


def list_study_plans(conn: sqlite3.Connection, *, user_id: str) -> StudyPlanListResponse:
    rows = conn.execute(_study_plan_summary_sql(), (user_id,)).fetchall()
    return StudyPlanListResponse(plans=[_study_plan_summary_from_row(row) for row in rows])


def get_study_plan_items(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    slug: str,
    group_slug: str | None = None,
    difficulty: str | None = None,
    tags: list[str] | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 3000,
) -> StudyPlanItemsResponse:
    plan = get_study_plan_summary(conn, user_id=user_id, slug=slug)
    groups = _study_plan_groups(conn, user_id=user_id, plan_id=plan.id)
    items = _study_plan_item_rows(
        conn,
        user_id=user_id,
        plan_id=plan.id,
        plan_slug=plan.slug,
        group_slug=group_slug,
        difficulty=difficulty,
        tags=tags,
        status=status,
        search=search,
        limit=limit,
    )
    next_item = next((item for item in items if item.available and item.status != "passed"), None)
    return StudyPlanItemsResponse(
        plan=plan,
        groups=groups,
        items=items,
        next_task_id=next_item.task_id if next_item else None,
    )


def get_study_plan_summary(conn: sqlite3.Connection, *, user_id: str, slug: str) -> StudyPlanSummary:
    row = conn.execute(_study_plan_summary_sql("WHERE sp.slug = ?"), (user_id, slug)).fetchone()
    if not row:
        raise StudyPlanNotFoundError(f"Study plan not found: {slug}")
    return _study_plan_summary_from_row(row)


def normalize_difficulty(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized == "easy":
        return "Easy"
    if normalized == "medium":
        return "Medium"
    if normalized == "hard":
        return "Hard"
    return value or ""


def _study_plan_summary_sql(where: str = "") -> str:
    return f"""
        SELECT
          sp.id,
          sp.slug,
          sp.title,
          sp.source_type,
          sp.source_url,
          sp.description,
          sp.fetched_at,
          COUNT(i.id) AS total_count,
          SUM(CASE WHEN p.task_id IS NOT NULL THEN 1 ELSE 0 END) AS available_count,
          SUM(CASE WHEN p.task_id IS NULL AND i.id IS NOT NULL THEN 1 ELSE 0 END) AS missing_count,
          SUM(CASE WHEN p.task_id IS NOT NULL AND COALESCE(s.status, 'unseen') = 'passed' THEN 1 ELSE 0 END) AS passed_count,
          SUM(CASE WHEN p.task_id IS NOT NULL AND COALESCE(s.status, 'unseen') = 'needs_review' THEN 1 ELSE 0 END) AS needs_review_count,
          SUM(CASE WHEN p.task_id IS NOT NULL AND COALESCE(s.status, 'unseen') = 'unseen' THEN 1 ELSE 0 END) AS unseen_count
        FROM study_plans sp
        LEFT JOIN study_plan_items i ON i.plan_id = sp.id
        LEFT JOIN problems p ON p.task_id = i.task_id
        LEFT JOIN user_problem_state s ON s.user_id = ? AND s.task_id = p.task_id
        {where}
        GROUP BY sp.id
        ORDER BY sp.id
    """


def _study_plan_summary_from_row(row: sqlite3.Row) -> StudyPlanSummary:
    total = int(row["total_count"] or 0)
    passed = int(row["passed_count"] or 0)
    return StudyPlanSummary(
        id=row["id"],
        slug=row["slug"],
        title=row["title"],
        source_type=row["source_type"],
        source_url=row["source_url"],
        description=row["description"],
        fetched_at=row["fetched_at"],
        total_count=total,
        available_count=int(row["available_count"] or 0),
        missing_count=int(row["missing_count"] or 0),
        passed_count=passed,
        needs_review_count=int(row["needs_review_count"] or 0),
        unseen_count=int(row["unseen_count"] or 0),
        progress=passed / total if total else 0,
    )


def _study_plan_groups(conn: sqlite3.Connection, *, user_id: str, plan_id: int) -> list[StudyPlanGroupSummary]:
    rows = conn.execute(
        """
        SELECT
          i.group_name,
          i.group_slug,
          i.group_position,
          COUNT(*) AS total_count,
          SUM(CASE WHEN p.task_id IS NOT NULL THEN 1 ELSE 0 END) AS available_count,
          SUM(CASE WHEN p.task_id IS NULL THEN 1 ELSE 0 END) AS missing_count,
          SUM(CASE WHEN p.task_id IS NOT NULL AND COALESCE(s.status, 'unseen') = 'passed' THEN 1 ELSE 0 END) AS passed_count,
          SUM(CASE WHEN p.task_id IS NOT NULL AND COALESCE(s.status, 'unseen') = 'needs_review' THEN 1 ELSE 0 END) AS needs_review_count,
          SUM(CASE WHEN p.task_id IS NOT NULL AND COALESCE(s.status, 'unseen') = 'unseen' THEN 1 ELSE 0 END) AS unseen_count
        FROM study_plan_items i
        LEFT JOIN problems p ON p.task_id = i.task_id
        LEFT JOIN user_problem_state s ON s.user_id = ? AND s.task_id = p.task_id
        WHERE i.plan_id = ?
        GROUP BY i.group_slug
        ORDER BY i.group_position
        """,
        (user_id, plan_id),
    ).fetchall()
    return [
        StudyPlanGroupSummary(
            group_name=row["group_name"],
            group_slug=row["group_slug"],
            group_position=row["group_position"],
            total_count=int(row["total_count"] or 0),
            available_count=int(row["available_count"] or 0),
            missing_count=int(row["missing_count"] or 0),
            passed_count=int(row["passed_count"] or 0),
            needs_review_count=int(row["needs_review_count"] or 0),
            unseen_count=int(row["unseen_count"] or 0),
        )
        for row in rows
    ]


def _study_plan_item_rows(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    plan_id: int,
    plan_slug: str,
    group_slug: str | None,
    difficulty: str | None,
    tags: list[str] | None,
    status: str | None,
    search: str | None,
    limit: int,
) -> list[StudyPlanProblemSummary]:
    clauses = ["i.plan_id = ?"]
    params: list[Any] = [plan_id]
    if group_slug:
        clauses.append("i.group_slug = ?")
        params.append(group_slug)
    if difficulty:
        clauses.append("i.difficulty = ?")
        params.append(difficulty)
    for selected_tag in dict.fromkeys([item for item in tags or [] if item]):
        aliases = topic_aliases(selected_tag)
        placeholders = ", ".join("?" for _ in aliases)
        clauses.append(f"p.task_id IS NOT NULL AND EXISTS (SELECT 1 FROM json_each(p.tags_json) WHERE value IN ({placeholders}))")
        params.extend(aliases)
    if status:
        if status == "missing":
            clauses.append("p.task_id IS NULL")
        else:
            clauses.append("p.task_id IS NOT NULL AND COALESCE(s.status, 'unseen') = ?")
            params.append(status)
    if search:
        clauses.append(
            "(i.external_slug LIKE ? OR i.title LIKE ? OR CAST(i.question_id AS TEXT) LIKE ? OR p.title_zh LIKE ?)"
        )
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])
    where = " AND ".join(clauses)
    rows = conn.execute(
        f"""
        SELECT
          i.external_slug,
          i.group_name,
          i.group_slug,
          i.group_position,
          i.item_position,
          i.plan_position,
          i.paid_only,
          i.title AS external_title,
          i.difficulty AS external_difficulty,
          i.question_id AS external_question_id,
          p.task_id,
          p.question_id,
          p.title_zh,
          p.difficulty,
          p.tags_json,
          COALESCE(s.status, 'unseen') AS status,
          COALESCE(s.submit_count, 0) AS submit_count,
          COALESCE(s.pass_count, 0) AS pass_count,
          s.last_submitted_at,
          c.frequency AS codetop_frequency,
          c.last_asked_at AS codetop_last_asked_at
        FROM study_plan_items i
        LEFT JOIN problems p ON p.task_id = i.task_id
        LEFT JOIN user_problem_state s ON s.user_id = ? AND s.task_id = p.task_id
        LEFT JOIN codetop_problem_signals c ON c.task_id = p.task_id
        WHERE {where}
        ORDER BY i.group_position, i.item_position
        LIMIT ?
        """,
        [user_id, *params, limit],
    ).fetchall()
    return [_study_plan_problem_from_row(row, plan_slug=plan_slug) for row in rows]


def _study_plan_problem_from_row(row: sqlite3.Row, *, plan_slug: str) -> StudyPlanProblemSummary:
    available = row["task_id"] is not None
    if available:
        base = problem_summary_from_row(row).model_dump()
    else:
        base = {
            "task_id": row["external_slug"],
            "question_id": row["external_question_id"],
            "title": row["external_title"],
            "difficulty": row["external_difficulty"],
            "tags": [],
            "status": "missing",
            "submit_count": 0,
            "pass_count": 0,
            "last_submitted_at": None,
            "codetop_frequency": None,
            "codetop_last_asked_at": None,
        }
    return StudyPlanProblemSummary(
        **base,
        study_plan_slug=plan_slug,
        group_name=row["group_name"],
        group_slug=row["group_slug"],
        group_position=row["group_position"],
        item_position=row["item_position"],
        plan_position=row["plan_position"],
        paid_only=bool(row["paid_only"]),
        available=available,
        external_slug=row["external_slug"],
        leetcode_url=LEETCODE_PROBLEM_URL.format(slug=row["external_slug"]),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync a LeetCode study plan into the local catalog DB.")
    parser.add_argument("slug", nargs="?", default="top-interview-150")
    args = parser.parse_args()
    conn = get_connection()
    init_db(conn)
    try:
        plan = sync_leetcode_study_plan(conn, args.slug)
    finally:
        conn.close()
    print(f"Synced {plan.title}: {plan.total_count} items ({plan.available_count} local, {plan.missing_count} missing)")


if __name__ == "__main__":
    main()
