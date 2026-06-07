from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .config import db_path


def get_connection(path: Path | None = None) -> sqlite3.Connection:
    target = path or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS problems (
            task_id TEXT PRIMARY KEY,
            question_id INTEGER NOT NULL,
            difficulty TEXT NOT NULL,
            tags_json TEXT NOT NULL,
            problem_description TEXT NOT NULL,
            title_zh TEXT,
            problem_description_zh TEXT,
            starter_code TEXT NOT NULL,
            entry_point TEXT NOT NULL,
            test_code TEXT NOT NULL,
            test_source TEXT NOT NULL DEFAULT 'dataset',
            test_strength TEXT NOT NULL DEFAULT 'strong',
            input_output_json TEXT NOT NULL,
            prompt TEXT NOT NULL,
            completion TEXT NOT NULL,
            estimated_date TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_problems_question_id ON problems(question_id);
        CREATE INDEX IF NOT EXISTS idx_problems_difficulty ON problems(difficulty);

        CREATE TABLE IF NOT EXISTS user_problem_state (
            user_id TEXT NOT NULL DEFAULT 'local' REFERENCES users(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL REFERENCES problems(task_id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'unseen',
            submit_count INTEGER NOT NULL DEFAULT 0,
            pass_count INTEGER NOT NULL DEFAULT 0,
            last_submitted_at TEXT,
            last_passed_at TEXT,
            last_failure_summary TEXT,
            mistake_tags_json TEXT NOT NULL DEFAULT '[]',
            review_at TEXT,
            PRIMARY KEY (user_id, task_id)
        );

        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL DEFAULT 'local' REFERENCES users(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL REFERENCES problems(task_id) ON DELETE CASCADE,
            code TEXT NOT NULL,
            passed INTEGER NOT NULL,
            failed_assertion TEXT,
            stderr TEXT,
            runtime_ms INTEGER NOT NULL,
            test_count_estimate INTEGER NOT NULL,
            passed_test_count INTEGER NOT NULL DEFAULT 0,
            ai_diagnosis_summary TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS coach_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL DEFAULT 'local' REFERENCES users(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL REFERENCES problems(task_id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_coach_messages_task_id_id
          ON coach_messages(task_id, id);

        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            display_name TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS user_solutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL REFERENCES problems(task_id) ON DELETE CASCADE,
            code TEXT NOT NULL,
            language TEXT NOT NULL DEFAULT 'python',
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, task_id)
        );

        CREATE INDEX IF NOT EXISTS idx_user_solutions_task_id
          ON user_solutions(task_id);

        CREATE TABLE IF NOT EXISTS practice_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL REFERENCES problems(task_id) ON DELETE CASCADE,
            content_markdown TEXT NOT NULL DEFAULT '',
            ai_summary TEXT,
            mistake_summary TEXT,
            invariant_summary TEXT,
            solution_pattern TEXT,
            source_submission_id INTEGER REFERENCES submissions(id) ON DELETE SET NULL,
            review_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, task_id)
        );

        CREATE INDEX IF NOT EXISTS idx_practice_notes_user_review
          ON practice_notes(user_id, review_at);
        CREATE INDEX IF NOT EXISTS idx_practice_notes_task_id
          ON practice_notes(task_id);

        CREATE TABLE IF NOT EXISTS practice_note_topics (
            note_id INTEGER NOT NULL REFERENCES practice_notes(id) ON DELETE CASCADE,
            topic_name TEXT NOT NULL,
            PRIMARY KEY (note_id, topic_name)
        );

        CREATE INDEX IF NOT EXISTS idx_practice_note_topics_topic
          ON practice_note_topics(topic_name);

        CREATE TABLE IF NOT EXISTS topic_memories (
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            topic_name TEXT NOT NULL,
            memory_markdown TEXT NOT NULL DEFAULT '',
            common_mistakes_json TEXT NOT NULL DEFAULT '[]',
            recognition_cues_json TEXT NOT NULL DEFAULT '[]',
            template_notes_json TEXT NOT NULL DEFAULT '[]',
            mastery_level TEXT NOT NULL DEFAULT 'learning',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, topic_name)
        );

        CREATE TABLE IF NOT EXISTS review_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            note_id INTEGER NOT NULL REFERENCES practice_notes(id) ON DELETE CASCADE,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            reviewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_review_events_user_note
          ON review_events(user_id, note_id, reviewed_at);

        CREATE TABLE IF NOT EXISTS codetop_questions (
            codetop_id INTEGER PRIMARY KEY,
            leetcode_id INTEGER,
            frontend_question_id TEXT NOT NULL,
            question_id INTEGER,
            title TEXT NOT NULL,
            slug_title TEXT,
            difficulty TEXT NOT NULL,
            frequency INTEGER NOT NULL DEFAULT 0,
            last_asked_at TEXT,
            status INTEGER NOT NULL DEFAULT 0,
            note_status INTEGER NOT NULL DEFAULT 0,
            rate INTEGER NOT NULL DEFAULT 0,
            content_markdown TEXT,
            raw_json TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_codetop_questions_frequency
          ON codetop_questions(frequency DESC);
        CREATE INDEX IF NOT EXISTS idx_codetop_questions_frontend_id
          ON codetop_questions(frontend_question_id);

        CREATE TABLE IF NOT EXISTS codetop_taxonomies (
            kind TEXT NOT NULL,
            codetop_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            is_new INTEGER NOT NULL DEFAULT 0,
            raw_json TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (kind, codetop_id)
        );

        CREATE VIEW IF NOT EXISTS codetop_problem_signals AS
        SELECT
            task_id,
            MAX(frequency) AS frequency,
            MAX(last_asked_at) AS last_asked_at,
            COUNT(DISTINCT codetop_id) AS match_count
        FROM (
            SELECT p.task_id, c.codetop_id, c.frequency, c.last_asked_at
            FROM problems p
            JOIN codetop_questions c ON c.frontend_question_id = CAST(p.question_id AS TEXT)
            UNION
            SELECT p.task_id, c.codetop_id, c.frequency, c.last_asked_at
            FROM problems p
            JOIN codetop_questions c ON c.slug_title = p.task_id
        )
        GROUP BY task_id;
        """
    )
    conn.execute(
        "INSERT OR IGNORE INTO users (id, display_name) VALUES (?, ?)",
        ("local", "Local User"),
    )
    _migrate_user_problem_state_user_id(conn)
    _ensure_column(conn, "problems", "title_zh", "TEXT")
    _ensure_column(conn, "problems", "problem_description_zh", "TEXT")
    _ensure_column(conn, "problems", "test_source", "TEXT NOT NULL DEFAULT 'dataset'")
    _ensure_column(conn, "problems", "test_strength", "TEXT NOT NULL DEFAULT 'strong'")
    _ensure_column(conn, "submissions", "user_id", "TEXT NOT NULL DEFAULT 'local'")
    _ensure_column(conn, "submissions", "passed_test_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "coach_messages", "user_id", "TEXT NOT NULL DEFAULT 'local'")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_coach_messages_user_task_id
          ON coach_messages(user_id, task_id, id)
        """
    )
    conn.commit()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def _migrate_user_problem_state_user_id(conn: sqlite3.Connection) -> None:
    columns = conn.execute("PRAGMA table_info(user_problem_state)").fetchall()
    column_names = {row["name"] for row in columns}
    primary_key = [row["name"] for row in sorted(columns, key=lambda row: row["pk"]) if row["pk"]]
    if column_names and primary_key == ["user_id", "task_id"]:
        return

    existing_columns = [
        "task_id",
        "status",
        "submit_count",
        "pass_count",
        "last_submitted_at",
        "last_passed_at",
        "last_failure_summary",
        "mistake_tags_json",
        "review_at",
    ]
    selected_columns = [column for column in existing_columns if column in column_names]
    conn.execute("ALTER TABLE user_problem_state RENAME TO user_problem_state_old")
    conn.execute(
        """
        CREATE TABLE user_problem_state (
            user_id TEXT NOT NULL DEFAULT 'local' REFERENCES users(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL REFERENCES problems(task_id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'unseen',
            submit_count INTEGER NOT NULL DEFAULT 0,
            pass_count INTEGER NOT NULL DEFAULT 0,
            last_submitted_at TEXT,
            last_passed_at TEXT,
            last_failure_summary TEXT,
            mistake_tags_json TEXT NOT NULL DEFAULT '[]',
            review_at TEXT,
            PRIMARY KEY (user_id, task_id)
        )
        """
    )
    if selected_columns:
        target_columns = ", ".join(["user_id", *selected_columns])
        source_columns = ", ".join(["'local'", *selected_columns])
        conn.execute(
            f"""
            INSERT OR IGNORE INTO user_problem_state ({target_columns})
            SELECT {source_columns}
            FROM user_problem_state_old
            """
        )
    conn.execute("DROP TABLE user_problem_state_old")
