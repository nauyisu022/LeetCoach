from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from .agent_runtime.model import stream_agent_model_messages
from .agent_runtime.memory import create_learning_event
from .agent_routes import create_agent_router
from .db import get_connection, init_db
from .judge_service import run_custom_input, run_submission
from .notes import (
    fetch_topic_memories,
    topic_labels_for_names,
)
from .practice_note_routes import create_practice_note_router
from .problem_practice_api import ProblemNotFoundError, ProblemPracticeApiService
from .problem_practice_routes import create_problem_practice_router
from .schemas import (
    SavedSolution,
    SaveSolutionRequest,
    SubmissionHistoryItem,
    SubmissionRequest,
    SubmissionResponse,
    TopicMemory,
    TopicMemoryListResponse,
)
from .semantic_tests import custom_compare_mode_for_problem, effective_test_code_for_problem

app = FastAPI(title="LeetCoach Local API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_IMAGE_HOSTS = {
    "assets.leetcode.com",
    "assets.leetcode-cn.com",
    "aliyun-lc-upload.oss-cn-hangzhou.aliyuncs.com",
    "leetcode.cn",
}

DEFAULT_USER_ID = "local"
agent_model_streamer = stream_agent_model_messages


@app.on_event("startup")
def startup() -> None:
    conn = get_connection()
    init_db(conn)
    conn.close()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/problem-image")
def problem_image(url: str) -> Response:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in ALLOWED_IMAGE_HOSTS:
        raise HTTPException(status_code=400, detail="Image host is not allowed")
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=12) as image_response:
            content_type = image_response.headers.get("Content-Type", "image/png")
            if not content_type.startswith("image/"):
                raise HTTPException(status_code=415, detail="URL did not return an image")
            return Response(content=image_response.read(), media_type=content_type)
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch image: {exc}") from exc


@app.get("/api/topic-memories", response_model=TopicMemoryListResponse)
def topic_memories(limit: int = Query(20, ge=1, le=80)) -> TopicMemoryListResponse:
    conn = get_connection()
    rows = fetch_topic_memories(conn, user_id=DEFAULT_USER_ID, limit=limit)
    conn.close()
    return TopicMemoryListResponse(memories=[_topic_memory_from_row(row) for row in rows])


@app.put("/api/problems/{task_id}/solution", response_model=SavedSolution)
def save_solution(task_id: str, request: SaveSolutionRequest) -> SavedSolution:
    _fetch_problem_row(task_id)
    conn = get_connection()
    with conn:
        solution = _upsert_saved_solution(
            conn,
            task_id=task_id,
            code=request.code,
            language=request.language,
            notes=request.notes,
        )
    conn.close()
    return solution


@app.post("/api/submissions", response_model=SubmissionResponse)
def submit(request: SubmissionRequest) -> SubmissionResponse:
    problem = _fetch_problem_row(request.task_id)
    result = run_submission(
        prompt=problem["prompt"],
        code=request.code,
        test_code=effective_test_code_for_problem(problem["task_id"], problem["test_code"], problem["input_output_json"]),
        entry_point=problem["entry_point"],
    )
    conn = get_connection()
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO submissions (
              user_id, task_id, code, passed, failed_assertion, stderr, runtime_ms, execution_ms, test_count_estimate, passed_test_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                DEFAULT_USER_ID,
                request.task_id,
                request.code,
                1 if result.passed else 0,
                result.failed_assertion,
                result.stderr,
                result.runtime_ms,
                result.execution_ms,
                result.test_count_estimate,
                result.passed_test_count,
            ),
        )
        status = "passed" if result.passed else "needs_review"
        conn.execute(
            """
            INSERT INTO user_problem_state (
              user_id, task_id, status, submit_count, pass_count, last_submitted_at, last_passed_at, last_failure_summary
            ) VALUES (?, ?, ?, 1, ?, CURRENT_TIMESTAMP, CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END, ?)
            ON CONFLICT(user_id, task_id) DO UPDATE SET
              status=excluded.status,
              submit_count=user_problem_state.submit_count + 1,
              pass_count=user_problem_state.pass_count + excluded.pass_count,
              last_submitted_at=CURRENT_TIMESTAMP,
              last_passed_at=CASE WHEN excluded.pass_count > 0 THEN CURRENT_TIMESTAMP ELSE user_problem_state.last_passed_at END,
              last_failure_summary=excluded.last_failure_summary
            """,
            (
                DEFAULT_USER_ID,
                request.task_id,
                status,
                1 if result.passed else 0,
                1 if result.passed else 0,
                None if result.passed else result.failed_assertion,
            ),
        )
        _upsert_saved_solution(conn, task_id=request.task_id, code=request.code)
        submission_id = int(cursor.lastrowid)
        _record_submission_learning_event(conn, problem=problem, request=request, result=result)
    conn.close()
    return _submission_response(submission_id, request.task_id, "submit", result)


@app.get("/api/problems/{task_id}/submissions", response_model=list[SubmissionHistoryItem])
def submission_history(task_id: str, limit: int = Query(20, ge=1, le=100)) -> list[SubmissionHistoryItem]:
    _fetch_problem_row(task_id)
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, task_id, passed, failed_assertion, runtime_ms, execution_ms, test_count_estimate,
               CASE
                 WHEN passed = 1 AND passed_test_count = 0 THEN test_count_estimate
                 ELSE passed_test_count
               END AS passed_test_count,
               created_at
        FROM submissions
        WHERE user_id = ? AND task_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (DEFAULT_USER_ID, task_id, limit),
    ).fetchall()
    conn.close()
    return [
        SubmissionHistoryItem(
            id=row["id"],
            task_id=row["task_id"],
            status="passed" if row["passed"] else "failed",
            passed=bool(row["passed"]),
            failed_assertion=row["failed_assertion"],
            runtime_ms=row["runtime_ms"],
            execution_ms=row["execution_ms"],
            test_count_estimate=row["test_count_estimate"],
            passed_test_count=row["passed_test_count"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


@app.post("/api/runs", response_model=SubmissionResponse)
def run(request: SubmissionRequest) -> SubmissionResponse:
    problem = _fetch_problem_row(request.task_id)
    if request.custom_input:
        result = run_custom_input(
            prompt=problem["prompt"],
            code=request.code,
            custom_input=request.custom_input,
            expected_output=request.custom_expected_output,
            entry_point=problem["entry_point"],
            compare_mode=custom_compare_mode_for_problem(problem["task_id"]),
        )
    else:
        result = run_submission(
            prompt=problem["prompt"],
            code=request.code,
            test_code=effective_test_code_for_problem(problem["task_id"], problem["test_code"], problem["input_output_json"]),
            entry_point=problem["entry_point"],
        )
    return _submission_response(None, request.task_id, "run", result)


def _fetch_problem_row(task_id: str):
    try:
        return _problem_practice_api_service().fetch_problem_row(task_id)
    except ProblemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _problem_practice_api_service() -> ProblemPracticeApiService:
    return ProblemPracticeApiService(user_id=DEFAULT_USER_ID, connection_factory=get_connection)


def _record_submission_learning_event(conn, *, problem, request: SubmissionRequest, result: Any) -> None:
    raw_tags = json.loads(problem["tags_json"])
    topic = raw_tags[0] if raw_tags else None
    title = problem["title_zh"] or problem["task_id"]
    if result.passed:
        event_type = "mastery"
        if result.test_count_estimate:
            content = (
                f"{problem['question_id']}. {title} 提交通过，"
                f"{result.passed_test_count}/{result.test_count_estimate} 个测试通过。"
            )
        else:
            content = f"{problem['question_id']}. {title} 提交通过。"
        confidence = 0.82
    else:
        event_type = "mistake"
        failure = result.failed_assertion or result.stderr or "提交未通过"
        content = f"{problem['question_id']}. {title} 提交失败：{str(failure)[:220]}"
        confidence = 0.68
    create_learning_event(
        conn,
        user_id=DEFAULT_USER_ID,
        task_id=request.task_id,
        topic=topic,
        event_type=event_type,
        content=content,
        evidence_message_ids=[],
        confidence=confidence,
    )


def _topic_memory_from_row(row) -> TopicMemory:
    labels = topic_labels_for_names([row["topic_name"]])
    return TopicMemory(
        user_id=row["user_id"],
        topic_name=row["topic_name"],
        topic_label=labels[0] if labels else row["topic_name"],
        memory_markdown=row["memory_markdown"],
        common_mistakes=json.loads(row["common_mistakes_json"]),
        recognition_cues=json.loads(row["recognition_cues_json"]),
        template_notes=json.loads(row["template_notes_json"]),
        mastery_level=row["mastery_level"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _saved_solution_from_row(row) -> SavedSolution:
    return SavedSolution(
        id=row["id"],
        user_id=row["user_id"],
        task_id=row["task_id"],
        code=row["code"],
        language=row["language"],
        notes=row["notes"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _upsert_saved_solution(
    conn,
    *,
    task_id: str,
    code: str,
    language: str = "python",
    notes: Optional[str] = None,
    user_id: str = DEFAULT_USER_ID,
) -> SavedSolution:
    conn.execute(
        "INSERT OR IGNORE INTO users (id, display_name) VALUES (?, ?)",
        (user_id, "Local User" if user_id == DEFAULT_USER_ID else user_id),
    )
    conn.execute(
        """
        INSERT INTO user_solutions (
            user_id, task_id, code, language, notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id, task_id) DO UPDATE SET
            code=excluded.code,
            language=excluded.language,
            notes=COALESCE(excluded.notes, user_solutions.notes),
            updated_at=CURRENT_TIMESTAMP
        """,
        (user_id, task_id, code, language, notes),
    )
    row = conn.execute(
        """
        SELECT id, user_id, task_id, code, language, notes, created_at, updated_at
        FROM user_solutions
        WHERE user_id = ? AND task_id = ?
        """,
        (user_id, task_id),
    ).fetchone()
    return _saved_solution_from_row(row)


def _submission_response(
    submission_id: Optional[int],
    task_id: str,
    mode: str,
    result: Any,
) -> SubmissionResponse:
    status = "passed" if result.passed else "failed"
    duration = _duration_summary(result)
    if mode == "run":
        title = "运行通过" if result.passed else "运行失败"
        summary = (
            f"当前输入执行完成 · {duration}"
            if result.passed
            else f"当前输入触发错误 · {duration}"
        )
    else:
        title = "提交通过" if result.passed else "提交失败"
        summary = (
            f"完整测试通过 · {result.passed_test_count}/{result.test_count_estimate} 通过 · {duration}"
            if result.passed
            else f"完整测试未通过 · {result.passed_test_count}/{result.test_count_estimate} 通过 · {duration}"
        )

    return SubmissionResponse(
        id=submission_id,
        task_id=task_id,
        mode=mode,
        status=status,
        title=title,
        summary=summary,
        **result.__dict__,
    )


def _duration_summary(result: Any) -> str:
    execution_ms = getattr(result, "execution_ms", None)
    runtime_ms = getattr(result, "runtime_ms")
    if execution_ms is None:
        return f"总耗时 {_format_ms(runtime_ms)}"
    if runtime_ms - execution_ms >= 50:
        return f"执行 {_format_ms(execution_ms)} · 总耗时 {_format_ms(runtime_ms)}"
    return f"执行 {_format_ms(execution_ms)}"


def _format_ms(value: int) -> str:
    return "<1 ms" if value <= 0 else f"{value} ms"


app.include_router(
    create_problem_practice_router(
        user_id=DEFAULT_USER_ID,
        connection_factory=get_connection,
    )
)

app.include_router(
    create_practice_note_router(
        user_id=DEFAULT_USER_ID,
        connection_factory=get_connection,
        problem_loader=_fetch_problem_row,
    )
)

app.include_router(
    create_agent_router(
        user_id=DEFAULT_USER_ID,
        connection_factory=get_connection,
        problem_loader=_fetch_problem_row,
        ai_streamer_provider=lambda: agent_model_streamer,
    )
)
