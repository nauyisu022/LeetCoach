export type ProblemSummary = {
  task_id: string;
  question_id: number;
  title: string;
  difficulty: "Easy" | "Medium" | "Hard" | string;
  tags: string[];
  status: string;
  submit_count: number;
  pass_count: number;
  last_submitted_at: string | null;
  codetop_frequency: number | null;
  codetop_last_asked_at: string | null;
  study_plan_slug?: string;
  group_name?: string;
  group_slug?: string;
  group_position?: number;
  item_position?: number;
  plan_position?: number;
  paid_only?: boolean;
  available?: boolean;
  external_slug?: string;
  leetcode_url?: string;
};

export type StudyPlanSummary = {
  id: number;
  slug: string;
  title: string;
  source_type: string;
  source_url: string;
  description: string | null;
  fetched_at: string | null;
  total_count: number;
  available_count: number;
  missing_count: number;
  passed_count: number;
  needs_review_count: number;
  unseen_count: number;
  progress: number;
};

export type StudyPlanGroupSummary = {
  group_name: string;
  group_slug: string;
  group_position: number;
  total_count: number;
  available_count: number;
  missing_count: number;
  passed_count: number;
  needs_review_count: number;
  unseen_count: number;
};

export type StudyPlanItemsResponse = {
  plan: StudyPlanSummary;
  groups: StudyPlanGroupSummary[];
  items: ProblemSummary[];
  next_task_id: string | null;
};

export type StudyPlanListResponse = {
  plans: StudyPlanSummary[];
};

export type ProgressSummary = {
  total: number;
  passed: number;
  needs_review: number;
  unseen: number;
  today_passed: number;
};

export type PracticeQueueItem = ProblemSummary & {
  recommendation_reason: string;
};

export type PracticeQueueResponse = {
  active_topics: string[];
  strategy: string;
  items: PracticeQueueItem[];
  next_task_id: string | null;
};

export type PracticeTopicInsight = {
  name: string;
  label: string;
  category: string;
  category_label: string;
  total_problem_count: number;
  unseen_count: number;
  attempted_count: number;
  needs_review_count: number;
  passed_count: number;
  submit_count: number;
  pass_count: number;
  codetop_frequency: number;
  progress: number;
  priority_score: number;
  recommendation: string;
  next_task_id: string | null;
};

export type PracticeInsightsResponse = {
  strategy: string;
  topics: PracticeTopicInsight[];
};

export type PracticeNote = {
  id: number;
  user_id: string;
  task_id: string;
  content_markdown: string;
  ai_summary: string | null;
  mistake_summary: string | null;
  invariant_summary: string | null;
  solution_pattern: string | null;
  source_submission_id: number | null;
  review_at: string | null;
  topics: string[];
  created_at: string;
  updated_at: string;
};

export type PracticeNoteResponse = {
  note: PracticeNote | null;
  suggested_topics: string[];
};

export type PracticeNoteSaveRequest = {
  content_markdown: string;
  ai_summary?: string | null;
  mistake_summary?: string | null;
  invariant_summary?: string | null;
  solution_pattern?: string | null;
  source_submission_id?: number | null;
  review_at?: string | null;
  topics?: string[] | null;
};

export type PracticeNoteDraftResponse = {
  content_markdown: string;
  source_submission_id: number | null;
  topics: string[];
};

export type AgentToolInfo = {
  name: string;
  description: string;
  trigger: string;
  prompt_visibility: string;
};

export type AgentToolListResponse = {
  tools: AgentToolInfo[];
};

export type AgentCommandInfo = {
  name: string;
  route: string;
  default_message: string;
  skill_name: string;
  aliases: string[];
  display_name: string | null;
  toolbar_icon: string | null;
  toolbar_order: number | null;
};

export type AgentCommandListResponse = {
  commands: AgentCommandInfo[];
};

export type AgentProfileInfo = {
  name: string;
  description: string;
  tool_names: string[];
  command_routes: string[];
  hook_names: string[];
  stream_only: boolean;
  state_backends: string[];
};

export type AgentProfileResponse = {
  profile: AgentProfileInfo;
};

export type AgentCommandRequest = {
  task_id: string;
  command?: string;
  message?: string;
  code?: string;
  submission_id?: number;
  current_result?: CoachCurrentResult;
  thinking_mode?: ThinkingMode;
  html_visual_mode?: HtmlVisualMode;
};

export type AssistantRunEvent =
  | { type: "text-delta"; delta: string }
  | { type: "thread-snapshot"; messages: AgentThreadMessage[] }
  | { type: "done" }
  | { type: "error"; message: string };

export type AgentToolRunPreview = {
  name: string;
  payload: Record<string, unknown>;
  prompt_section: string;
  ok: boolean;
};

export type AgentCommandPreviewResponse = {
  task_id: string;
  command: string;
  user_content: string;
  thinking_mode: ThinkingMode | null;
  html_visual_mode: HtmlVisualMode | null;
  current_topics: string[];
  history_count: number;
  memory_count: number;
  tool_results: AgentToolRunPreview[];
  code_present: boolean;
  failure_present: boolean;
  failure: Record<string, unknown> | null;
  messages: Array<{ role: string; content: string }>;
};

export type TopicMemory = {
  user_id: string;
  topic_name: string;
  topic_label: string;
  memory_markdown: string;
  common_mistakes: string[];
  recognition_cues: string[];
  template_notes: string[];
  mastery_level: string;
  created_at: string;
  updated_at: string;
};

export type TopicMemoryListResponse = {
  memories: TopicMemory[];
};

export type ProblemTag = {
  name: string;
  label: string;
  category: string;
  category_label: string;
  aliases: string[];
  count: number;
};

export type ProblemDetail = ProblemSummary & {
  title: string;
  problem_description: string;
  starter_code: string;
  entry_point: string;
  input_output: Array<{ input: string; output: string }>;
  saved_solution: SavedSolution | null;
};

export type SavedSolution = {
  id: number;
  user_id: string;
  task_id: string;
  code: string;
  language: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type SubmissionResponse = {
  id: number | null;
  task_id: string;
  mode: "run" | "submit";
  status: "passed" | "failed";
  title: string;
  summary: string;
  passed: boolean;
  failed_assertion: string | null;
  stderr: string | null;
  stdout: string | null;
  return_output: string | null;
  runtime_ms: number;
  execution_ms: number | null;
  test_count_estimate: number;
  passed_test_count: number;
};

export type SubmissionHistoryItem = {
  id: number;
  task_id: string;
  status: "passed" | "failed";
  passed: boolean;
  failed_assertion: string | null;
  runtime_ms: number;
  execution_ms: number | null;
  test_count_estimate: number;
  passed_test_count: number;
  created_at: string;
};

export type CustomTestCase = {
  id: string;
  name: string;
  input: string;
  expectedOutput?: string;
};

export type CustomCaseResult = {
  case: CustomTestCase;
  response: SubmissionResponse;
};

export type DisplaySubmissionResponse = SubmissionResponse & {
  case_results?: CustomCaseResult[];
};

export type CoachCurrentResult = Pick<
  DisplaySubmissionResponse,
  | "task_id"
  | "mode"
  | "status"
  | "summary"
  | "passed"
  | "failed_assertion"
  | "stderr"
  | "stdout"
  | "return_output"
  | "runtime_ms"
  | "execution_ms"
  | "test_count_estimate"
  | "passed_test_count"
  | "case_results"
>;

export type AgentThreadMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type AgentThreadResponse = {
  messages: AgentThreadMessage[];
};

export type ThinkingMode = "enabled" | "disabled";
export type HtmlVisualMode = "enabled" | "disabled";

export type AgentMemoryStatus = "proposed" | "accepted" | "rejected" | "archived";

export type AgentMemoryItem = {
  id: number;
  user_id: string;
  memory_type: string;
  scope: "global" | "topic" | "task" | string;
  topic: string | null;
  task_id: string | null;
  content: string;
  source: string;
  confidence: number;
  status: AgentMemoryStatus;
  created_at: string;
  updated_at: string;
};

export type AgentMemoryListResponse = {
  memories: AgentMemoryItem[];
};

export type AgentMemoryUpdateRequest = {
  content?: string | null;
  status?: AgentMemoryStatus | null;
};

export type AgentProblemSearchResult = {
  task_id: string;
  question_id: number;
  title: string;
  url: string;
  markdown_link: string;
  difficulty: string;
  tags: string[];
  codetop_frequency?: number | null;
};

export type AgentProblemSearchResponse = {
  query: string;
  interpreted_topics: string[];
  results: AgentProblemSearchResult[];
  recommendation_set_id: number | null;
};

export type AgentRecommendationItem = {
  order: number;
  task_id: string;
  question_id: number;
  title: string;
  url?: string | null;
  markdown_link?: string | null;
  difficulty: string;
  tags: string[];
  codetop_frequency?: number | null;
  status: string;
};

export type AgentRecommendationSet = {
  id: number;
  user_id: string;
  source_task_id: string | null;
  title: string;
  query: string;
  interpreted_topics: string[];
  items: AgentRecommendationItem[];
  status: string;
  created_at: string;
  updated_at: string;
};

export type AgentRecommendationSetResponse = {
  recommendation_set: AgentRecommendationSet | null;
};

export type Filters = {
  difficulty?: string;
  tags?: string[];
  status?: string;
  search?: string;
};
