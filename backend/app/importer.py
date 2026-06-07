from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import dataset_path
from .db import get_connection, init_db
from .semantic_tests import effective_input_output_for_problem


def import_dataset(source_dir: Path | None = None) -> int:
    source = source_dir or dataset_path()
    files = sorted(source.glob("LeetCodeDataset-*.jsonl"))
    if not files:
        raise FileNotFoundError(f"No LeetCodeDataset JSONL files found in {source}")

    conn = get_connection()
    init_db(conn)
    count = 0
    with conn:
        for file_path in files:
            with file_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    row = json.loads(line)
                    raw_input_output_json = json.dumps(row.get("input_output", []), ensure_ascii=False)
                    input_output_json = json.dumps(
                        effective_input_output_for_problem(row["task_id"], raw_input_output_json),
                        ensure_ascii=False,
                    )
                    conn.execute(
                        """
                        INSERT INTO problems (
                            task_id, question_id, difficulty, tags_json, problem_description,
                            starter_code, entry_point, test_code, input_output_json,
                            prompt, completion, estimated_date
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(task_id) DO UPDATE SET
                            question_id=excluded.question_id,
                            difficulty=excluded.difficulty,
                            tags_json=excluded.tags_json,
                            problem_description=excluded.problem_description,
                            starter_code=excluded.starter_code,
                            entry_point=excluded.entry_point,
                            test_code=excluded.test_code,
                            input_output_json=excluded.input_output_json,
                            prompt=excluded.prompt,
                            completion=excluded.completion,
                            estimated_date=excluded.estimated_date
                        """,
                        (
                            row["task_id"],
                            row["question_id"],
                            row["difficulty"],
                            json.dumps(row.get("tags", []), ensure_ascii=False),
                            row["problem_description"],
                            row["starter_code"],
                            row["entry_point"],
                            row["test"],
                            input_output_json,
                            row["prompt"],
                            row["completion"],
                            row.get("estimated_date"),
                        ),
                    )
                    count += 1
    conn.close()
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=dataset_path())
    args = parser.parse_args()
    count = import_dataset(args.source)
    print(f"Imported {count} problems from {args.source}")


if __name__ == "__main__":
    main()
