import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Tabs from "@radix-ui/react-tabs";
import { Group, Panel, Separator } from "react-resizable-panels";
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
  AgentCommandInfo,
  AgentCommandPreviewResponse,
  CustomTestCase,
  DisplaySubmissionResponse,
  Filters,
  PracticeNote,
  PracticeNoteDraftResponse,
  PracticeNoteResponse,
  PracticeNoteSaveRequest,
  ProblemDetail,
  ProblemSummary,
  StudyPlanItemsResponse,
  SubmissionResponse,
  HtmlVisualMode,
  ThinkingMode
} from "./types/api";

const RUN_CASE_CONCURRENCY = 4;
const FALLBACK_CUSTOM_INPUT = "nums = [2,7,11,15]\ntarget = 9";
const SELECTED_TASK_STORAGE_KEY = "leetcoach:selected-task-id";
const AI_THINKING_STORAGE_KEY = "leetcoach:ai-thinking-mode";
const AI_HTML_VISUAL_STORAGE_KEY = "leetcoach:ai-html-visual-mode";
const ACTIVE_RECOMMENDATION_SOURCE_STORAGE_KEY = "leetcoach:active-recommendation-source-task-id";
const EMPTY_PROBLEMS: ProblemSummary[] = [];

const FALLBACK_COACH_COMMANDS: CoachCommandAction[] = [
  { command: "/explain", label: "讲解", icon: "explain", defaultMessage: "讲讲这题的核心思路。" },
  { command: "/diagnose", label: "诊断", icon: "diagnose", defaultMessage: "帮我诊断当前代码/运行结果。" },
  { command: "/search-problems", label: "找题", icon: "search", defaultMessage: "有哪些经典题和同类练习？" }
];

type RunCaseResult = { case: CustomTestCase; response: SubmissionResponse };

function isStudyPlanItemsResponse(
  value: ProblemSummary[] | StudyPlanItemsResponse | undefined
): value is StudyPlanItemsResponse {
  return Boolean(value) && !Array.isArray(value);
}

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
    `- HTML 可视化：${preview.html_visual_mode ?? "disabled"}`,
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
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<Filters>({});
  const [activeStudyPlanSlug, setActiveStudyPlanSlug] = useState<string | undefined>();
  const [activeStudyPlanGroupSlug, setActiveStudyPlanGroupSlug] = useState<string | undefined>();
  const [error, setError] = useState<string>();
  const { activeRecommendationSet, refreshRecommendationForTask } = useRecommendationRefresh({
    storageKey: ACTIVE_RECOMMENDATION_SOURCE_STORAGE_KEY,
    onError: setError
  });
  const { selectedTaskId, setSelectedTaskId, hasBootstrappedSelectionRef } = useProblemSelection(
    SELECTED_TASK_STORAGE_KEY
  );
  const [code, setCode] = useState("");
  const [result, setResult] = useState<DisplaySubmissionResponse>();
  const [isHistoryOpen, setHistoryOpen] = useState(false);
  const [customCases, setCustomCases] = useState<CustomTestCase[]>(() => customCasesFromExamples([]));
  const [selectedCaseId, setSelectedCaseId] = useState("case-1");
  const [thinkingMode, setThinkingMode] = useState<ThinkingMode>(() => (
    window.localStorage.getItem(AI_THINKING_STORAGE_KEY) === "disabled" ? "disabled" : "enabled"
  ));
  const [htmlVisualMode, setHtmlVisualMode] = useState<HtmlVisualMode>(() => (
    window.localStorage.getItem(AI_HTML_VISUAL_STORAGE_KEY) === "enabled" ? "enabled" : "disabled"
  ));
  const [isRunning, setIsRunning] = useState(false);
  const [isDraftingNote, setDraftingNote] = useState(false);
  const [updatingMemoryId, setUpdatingMemoryId] = useState<number | null>(null);
  const [isAgentPreviewLoading, setAgentPreviewLoading] = useState(false);
  const [agentPreview, setAgentPreview] = useState<string | null>(null);
  const [queuedCoachCommand, setQueuedCoachCommand] = useState<{ id: number; command: string } | null>(null);
  const [isProblemDrawerOpen, setProblemDrawerOpen] = useState(false);
  const [learningTab, setLearningTab] = useState<"coach" | "notes" | "memory">("coach");
  const isCompactLayout = useCompactLayout();
  const testInputRef = useRef<HTMLTextAreaElement | null>(null);
  const appliedProblemTaskIdRef = useRef<string | null>(null);
  const problemTagsQuery = useQuery({
    queryKey: ["problemTags"],
    queryFn: fetchProblemTags
  });
  const studyPlansQuery = useQuery({
    queryKey: ["studyPlans"],
    queryFn: fetchStudyPlans
  });
  const agentCommandsQuery = useQuery({
    queryKey: ["agentCommands"],
    queryFn: fetchAgentCommands,
    retry: false
  });
  const problemListQuery = useQuery<ProblemSummary[] | StudyPlanItemsResponse>({
    queryKey: ["problemList", filters, activeStudyPlanSlug, activeStudyPlanGroupSlug],
    queryFn: () => (
      activeStudyPlanSlug
        ? fetchStudyPlanItems(activeStudyPlanSlug, filters, activeStudyPlanGroupSlug)
        : fetchProblems(filters)
    )
  });
  const problemQuery = useQuery({
    queryKey: ["problem", selectedTaskId],
    queryFn: () => fetchProblem(selectedTaskId!),
    enabled: Boolean(selectedTaskId),
    staleTime: Infinity,
    refetchOnWindowFocus: false
  });
  const progressSummaryQuery = useQuery({
    queryKey: ["progressSummary"],
    queryFn: fetchProgressSummary
  });
  const practiceQueueQuery = useQuery({
    queryKey: ["practiceQueue", filters, selectedTaskId],
    queryFn: () => fetchPracticeQueue(filters, selectedTaskId)
  });
  const practiceInsightsQuery = useQuery({
    queryKey: ["practiceInsights"],
    queryFn: fetchPracticeInsights
  });
  const practiceNoteQuery = useQuery({
    queryKey: ["practiceNote", selectedTaskId],
    queryFn: () => fetchPracticeNote(selectedTaskId!),
    enabled: Boolean(selectedTaskId)
  });
  const topicMemoriesQuery = useQuery({
    queryKey: ["topicMemories"],
    queryFn: fetchTopicMemories
  });
  const agentMemoriesQuery = useQuery({
    queryKey: ["agentMemories", selectedTaskId],
    queryFn: () => fetchAgentMemories(undefined, selectedTaskId),
    enabled: Boolean(selectedTaskId)
  });
  const submissionHistoryQuery = useQuery({
    queryKey: ["submissionHistory", problemQuery.data?.task_id],
    queryFn: () => fetchSubmissionHistory(problemQuery.data!.task_id),
    enabled: Boolean(problemQuery.data && isHistoryOpen)
  });
  const problemListData = problemListQuery.data;
  const activeStudyPlanItems = isStudyPlanItemsResponse(problemListData) ? problemListData : undefined;
  const problems = useMemo(() => {
    if (!problemListData) return EMPTY_PROBLEMS;
    return Array.isArray(problemListData) ? problemListData : problemListData.items;
  }, [problemListData]);
  const problem = problemQuery.data;
  const problemTags = problemTagsQuery.data ?? [];
  const studyPlans = studyPlansQuery.data?.plans ?? [];
  const progressSummary = progressSummaryQuery.data;
  const practiceQueue = practiceQueueQuery.data;
  const practiceInsights = practiceInsightsQuery.data;
  const practiceNoteResponse = practiceNoteQuery.data;
  const topicMemories = topicMemoriesQuery.data?.memories ?? [];
  const agentCommands: AgentCommandInfo[] = useMemo(
    () => agentCommandsQuery.data?.commands ?? [],
    [agentCommandsQuery.data]
  );
  const agentMemories = selectedTaskId ? agentMemoriesQuery.data?.memories ?? [] : [];
  const isMemoryLoading = agentMemoriesQuery.isFetching;
  const submissionHistory = isHistoryOpen ? submissionHistoryQuery.data ?? [] : [];
  const isHistoryLoading = isHistoryOpen && submissionHistoryQuery.isFetching;
  const isNoteLoading = practiceNoteQuery.isFetching || topicMemoriesQuery.isFetching;
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

  const queryError = problemTagsQuery.error
    ?? studyPlansQuery.error
    ?? problemListQuery.error
    ?? problemQuery.error
    ?? progressSummaryQuery.error
    ?? practiceQueueQuery.error
    ?? practiceInsightsQuery.error
    ?? practiceNoteQuery.error
    ?? topicMemoriesQuery.error
    ?? submissionHistoryQuery.error
    ?? agentMemoriesQuery.error;

  const submitMutation = useMutation({
    mutationFn: ({ taskId, solutionCode }: { taskId: string; solutionCode: string }) => (
      submitCode(taskId, solutionCode)
    ),
    onSuccess: (response, variables) => {
      setResult(response);
      setHistoryOpen(false);
      markDraftSaved(variables.taskId, variables.solutionCode, new Date().toISOString());
      void queryClient.invalidateQueries({ queryKey: ["submissionHistory", variables.taskId] });
    }
  });
  const isSubmitting = submitMutation.isPending;

  const savePracticeNoteMutation = useMutation({
    mutationFn: ({
      taskId,
      payload
    }: {
      taskId: string;
      payload: PracticeNoteSaveRequest;
      fallbackTopics: string[];
    }) => savePracticeNote(taskId, payload),
    onSuccess: (saved, variables) => {
      queryClient.setQueryData<PracticeNoteResponse>(
        ["practiceNote", variables.taskId],
        (current) => ({
          note: saved,
          suggested_topics: saved.topics.length ? saved.topics : current?.suggested_topics ?? variables.fallbackTopics
        })
      );
      void queryClient.invalidateQueries({ queryKey: ["topicMemories"] });
    }
  });
  const isSavingNote = savePracticeNoteMutation.isPending;

  const reviewPracticeNoteMutation = useMutation({
    mutationFn: ({ taskId, rating }: { taskId: string; rating: number }) => reviewPracticeNote(taskId, rating),
    onSuccess: (_response, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["practiceNote", variables.taskId] });
      void queryClient.invalidateQueries({ queryKey: ["practiceInsights"] });
    }
  });

  const memoryMutation = useMutation({
    mutationFn: async ({
      memoryId,
      action,
      content
    }: {
      memoryId: number;
      taskId: string;
      action: "accept" | "reject" | "archive" | "save";
      content?: string;
    }) => {
      if (action === "accept") return acceptAgentMemory(memoryId);
      if (action === "reject") return rejectAgentMemory(memoryId);
      if (action === "archive") return updateAgentMemory(memoryId, { status: "archived" });
      return updateAgentMemory(memoryId, { content: content ?? "" });
    },
    onMutate: (variables) => {
      setUpdatingMemoryId(variables.memoryId);
    },
    onSuccess: (_response, variables) => {
      void refreshAgentMemoryList(variables.taskId);
    },
    onSettled: () => {
      setUpdatingMemoryId(null);
    }
  });

  const refreshAgentMemoryList = useCallback(async (taskId: string) => {
    await queryClient.invalidateQueries({ queryKey: ["agentMemories", taskId] });
  }, [queryClient]);

  useEffect(() => {
    const selectableItems = problems.filter((item) => item.available !== false);
    if (!hasBootstrappedSelectionRef.current && selectableItems.length) {
      hasBootstrappedSelectionRef.current = true;
      setSelectedTaskId(selectableItems[0].task_id, "replace");
    }
  }, [hasBootstrappedSelectionRef, problems, setSelectedTaskId]);

  useEffect(() => {
    if (queryError) setError(queryError.message);
  }, [queryError]);

  useEffect(() => {
    setAgentPreview(null);
  }, [selectedTaskId]);

  useEffect(() => {
    window.localStorage.setItem(AI_THINKING_STORAGE_KEY, thinkingMode);
  }, [thinkingMode]);

  useEffect(() => {
    window.localStorage.setItem(AI_HTML_VISUAL_STORAGE_KEY, htmlVisualMode);
  }, [htmlVisualMode]);

  useEffect(() => {
    if (!result) return;
    void queryClient.invalidateQueries({ queryKey: ["progressSummary"] });
    void queryClient.invalidateQueries({ queryKey: ["practiceQueue"] });
    void queryClient.invalidateQueries({ queryKey: ["practiceInsights"] });
    if (selectedTaskId) {
      void queryClient.invalidateQueries({ queryKey: ["practiceNote", selectedTaskId] });
    }
    void queryClient.invalidateQueries({ queryKey: ["topicMemories"] });
  }, [queryClient, result, selectedTaskId]);

  useEffect(() => {
    appliedProblemTaskIdRef.current = null;
    clearSolutionDraft();
    setResult(undefined);
    setHistoryOpen(false);
    setCustomCases(customCasesFromExamples([]));
    setSelectedCaseId("case-1");
  }, [clearSolutionDraft, selectedTaskId]);

  useEffect(() => {
    if (!problem || appliedProblemTaskIdRef.current === problem.task_id) return;
    appliedProblemTaskIdRef.current = problem.task_id;
    const nextCode = problem.saved_solution?.code ?? problem.starter_code;
    resetSolutionDraft(problem.task_id, nextCode, problem.saved_solution?.updated_at ?? undefined);
    const nextCases = customCasesFromExamples(problem.input_output);
    setCustomCases(nextCases);
    setSelectedCaseId(nextCases[0]?.id ?? "case-1");
    setResult(undefined);
    setHistoryOpen(false);
  }, [problem, resetSolutionDraft]);

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
    setError(undefined);
    try {
      await submitMutation.mutateAsync({ taskId: problem.task_id, solutionCode: code });
    } catch (err) {
      setError((err as Error).message);
    }
  }, [code, isRunning, isSubmitting, problem, submitMutation]);

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
    setError(undefined);
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
        thinking_mode: thinkingMode,
        html_visual_mode: htmlVisualMode
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
    setError(undefined);
    try {
      return await savePracticeNoteMutation.mutateAsync({
        taskId: problem.task_id,
        payload,
        fallbackTopics: problem.tags
      });
    } catch (err) {
      setError((err as Error).message);
      throw err;
    }
  }, [problem, savePracticeNoteMutation]);

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
      await reviewPracticeNoteMutation.mutateAsync({ taskId: problem.task_id, rating });
    } catch (err) {
      setError((err as Error).message);
      throw err;
    }
  }, [problem, reviewPracticeNoteMutation]);

  const handleMemoryAccept = useCallback(async (memoryId: number) => {
    if (!problem) return;
    setError(undefined);
    try {
      await memoryMutation.mutateAsync({ memoryId, taskId: problem.task_id, action: "accept" });
    } catch (err) {
      setError((err as Error).message);
      throw err;
    }
  }, [memoryMutation, problem]);

  const handleMemoryReject = useCallback(async (memoryId: number) => {
    if (!problem) return;
    setError(undefined);
    try {
      await memoryMutation.mutateAsync({ memoryId, taskId: problem.task_id, action: "reject" });
    } catch (err) {
      setError((err as Error).message);
      throw err;
    }
  }, [memoryMutation, problem]);

  const handleMemoryArchive = useCallback(async (memoryId: number) => {
    if (!problem) return;
    setError(undefined);
    try {
      await memoryMutation.mutateAsync({ memoryId, taskId: problem.task_id, action: "archive" });
    } catch (err) {
      setError((err as Error).message);
      throw err;
    }
  }, [memoryMutation, problem]);

  const handleMemorySave = useCallback(async (memoryId: number, content: string) => {
    if (!problem) return;
    setError(undefined);
    try {
      await memoryMutation.mutateAsync({ memoryId, taskId: problem.task_id, action: "save", content });
    } catch (err) {
      setError((err as Error).message);
      throw err;
    }
  }, [memoryMutation, problem]);

  const layoutKey = isCompactLayout ? "compact-resizable-v1" : "desktop-resizable-v1";

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
        <Group
          key={layoutKey}
          id={`main-layout-${layoutKey}`}
          className={`work-layout ${isCompactLayout ? "compact" : ""}`}
          orientation={isCompactLayout ? "vertical" : "horizontal"}
        >
          <Panel id="problem" minSize={isCompactLayout ? "80px" : "280px"} defaultSize={isCompactLayout ? "100px" : "340px"}>
            <div className="pane-content">
              <ProblemPanel problem={problem} />
            </div>
          </Panel>
          <Separator className="resize-handle" />
          <Panel id="workspace" minSize={isCompactLayout ? "260px" : "520px"} defaultSize={isCompactLayout ? "300px" : "600px"}>
            <Group
              id={`editor-layout-${layoutKey}`}
              className="editor-layout"
              orientation="vertical"
            >
              <Panel id="editor" minSize={isCompactLayout ? "90px" : "320px"} defaultSize={isCompactLayout ? "160px" : "520px"}>
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
              </Panel>
              <Separator className="resize-handle" />
              <Panel id="tests" minSize={isCompactLayout ? "120px" : "240px"} defaultSize={isCompactLayout ? "140px" : "320px"}>
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
              </Panel>
            </Group>
          </Panel>
          <Separator className="resize-handle" />
          <Panel id="learning" minSize={isCompactLayout ? "220px" : "260px"} defaultSize={isCompactLayout ? "260px" : "300px"}>
            <div className="pane-content">
              <Tabs.Root
                className="learning-panel"
                value={learningTab}
                onValueChange={(value) => setLearningTab(value as "coach" | "notes" | "memory")}
              >
                <Tabs.List className="learning-tabs" aria-label="学习面板">
                  <Tabs.Trigger value="coach">
                    <Brain size={15} />
                    AI 教练
                  </Tabs.Trigger>
                  <Tabs.Trigger value="notes">
                    <BookMarked size={15} />
                    Notes
                  </Tabs.Trigger>
                  <Tabs.Trigger value="memory">
                    <Database size={15} />
                    Memory
                  </Tabs.Trigger>
                </Tabs.List>
                <div className="learning-content">
                  <Tabs.Content className="learning-content-pane" value="coach" forceMount>
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
                      htmlVisualMode={htmlVisualMode}
                      onHtmlVisualModeChange={setHtmlVisualMode}
                      onRunComplete={handleCoachRunComplete}
                      onError={setError}
                    />
                  </Tabs.Content>
                  <Tabs.Content className="learning-content-pane" value="notes" forceMount>
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
                  </Tabs.Content>
                  <Tabs.Content className="learning-content-pane" value="memory" forceMount>
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
                  </Tabs.Content>
                </div>
              </Tabs.Root>
            </div>
          </Panel>
        </Group>
      </div>
    </div>
  );
}
