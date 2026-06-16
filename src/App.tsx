import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Allotment, setSashSize } from "allotment";
import "allotment/dist/style.css";
import { BookMarked, BookOpen, Brain, Database, PanelLeftOpen } from "lucide-react";
import { CoachPanel, type CoachCommandAction } from "./components/CoachPanel";
import { EditorPanel } from "./components/EditorPanel";
import { MemoryPanel } from "./components/MemoryPanel";
import { NotesPanel } from "./components/NotesPanel";
import { ProblemList } from "./components/ProblemList";
import { ProblemPanel } from "./components/ProblemPanel";
import { RecommendationTrail } from "./components/RecommendationTrail";
import { TestDock } from "./components/TestDock";
import {
  acceptAgentMemory,
  fetchAgentCommands,
  fetchAgentMemories,
  fetchProblem,
  fetchProblems,
  fetchProblemTags,
  fetchProgressSummary,
  fetchPracticeNote,
  fetchPracticeInsights,
  fetchPracticeQueue,
  fetchStudyPlanItems,
  fetchStudyPlans,
  fetchSubmissionHistory,
  fetchTopicMemories,
  previewAgentCommand,
  rejectAgentMemory,
  reviewPracticeNote,
  runCode,
  savePracticeNote,
  streamPracticeNoteDraft,
  submitCode,
  updateAgentMemory
} from "./lib/api";
import {
  useCompactLayout,
  problemTaskIdFromPath,
  useProblemSelection,
  useRecommendationRefresh,
  useSolutionAutosave
} from "./hooks";
import type {
  AgentMemoryItem,
  AgentCommandInfo,
  AgentCommandPreviewResponse,
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
  StudyPlanItemsResponse,
  StudyPlanSummary,
  SubmissionHistoryItem,
  SubmissionResponse,
  ThinkingMode,
  TopicMemory
} from "./types/api";

setSashSize(10);

const RUN_CASE_CONCURRENCY = 4;
const FALLBACK_CUSTOM_INPUT = "nums = [2,7,11,15]\ntarget = 9";
const SELECTED_TASK_STORAGE_KEY = "leetcoach:selected-task-id";
const AI_THINKING_STORAGE_KEY = "leetcoach:ai-thinking-mode";
const ACTIVE_RECOMMENDATION_SOURCE_STORAGE_KEY = "leetcoach:active-recommendation-source-task-id";

const FALLBACK_COACH_COMMANDS: CoachCommandAction[] = [
  { command: "/explain", label: "讲解", icon: "explain", defaultMessage: "讲讲这题的核心思路。" },
  { command: "/diagnose", label: "诊断", icon: "diagnose", defaultMessage: "帮我诊断当前代码/运行结果。" },
  { command: "/search-problems", label: "找题", icon: "search", defaultMessage: "有哪些经典题和同类练习？" }
];

type RunCaseResult = { case: CustomTestCase; response: SubmissionResponse };

function toolbarIcon(value: string | null | undefined): CoachCommandAction["icon"] {
  if (value === "explain" || value === "search" || value === "diagnose") return value;
  return "diagnose";
}

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

function formatAgentPreview(preview: AgentCommandPreviewResponse): string {
  const failureLine = preview.failure_present
    ? `有：${safeInline(preview.failure?.failed_assertion ?? preview.failure?.summary ?? preview.failure?.source)}`
    : "无";
  const toolLines = preview.tool_results.map((tool) => {
    const payloadKeys = Object.keys(tool.payload);
    const suffix = payloadKeys.length ? ` (${payloadKeys.join(", ")})` : "";
    const status = tool.ok ? "ok" : "failed";
    return `- ${tool.name}：${status}${suffix}`;
  });
  const promptSummary = preview.messages
    .map((message, index) => `### ${index + 1}. ${message.role}\n\n${message.content}`)
    .join("\n\n");

  return [
    "## Agent 上下文预览",
    `- 命令：${preview.command}`,
    `- 用户问题：${preview.user_content}`,
    `- Thinking：${preview.thinking_mode ?? "未设置"}`,
    `- 主题：${preview.current_topics.join("、") || "无"}`,
    `- 历史消息：${preview.history_count}`,
    `- 已确认记忆：${preview.memory_count}`,
    `- 当前代码：${preview.code_present ? "有" : "无"}`,
    `- 失败信息：${failureLine}`,
    "",
    "## 工具结果",
    toolLines.length ? toolLines.join("\n") : "- 无",
    "",
    "## Prompt 摘要",
    promptSummary || "无"
  ].join("\n");
}

function safeInline(value: unknown): string {
  const text = value === null || value === undefined ? "" : String(value);
  return text.length <= 160 ? text : `${text.slice(0, 160)}...`;
}

export function App() {
  const [filters, setFilters] = useState<Filters>({});
  const [problems, setProblems] = useState<ProblemSummary[]>([]);
  const [problemTags, setProblemTags] = useState<ProblemTag[]>([]);
  const [studyPlans, setStudyPlans] = useState<StudyPlanSummary[]>([]);
  const [activeStudyPlanSlug, setActiveStudyPlanSlug] = useState<string | undefined>();
  const [activeStudyPlanGroupSlug, setActiveStudyPlanGroupSlug] = useState<string | undefined>();
  const [activeStudyPlanItems, setActiveStudyPlanItems] = useState<StudyPlanItemsResponse>();
  const [progressSummary, setProgressSummary] = useState<ProgressSummary>();
  const [practiceQueue, setPracticeQueue] = useState<PracticeQueueResponse>();
  const [practiceInsights, setPracticeInsights] = useState<PracticeInsightsResponse>();
  const [practiceNoteResponse, setPracticeNoteResponse] = useState<PracticeNoteResponse>();
  const [topicMemories, setTopicMemories] = useState<TopicMemory[]>([]);
  const [agentMemories, setAgentMemories] = useState<AgentMemoryItem[]>([]);
  const [agentCommands, setAgentCommands] = useState<AgentCommandInfo[]>([]);
  const [error, setError] = useState<string>();
  const { activeRecommendationSet, refreshRecommendationForTask } = useRecommendationRefresh({
    storageKey: ACTIVE_RECOMMENDATION_SOURCE_STORAGE_KEY,
    onError: setError
  });
  const { selectedTaskId, setSelectedTaskId, hasBootstrappedSelectionRef } = useProblemSelection(
    SELECTED_TASK_STORAGE_KEY
  );
  const [problem, setProblem] = useState<ProblemDetail>();
  const [code, setCode] = useState("");
  const [result, setResult] = useState<DisplaySubmissionResponse>();
  const [submissionHistory, setSubmissionHistory] = useState<SubmissionHistoryItem[]>([]);
  const [isHistoryOpen, setHistoryOpen] = useState(false);
  const [isHistoryLoading, setHistoryLoading] = useState(false);
  const [customCases, setCustomCases] = useState<CustomTestCase[]>(() => customCasesFromExamples([]));
  const [selectedCaseId, setSelectedCaseId] = useState("case-1");
  const [thinkingMode, setThinkingMode] = useState<ThinkingMode>(() => (
    window.localStorage.getItem(AI_THINKING_STORAGE_KEY) === "disabled" ? "disabled" : "enabled"
  ));
  const [isRunning, setIsRunning] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isNoteLoading, setNoteLoading] = useState(false);
  const [isSavingNote, setSavingNote] = useState(false);
  const [isDraftingNote, setDraftingNote] = useState(false);
  const [isMemoryLoading, setMemoryLoading] = useState(false);
  const [updatingMemoryId, setUpdatingMemoryId] = useState<number | null>(null);
  const [isAgentPreviewLoading, setAgentPreviewLoading] = useState(false);
  const [agentPreview, setAgentPreview] = useState<string | null>(null);
  const [queuedCoachCommand, setQueuedCoachCommand] = useState<{ id: number; command: string } | null>(null);
  const [isProblemDrawerOpen, setProblemDrawerOpen] = useState(false);
  const [learningTab, setLearningTab] = useState<"coach" | "notes" | "memory">("coach");
  const isCompactLayout = useCompactLayout();
  const testInputRef = useRef<HTMLTextAreaElement | null>(null);
  const {
    isSavingSolution,
    solutionDirty,
    solutionSavedAt,
    handleCodeChange,
    handleSaveSolution,
    saveDirtyDraftNow,
    clearSolutionDraft,
    resetSolutionDraft,
    markDraftSaved
  } = useSolutionAutosave({
    problem,
    code,
    setCode,
    onError: setError
  });

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
    let isCurrent = true;
    const request = activeStudyPlanSlug
      ? fetchStudyPlanItems(activeStudyPlanSlug, filters, activeStudyPlanGroupSlug)
      : fetchProblems(filters);
    request
      .then((response) => {
        if (!isCurrent) return;
        const items = Array.isArray(response) ? response : response.items;
        setActiveStudyPlanItems(Array.isArray(response) ? undefined : response);
        setProblems(items);
        const selectableItems = items.filter((item) => item.available !== false);
        if (!hasBootstrappedSelectionRef.current && selectableItems.length) {
          hasBootstrappedSelectionRef.current = true;
          setSelectedTaskId(selectableItems[0].task_id, "replace");
        }
      })
      .catch((err: Error) => {
        if (isCurrent) setError(err.message);
      });
    return () => {
      isCurrent = false;
    };
  }, [activeStudyPlanGroupSlug, activeStudyPlanSlug, filters, hasBootstrappedSelectionRef, setSelectedTaskId]);

  useEffect(() => {
    fetchProblemTags()
      .then(setProblemTags)
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    fetchStudyPlans()
      .then((response) => setStudyPlans(response.plans))
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    let isCurrent = true;
    fetchAgentCommands()
      .then((response) => {
        if (isCurrent) setAgentCommands(response.commands);
      })
      .catch(() => {
        if (isCurrent) setAgentCommands([]);
      });

    return () => {
      isCurrent = false;
    };
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
    setAgentPreview(null);
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
    clearSolutionDraft();
    setResult(undefined);
    setSubmissionHistory([]);
    setHistoryOpen(false);
    fetchProblem(selectedTaskId)
      .then((detail) => {
        if (!isCurrent) return;
        const nextCode = detail.saved_solution?.code ?? detail.starter_code;
        setProblem(detail);
        resetSolutionDraft(detail.task_id, nextCode, detail.saved_solution?.updated_at ?? undefined);
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
  }, [clearSolutionDraft, resetSolutionDraft, selectedTaskId]);

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

  const coachCommandActions = useMemo(() => (
    agentCommands.length
      ? agentCommands
        .filter((command) => command.toolbar_order !== null)
        .sort((left, right) => (left.toolbar_order ?? 0) - (right.toolbar_order ?? 0))
        .map((command) => ({
          command: command.name,
          label: command.display_name ?? command.name,
          icon: toolbarIcon(command.toolbar_icon),
          defaultMessage: command.default_message
        }))
      : FALLBACK_COACH_COMMANDS.map((action) => ({ ...action }))
  ), [agentCommands]);

  const handleProblemSelect = useCallback(async (taskId: string, historyMode: "push" | "replace" | "none" = "push") => {
    if (taskId === selectedTaskId) {
      setProblemDrawerOpen(false);
      return;
    }
    await saveDirtyDraftNow();
    setSelectedTaskId(taskId, historyMode);
    setProblemDrawerOpen(false);
  }, [saveDirtyDraftNow, selectedTaskId, setSelectedTaskId]);

  useEffect(() => {
    function handlePopState() {
      const taskId = problemTaskIdFromPath(window.location.pathname);
      if (!taskId || taskId === selectedTaskId) return;
      void handleProblemSelect(taskId, "none");
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [handleProblemSelect, selectedTaskId]);

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
      setResult(response);
      setHistoryOpen(false);
      markDraftSaved(problem.task_id, code, new Date().toISOString());
      fetchSubmissionHistory(problem.task_id)
        .then(setSubmissionHistory)
        .catch(() => undefined);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsSubmitting(false);
    }
  }, [code, isRunning, isSubmitting, markDraftSaved, problem]);

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

  function handleCoachCommand(command: string) {
    setError(undefined);
    setAgentPreview(null);
    setLearningTab("coach");
    setQueuedCoachCommand({ id: Date.now(), command });
  }

  const handleCoachRunComplete = useCallback((command: string) => {
    if (!problem) return;
    void refreshAgentMemoryList(problem.task_id);
    if (command === "/search-problems") {
      refreshRecommendationForTask(problem.task_id);
    }
  }, [problem, refreshAgentMemoryList, refreshRecommendationForTask]);

  async function handlePreviewAgentContext(message?: string) {
    if (!problem) return;
    setAgentPreviewLoading(true);
    setError(undefined);
    try {
      const trimmed = message?.trim();
      const preview = await previewAgentCommand({
        task_id: problem.task_id,
        command: trimmed ? "auto" : "/diagnose",
        message: trimmed || undefined,
        code,
        submission_id: result?.id ?? undefined,
        current_result: result?.task_id === problem.task_id ? result : undefined,
        thinking_mode: thinkingMode
      });
      setAgentPreview(formatAgentPreview(preview));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setAgentPreviewLoading(false);
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

  const handlePracticeNoteDraft = useCallback(async (onChunk: (chunk: string) => void): Promise<PracticeNoteDraftResponse> => {
    if (!problem) throw new Error("No problem selected");
    setDraftingNote(true);
    setError(undefined);
    try {
      return await streamPracticeNoteDraft(
        problem.task_id,
        code,
        result?.id ?? undefined,
        result?.task_id === problem.task_id ? result : undefined,
        thinkingMode,
        onChunk
      );
    } catch (err) {
      setError((err as Error).message);
      throw err;
    } finally {
      setDraftingNote(false);
    }
  }, [code, problem, result, thinkingMode]);

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
              studyPlans={studyPlans}
              activeStudyPlanSlug={activeStudyPlanSlug}
              activeStudyPlanGroupSlug={activeStudyPlanGroupSlug}
              activeStudyPlanItems={activeStudyPlanItems}
              practiceQueue={practiceQueue}
              practiceInsights={practiceInsights}
              selectedTaskId={selectedTaskId}
              filters={filters}
              onFiltersChange={setFilters}
              onStudyPlanChange={(slug) => {
                setActiveStudyPlanSlug(slug);
                setActiveStudyPlanGroupSlug(undefined);
                setActiveStudyPlanItems(undefined);
              }}
              onStudyPlanGroupChange={setActiveStudyPlanGroupSlug}
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
        <RecommendationTrail
          recommendationSet={activeRecommendationSet}
          selectedTaskId={selectedTaskId}
          onSelect={(taskId) => void handleProblemSelect(taskId)}
        />
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
                    problemTaskId={problem?.task_id}
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
                    onDiagnose={() => handleCoachCommand("/diagnose")}
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
                      taskId={problem?.task_id}
                      code={code}
                      submissionId={result?.id ?? undefined}
                      currentResult={result?.task_id === problem?.task_id ? result : undefined}
                      problemLinks={problems}
                      commandActions={coachCommandActions}
                      commandRequest={queuedCoachCommand}
                      onCommandRequestHandled={(id) => {
                        setQueuedCoachCommand((current) => (current?.id === id ? null : current));
                      }}
                      onProblemLinkClick={(taskId) => void handleProblemSelect(taskId)}
                      onPreviewContext={handlePreviewAgentContext}
                      onClearPreview={() => setAgentPreview(null)}
                      contextPreview={agentPreview}
                      isPreviewLoading={isAgentPreviewLoading}
                      thinkingMode={thinkingMode}
                      onThinkingModeChange={setThinkingMode}
                      onRunComplete={handleCoachRunComplete}
                      onError={setError}
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
