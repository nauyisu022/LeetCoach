from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from .config import catalog_db_path, legacy_db_path, user_db_path
from .db import USER_DB_ALIAS, get_connection, init_db

CATALOG_TABLES = (
    "problems",
    "codetop_questions",
    "codetop_taxonomies",
)

USER_TABLES = (
    "users",
    "user_problem_state",
    "submissions",
    "coach_messages",
    "user_solutions",
    "practice_notes",
    "practice_note_topics",
    "topic_memories",
    "review_events",
    "learning_events",
    "user_memory_items",
    "coach_thread_summaries",
)


def split_legacy_db(
    *,
    source_path: Path,
    catalog_path: Path,
    user_path: Path,
    replace: bool = False,
) -> dict[str, int]:
    if not source_path.exists():
        raise FileNotFoundError(f"Legacy DB not found: {source_path}")
    if source_path.resolve() in {catalog_path.resolve(), user_path.resolve()}:
        raise ValueError("Source DB must be different from target DBs")
    if replace:
        for target in (catalog_path, user_path):
            if target.exists():
                target.unlink()

    conn = get_connection(catalog_path, user_path=user_path)
    init_db(conn)
    conn.execute("ATTACH DATABASE ? AS legacy", (str(source_path),))
    counts: dict[str, int] = {}
    try:
        with conn:
            for table in CATALOG_TABLES:
                counts[f"catalog.{table}"] = _copy_table(conn, "legacy", "main", table)
            for table in USER_TABLES:
                counts[f"user.{table}"] = _copy_table(conn, "legacy", USER_DB_ALIAS, table)
    finally:
        conn.close()
    return counts


def _copy_table(conn: sqlite3.Connection, source_schema: str, target_schema: str, table: str) -> int:
    if not _table_exists(conn, source_schema, table):
        return 0
    source_columns = _table_columns(conn, source_schema, table)
    target_columns = _table_columns(conn, target_schema, table)
    columns = [column for column in target_columns if column in source_columns]
    if not columns:
        return 0

    quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
    conn.execute(
        f"""
        INSERT OR REPLACE INTO {target_schema}.{table} ({quoted_columns})
        SELECT {quoted_columns}
        FROM {source_schema}.{table}
        """
    )
    return conn.execute(f"SELECT COUNT(*) AS count FROM {target_schema}.{table}").fetchone()["count"]


def _table_exists(conn: sqlite3.Connection, schema: str, table: str) -> bool:
    row = conn.execute(
        f"SELECT 1 FROM {schema}.sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, schema: str, table: str) -> list[str]:
    return [row["name"] for row in conn.execute(f"PRAGMA {schema}.table_info({table})").fetchall()]


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def main() -> None:
    parser = argparse.ArgumentParser(description="Split legacy LeetCoach app.legacy.db into catalog and user DBs.")
    parser.add_argument("--source", type=Path, default=legacy_db_path())
    parser.add_argument("--catalog", type=Path, default=catalog_db_path())
    parser.add_argument("--user", type=Path, default=user_db_path())
    parser.add_argument("--replace", action="store_true", help="Delete existing target DBs before copying.")
    args = parser.parse_args()

    counts = split_legacy_db(
        source_path=args.source,
        catalog_path=args.catalog,
        user_path=args.user,
        replace=args.replace,
    )
    for name, count in counts.items():
        print(f"{name}\t{count}")
    print(f"catalog_db\t{args.catalog}")
    print(f"user_db\t{args.user}")


if __name__ == "__main__":
    main()
