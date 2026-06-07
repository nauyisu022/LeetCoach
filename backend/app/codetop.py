from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import sqlite3

from .db import get_connection, init_db
from .leetcode_cn import html_to_text

BASE_URL = "https://codetop.cc"
QUESTION_ENDPOINT = "/api/questions/"
TAXONOMY_ENDPOINTS = {
    "company": "/api/companies/",
    "department": "/api/departments/",
    "job": "/api/jobs/",
    "tag": "/api/tags/",
    "list": "/api/lists/",
}
DEFAULT_DELAY_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class SyncStats:
    questions: int = 0
    taxonomies: int = 0
    pages: int = 0


def sync_codetop(
    *,
    max_pages: int | None = None,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    include_content: bool = False,
    conn: sqlite3.Connection | None = None,
) -> SyncStats:
    owns_connection = conn is None
    active_conn = conn or get_connection()
    init_db(active_conn)
    try:
        with active_conn:
            taxonomies = _sync_taxonomies(active_conn)
            stats = _sync_questions(
                active_conn,
                max_pages=max_pages,
                delay_seconds=delay_seconds,
                include_content=include_content,
            )
        return SyncStats(
            questions=stats.questions,
            taxonomies=taxonomies,
            pages=stats.pages,
        )
    finally:
        if owns_connection:
            active_conn.close()


def _sync_taxonomies(conn: sqlite3.Connection) -> int:
    total = 0
    for kind, endpoint in TAXONOMY_ENDPOINTS.items():
        try:
            payload = _get_json(endpoint)
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                continue
            raise
        if not isinstance(payload, list):
            continue
        for item in payload:
            if not isinstance(item, dict):
                continue
            row = _normalize_taxonomy_item(item)
            conn.execute(
                """
                INSERT INTO codetop_taxonomies (
                    kind, codetop_id, name, is_new, raw_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(kind, codetop_id) DO UPDATE SET
                    name=excluded.name,
                    is_new=excluded.is_new,
                    raw_json=excluded.raw_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    kind,
                    row["id"],
                    row["name"],
                    1 if row["is_new"] else 0,
                    json.dumps(item, ensure_ascii=False),
                ),
            )
            total += 1
    return total


def _sync_questions(
    conn: sqlite3.Connection,
    *,
    max_pages: int | None,
    delay_seconds: float,
    include_content: bool,
) -> SyncStats:
    total = 0
    page = 1
    pages_fetched = 0
    while max_pages is None or page <= max_pages:
        payload = _get_json(QUESTION_ENDPOINT, {"page": page})
        items = payload.get("list", []) if isinstance(payload, dict) else []
        if not items:
            break
        pages_fetched += 1
        for item in items:
            if not isinstance(item, dict):
                continue
            upsert_codetop_question(conn, item, include_content=include_content)
            total += 1
        count = payload.get("count") if isinstance(payload, dict) else None
        if isinstance(count, int) and total >= count:
            break
        page += 1
        if delay_seconds > 0:
            time.sleep(delay_seconds)
    return SyncStats(questions=total, pages=pages_fetched)


def upsert_codetop_question(
    conn: sqlite3.Connection,
    item: dict[str, Any],
    *,
    include_content: bool = False,
) -> None:
    row = normalize_question_item(item, include_content=include_content)
    conn.execute(
        """
        INSERT INTO codetop_questions (
            codetop_id, leetcode_id, frontend_question_id, question_id, title,
            slug_title, difficulty, frequency, last_asked_at, status, note_status,
            rate, content_markdown, raw_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(codetop_id) DO UPDATE SET
            leetcode_id=excluded.leetcode_id,
            frontend_question_id=excluded.frontend_question_id,
            question_id=excluded.question_id,
            title=excluded.title,
            slug_title=excluded.slug_title,
            difficulty=excluded.difficulty,
            frequency=excluded.frequency,
            last_asked_at=excluded.last_asked_at,
            status=excluded.status,
            note_status=excluded.note_status,
            rate=excluded.rate,
            content_markdown=excluded.content_markdown,
            raw_json=excluded.raw_json,
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            row["codetop_id"],
            row["leetcode_id"],
            row["frontend_question_id"],
            row["question_id"],
            row["title"],
            row["slug_title"],
            row["difficulty"],
            row["frequency"],
            row["last_asked_at"],
            1 if row["status"] else 0,
            1 if row["note_status"] else 0,
            row["rate"],
            row["content_markdown"],
            row["raw_json"],
        ),
    )


def normalize_question_item(
    item: dict[str, Any],
    *,
    include_content: bool = False,
) -> dict[str, Any]:
    leetcode = item.get("leetcode") or {}
    if not isinstance(leetcode, dict):
        leetcode = {}
    raw_item = _strip_content(item) if not include_content else item
    content = leetcode.get("content") if include_content else None
    return {
        "codetop_id": _required_int(item, "id"),
        "leetcode_id": _optional_int(leetcode.get("id")),
        "frontend_question_id": str(leetcode.get("frontend_question_id") or ""),
        "question_id": _optional_int(leetcode.get("question_id")),
        "title": str(leetcode.get("title") or ""),
        "slug_title": leetcode.get("slug_title"),
        "difficulty": _difficulty_label(leetcode.get("level")),
        "frequency": _optional_int(item.get("value")) or 0,
        "last_asked_at": item.get("time"),
        "status": bool(item.get("status")),
        "note_status": bool(item.get("note_status")),
        "rate": _optional_int(item.get("rate")) or 0,
        "content_markdown": html_to_text(content) if isinstance(content, str) else None,
        "raw_json": json.dumps(raw_item, ensure_ascii=False),
    }


def _normalize_taxonomy_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _required_int(item, "id"),
        "name": str(item.get("name") or item.get("title") or ""),
        "is_new": bool(item.get("is_new")),
    }


def _get_json(endpoint: str, params: dict[str, Any] | None = None) -> Any:
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    request = urllib.request.Request(
        f"{BASE_URL}{endpoint}{query}",
        headers={
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/home",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
            ),
        },
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def _strip_content(item: dict[str, Any]) -> dict[str, Any]:
    clone = json.loads(json.dumps(item, ensure_ascii=False))
    leetcode = clone.get("leetcode")
    if isinstance(leetcode, dict):
        leetcode.pop("content", None)
    return clone


def _required_int(item: dict[str, Any], key: str) -> int:
    value = _optional_int(item.get(key))
    if value is None:
        raise ValueError(f"CodeTop item is missing integer field: {key}")
    return value


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _difficulty_label(level: Any) -> str:
    labels = {1: "Easy", 2: "Medium", 3: "Hard"}
    return labels.get(_optional_int(level), "Unknown")


def iter_top_codetop_questions(conn: sqlite3.Connection, limit: int = 20) -> Iterable[sqlite3.Row]:
    return conn.execute(
        """
        SELECT frontend_question_id, title, difficulty, frequency, last_asked_at, slug_title
        FROM codetop_questions
        ORDER BY frequency DESC, frontend_question_id
        LIMIT ?
        """,
        (limit,),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync public CodeTop metadata into local SQLite.")
    parser.add_argument("--max-pages", type=int, default=None, help="Limit pages for a dry run.")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS, help="Delay between question pages.")
    parser.add_argument(
        "--include-content",
        action="store_true",
        help="Also store converted problem statement content. Disabled by default.",
    )
    args = parser.parse_args()
    stats = sync_codetop(
        max_pages=args.max_pages,
        delay_seconds=args.delay,
        include_content=args.include_content,
    )
    print(
        f"Synced {stats.questions} CodeTop questions, "
        f"{stats.taxonomies} taxonomy rows across {stats.pages} page(s)."
    )


if __name__ == "__main__":
    main()
