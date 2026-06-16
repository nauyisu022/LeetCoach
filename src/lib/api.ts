import type {
  AgentCommandListResponse,
  AgentCommandPreviewResponse,
  AgentCommandRequest,
  AssistantRunEvent,
  AgentMemoryItem,
  AgentMemoryListResponse,
  AgentMemoryStatus,
  AgentMemoryUpdateRequest,
  AgentProfileResponse,
  AgentProblemSearchResponse,
  AgentRecommendationSetResponse,
  AgentThreadResponse,
  AgentToolListResponse,
  CoachCurrentResult,
  Filters,
  PracticeInsightsResponse,
  PracticeNote,
  PracticeNoteDraftResponse,
  PracticeNoteResponse,
  PracticeNoteSaveRequest,
  PracticeQueueResponse,
  ProblemDetail,
  ProblemSummary,
  ProblemTag,
  ProgressSummary,
  SavedSolution,
  StudyPlanItemsResponse,
  StudyPlanListResponse,
  SubmissionHistoryItem,
  SubmissionResponse,
  ThinkingMode,
  TopicMemoryListResponse
} from "../types/api";

const AI_FIRST_CHUNK_TIMEOUT_MS = 45_000;
const PROBLEM_LIST_LIMIT = 3000;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || response.statusText);
  }
  return response.json() as Promise<T>;
}

async function streamRequest(path: string, init: RequestInit, onChunk: (chunk: string) => void): Promise<string> {
  const controller = new AbortController();
  const externalSignal = init.signal;
  let timedOut = false;
  let receivedFirstChunk = false;
  function abortFromExternalSignal() {
    controller.abort();
  }

  if (externalSignal?.aborted) {
    controller.abort();
  } else {
    externalSignal?.addEventListener("abort", abortFromExternalSignal, { once: true });
  }

  const firstChunkTimer = window.setTimeout(() => {
    if (receivedFirstChunk) return;
    timedOut = true;
    controller.abort();
  }, AI_FIRST_CHUNK_TIMEOUT_MS);

  try {
    const response = await fetch(path, {
      ...init,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(init.headers ?? {})
      }
    });
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || response.statusText);
    }

    if (!response.body) {
      const text = await response.text();
      receivedFirstChunk = Boolean(text);
      if (text) onChunk(text);
      return text;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let text = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      if (chunk && !receivedFirstChunk) {
        receivedFirstChunk = true;
        window.clearTimeout(firstChunkTimer);
      }
      text += chunk;
      onChunk(chunk);
    }

    const tail = decoder.decode();
    if (tail) {
      if (!receivedFirstChunk) receivedFirstChunk = true;
      text += tail;
      onChunk(tail);
    }
    return text;
  } catch (err) {
    if (timedOut) {
      throw new Error("AI 响应超过 45 秒没有输出，已取消。请稍后重试。");
    }
    throw err;
  } finally {
    window.clearTimeout(firstChunkTimer);
    externalSignal?.removeEventListener("abort", abortFromExternalSignal);
  }
}

async function* eventStreamRequest<TEvent>(path: string, init: RequestInit): AsyncGenerator<TEvent, void> {
  const controller = new AbortController();
  const externalSignal = init.signal;
  let timedOut = false;
  let receivedFirstEvent = false;
  function abortFromExternalSignal() {
    controller.abort();
  }

  if (externalSignal?.aborted) {
    controller.abort();
  } else {
    externalSignal?.addEventListener("abort", abortFromExternalSignal, { once: true });
  }

  const firstEventTimer = window.setTimeout(() => {
    if (receivedFirstEvent) return;
    timedOut = true;
    controller.abort();
  }, AI_FIRST_CHUNK_TIMEOUT_MS);

  try {
    const response = await fetch(path, {
      ...init,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(init.headers ?? {})
      }
    });
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || response.statusText);
    }
    if (!response.body) return;

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        if (!receivedFirstEvent) {
          receivedFirstEvent = true;
          window.clearTimeout(firstEventTimer);
        }
        yield JSON.parse(trimmed) as TEvent;
      }
    }

    buffer += decoder.decode();
    const tail = buffer.trim();
    if (tail) {
      if (!receivedFirstEvent) receivedFirstEvent = true;
      yield JSON.parse(tail) as TEvent;
    }
  } catch (err) {
    if (timedOut) {
      throw new Error("AI 响应超过 45 秒没有输出，已取消。请稍后重试。");
    }
    throw err;
  } finally {
    window.clearTimeout(firstEventTimer);
    externalSignal?.removeEventListener("abort", abortFromExternalSignal);
  }
}

export function fetchProblems(filters: Filters): Promise<ProblemSummary[]> {
  const params = new URLSearchParams();
  params.set("limit", String(PROBLEM_LIST_LIMIT));
  Object.entries(filters).forEach(([key, value]) => {
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item) params.append(key, item);
      });
    } else if (value) {
      params.set(key, value);
    }
  });
  return request(`/api/problems?${params.toString()}`);
}

export function fetchProblemTags(): Promise<ProblemTag[]> {
  return request("/api/problem-tags");
}

export function fetchStudyPlans(): Promise<StudyPlanListResponse> {
  return request("/api/study-plans");
}

export function fetchStudyPlanItems(
  slug: string,
  filters: Filters,
  groupSlug?: string
): Promise<StudyPlanItemsResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(PROBLEM_LIST_LIMIT));
  if (groupSlug) params.set("group_slug", groupSlug);
  Object.entries(filters).forEach(([key, value]) => {
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item) params.append(key, item);
      });
    } else if (value) {
      params.set(key, value);
    }
  });
  return request(`/api/study-plans/${encodeURIComponent(slug)}?${params.toString()}`);
}

export function fetchProgressSummary(): Promise<ProgressSummary> {
  return request("/api/progress/summary");
}

export function fetchPracticeQueue(filters: Filters, currentTaskId?: string): Promise<PracticeQueueResponse> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item) params.append(key, item);
      });
    } else if (value) {
      params.set(key, value);
    }
  });
  if (currentTaskId) params.set("current_task_id", currentTaskId);
  return request(`/api/practice/queue?${params.toString()}`);
}

export function fetchPracticeInsights(): Promise<PracticeInsightsResponse> {
  return request("/api/practice/insights");
}

export function fetchPracticeNote(taskId: string): Promise<PracticeNoteResponse> {
  return request(`/api/problems/${taskId}/note`);
}

export function savePracticeNote(taskId: string, payload: PracticeNoteSaveRequest): Promise<PracticeNote> {
  return request(`/api/problems/${taskId}/note`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export async function streamPracticeNoteDraft(
  taskId: string,
  code: string,
  submissionId: number | undefined,
  currentResult: CoachCurrentResult | undefined,
  thinkingMode: ThinkingMode,
  onChunk: (chunk: string) => void,
  signal?: AbortSignal
): Promise<PracticeNoteDraftResponse> {
  const content = await streamRequest(
    `/api/problems/${taskId}/note/draft/stream`,
    {
      method: "POST",
      signal,
      body: JSON.stringify({
        code,
        submission_id: submissionId,
        current_result: currentResult,
        thinking_mode: thinkingMode
      })
    },
    onChunk
  );
  return {
    content_markdown: content,
    source_submission_id: submissionId ?? null,
    topics: []
  };
}

export function reviewPracticeNote(taskId: string, rating: number): Promise<{ rating: number }> {
  return request(`/api/problems/${taskId}/note/review`, {
    method: "POST",
    body: JSON.stringify({ rating })
  });
}

export function fetchTopicMemories(): Promise<TopicMemoryListResponse> {
  return request("/api/topic-memories");
}

export function fetchAgentMemories(status?: AgentMemoryStatus, taskId?: string): Promise<AgentMemoryListResponse> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (taskId) params.set("task_id", taskId);
  const suffix = params.toString();
  return request(`/api/agent/memories${suffix ? `?${suffix}` : ""}`);
}

export function fetchAgentTools(): Promise<AgentToolListResponse> {
  return request("/api/agent/tools");
}

export function fetchAgentCommands(): Promise<AgentCommandListResponse> {
  return request("/api/agent/commands");
}

export function fetchAgentProfile(): Promise<AgentProfileResponse> {
  return request("/api/agent/profile");
}

export function fetchLatestRecommendationSet(sourceTaskId?: string): Promise<AgentRecommendationSetResponse> {
  const params = new URLSearchParams();
  if (sourceTaskId) params.set("source_task_id", sourceTaskId);
  const suffix = params.toString();
  return request(`/api/agent/recommendation-sets/latest${suffix ? `?${suffix}` : ""}`);
}

export function previewAgentCommand(payload: AgentCommandRequest): Promise<AgentCommandPreviewResponse> {
  return request("/api/agent/command/preview", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateAgentMemory(memoryId: number, payload: AgentMemoryUpdateRequest): Promise<AgentMemoryItem> {
  return request(`/api/agent/memories/${memoryId}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function acceptAgentMemory(memoryId: number): Promise<AgentMemoryItem> {
  return request(`/api/agent/memories/${memoryId}/accept`, { method: "POST" });
}

export function rejectAgentMemory(memoryId: number): Promise<AgentMemoryItem> {
  return request(`/api/agent/memories/${memoryId}/reject`, { method: "POST" });
}

export function fetchProblem(taskId: string): Promise<ProblemDetail> {
  return request(`/api/problems/${taskId}`);
}

export function saveSolution(taskId: string, code: string): Promise<SavedSolution> {
  return request(`/api/problems/${taskId}/solution`, {
    method: "PUT",
    body: JSON.stringify({ code })
  });
}

export function submitCode(taskId: string, code: string): Promise<SubmissionResponse> {
  return request("/api/submissions", {
    method: "POST",
    body: JSON.stringify({ task_id: taskId, code })
  });
}

export function fetchSubmissionHistory(taskId: string): Promise<SubmissionHistoryItem[]> {
  return request(`/api/problems/${taskId}/submissions`);
}

export function runCode(taskId: string, code: string, customInput?: string, customExpectedOutput?: string): Promise<SubmissionResponse> {
  return request("/api/runs", {
    method: "POST",
    body: JSON.stringify({
      task_id: taskId,
      code,
      custom_input: customInput || undefined,
      custom_expected_output: customExpectedOutput || undefined
    })
  });
}

export function streamAgentCommand(
  payload: AgentCommandRequest,
  onChunk: (chunk: string) => void,
  signal?: AbortSignal
): Promise<string> {
  return streamRequest(
    "/api/agent/command/stream",
    {
      method: "POST",
      signal,
      body: JSON.stringify(payload)
    },
    onChunk
  );
}

export function fetchAgentThread(taskId: string): Promise<AgentThreadResponse> {
  return request(`/api/agent/thread/${taskId}`);
}

export function clearAgentThread(taskId: string): Promise<{ status: string }> {
  return request(`/api/agent/thread/${taskId}`, { method: "DELETE" });
}

export function fetchAssistantThread(taskId: string): Promise<AgentThreadResponse> {
  return request(`/api/assistant/thread/${taskId}`);
}

export function clearAssistantThread(taskId: string): Promise<{ status: string }> {
  return request(`/api/assistant/thread/${taskId}`, { method: "DELETE" });
}

export function streamAssistantRun(
  payload: AgentCommandRequest,
  signal?: AbortSignal
): AsyncGenerator<AssistantRunEvent, void> {
  return eventStreamRequest<AssistantRunEvent>(
    "/api/assistant/run",
    {
      method: "POST",
      signal,
      body: JSON.stringify(payload)
    }
  );
}

export function searchAgentProblems(query: string, currentTaskId?: string, limit = 8): Promise<AgentProblemSearchResponse> {
  const params = new URLSearchParams();
  params.set("q", query);
  params.set("limit", String(limit));
  if (currentTaskId) params.set("current_task_id", currentTaskId);
  return request(`/api/agent/tools/problem-search?${params.toString()}`);
}
