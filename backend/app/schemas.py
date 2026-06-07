from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ProblemSummary(BaseModel):
    task_id: str
    question_id: int
    title: str
    difficulty: str
    tags: list[str]
    status: str
    submit_count: int
    pass_count: int
    last_submitted_at: str | None
    codetop_frequency: int | None = None
    codetop_last_asked_at: str | None = None


class ProgressSummary(BaseModel):
    total: int
    passed: int
    needs_review: int
    unseen: int
    today_passed: int


class PracticeQueueItem(ProblemSummary):
    recommendation_reason: str


class PracticeQueueResponse(BaseModel):
    active_topics: list[str]
    strategy: str
    items: list[PracticeQueueItem]
    next_task_id: str | None


class PracticeTopicInsight(BaseModel):
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


class PracticeInsightsResponse(BaseModel):
    strategy: str
    topics: list[PracticeTopicInsight]


class ProblemTag(BaseModel):
    name: str
    label: str
    category: str
    category_label: str
    aliases: list[str]
    count: int


class SavedSolution(BaseModel):
    id: int
    user_id: str
    task_id: str
    code: str
    language: str
    notes: str | None
    created_at: str
    updated_at: str


class PracticeNote(BaseModel):
    id: int
    user_id: str
    task_id: str
    content_markdown: str
    ai_summary: str | None
    mistake_summary: str | None
    invariant_summary: str | None
    solution_pattern: str | None
    source_submission_id: int | None
    review_at: str | None
    topics: list[str]
    created_at: str
    updated_at: str


class PracticeNoteResponse(BaseModel):
    note: PracticeNote | None
    suggested_topics: list[str]


class PracticeNoteSaveRequest(BaseModel):
    content_markdown: str
    ai_summary: str | None = None
    mistake_summary: str | None = None
    invariant_summary: str | None = None
    solution_pattern: str | None = None
    source_submission_id: int | None = None
    review_at: str | None = None
    topics: list[str] | None = None


class PracticeNoteDraftRequest(BaseModel):
    code: str | None = None
    submission_id: int | None = None


class PracticeNoteDraftResponse(BaseModel):
    content_markdown: str
    source_submission_id: int | None
    topics: list[str]


class TopicMemory(BaseModel):
    user_id: str
    topic_name: str
    topic_label: str
    memory_markdown: str
    common_mistakes: list[str]
    recognition_cues: list[str]
    template_notes: list[str]
    mastery_level: str
    created_at: str
    updated_at: str


class TopicMemoryListResponse(BaseModel):
    memories: list[TopicMemory]


class ReviewEventRequest(BaseModel):
    rating: int


class ReviewEvent(BaseModel):
    id: int
    user_id: str
    note_id: int
    rating: int
    reviewed_at: str


class ProblemDetail(ProblemSummary):
    title: str
    problem_description: str
    starter_code: str
    entry_point: str
    input_output: list[dict[str, Any]]
    saved_solution: SavedSolution | None = None


class SubmissionRequest(BaseModel):
    task_id: str
    code: str
    custom_input: str | None = None
    custom_expected_output: str | None = None


class SaveSolutionRequest(BaseModel):
    code: str
    language: str = "python"
    notes: str | None = None


class SubmissionResponse(BaseModel):
    id: int | None
    task_id: str
    mode: str
    status: str
    title: str
    summary: str
    passed: bool
    failed_assertion: str | None
    stderr: str | None
    stdout: str | None
    return_output: str | None = None
    runtime_ms: int
    execution_ms: int | None = None
    test_count_estimate: int
    passed_test_count: int


class SubmissionHistoryItem(BaseModel):
    id: int
    task_id: str
    status: str
    passed: bool
    failed_assertion: str | None
    runtime_ms: int
    execution_ms: int | None = None
    test_count_estimate: int
    passed_test_count: int
    created_at: str


class CoachRequest(BaseModel):
    task_id: str
    code: str | None = None
    submission_id: int | None = None


class CoachResponse(BaseModel):
    text: str


class CoachChatRequest(BaseModel):
    task_id: str
    message: str
    code: str | None = None
    submission_id: int | None = None


class CoachMessage(BaseModel):
    id: int
    role: str
    content: str
    created_at: str


class CoachThreadResponse(BaseModel):
    messages: list[CoachMessage]
