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


class StudyPlanSummary(BaseModel):
    id: int
    slug: str
    title: str
    source_type: str
    source_url: str
    description: Optional[str] = None
    fetched_at: Optional[str] = None
    total_count: int
    available_count: int
    missing_count: int
    passed_count: int
    needs_review_count: int
    unseen_count: int
    progress: float


class StudyPlanGroupSummary(BaseModel):
    group_name: str
    group_slug: str
    group_position: int
    total_count: int
    available_count: int
    missing_count: int
    passed_count: int
    needs_review_count: int
    unseen_count: int


class StudyPlanProblemSummary(ProblemSummary):
    study_plan_slug: str
    group_name: str
    group_slug: str
    group_position: int
    item_position: int
    plan_position: int
    paid_only: bool
    available: bool
    external_slug: str
    leetcode_url: str


class StudyPlanListResponse(BaseModel):
    plans: list[StudyPlanSummary]


class StudyPlanItemsResponse(BaseModel):
    plan: StudyPlanSummary
    groups: list[StudyPlanGroupSummary]
    items: list[StudyPlanProblemSummary]
    next_task_id: Optional[str]


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


class CoachCurrentResult(BaseModel):
    task_id: str
    mode: str
    status: str
    summary: str
    passed: bool
    failed_assertion: Optional[str] = None
    stderr: Optional[str] = None
    stdout: Optional[str] = None
    return_output: Optional[str] = None
    runtime_ms: Optional[int] = None
    execution_ms: Optional[int] = None
    test_count_estimate: Optional[int] = None
    passed_test_count: Optional[int] = None
    case_results: Optional[list[dict[str, Any]]] = None


class PracticeNoteDraftRequest(BaseModel):
    code: Optional[str] = None
    submission_id: Optional[int] = None
    current_result: Optional[CoachCurrentResult] = None
    thinking_mode: Optional[str] = None


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


class AgentCommandRequest(BaseModel):
    task_id: str
    command: str = "auto"
    message: Optional[str] = None
    code: Optional[str] = None
    submission_id: Optional[int] = None
    current_result: Optional[CoachCurrentResult] = None
    thinking_mode: Optional[str] = None


AssistantRunRequest = AgentCommandRequest


class AgentCommandInfo(BaseModel):
    name: str
    route: str
    default_message: str
    skill_name: str
    aliases: list[str]
    display_name: Optional[str] = None
    toolbar_icon: Optional[str] = None
    toolbar_order: Optional[int] = None


class AgentCommandListResponse(BaseModel):
    commands: list[AgentCommandInfo]


class AgentProfileInfo(BaseModel):
    name: str
    description: str
    tool_names: list[str]
    command_routes: list[str]
    hook_names: list[str]
    stream_only: bool
    state_backends: list[str]


class AgentProfileResponse(BaseModel):
    profile: AgentProfileInfo


class AgentToolRunPreview(BaseModel):
    name: str
    payload: dict[str, Any]
    prompt_section: str
    ok: bool


class AgentCommandPreviewResponse(BaseModel):
    task_id: str
    command: str
    user_content: str
    thinking_mode: Optional[str]
    current_topics: list[str]
    history_count: int
    memory_count: int
    tool_results: list[AgentToolRunPreview]
    code_present: bool
    failure_present: bool
    failure: Optional[dict[str, Any]]
    messages: list[dict[str, str]]


class AgentThreadMessage(BaseModel):
    id: int
    role: str
    content: str
    created_at: str


class AgentThreadResponse(BaseModel):
    messages: list[AgentThreadMessage]


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


class AgentProblemSearchResult(BaseModel):
    task_id: str
    question_id: int
    title: str
    url: str
    markdown_link: str
    difficulty: str
    tags: list[str]
    codetop_frequency: Optional[int] = None


class AgentProblemSearchResponse(BaseModel):
    query: str
    interpreted_topics: list[str]
    results: list[AgentProblemSearchResult]
    recommendation_set_id: Optional[int] = None


class AgentRecommendationItem(BaseModel):
    order: int
    task_id: str
    question_id: int
    title: str
    url: Optional[str] = None
    markdown_link: Optional[str] = None
    difficulty: str
    tags: list[str]
    codetop_frequency: Optional[int] = None
    status: str = "not_started"


class AgentRecommendationSet(BaseModel):
    id: int
    user_id: str
    source_task_id: Optional[str]
    title: str
    query: str
    interpreted_topics: list[str]
    items: list[AgentRecommendationItem]
    status: str
    created_at: str
    updated_at: str


class AgentRecommendationSetResponse(BaseModel):
    recommendation_set: Optional[AgentRecommendationSet]


class AgentToolInfo(BaseModel):
    name: str
    description: str
    trigger: str
    prompt_visibility: str


class AgentToolListResponse(BaseModel):
    tools: list[AgentToolInfo]
