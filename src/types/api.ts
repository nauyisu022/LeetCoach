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

export type CoachMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type Filters = {
  difficulty?: string;
  tags?: string[];
  status?: string;
  search?: string;
};
