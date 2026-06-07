import type {
  CoachMessage,
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
  SubmissionHistoryItem,
  SubmissionResponse,
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

export function draftPracticeNote(taskId: string, code: string, submissionId?: number): Promise<PracticeNoteDraftResponse> {
  return request(`/api/problems/${taskId}/note/draft`, {
    method: "POST",
    body: JSON.stringify({ code, submission_id: submissionId })
  });
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

export function streamDiagnose(
  taskId: string,
  code: string,
  submissionId: number | undefined,
  onChunk: (chunk: string) => void,
  signal?: AbortSignal
): Promise<string> {
  return streamRequest(
    "/api/coach/diagnose/stream",
    {
      method: "POST",
      signal,
      body: JSON.stringify({ task_id: taskId, code, submission_id: submissionId })
    },
    onChunk
  );
}

export function streamExplain(taskId: string, onChunk: (chunk: string) => void, signal?: AbortSignal): Promise<string> {
  return streamRequest(
    "/api/coach/explain/stream",
    {
      method: "POST",
      signal,
      body: JSON.stringify({ task_id: taskId })
    },
    onChunk
  );
}

export function fetchCoachThread(taskId: string): Promise<{ messages: CoachMessage[] }> {
  return request(`/api/coach/thread/${taskId}`);
}

export function clearCoachThread(taskId: string): Promise<{ status: string }> {
  return request(`/api/coach/thread/${taskId}`, { method: "DELETE" });
}

export function streamCoachMessage(
  taskId: string,
  message: string,
  code: string,
  submissionId: number | undefined,
  onChunk: (chunk: string) => void,
  signal?: AbortSignal
): Promise<string> {
  return streamRequest(
    "/api/coach/chat/stream",
    {
      method: "POST",
      signal,
      body: JSON.stringify({ task_id: taskId, message, code, submission_id: submissionId })
    },
    onChunk
  );
}
