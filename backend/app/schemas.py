from __future__ import annotations

from typing import Any
from typing import Optional

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
    last_submitted_at: Optional[str]
    codetop_frequency: Optional[int] = None
    codetop_last_asked_at: Optional[str] = None


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
    next_task_id: Optional[str]


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
    next_task_id: Optional[str]


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
    notes: Optional[str]
    created_at: str
    updated_at: str


class PracticeNote(BaseModel):
    id: int
    user_id: str
    task_id: str
    content_markdown: str
    ai_summary: Optional[str]
    mistake_summary: Optional[str]
    invariant_summary: Optional[str]
    solution_pattern: Optional[str]
    source_submission_id: Optional[int]
    review_at: Optional[str]
    topics: list[str]
    created_at: str
    updated_at: str


class PracticeNoteResponse(BaseModel):
    note: Optional[PracticeNote]
    suggested_topics: list[str]


class PracticeNoteSaveRequest(BaseModel):
    content_markdown: str
    ai_summary: Optional[str] = None
    mistake_summary: Optional[str] = None
    invariant_summary: Optional[str] = None
    solution_pattern: Optional[str] = None
    source_submission_id: Optional[int] = None
    review_at: Optional[str] = None
    topics: Optional[list[str]] = None


class PracticeNoteDraftRequest(BaseModel):
    code: Optional[str] = None
    submission_id: Optional[int] = None


class PracticeNoteDraftResponse(BaseModel):
    content_markdown: str
    source_submission_id: Optional[int]
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
    saved_solution: Optional[SavedSolution] = None


class SubmissionRequest(BaseModel):
    task_id: str
    code: str
    custom_input: Optional[str] = None
    custom_expected_output: Optional[str] = None


class SaveSolutionRequest(BaseModel):
    code: str
    language: str = "python"
    notes: Optional[str] = None


class SubmissionResponse(BaseModel):
    id: Optional[int]
    task_id: str
    mode: str
    status: str
    title: str
    summary: str
    passed: bool
    failed_assertion: Optional[str]
    stderr: Optional[str]
    stdout: Optional[str]
    return_output: Optional[str] = None
    runtime_ms: int
    execution_ms: Optional[int] = None
    test_count_estimate: int
    passed_test_count: int


class SubmissionHistoryItem(BaseModel):
    id: int
    task_id: str
    status: str
    passed: bool
    failed_assertion: Optional[str]
    runtime_ms: int
    execution_ms: Optional[int] = None
    test_count_estimate: int
    passed_test_count: int
    created_at: str


class CoachRequest(BaseModel):
    task_id: str
    code: Optional[str] = None
    submission_id: Optional[int] = None
    thinking_mode: Optional[str] = None


class CoachResponse(BaseModel):
    text: str


class CoachChatRequest(BaseModel):
    task_id: str
    message: str
    code: Optional[str] = None
    submission_id: Optional[int] = None
    thinking_mode: Optional[str] = None


class AgentCommandRequest(BaseModel):
    task_id: str
    command: str = "auto"
    message: Optional[str] = None
    code: Optional[str] = None
    submission_id: Optional[int] = None
    thinking_mode: Optional[str] = None


class CoachMessage(BaseModel):
    id: int
    role: str
    content: str
    created_at: str


class CoachThreadResponse(BaseModel):
    messages: list[CoachMessage]


class AgentMemoryItem(BaseModel):
    id: int
    user_id: str
    memory_type: str
    scope: str
    topic: Optional[str]
    task_id: Optional[str]
    content: str
    source: str
    confidence: float
    status: str
    created_at: str
    updated_at: str


class AgentMemoryListResponse(BaseModel):
    memories: list[AgentMemoryItem]


class AgentMemoryUpdateRequest(BaseModel):
    content: Optional[str] = None
    status: Optional[str] = None


class AgentThreadSummaryResponse(BaseModel):
    task_id: str
    summary: Optional[str]
    last_message_id: Optional[int] = None
    updated_at: Optional[str] = None
