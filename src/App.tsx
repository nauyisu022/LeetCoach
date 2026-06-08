import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Allotment, setSashSize } from "allotment";
import "allotment/dist/style.css";
import { BookMarked, BookOpen, Brain, Database, PanelLeftOpen } from "lucide-react";
import { CoachPanel } from "./components/CoachPanel";
import { EditorPanel } from "./components/EditorPanel";
import { MemoryPanel } from "./components/MemoryPanel";
import { NotesPanel } from "./components/NotesPanel";
import { ProblemList } from "./components/ProblemList";
import { ProblemPanel } from "./components/ProblemPanel";
import { TestDock } from "./components/TestDock";
import {
  acceptAgentMemory,
  clearCoachThread,
  draftPracticeNote,
  fetchAgentMemories,
  fetchCoachThread,
  fetchProblem,
  fetchProblems,
  fetchProblemTags,
  fetchProgressSummary,
  fetchPracticeNote,
  fetchPracticeInsights,
  fetchPracticeQueue,
  fetchSubmissionHistory,
  fetchTopicMemories,
  rejectAgentMemory,
  reviewPracticeNote,
  runCode,
  savePracticeNote,
  saveSolution,
  streamCoachMessage,
  streamDiagnose,
  streamExplain,
  submitCode,
  updateAgentMemory
} from "./lib/api";
import type {
  AgentMemoryItem,
  CoachMessage,
  CustomTestCase,
  DisplaySubmissionResponse,
  Filters,
  PracticeInsightsResponse,
  PracticeNote,
  PracticeNoteDraftResponse,
  PracticeNoteResponse,
  PracticeNoteSaveRequest,
  PracticeQueueResponse,
  ProblemDetail,
  ProblemTag,
  ProblemSummary,
  ProgressSummary,
  SubmissionHistoryItem,
  SubmissionResponse,
  ThinkingMode,
  TopicMemory
} from "./types/api";

setSashSize(10);

const AUTO_SAVE_DELAY_MS = 5000;
const RUN_CASE_CONCURRENCY = 4;
const FALLBACK_CUSTOM_INPUT = "nums = [2,7,11,15]\ntarget = 9";
const SELECTED_TASK_STORAGE_KEY = "leetcoach:selected-task-id";
const AI_THINKING_STORAGE_KEY = "leetcoach:ai-thinking-mode";

type RunCaseResult = { case: CustomTestCase; response: SubmissionResponse };

function cleanExampleInput(input: string) {
  return input
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/\r\n/g, "\n")
    .trim();
}

function customCasesFromExamples(examples: ProblemDetail["input_output"]): CustomTestCase[] {
  const sourceExamples = examples.length ? examples.slice(0, 4) : [{ input: FALLBACK_CUSTOM_INPUT, output: "" }];
  return sourceExamples.map((example, index) => ({
    id: `case-${index + 1}`,
    name: `用例 ${index + 1}`,
    input: cleanExampleInput(String(example.input ?? FALLBACK_CUSTOM_INPUT)),
    expectedOutput: String(example.output ?? "").trim() || undefined
  }));
}

function aggregateRunResults(taskId: string, caseResults: RunCaseResult[]): DisplaySubmissionResponse {
  const firstFailed = caseResults.find((item) => !item.response.passed);
  const totalRuntime = caseResults.reduce((sum, item) => sum + item.response.runtime_ms, 0);
  const executionValues = caseResults.map((item) => item.response.execution_ms);
  const totalExecution = executionValues.every((value) => value !== null)
    ? executionValues.reduce((sum, value) => sum + (value ?? 0), 0)
    : null;
  const passedCount = caseResults.filter((item) => item.response.passed).length;
  const passed = passedCount === caseResults.length;
  const duration = totalExecution !== null && totalRuntime - totalExecution >= 50
    ? `执行 ${formatMs(totalExecution)} · 总耗时 ${formatMs(totalRuntime)}`
    : `${formatMs(totalExecution ?? totalRuntime)}`;
  return {
    id: null,
    task_id: taskId,
    mode: "run",
    status: passed ? "passed" : "failed",
    title: passed ? "运行通过" : "运行失败",
    summary: `${passedCount}/${caseResults.length} 个自定义用例通过 · ${duration}`,
    passed,
    failed_assertion: firstFailed?.response.failed_assertion ?? null,
    stderr: firstFailed?.response.stderr ?? null,
    stdout: caseResults.length === 1 ? caseResults[0].response.stdout : null,
    return_output: caseResults.length === 1 ? caseResults[0].response.return_output : null,
    runtime_ms: totalRuntime,
    execution_ms: totalExecution,
    test_count_estimate: caseResults.length,
    passed_test_count: passedCount,
    case_results: caseResults
  };
}

function formatMs(value: number) {
  return value <= 0 ? "<1 ms" : `${value} ms`;
}

async function runCustomCasesConcurrently(
  taskId: string,
  code: string,
  casesToRun: CustomTestCase[],
  onProgress: (caseResults: RunCaseResult[]) => void
): Promise<RunCaseResult[]> {
  const caseResults = new Array<RunCaseResult>(casesToRun.length);
  let nextIndex = 0;
  const workerCount = Math.min(RUN_CASE_CONCURRENCY, casesToRun.length);

  async function runWorker() {
    while (nextIndex < casesToRun.length) {
      const index = nextIndex;
      nextIndex += 1;
      const testCase = casesToRun[index];
      const response = await runCode(taskId, code, testCase.input, testCase.expectedOutput);
      caseResults[index] = { case: testCase, response };
      onProgress(caseResults.filter((item): item is RunCaseResult => Boolean(item)));
    }
  }

  await Promise.all(Array.from({ length: workerCount }, runWorker));
  return caseResults;
}

export function App() {
  const [filters, setFilters] = useState<Filters>({});
  const [problems, setProblems] = useState<ProblemSummary[]>([]);
  const [problemTags, setProblemTags] = useState<ProblemTag[]>([]);
  const [progressSummary, setProgressSummary] = useState<ProgressSummary>();
  const [practiceQueue, setPracticeQueue] = useState<PracticeQueueResponse>();
  const [practiceInsights, setPracticeInsights] = useState<PracticeInsightsResponse>();
  const [practiceNoteResponse, setPracticeNoteResponse] = useState<PracticeNoteResponse>();
  const [topicMemories, setTopicMemories] = useState<TopicMemory[]>([]);
  const [agentMemories, setAgentMemories] = useState<AgentMemoryItem[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | undefined>(() => (
    window.localStorage.getItem(SELECTED_TASK_STORAGE_KEY) ?? undefined
  ));
  const [problem, setProblem] = useState<ProblemDetail>();
  const [code, setCode] = useState("");
  const [result, setResult] = useState<DisplaySubmissionResponse>();
  const [submissionHistory, setSubmissionHistory] = useState<SubmissionHistoryItem[]>([]);
  const [isHistoryOpen, setHistoryOpen] = useState(false);
  const [isHistoryLoading, setHistoryLoading] = useState(false);
  const [customCases, setCustomCases] = useState<CustomTestCase[]>(() => customCasesFromExamples([]));
  const [selectedCaseId, setSelectedCaseId] = useState("case-1");
  const [coachMessages, setCoachMessages] = useState<CoachMessage[]>([]);
  const [thinkingMode, setThinkingMode] = useState<ThinkingMode>(() => (
    window.localStorage.getItem(AI_THINKING_STORAGE_KEY) === "disabled" ? "disabled" : "enabled"
  ));
  const [isRunning, setIsRunning] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSavingSolution, setSavingSolution] = useState(false);
  const [isNoteLoading, setNoteLoading] = useState(false);
  const [isSavingNote, setSavingNote] = useState(false);
  const [isDraftingNote, setDraftingNote] = useState(false);
  const [isMemoryLoading, setMemoryLoading] = useState(false);
  const [updatingMemoryId, setUpdatingMemoryId] = useState<number | null>(null);
  const [solutionDirty, setSolutionDirty] = useState(false);
  const [solutionSavedAt, setSolutionSavedAt] = useState<string>();
  const [isCoachLoading, setCoachLoading] = useState(false);
  const [error, setError] = useState<string>();
  const [isProblemDrawerOpen, setProblemDrawerOpen] = useState(false);
  const [learningTab, setLearningTab] = useState<"coach" | "notes" | "memory">("coach");
  const [isCompactLayout, setCompactLayout] = useState(() => window.innerWidth < 1240);
  const testInputRef = useRef<HTMLTextAreaElement | null>(null);
  const draftRef = useRef<{ taskId?: string; code: string; dirty: boolean }>({ code: "", dirty: false });
  const autoSaveTimerRef = useRef<number | undefined>(undefined);
  const saveQueueRef = useRef<Promise<unknown>>(Promise.resolve());
  const coachAbortRef = useRef<AbortController | null>(null);

  const refreshAgentMemoryList = useCallback(async (taskId: string, options?: { showLoading?: boolean }) => {
    if (options?.showLoading) setMemoryLoading(true);
    try {
      const response = await fetchAgentMemories(undefined, taskId);
      setAgentMemories(response.memories);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      if (options?.showLoading) setMemoryLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProblems(filters)
      .then((items) => {
        setProblems(items);
        if (!items.length) return;
        if (!selectedTaskId || !items.some((item) => item.task_id === selectedTaskId)) {
          setSelectedTaskId(items[0].task_id);
        }
      })
      .catch((err: Error) => setError(err.message));
  }, [filters, selectedTaskId]);

  useEffect(() => {
    fetchProblemTags()
      .then(setProblemTags)
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    let isCurrent = true;
    fetchProgressSummary()
      .then((summary) => {
        if (isCurrent) setProgressSummary(summary);
      })
      .catch((err: Error) => {
        if (isCurrent) setError(err.message);
      });

    return () => {
      isCurrent = false;
    };
  }, [result]);

  useEffect(() => {
    if (selectedTaskId) {
      window.localStorage.setItem(SELECTED_TASK_STORAGE_KEY, selectedTaskId);
    } else {
      window.localStorage.removeItem(SELECTED_TASK_STORAGE_KEY);
    }
  }, [selectedTaskId]);

  useEffect(() => {
    window.localStorage.setItem(AI_THINKING_STORAGE_KEY, thinkingMode);
  }, [thinkingMode]);

  useEffect(() => {
    fetchPracticeQueue(filters, selectedTaskId)
      .then(setPracticeQueue)
      .catch((err: Error) => setError(err.message));
  }, [filters, result, selectedTaskId]);

  useEffect(() => {
    fetchPracticeInsights()
      .then(setPracticeInsights)
      .catch((err: Error) => setError(err.message));
  }, [result]);

  useEffect(() => {
    if (!selectedTaskId) {
      setPracticeNoteResponse(undefined);
      setTopicMemories([]);
      return;
    }
    let isCurrent = true;
    setNoteLoading(true);
    Promise.all([fetchPracticeNote(selectedTaskId), fetchTopicMemories()])
      .then(([noteResponse, memoriesResponse]) => {
        if (!isCurrent) return;
        setPracticeNoteResponse(noteResponse);
        setTopicMemories(memoriesResponse.memories);
      })
      .catch((err: Error) => {
        if (isCurrent) setError(err.message);
      })
      .finally(() => {
        if (isCurrent) setNoteLoading(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [result, selectedTaskId]);

  useEffect(() => {
    if (!selectedTaskId) return;
    let isCurrent = true;
    setProblem(undefined);
    setCode("");
    setSolutionSavedAt(undefined);
    setSolutionDirty(false);
    setResult(undefined);
    setSubmissionHistory([]);
    setHistoryOpen(false);
    fetchProblem(selectedTaskId)
      .then((detail) => {
        if (!isCurrent) return;
        const nextCode = detail.saved_solution?.code ?? detail.starter_code;
        setProblem(detail);
        setCode(nextCode);
        setSolutionSavedAt(detail.saved_solution?.updated_at ?? undefined);
        setSolutionDirty(false);
        draftRef.current = { taskId: detail.task_id, code: nextCode, dirty: false };
        const nextCases = customCasesFromExamples(detail.input_output);
        setCustomCases(nextCases);
        setSelectedCaseId(nextCases[0]?.id ?? "case-1");
        setResult(undefined);
        setSubmissionHistory([]);
        setHistoryOpen(false);
      })
      .catch((err: Error) => {
        if (isCurrent) setError(err.message);
      });

    return () => {
      isCurrent = false;
    };
  }, [selectedTaskId]);

  useEffect(() => {
    if (!selectedTaskId) {
      setCoachMessages([]);
      return;
    }
    let isCurrent = true;
    fetchCoachThread(selectedTaskId)
      .then((thread) => {
        if (isCurrent) setCoachMessages(thread.messages ?? []);
      })
      .catch((err: Error) => {
        if (isCurrent) setError(err.message);
      });

    return () => {
      isCurrent = false;
    };
  }, [selectedTaskId]);

  useEffect(() => {
    if (!selectedTaskId) {
      setAgentMemories([]);
      return;
    }
    void refreshAgentMemoryList(selectedTaskId, { showLoading: true });
  }, [refreshAgentMemoryList, selectedTaskId]);

  const progressStats = useMemo(() => ({
    total: progressSummary?.total ?? 0,
    completed: progressSummary?.passed ?? 0,
    todayPassed: progressSummary?.today_passed ?? 0,
    review: progressSummary?.needs_review ?? 0
  }), [progressSummary]);

  useEffect(() => {
    function onResize() {
      setCompactLayout(window.innerWidth < 1240);
    }

    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const persistSolution = useCallback((taskId: string, nextCode: string, options?: { showError?: boolean; showSaving?: boolean }) => {
    const saveTask = saveQueueRef.current
      .catch(() => undefined)
      .then(async () => {
        if (options?.showSaving) setSavingSolution(true);
        try {
          const saved = await saveSolution(taskId, nextCode);
          if (draftRef.current.taskId === taskId && draftRef.current.code === nextCode) {
            draftRef.current.dirty = false;
            setSolutionSavedAt(saved.updated_at);
            setSolutionDirty(false);
          }
          return saved;
        } catch (err) {
          if (options?.showError) setError((err as Error).message);
          throw err;
        } finally {
          if (options?.showSaving) setSavingSolution(false);
        }
      });

    saveQueueRef.current = saveTask.catch(() => undefined);
    return saveTask;
  }, []);

  const handleCodeChange = useCallback((nextCode: string) => {
    setCode(nextCode);
    if (!problem) return;
    draftRef.current = { taskId: problem.task_id, code: nextCode, dirty: true };
    setSolutionDirty(true);
  }, [problem]);

  const handleSaveSolution = useCallback(async () => {
    if (!problem || isSavingSolution) return;
    setError(undefined);
    try {
      await persistSolution(problem.task_id, code, { showError: true, showSaving: true });
    } catch (err) {
      setError((err as Error).message);
    }
  }, [code, isSavingSolution, persistSolution, problem]);

  useEffect(() => {
    if (autoSaveTimerRef.current) window.clearTimeout(autoSaveTimerRef.current);
    if (!problem || !solutionDirty) return;

    const taskId = problem.task_id;
    const nextCode = code;
    autoSaveTimerRef.current = window.setTimeout(() => {
      void persistSolution(taskId, nextCode).catch(() => undefined);
    }, AUTO_SAVE_DELAY_MS);

    return () => {
      if (autoSaveTimerRef.current) window.clearTimeout(autoSaveTimerRef.current);
    };
  }, [code, persistSolution, problem, solutionDirty]);

  useEffect(() => {
    function saveLatestDraft() {
      const draft = draftRef.current;
      if (!draft.taskId || !draft.dirty) return;
      void fetch(`/api/problems/${draft.taskId}/solution`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: draft.code }),
        keepalive: true
      }).catch(() => undefined);
    }

    window.addEventListener("pagehide", saveLatestDraft);
    window.addEventListener("beforeunload", saveLatestDraft);
    return () => {
      window.removeEventListener("pagehide", saveLatestDraft);
      window.removeEventListener("beforeunload", saveLatestDraft);
    };
  }, []);

  const saveDirtyDraftNow = useCallback(async () => {
    const draft = draftRef.current;
    if (!draft.taskId || !draft.dirty) return;
    await persistSolution(draft.taskId, draft.code).catch(() => undefined);
  }, [persistSolution]);

  const handleProblemSelect = useCallback(async (taskId: string) => {
    if (taskId === selectedTaskId) {
      setProblemDrawerOpen(false);
      return;
    }
    await saveDirtyDraftNow();
    setSelectedTaskId(taskId);
    setProblemDrawerOpen(false);
  }, [saveDirtyDraftNow, selectedTaskId]);

  const handleNextPractice = useCallback(async () => {
    const nextTaskId = practiceQueue?.next_task_id;
    if (!nextTaskId) return;
    await handleProblemSelect(nextTaskId);
  }, [handleProblemSelect, practiceQueue]);

  const handleSubmit = useCallback(async () => {
    if (!problem || isRunning || isSubmitting) return;
    setIsSubmitting(true);
    setError(undefined);
    try {
      const response = await submitCode(problem.task_id, code);
      draftRef.current = { taskId: problem.task_id, code, dirty: false };
      setResult(response);
      setHistoryOpen(false);
      setSolutionSavedAt(new Date().toISOString());
      setSolutionDirty(false);
      fetchSubmissionHistory(problem.task_id)
        .then(setSubmissionHistory)
        .catch(() => undefined);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsSubmitting(false);
    }
  }, [code, isRunning, isSubmitting, problem]);

  const handleRun = useCallback(async () => {
    if (!problem || isRunning || isSubmitting) return;
    setIsRunning(true);
    setError(undefined);
    try {
      await saveDirtyDraftNow();
      const runnableCases = customCases.filter((item) => item.input.trim());
      const casesToRun = runnableCases.length ? runnableCases : customCasesFromExamples([]);
      await runCustomCasesConcurrently(problem.task_id, code, casesToRun, (caseResults) => {
        setResult(aggregateRunResults(problem.task_id, caseResults));
      });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsRunning(false);
    }
  }, [code, customCases, isRunning, isSubmitting, problem, saveDirtyDraftNow]);

  const handleCaseInputChange = useCallback((caseId: string, input: string) => {
    setCustomCases((items) => items.map((item) => (item.id === caseId ? { ...item, input, expectedOutput: undefined } : item)));
  }, []);

  const handleCaseAdd = useCallback(() => {
    setCustomCases((items) => {
      const nextIndex = items.length + 1;
      const nextCase = { id: `case-${Date.now()}`, name: `用例 ${nextIndex}`, input: "" };
      setSelectedCaseId(nextCase.id);
      return [...items, nextCase];
    });
  }, []);

  const handleCaseRemove = useCallback((caseId: string) => {
    setCustomCases((items) => {
      if (items.length <= 1) {
        return items.map((item) => (item.id === caseId ? { ...item, input: "" } : item));
      }
      const nextItems = items.filter((item) => item.id !== caseId);
      if (!nextItems.some((item) => item.id === selectedCaseId)) {
        setSelectedCaseId(nextItems[0]?.id ?? "case-1");
      }
      return nextItems.map((item, index) => ({ ...item, name: `用例 ${index + 1}` }));
    });
  }, [selectedCaseId]);

  const handleHistoryToggle = useCallback(async () => {
    if (!problem) return;
    if (isHistoryOpen) {
      setHistoryOpen(false);
      return;
    }
    setHistoryOpen(true);
    setHistoryLoading(true);
    setError(undefined);
    try {
      const items = await fetchSubmissionHistory(problem.task_id);
      setSubmissionHistory(items);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setHistoryLoading(false);
    }
  }, [isHistoryOpen, problem]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && coachAbortRef.current) {
        event.preventDefault();
        coachAbortRef.current.abort();
        return;
      }

      const target = event.target as HTMLElement | null;
      const isCoachInput = Boolean(target?.closest(".coach-panel"));
      const isNotesInput = Boolean(target?.closest(".notes-panel"));
      const isMemoryInput = Boolean(target?.closest(".memory-panel"));
      const isLearningInput = isCoachInput || isNotesInput || isMemoryInput;
      const hasCommandModifier = event.ctrlKey || event.metaKey;
      if (hasCommandModifier && event.key.toLowerCase() === "s") {
        if (isLearningInput) return;
        event.preventDefault();
        void handleSaveSolution();
        return;
      }

      if (!hasCommandModifier || isLearningInput) return;

      if (event.key === "Enter") {
        event.preventDefault();
        void handleSubmit();
      } else if (event.key === "'" || event.key === "\"") {
        event.preventDefault();
        void handleRun();
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handleRun, handleSaveSolution, handleSubmit]);

  function startStreamingCoachTurn(userContent: string) {
    const now = Date.now();
    const userId = -now;
    const assistantId = -(now + 1);
    const createdAt = new Date().toISOString();
    const userMessage: CoachMessage = {
      id: userId,
      role: "user",
      content: userContent,
      created_at: createdAt
    };
    const assistantMessage: CoachMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      created_at: createdAt
    };
    setCoachMessages((items) => [...items, userMessage, assistantMessage]);
    return { userId, assistantId };
  }

  function appendCoachChunk(assistantId: number, chunk: string) {
    setCoachMessages((items) => (
      items.map((item) => (
        item.id === assistantId ? { ...item, content: item.content + chunk } : item
      ))
    ));
  }

  function removeStreamingCoachTurn(userId: number, assistantId: number) {
    setCoachMessages((items) => items.filter((item) => item.id !== userId && item.id !== assistantId));
  }

  function markCoachStopped(assistantId: number) {
    setCoachMessages((items) => (
      items.map((item) => {
        if (item.id !== assistantId) return item;
        return { ...item, content: item.content ? `${item.content}\n\n（已停止）` : "已停止。" };
      })
    ));
  }

  function isAbortError(err: unknown) {
    return err instanceof DOMException && err.name === "AbortError";
  }

  async function handleDiagnose() {
    if (!problem) return;
    setCoachLoading(true);
    setError(undefined);
    const userContent = "请诊断我这次提交为什么失败。";
    const { userId, assistantId } = startStreamingCoachTurn(userContent);
    const controller = new AbortController();
    coachAbortRef.current = controller;
    try {
      await streamDiagnose(
        problem.task_id,
        code,
        result?.id ?? undefined,
        thinkingMode,
        (chunk) => appendCoachChunk(assistantId, chunk),
        controller.signal
      );
      const thread = await fetchCoachThread(problem.task_id);
      setCoachMessages(thread.messages);
      void refreshAgentMemoryList(problem.task_id);
    } catch (err) {
      if (isAbortError(err)) {
        markCoachStopped(assistantId);
      } else {
        setError((err as Error).message);
        removeStreamingCoachTurn(userId, assistantId);
      }
    } finally {
      if (coachAbortRef.current === controller) coachAbortRef.current = null;
      setCoachLoading(false);
    }
  }

  async function handleExplain() {
    if (!problem) return;
    setCoachLoading(true);
    setError(undefined);
    const userContent = "请完整讲解这道题，并总结解法范式。";
    const { userId, assistantId } = startStreamingCoachTurn(userContent);
    const controller = new AbortController();
    coachAbortRef.current = controller;
    try {
      await streamExplain(problem.task_id, thinkingMode, (chunk) => appendCoachChunk(assistantId, chunk), controller.signal);
      const thread = await fetchCoachThread(problem.task_id);
      setCoachMessages(thread.messages);
      void refreshAgentMemoryList(problem.task_id);
    } catch (err) {
      if (isAbortError(err)) {
        markCoachStopped(assistantId);
      } else {
        setError((err as Error).message);
        removeStreamingCoachTurn(userId, assistantId);
      }
    } finally {
      if (coachAbortRef.current === controller) coachAbortRef.current = null;
      setCoachLoading(false);
    }
  }

  async function handleCoachSend(message: string) {
    if (!problem) return;
    setCoachLoading(true);
    setError(undefined);
    const { userId, assistantId } = startStreamingCoachTurn(message);
    const controller = new AbortController();
    coachAbortRef.current = controller;
    try {
      await streamCoachMessage(
        problem.task_id,
        message,
        code,
        result?.id ?? undefined,
        thinkingMode,
        (chunk) => appendCoachChunk(assistantId, chunk),
        controller.signal
      );
      const thread = await fetchCoachThread(problem.task_id);
      setCoachMessages(thread.messages);
      void refreshAgentMemoryList(problem.task_id);
    } catch (err) {
      if (isAbortError(err)) {
        markCoachStopped(assistantId);
      } else {
        setError((err as Error).message);
        removeStreamingCoachTurn(userId, assistantId);
      }
    } finally {
      if (coachAbortRef.current === controller) coachAbortRef.current = null;
      setCoachLoading(false);
    }
  }

  async function handleCoachClear() {
    if (!problem) return;
    setError(undefined);
    try {
      await clearCoachThread(problem.task_id);
      setCoachMessages([]);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const handlePracticeNoteSave = useCallback(async (payload: PracticeNoteSaveRequest): Promise<PracticeNote> => {
    if (!problem) throw new Error("No problem selected");
    setSavingNote(true);
    setError(undefined);
    try {
      const saved = await savePracticeNote(problem.task_id, payload);
      setPracticeNoteResponse((current) => ({
        note: saved,
        suggested_topics: saved.topics.length ? saved.topics : current?.suggested_topics ?? problem.tags
      }));
      fetchTopicMemories()
        .then((response) => setTopicMemories(response.memories))
        .catch(() => undefined);
      return saved;
    } catch (err) {
      setError((err as Error).message);
      throw err;
    } finally {
      setSavingNote(false);
    }
  }, [problem]);

  const handlePracticeNoteDraft = useCallback(async (): Promise<PracticeNoteDraftResponse> => {
    if (!problem) throw new Error("No problem selected");
    setDraftingNote(true);
    setError(undefined);
    try {
      return await draftPracticeNote(problem.task_id, code, result?.id ?? undefined);
    } catch (err) {
      setError((err as Error).message);
      throw err;
    } finally {
      setDraftingNote(false);
    }
  }, [code, problem, result?.id]);

  const handlePracticeNoteReview = useCallback(async (rating: number) => {
    if (!problem) return;
    setError(undefined);
    try {
      await reviewPracticeNote(problem.task_id, rating);
      const noteResponse = await fetchPracticeNote(problem.task_id);
      setPracticeNoteResponse(noteResponse);
      fetchPracticeInsights()
        .then(setPracticeInsights)
        .catch(() => undefined);
    } catch (err) {
      setError((err as Error).message);
      throw err;
    }
  }, [problem]);

  const handleMemoryAccept = useCallback(async (memoryId: number) => {
    if (!problem) return;
    setUpdatingMemoryId(memoryId);
    setError(undefined);
    try {
      await acceptAgentMemory(memoryId);
      await refreshAgentMemoryList(problem.task_id);
    } catch (err) {
      setError((err as Error).message);
      throw err;
    } finally {
      setUpdatingMemoryId(null);
    }
  }, [problem, refreshAgentMemoryList]);

  const handleMemoryReject = useCallback(async (memoryId: number) => {
    if (!problem) return;
    setUpdatingMemoryId(memoryId);
    setError(undefined);
    try {
      await rejectAgentMemory(memoryId);
      await refreshAgentMemoryList(problem.task_id);
    } catch (err) {
      setError((err as Error).message);
      throw err;
    } finally {
      setUpdatingMemoryId(null);
    }
  }, [problem, refreshAgentMemoryList]);

  const handleMemoryArchive = useCallback(async (memoryId: number) => {
    if (!problem) return;
    setUpdatingMemoryId(memoryId);
    setError(undefined);
    try {
      await updateAgentMemory(memoryId, { status: "archived" });
      await refreshAgentMemoryList(problem.task_id);
    } catch (err) {
      setError((err as Error).message);
      throw err;
    } finally {
      setUpdatingMemoryId(null);
    }
  }, [problem, refreshAgentMemoryList]);

  const handleMemorySave = useCallback(async (memoryId: number, content: string) => {
    if (!problem) return;
    setUpdatingMemoryId(memoryId);
    setError(undefined);
    try {
      await updateAgentMemory(memoryId, { content });
      await refreshAgentMemoryList(problem.task_id);
    } catch (err) {
      setError((err as Error).message);
      throw err;
    } finally {
      setUpdatingMemoryId(null);
    }
  }, [problem, refreshAgentMemoryList]);

  const layoutKey = isCompactLayout ? "compact-allotment-v2" : "desktop-allotment-v2";
  const outerSizes = isCompactLayout ? [120, 460, 140] : [520, 760, 420];
  const editorSizes = isCompactLayout ? [180, 280] : [470, 310];

  return (
    <div className="app-shell">
      {isProblemDrawerOpen && (
        <div className="drawer-layer" aria-label="题单抽屉">
          <button className="drawer-backdrop" aria-label="关闭题单" onClick={() => setProblemDrawerOpen(false)} />
          <div className="problem-drawer">
            <ProblemList
              problems={problems}
              problemTags={problemTags}
              practiceQueue={practiceQueue}
              practiceInsights={practiceInsights}
              selectedTaskId={selectedTaskId}
              filters={filters}
              onFiltersChange={setFilters}
              onSelect={(taskId) => void handleProblemSelect(taskId)}
              onNextPractice={() => void handleNextPractice()}
              onClose={() => setProblemDrawerOpen(false)}
            />
          </div>
        </div>
      )}
      <div className="workspace">
        <header className="topbar">
          <div className="topbar-main">
            <button className="icon-button" onClick={() => setProblemDrawerOpen(true)} aria-label="打开题单">
              <PanelLeftOpen size={18} />
            </button>
            <div>
              <strong>LeetCoach</strong>
              <span>本地判题 · AI 讲解 · 进度记录</span>
            </div>
          </div>
          <div className="stats" aria-label="全局进度摘要">
            <span title={`题库总数 ${progressStats.total}`} aria-label={`题库总数 ${progressStats.total}`}>
              <strong>{progressStats.total}</strong>
              <small>总题</small>
            </span>
            <span title={`总共完成 ${progressStats.completed}`} aria-label={`总共完成 ${progressStats.completed}`}>
              <strong>{progressStats.completed}</strong>
              <small>完成</small>
            </span>
            <span title={`今日通过 ${progressStats.todayPassed}`} aria-label={`今日通过 ${progressStats.todayPassed}`}>
              <strong>{progressStats.todayPassed}</strong>
              <small>今日</small>
            </span>
            <span title={`待复习 ${progressStats.review}`} aria-label={`待复习 ${progressStats.review}`}>
              <strong>{progressStats.review}</strong>
              <small>复习</small>
            </span>
          </div>
        </header>
        {error && <div className="error-banner">{error}</div>}
        {!problem && (
          <button className="empty-start" onClick={() => setProblemDrawerOpen(true)}>
            <BookOpen size={18} />
            打开题单开始练习
          </button>
        )}
        <Allotment
          key={layoutKey}
          id={`main-layout-${layoutKey}`}
          className={`work-layout ${isCompactLayout ? "compact" : ""}`}
          defaultSizes={outerSizes}
          minSize={80}
          proportionalLayout={false}
          vertical={isCompactLayout}
        >
          <Allotment.Pane minSize={isCompactLayout ? 120 : 360} preferredSize={isCompactLayout ? 150 : 520}>
            <div className="pane-content">
              <ProblemPanel problem={problem} />
            </div>
          </Allotment.Pane>
          <Allotment.Pane minSize={isCompactLayout ? 360 : 640} preferredSize={isCompactLayout ? 460 : 760}>
            <Allotment
              id={`editor-layout-${layoutKey}`}
              className="editor-layout"
              defaultSizes={editorSizes}
              minSize={80}
              proportionalLayout={false}
              vertical
            >
              <Allotment.Pane minSize={isCompactLayout ? 120 : 320} preferredSize={isCompactLayout ? 180 : 520}>
                <div className="pane-content">
                  <EditorPanel
                    code={code}
                    isSavingSolution={isSavingSolution}
                    solutionDirty={solutionDirty}
                    solutionSavedAt={solutionSavedAt}
                    onCodeChange={handleCodeChange}
                  />
                </div>
              </Allotment.Pane>
              <Allotment.Pane minSize={isCompactLayout ? 220 : 240} preferredSize={isCompactLayout ? 300 : 320}>
                <div className="pane-content">
                  <TestDock
                    result={result}
                    history={submissionHistory}
                    isHistoryOpen={isHistoryOpen}
                    isHistoryLoading={isHistoryLoading}
                    canDiagnose={Boolean(problem && result?.id)}
                    canExecute={Boolean(problem)}
                    isRunning={isRunning}
                    isSubmitting={isSubmitting}
                    customCases={customCases}
                    selectedCaseId={selectedCaseId}
                    testInputRef={testInputRef}
                    onCaseSelect={setSelectedCaseId}
                    onCaseInputChange={handleCaseInputChange}
                    onCaseAdd={handleCaseAdd}
                    onCaseRemove={handleCaseRemove}
                    onDiagnose={handleDiagnose}
                    onRun={handleRun}
                    onSubmit={handleSubmit}
                    onHistoryToggle={handleHistoryToggle}
                  />
                </div>
              </Allotment.Pane>
            </Allotment>
          </Allotment.Pane>
          <Allotment.Pane minSize={isCompactLayout ? 120 : 360} preferredSize={isCompactLayout ? 150 : 420}>
            <div className="pane-content">
              <section className="learning-panel">
                <div className="learning-tabs" role="tablist" aria-label="学习面板">
                  <button
                    className={learningTab === "coach" ? "active" : ""}
                    type="button"
                    role="tab"
                    aria-selected={learningTab === "coach"}
                    onClick={() => setLearningTab("coach")}
                  >
                    <Brain size={15} />
                    AI 教练
                  </button>
	                  <button
	                    className={learningTab === "notes" ? "active" : ""}
	                    type="button"
	                    role="tab"
	                    aria-selected={learningTab === "notes"}
	                    onClick={() => setLearningTab("notes")}
	                  >
	                    <BookMarked size={15} />
	                    Notes
	                  </button>
	                  <button
	                    className={learningTab === "memory" ? "active" : ""}
	                    type="button"
	                    role="tab"
	                    aria-selected={learningTab === "memory"}
	                    onClick={() => setLearningTab("memory")}
	                  >
	                    <Database size={15} />
	                    Memory
	                  </button>
	                </div>
                <div className="learning-content">
                  <div className={`learning-content-pane ${learningTab === "coach" ? "active" : ""}`} aria-hidden={learningTab !== "coach"}>
                    <CoachPanel
                      messages={coachMessages}
                      isLoading={isCoachLoading}
                      onExplain={handleExplain}
	                      onDiagnose={handleDiagnose}
	                      onSend={handleCoachSend}
	                      onClear={handleCoachClear}
	                      thinkingMode={thinkingMode}
	                      onThinkingModeChange={setThinkingMode}
	                    />
                  </div>
                  <div className={`learning-content-pane ${learningTab === "notes" ? "active" : ""}`} aria-hidden={learningTab !== "notes"}>
                    <NotesPanel
                      problem={problem}
                      note={practiceNoteResponse?.note}
                      suggestedTopics={practiceNoteResponse?.suggested_topics ?? problem?.tags ?? []}
                      topicMemories={topicMemories}
                      isLoading={isNoteLoading}
                      isSaving={isSavingNote}
                      isDrafting={isDraftingNote}
                      onSave={handlePracticeNoteSave}
                      onDraft={handlePracticeNoteDraft}
	                      onReview={handlePracticeNoteReview}
	                    />
	                  </div>
	                  <div className={`learning-content-pane ${learningTab === "memory" ? "active" : ""}`} aria-hidden={learningTab !== "memory"}>
	                    <MemoryPanel
	                      problem={problem}
	                      memories={agentMemories}
	                      isLoading={isMemoryLoading}
	                      updatingMemoryId={updatingMemoryId}
	                      onAccept={handleMemoryAccept}
	                      onReject={handleMemoryReject}
	                      onArchive={handleMemoryArchive}
	                      onSave={handleMemorySave}
	                    />
	                  </div>
	                </div>
              </section>
            </div>
          </Allotment.Pane>
        </Allotment>
      </div>
    </div>
  );
}
