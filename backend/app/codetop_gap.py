from __future__ import annotations

import argparse
import ast
import json
import re
import sqlite3
import urllib.request
from dataclasses import dataclass
from typing import Any

from .db import get_connection, init_db
from .leetcode_cn import html_to_text

LEETCODE_GRAPHQL_URL = "https://leetcode.cn/graphql/"

COMMON_PROMPT = """
import random
import functools
import collections
import string
import math
import datetime

from typing import *
from functools import *
from collections import *
from itertools import *
from heapq import *
from bisect import *
from string import *
from operator import *
from math import *

inf = float('inf')
""".strip()


@dataclass(frozen=True)
class GapRow:
    frontend_question_id: str
    title: str
    frequency: int
    slug_title: str
    bucket: str


@dataclass(frozen=True)
class ImportResult:
    slug_title: str
    title: str
    action: str
    reason: str = ""


def classify_gap(frontend_question_id: str, slug_title: str | None) -> str:
    slug = slug_title or ""
    if frontend_question_id.isdigit():
        return "numeric"
    if frontend_question_id.startswith("剑指 Offer"):
        return "offer"
    if frontend_question_id.startswith("面试题"):
        return "lcci"
    if frontend_question_id.startswith("补充题") and slug.startswith("http"):
        return "supplement_url"
    if frontend_question_id.startswith("补充题"):
        return "supplement_slug"
    return "other"


def load_gap_rows(conn: sqlite3.Connection) -> list[GapRow]:
    rows = conn.execute(
        """
        SELECT c.frontend_question_id, c.title, c.frequency, c.slug_title
        FROM codetop_questions c
        LEFT JOIN problems by_qid ON c.frontend_question_id = CAST(by_qid.question_id AS TEXT)
        LEFT JOIN problems by_slug ON c.slug_title = by_slug.task_id
        WHERE by_qid.task_id IS NULL AND by_slug.task_id IS NULL
        ORDER BY c.frequency DESC
        """
    ).fetchall()
    return [
        GapRow(
            frontend_question_id=row["frontend_question_id"],
            title=row["title"],
            frequency=row["frequency"],
            slug_title=row["slug_title"] or "",
            bucket=classify_gap(row["frontend_question_id"], row["slug_title"]),
        )
        for row in rows
    ]


def import_top_gaps(
    *,
    limit: int,
    dry_run: bool = False,
    conn: sqlite3.Connection | None = None,
) -> list[ImportResult]:
    owns_connection = conn is None
    active_conn = conn or get_connection()
    init_db(active_conn)
    try:
        candidates = [row for row in load_gap_rows(active_conn) if row.bucket == "numeric"][:limit]
        results: list[ImportResult] = []
        with active_conn:
            for gap in candidates:
                try:
                    question = fetch_leetcode_question(gap.slug_title)
                    row = build_problem_row(question)
                except UnsupportedQuestion as exc:
                    results.append(ImportResult(gap.slug_title, gap.title, "skipped", str(exc)))
                    continue
                except Exception as exc:
                    results.append(ImportResult(gap.slug_title, gap.title, "failed", str(exc)))
                    continue
                if not dry_run:
                    upsert_problem(active_conn, row)
                results.append(ImportResult(gap.slug_title, row["title_zh"], "would_import" if dry_run else "imported"))
        return results
    finally:
        if owns_connection:
            active_conn.close()


def fetch_leetcode_question(slug_title: str) -> dict[str, Any]:
    body = json.dumps(
        {
            "query": """
            query questionData($titleSlug: String!) {
              question(titleSlug: $titleSlug) {
                questionId
                questionFrontendId
                titleSlug
                translatedTitle
                translatedContent
                difficulty
                topicTags { name translatedName }
                metaData
                codeSnippets { langSlug code }
              }
            }
            """,
            "variables": {"titleSlug": slug_title},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        LEETCODE_GRAPHQL_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
            "Referer": f"https://leetcode.cn/problems/{slug_title}/",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    question = payload.get("data", {}).get("question")
    if not question:
        raise UnsupportedQuestion(f"LeetCode question not found: {slug_title}")
    return question


def build_problem_row(question: dict[str, Any]) -> dict[str, Any]:
    metadata = _parse_metadata(question.get("metaData"))
    translated_content = question.get("translatedContent") or ""
    description = html_to_text(translated_content)
    starter_code = _python3_snippet(question)
    if not starter_code:
        raise UnsupportedQuestion("missing Python3 starter code")
    if _is_randomized_question(question):
        raise UnsupportedQuestion("randomized examples need custom statistical/local tests")

    if "classname" in metadata:
        entry_point = metadata["classname"]
        test_code = build_class_test_code(description, entry_point)
    else:
        if metadata.get("manual"):
            raise UnsupportedQuestion("manual LeetCode harness requires custom local tests")
        method_name = metadata.get("name")
        if not method_name:
            raise UnsupportedQuestion("missing function entry point")
        entry_point = f"Solution().{method_name}"
        test_code = build_function_test_code(description)

    if estimate_assertions(test_code) == 0:
        raise UnsupportedQuestion("could not derive example assertions")

    question_id = int(question["questionFrontendId"])
    tags = [
        tag.get("translatedName") or tag.get("name")
        for tag in question.get("topicTags") or []
        if tag.get("translatedName") or tag.get("name")
    ]
    return {
        "task_id": question["titleSlug"],
        "question_id": question_id,
        "difficulty": question["difficulty"],
        "tags": tags,
        "problem_description": description,
        "title_zh": question.get("translatedTitle"),
        "problem_description_zh": description,
        "starter_code": starter_code,
        "entry_point": entry_point,
        "test_code": test_code,
        "test_source": "leetcode_examples",
        "test_strength": "weak",
        "input_output": [],
        "prompt": COMMON_PROMPT,
        "completion": "",
        "estimated_date": None,
    }


def build_class_test_code(description: str, class_name: str) -> str:
    examples = parse_class_examples(description)
    if not examples:
        raise UnsupportedQuestion("no class-design example output found")
    lines = ["def check(candidate):"]
    for index, (operations, arguments, outputs) in enumerate(examples):
        if not operations or operations[0] != class_name:
            continue
        if len(operations) != len(arguments) or len(operations) != len(outputs):
            continue
        obj_name = f"obj_{index}"
        lines.append(f"    {obj_name} = candidate(*{repr(arguments[0])})")
        for op, args, expected in zip(operations[1:], arguments[1:], outputs[1:]):
            call = f"{obj_name}.{op}(*{repr(args)})"
            if expected is None:
                lines.append(f"    {call}")
            else:
                lines.append(f"    assert {call} == {repr(expected)}")
    if len(lines) == 1:
        raise UnsupportedQuestion("class examples did not match starter class")
    return "\n".join(lines) + "\n"


def build_function_test_code(description: str) -> str:
    examples = parse_function_examples(description)
    lines = ["def check(candidate):"]
    for kwargs, expected in examples:
        args = ", ".join(f"{key} = {repr(value)}" for key, value in kwargs.items())
        lines.append(f"    assert candidate({args}) == {repr(expected)}")
    if len(lines) == 1:
        raise UnsupportedQuestion("no function example output found")
    return "\n".join(lines) + "\n"


def parse_class_examples(description: str) -> list[tuple[list[str], list[list[Any]], list[Any]]]:
    normalized = _normalize_example_text(description)
    pattern = re.compile(
        r"输入[:：]?\s*\n(?P<ops>\[[^\n]+\])\s*\n(?P<args>\[[^\n]+\])\s*\n输出[:：]?\s*\n(?P<outs>\[[^\n]+\])",
        re.MULTILINE,
    )
    examples = []
    for match in pattern.finditer(normalized):
        operations = _loads_jsonish(match.group("ops"))
        arguments = _loads_jsonish(match.group("args"))
        outputs = _loads_jsonish(match.group("outs"))
        if isinstance(operations, list) and isinstance(arguments, list) and isinstance(outputs, list):
            examples.append((operations, arguments, outputs))
    return examples


def parse_function_examples(description: str) -> list[tuple[dict[str, Any], Any]]:
    lines = [line.strip() for line in _normalize_example_text(description).splitlines() if line.strip()]
    examples: list[tuple[dict[str, Any], Any]] = []
    pending_input: str | None = None
    for line in lines:
        if line.startswith("输入："):
            pending_input = line.removeprefix("输入：").strip()
        elif line.startswith("输出：") and pending_input:
            output_text = line.removeprefix("输出：").strip()
            try:
                examples.append((_parse_kwargs(pending_input), _literal_value(output_text)))
            except ValueError:
                pass
            pending_input = None
    return examples


def upsert_problem(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO problems (
            task_id, question_id, difficulty, tags_json, problem_description,
            title_zh, problem_description_zh, starter_code, entry_point, test_code,
            test_source, test_strength, input_output_json, prompt, completion, estimated_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(task_id) DO UPDATE SET
            question_id=excluded.question_id,
            difficulty=excluded.difficulty,
            tags_json=excluded.tags_json,
            problem_description=excluded.problem_description,
            title_zh=excluded.title_zh,
            problem_description_zh=excluded.problem_description_zh,
            starter_code=excluded.starter_code,
            entry_point=excluded.entry_point,
            test_code=excluded.test_code,
            test_source=excluded.test_source,
            test_strength=excluded.test_strength,
            input_output_json=excluded.input_output_json,
            prompt=excluded.prompt,
            completion=excluded.completion,
            estimated_date=excluded.estimated_date
        """,
        (
            row["task_id"],
            row["question_id"],
            row["difficulty"],
            json.dumps(row["tags"], ensure_ascii=False),
            row["problem_description"],
            row["title_zh"],
            row["problem_description_zh"],
            row["starter_code"],
            row["entry_point"],
            row["test_code"],
            row["test_source"],
            row["test_strength"],
            json.dumps(row["input_output"], ensure_ascii=False),
            row["prompt"],
            row["completion"],
            row["estimated_date"],
        ),
    )


def print_report(rows: list[GapRow], top: int) -> None:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.bucket] = counts.get(row.bucket, 0) + 1
    print(f"total {len(rows)}")
    for bucket in ["numeric", "offer", "lcci", "supplement_url", "supplement_slug", "other"]:
        print(f"{bucket} {counts.get(bucket, 0)}")
    for bucket in ["numeric", "offer", "lcci", "supplement_url", "supplement_slug", "other"]:
        print(f"\n[{bucket}]")
        shown = 0
        for row in rows:
            if row.bucket != bucket:
                continue
            print(f"{row.frontend_question_id}\t{row.title}\t{row.frequency}\t{row.slug_title}")
            shown += 1
            if shown >= top:
                break


def estimate_assertions(test_code: str) -> int:
    return len(re.findall(r"^\s*assert\s+", test_code, re.MULTILINE))


def _parse_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    return json.loads(raw)


def _python3_snippet(question: dict[str, Any]) -> str:
    for snippet in question.get("codeSnippets") or []:
        if snippet.get("langSlug") == "python3":
            return snippet.get("code") or ""
    return ""


def _is_randomized_question(question: dict[str, Any]) -> bool:
    slug = (question.get("titleSlug") or "").lower()
    title = question.get("translatedTitle") or ""
    metadata = _parse_metadata(question.get("metaData"))
    method_names = [method.get("name", "") for method in metadata.get("methods", [])]
    return (
        "random" in slug
        or "shuffle" in slug
        or "随机" in title
        or any(name in {"getRandom", "pickIndex", "shuffle"} for name in method_names)
    )


def _normalize_example_text(description: str) -> str:
    text = description.replace("**", "")
    text = re.sub(r"[ \t]+", " ", text)
    return "\n".join(line.strip() for line in text.splitlines())


def _loads_jsonish(value: str) -> Any:
    return json.loads(value.replace("'", '"'))


def _parse_kwargs(value: str) -> dict[str, Any]:
    parts = _split_top_level(value)
    kwargs: dict[str, Any] = {}
    for part in parts:
        if "=" not in part:
            raise ValueError(f"not a keyword assignment: {part}")
        key, raw_value = part.split("=", 1)
        kwargs[key.strip()] = _literal_value(raw_value.strip())
    return kwargs


def _split_top_level(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    for index, char in enumerate(value):
        if char in "[{(":
            depth += 1
        elif char in "]})":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1
    parts.append(value[start:].strip())
    return [part for part in parts if part]


def _literal_value(value: str) -> Any:
    cleaned = value.strip().rstrip("。")
    cleaned = re.sub(r"\btrue\b", "True", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bfalse\b", "False", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bnull\b", "None", cleaned, flags=re.IGNORECASE)
    try:
        return ast.literal_eval(cleaned)
    except (SyntaxError, ValueError) as exc:
        raise ValueError(f"unsupported literal: {value}") from exc


class UnsupportedQuestion(RuntimeError):
    pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Report or import CodeTop gaps missing from local problems.")
    parser.add_argument("--report", action="store_true", help="Print categorized gap report.")
    parser.add_argument("--top", type=int, default=12, help="Rows to show per report bucket.")
    parser.add_argument("--import-top", type=int, default=0, help="Import top N numeric LeetCode gaps.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and build rows without writing to SQLite.")
    args = parser.parse_args()

    conn = get_connection()
    init_db(conn)
    try:
        if args.report or not args.import_top:
            print_report(load_gap_rows(conn), args.top)
        if args.import_top:
            results = import_top_gaps(limit=args.import_top, dry_run=args.dry_run, conn=conn)
            for result in results:
                suffix = f" ({result.reason})" if result.reason else ""
                print(f"{result.action}\t{result.slug_title}\t{result.title}{suffix}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
