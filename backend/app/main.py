from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from .agent_runtime.memory import (
    fetch_accepted_memories_for_context,
    fetch_memory_items,
    fetch_thread_summary,
    memory_rows_for_prompt,
    run_after_coach_response_hook,
    set_memory_status,
    update_memory_item,
)
from .agent_runtime.runtime import build_command_plan, enrich_problem_with_memories, normalize_command
from .coach import (
    build_note_draft_prompt,
    call_claude,
    call_claude_messages_stream,
)
from .db import get_connection, init_db
from .judge_service import run_custom_input, run_submission
from .leetcode_cn import fetch_chinese_problem, fetch_chinese_titles
from .notes import (
    create_review_event,
    fetch_note,
    fetch_note_topics,
    fetch_topic_memories,
    note_topic_names_for_problem,
    topic_labels_for_names,
    upsert_note,
)
from .practice import PracticeFilters, fetch_practice_queue, fetch_topic_insights, practice_reason, topic_names_for_problem
from .schemas import (
    AgentCommandRequest,
    AgentMemoryItem,
    AgentMemoryListResponse,
    AgentMemoryUpdateRequest,
    AgentThreadSummaryResponse,
    CoachChatRequest,
    CoachMessage,
    CoachRequest,
    CoachResponse,
    CoachThreadResponse,
    PracticeQueueItem,
    PracticeQueueResponse,
    PracticeInsightsResponse,
    PracticeTopicInsight,
    PracticeNote,
    PracticeNoteDraftRequest,
    PracticeNoteDraftResponse,
    PracticeNoteResponse,
    PracticeNoteSaveRequest,
    ProblemDetail,
    ProblemTag,
    ProblemSummary,
    ProgressSummary,
    ReviewEvent,
    ReviewEventRequest,
    SavedSolution,
    SaveSolutionRequest,
    SubmissionHistoryItem,
    SubmissionRequest,
    SubmissionResponse,
    TopicMemory,
    TopicMemoryListResponse,
)
from .topic_taxonomy import (
    CATEGORY_ORDER,
    TOPIC_BY_NAME,
    display_topic_labels,
    normalize_topic_name,
    topic_aliases,
)
from .semantic_tests import custom_compare_mode_for_problem, effective_input_output_for_problem, effective_test_code_for_problem

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


@app.get("/api/problems", response_model=list[ProblemSummary])
def list_problems(
    difficulty: Optional[str] = None,
    tag: Optional[str] = None,
    tags: Optional[list[str]] = Query(None),
    status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(3000, ge=1, le=5000),
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
    conn = get_connection()
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
        [DEFAULT_USER_ID, *params, limit],
    ).fetchall()
    _ensure_chinese_titles(conn, rows)
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
        [DEFAULT_USER_ID, *params, limit],
    ).fetchall()
    conn.close()
    return [_problem_summary(row) for row in rows]


@app.get("/api/progress/summary", response_model=ProgressSummary)
def progress_summary() -> ProgressSummary:
    conn = get_connection()
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
        (DEFAULT_USER_ID,),
    ).fetchone()
    today_row = conn.execute(
        """
        SELECT COUNT(DISTINCT task_id) AS today_passed
        FROM submissions
        WHERE user_id = ?
          AND passed = 1
          AND date(datetime(created_at, '+8 hours')) = date(datetime('now', '+8 hours'))
        """,
        (DEFAULT_USER_ID,),
    ).fetchone()
    conn.close()
    return ProgressSummary(
        total=int(row["total"] or 0),
        passed=int(row["passed"] or 0),
        needs_review=int(row["needs_review"] or 0),
        unseen=int(row["unseen"] or 0),
        today_passed=int(today_row["today_passed"] or 0),
    )


@app.get("/api/problem-tags", response_model=list[ProblemTag])
def list_problem_tags() -> list[ProblemTag]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT value AS name, COUNT(*) AS count
        FROM problems, json_each(problems.tags_json)
        GROUP BY value
        ORDER BY count DESC, name
        """
    ).fetchall()
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


@app.get("/api/practice/queue", response_model=PracticeQueueResponse)
def practice_queue(
    tags: Optional[list[str]] = Query(None),
    current_task_id: Optional[str] = None,
    difficulty: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(30, ge=1, le=100),
) -> PracticeQueueResponse:
    filters = PracticeFilters(
        user_id=DEFAULT_USER_ID,
        topics=tuple(tags or ()),
        difficulty=difficulty,
        status=status,
        search=search,
        current_task_id=current_task_id,
        limit=limit,
    )
    return _practice_queue_response(filters)


@app.get("/api/practice/next", response_model=PracticeQueueResponse)
def practice_next(
    current_task_id: str,
    tags: Optional[list[str]] = Query(None),
    difficulty: Optional[str] = None,
) -> PracticeQueueResponse:
    filters = PracticeFilters(
        user_id=DEFAULT_USER_ID,
        topics=tuple(tags or ()),
        difficulty=difficulty,
        current_task_id=current_task_id,
        exclude_current=True,
        match_any_topic=not tags,
        limit=1,
    )
    return _practice_queue_response(filters)


@app.get("/api/practice/insights", response_model=PracticeInsightsResponse)
def practice_insights(limit: int = Query(8, ge=1, le=30)) -> PracticeInsightsResponse:
    conn = get_connection()
    insights = fetch_topic_insights(conn, user_id=DEFAULT_USER_ID, limit=limit)
    conn.close()
    return PracticeInsightsResponse(
        strategy="优先看待复习和做过未通过的考点，再结合高频未做题补齐覆盖",
        topics=[PracticeTopicInsight(**insight.__dict__) for insight in insights],
    )


@app.get("/api/topic-memories", response_model=TopicMemoryListResponse)
def topic_memories(limit: int = Query(20, ge=1, le=80)) -> TopicMemoryListResponse:
    conn = get_connection()
    rows = fetch_topic_memories(conn, user_id=DEFAULT_USER_ID, limit=limit)
    conn.close()
    return TopicMemoryListResponse(memories=[_topic_memory_from_row(row) for row in rows])


@app.get("/api/agent/memories", response_model=AgentMemoryListResponse)
def agent_memories(
    status: Optional[str] = None,
    task_id: Optional[str] = None,
    limit: int = Query(80, ge=1, le=200),
) -> AgentMemoryListResponse:
    conn = get_connection()
    try:
        rows = fetch_memory_items(conn, user_id=DEFAULT_USER_ID, status=status, task_id=task_id, limit=limit)
    except ValueError as exc:
        conn.close()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    conn.close()
    return AgentMemoryListResponse(memories=[_agent_memory_item_from_row(row) for row in rows])


@app.put("/api/agent/memories/{memory_id}", response_model=AgentMemoryItem)
def update_agent_memory(memory_id: int, request: AgentMemoryUpdateRequest) -> AgentMemoryItem:
    conn = get_connection()
    try:
        with conn:
            row = update_memory_item(
                conn,
                user_id=DEFAULT_USER_ID,
                memory_id=memory_id,
                content=request.content,
                status=request.status,
            )
    except ValueError as exc:
        conn.close()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Memory not found")
    return _agent_memory_item_from_row(row)


@app.post("/api/agent/memories/{memory_id}/accept", response_model=AgentMemoryItem)
def accept_agent_memory(memory_id: int) -> AgentMemoryItem:
    return _set_agent_memory_status(memory_id, "accepted")


@app.post("/api/agent/memories/{memory_id}/reject", response_model=AgentMemoryItem)
def reject_agent_memory(memory_id: int) -> AgentMemoryItem:
    return _set_agent_memory_status(memory_id, "rejected")


@app.get("/api/agent/thread-summary/{task_id}", response_model=AgentThreadSummaryResponse)
def get_agent_thread_summary(task_id: str) -> AgentThreadSummaryResponse:
    _fetch_problem_row(task_id)
    conn = get_connection()
    row = fetch_thread_summary(conn, user_id=DEFAULT_USER_ID, task_id=task_id)
    conn.close()
    if not row:
        return AgentThreadSummaryResponse(task_id=task_id, summary=None)
    return AgentThreadSummaryResponse(
        task_id=task_id,
        summary=row["summary"],
        last_message_id=row["last_message_id"],
        updated_at=row["updated_at"],
    )


@app.post("/api/agent/command/stream")
def agent_command_stream(request: AgentCommandRequest) -> StreamingResponse:
    return _agent_command_stream_response(request)


@app.get("/api/problems/{task_id}/note", response_model=PracticeNoteResponse)
def get_practice_note(task_id: str) -> PracticeNoteResponse:
    _fetch_problem_row(task_id)
    conn = get_connection()
    row = fetch_note(conn, user_id=DEFAULT_USER_ID, task_id=task_id)
    suggested_topics = topic_labels_for_names(note_topic_names_for_problem(conn, task_id))
    note = _practice_note_from_row(conn, row) if row else None
    conn.close()
    return PracticeNoteResponse(note=note, suggested_topics=suggested_topics)


@app.put("/api/problems/{task_id}/note", response_model=PracticeNote)
def save_practice_note(task_id: str, request: PracticeNoteSaveRequest) -> PracticeNote:
    _fetch_problem_row(task_id)
    conn = get_connection()
    with conn:
        row = upsert_note(
            conn,
            user_id=DEFAULT_USER_ID,
            task_id=task_id,
            content_markdown=request.content_markdown,
            ai_summary=request.ai_summary,
            mistake_summary=request.mistake_summary,
            invariant_summary=request.invariant_summary,
            solution_pattern=request.solution_pattern,
            source_submission_id=request.source_submission_id,
            review_at=request.review_at,
            topics=request.topics,
        )
        note = _practice_note_from_row(conn, row)
    conn.close()
    return note


@app.post("/api/problems/{task_id}/note/draft", response_model=PracticeNoteDraftResponse)
def draft_practice_note(task_id: str, request: PracticeNoteDraftRequest) -> PracticeNoteDraftResponse:
    row = _fetch_problem_row(task_id)
    problem = _problem_payload(row)
    code, failure = _submission_context(task_id, request.code, request.submission_id)
    conn = get_connection()
    existing_note = fetch_note(conn, user_id=DEFAULT_USER_ID, task_id=task_id)
    topics = topic_labels_for_names(note_topic_names_for_problem(conn, task_id))
    conn.close()
    text = call_claude(
        build_note_draft_prompt(
            problem,
            code,
            failure,
            existing_note["content_markdown"] if existing_note else None,
        )
    )
    return PracticeNoteDraftResponse(
        content_markdown=text,
        source_submission_id=request.submission_id,
        topics=topics,
    )


@app.post("/api/problems/{task_id}/note/review", response_model=ReviewEvent)
def review_practice_note(task_id: str, request: ReviewEventRequest) -> ReviewEvent:
    if request.rating < 1 or request.rating > 5:
        raise HTTPException(status_code=400, detail="rating must be between 1 and 5")
    _fetch_problem_row(task_id)
    conn = get_connection()
    note = fetch_note(conn, user_id=DEFAULT_USER_ID, task_id=task_id)
    if not note:
        conn.close()
        raise HTTPException(status_code=404, detail="Practice note not found")
    with conn:
        event = create_review_event(conn, user_id=DEFAULT_USER_ID, note_id=note["id"], rating=request.rating)
    conn.close()
    return ReviewEvent(
        id=event["id"],
        user_id=event["user_id"],
        note_id=event["note_id"],
        rating=event["rating"],
        reviewed_at=event["reviewed_at"],
    )


@app.get("/api/problems/{task_id}", response_model=ProblemDetail)
def get_problem(task_id: str) -> ProblemDetail:
    row = _fetch_problem_row(task_id)
    return _problem_detail(row)


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


@app.post("/api/coach/diagnose", response_model=CoachResponse)
def diagnose(request: CoachRequest) -> CoachResponse:
    raise HTTPException(status_code=410, detail="Use /api/coach/diagnose/stream")


@app.post("/api/coach/diagnose/stream")
def diagnose_stream(request: CoachRequest) -> StreamingResponse:
    return _agent_command_stream_response(
        AgentCommandRequest(
            task_id=request.task_id,
            command="/diagnose",
            code=request.code,
            submission_id=request.submission_id,
            thinking_mode=request.thinking_mode,
        )
    )


@app.post("/api/coach/explain", response_model=CoachResponse)
def explain(request: CoachRequest) -> CoachResponse:
    raise HTTPException(status_code=410, detail="Use /api/coach/explain/stream")


@app.post("/api/coach/explain/stream")
def explain_stream(request: CoachRequest) -> StreamingResponse:
    return _agent_command_stream_response(
        AgentCommandRequest(
            task_id=request.task_id,
            command="/explain",
            code=request.code,
            submission_id=request.submission_id,
            thinking_mode=request.thinking_mode,
        )
    )


@app.get("/api/coach/thread/{task_id}", response_model=CoachThreadResponse)
def get_coach_thread(task_id: str) -> CoachThreadResponse:
    _fetch_problem_row(task_id)
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, role, content, created_at
        FROM coach_messages
        WHERE user_id = ? AND task_id = ?
        ORDER BY id
        """,
        (DEFAULT_USER_ID, task_id),
    ).fetchall()
    conn.close()
    return CoachThreadResponse(
        messages=[
            CoachMessage(id=row["id"], role=row["role"], content=row["content"], created_at=row["created_at"])
            for row in rows
        ]
    )


@app.delete("/api/coach/thread/{task_id}")
def clear_coach_thread(task_id: str) -> dict[str, str]:
    _fetch_problem_row(task_id)
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM coach_messages WHERE user_id = ? AND task_id = ?", (DEFAULT_USER_ID, task_id))
        conn.execute("DELETE FROM coach_thread_summaries WHERE user_id = ? AND task_id = ?", (DEFAULT_USER_ID, task_id))
    conn.close()
    return {"status": "cleared"}


@app.post("/api/coach/chat", response_model=CoachResponse)
def coach_chat(request: CoachChatRequest) -> CoachResponse:
    raise HTTPException(status_code=410, detail="Use /api/coach/chat/stream")


@app.post("/api/coach/chat/stream")
def coach_chat_stream(request: CoachChatRequest) -> StreamingResponse:
    return _agent_command_stream_response(
        AgentCommandRequest(
            task_id=request.task_id,
            command="auto",
            message=request.message,
            code=request.code,
            submission_id=request.submission_id,
            thinking_mode=request.thinking_mode,
        )
    )


def _agent_command_stream_response(request: AgentCommandRequest) -> StreamingResponse:
    row = _fetch_problem_row(request.task_id)
    problem = _problem_payload(row)
    command = normalize_command(request.command, request.message)
    code, failure = _submission_context(request.task_id, request.code, request.submission_id)
    conn = get_connection()
    topics = [*topic_names_for_problem(conn, request.task_id), *(problem.get("tags") or [])]
    memories = memory_rows_for_prompt(
        fetch_accepted_memories_for_context(
            conn,
            user_id=DEFAULT_USER_ID,
            task_id=request.task_id,
            topics=topics,
        )
    )
    history = _coach_history(conn, request.task_id)
    conn.close()
    enriched_problem = enrich_problem_with_memories(problem, memories)
    try:
        plan = build_command_plan(
            command=command,
            task_id=request.task_id,
            problem=enriched_problem,
            code=code,
            failure=failure,
            message=request.message,
            history=history,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _stream_coach_response(
        task_id=request.task_id,
        user_content=plan.user_content,
        messages=plan.messages,
        command=plan.command,
        problem=enriched_problem,
        submission_id=request.submission_id,
        thinking_mode=request.thinking_mode,
    )


def _fetch_problem_row(task_id: str):
    conn = get_connection()
    row = conn.execute(
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
        (DEFAULT_USER_ID, DEFAULT_USER_ID, task_id),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Problem not found: {task_id}")
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
            row = conn.execute(
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
                (DEFAULT_USER_ID, DEFAULT_USER_ID, task_id),
            ).fetchone()
    conn.close()
    return row


def _problem_summary(row) -> ProblemSummary:
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


def _practice_queue_response(filters: PracticeFilters) -> PracticeQueueResponse:
    conn = get_connection()
    queue = fetch_practice_queue(conn, filters)
    _ensure_chinese_titles(conn, queue.rows)
    queue = fetch_practice_queue(conn, filters)
    conn.close()
    items = [
        PracticeQueueItem(
            **_problem_summary(row).model_dump(),
            recommendation_reason=practice_reason(row, queue.active_topics),
        )
        for row in queue.rows
    ]
    return PracticeQueueResponse(
        active_topics=queue.active_topics,
        strategy="待复习 > 做过未通过 > 未做高频 > 难度递进 > 已通过巩固",
        items=items,
        next_task_id=items[0].task_id if items else None,
    )


def _practice_note_from_row(conn, row) -> PracticeNote:
    topics = topic_labels_for_names(fetch_note_topics(conn, row["id"]))
    return PracticeNote(
        id=row["id"],
        user_id=row["user_id"],
        task_id=row["task_id"],
        content_markdown=row["content_markdown"],
        ai_summary=row["ai_summary"],
        mistake_summary=row["mistake_summary"],
        invariant_summary=row["invariant_summary"],
        solution_pattern=row["solution_pattern"],
        source_submission_id=row["source_submission_id"],
        review_at=row["review_at"],
        topics=topics,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
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


def _agent_memory_item_from_row(row) -> AgentMemoryItem:
    return AgentMemoryItem(
        id=row["id"],
        user_id=row["user_id"],
        memory_type=row["memory_type"],
        scope=row["scope"],
        topic=row["topic"],
        task_id=row["task_id"],
        content=row["content"],
        source=row["source"],
        confidence=row["confidence"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _set_agent_memory_status(memory_id: int, status: str) -> AgentMemoryItem:
    conn = get_connection()
    with conn:
        row = set_memory_status(conn, user_id=DEFAULT_USER_ID, memory_id=memory_id, status=status)
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Memory not found")
    return _agent_memory_item_from_row(row)


def _coach_history(conn, task_id: str, limit: int = 12) -> list[dict[str, str]]:
    rows = conn.execute(
        """
        SELECT role, content
        FROM coach_messages
        WHERE user_id = ? AND task_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (DEFAULT_USER_ID, task_id, limit),
    ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]


def _ensure_chinese_titles(conn, rows) -> None:
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


def _problem_detail(row) -> ProblemDetail:
    base = _problem_summary(row).model_dump()
    base["title"] = row["title_zh"] or row["task_id"]
    return ProblemDetail(
        **base,
        problem_description=row["problem_description_zh"] or row["problem_description"],
        starter_code=row["starter_code"],
        entry_point=row["entry_point"],
        input_output=effective_input_output_for_problem(row["task_id"], row["input_output_json"]),
        saved_solution=_saved_solution_from_problem_row(row),
    )


def _saved_solution_from_problem_row(row) -> Optional[SavedSolution]:
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


def _problem_payload(row) -> dict[str, Any]:
    return {
        "task_id": row["task_id"],
        "question_id": row["question_id"],
        "difficulty": row["difficulty"],
        "tags": display_topic_labels(json.loads(row["tags_json"])),
        "problem_description": row["problem_description_zh"] or row["problem_description"],
        "practice_context": _practice_context(row["task_id"]),
    }


def _practice_context(task_id: str) -> dict[str, Any]:
    conn = get_connection()
    current_topics = set(topic_names_for_problem(conn, task_id))
    insights = fetch_topic_insights(conn, user_id=DEFAULT_USER_ID, limit=8)
    relevant_insights = [insight for insight in insights if insight.name in current_topics] or insights[:3]
    queue = fetch_practice_queue(
        conn,
        PracticeFilters(
            user_id=DEFAULT_USER_ID,
            current_task_id=task_id,
            exclude_current=True,
            match_any_topic=True,
            limit=3,
        ),
    )
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


def _submission_context(task_id: str, code: Optional[str], submission_id: Optional[int]) -> tuple[str, Optional[dict[str, Any]]]:
    failure: Optional[dict[str, Any]] = None
    resolved_code = code or ""
    conn = get_connection()
    submission = None
    if submission_id:
        submission = conn.execute(
            "SELECT * FROM submissions WHERE user_id = ? AND id = ?",
            (DEFAULT_USER_ID, submission_id),
        ).fetchone()
    if not submission:
        submission = conn.execute(
            "SELECT * FROM submissions WHERE user_id = ? AND task_id = ? ORDER BY id DESC LIMIT 1",
            (DEFAULT_USER_ID, task_id),
        ).fetchone()
    conn.close()
    if submission:
        resolved_code = resolved_code or submission["code"]
        if not submission["passed"]:
            failure = {
                "failed_assertion": submission["failed_assertion"],
                "stderr": submission["stderr"],
                "runtime_ms": submission["runtime_ms"],
            }
    return resolved_code, failure


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


def _append_coach_message(task_id: str, role: str, content: str) -> int:
    conn = get_connection()
    with conn:
        cursor = conn.execute(
            "INSERT INTO coach_messages (user_id, task_id, role, content) VALUES (?, ?, ?, ?)",
            (DEFAULT_USER_ID, task_id, role, content),
        )
        message_id = int(cursor.lastrowid)
    conn.close()
    return message_id


def _stream_coach_response(
    *,
    task_id: str,
    user_content: str,
    messages: list[dict[str, str]],
    command: str = "auto",
    problem: Optional[dict[str, Any]] = None,
    submission_id: Optional[int] = None,
    thinking_mode: Optional[str] = None,
) -> StreamingResponse:
    def generate():
        chunks: list[str] = []
        for chunk in call_claude_messages_stream(messages, thinking_mode=thinking_mode):
            chunks.append(chunk)
            yield chunk

        text = "".join(chunks).strip()
        if not text:
            text = "AI 没有返回内容。请稍后重试，或检查当前模型/API 配置。"
            yield text
        user_message_id = _append_coach_message(task_id, "user", user_content)
        assistant_message_id = _append_coach_message(task_id, "assistant", text)
        conn = get_connection()
        with conn:
            run_after_coach_response_hook(
                conn,
                user_id=DEFAULT_USER_ID,
                task_id=task_id,
                command=command,
                problem=problem or {"task_id": task_id},
                user_content=user_content,
                assistant_text=text,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
            )
        conn.close()
        if submission_id:
            conn = get_connection()
            with conn:
                conn.execute(
                    "UPDATE submissions SET ai_diagnosis_summary = ? WHERE user_id = ? AND id = ?",
                    (text[:1000], DEFAULT_USER_ID, submission_id),
                )
            conn.close()

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")
