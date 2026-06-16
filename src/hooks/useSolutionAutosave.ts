import { type Dispatch, type SetStateAction, useCallback, useEffect, useRef, useState } from "react";
import { saveSolution } from "../lib/api";
import type { ProblemDetail } from "../types/api";

const AUTO_SAVE_DELAY_MS = 5000;

type DraftState = {
  taskId?: string;
  code: string;
  dirty: boolean;
};

type UseSolutionAutosaveOptions = {
  problem?: ProblemDetail;
  code: string;
  setCode: Dispatch<SetStateAction<string>>;
  onError: (message: string | undefined) => void;
};

export function useSolutionAutosave({ problem, code, setCode, onError }: UseSolutionAutosaveOptions) {
  const [isSavingSolution, setSavingSolution] = useState(false);
  const [solutionDirty, setSolutionDirty] = useState(false);
  const [solutionSavedAt, setSolutionSavedAt] = useState<string>();
  const draftRef = useRef<DraftState>({ code: "", dirty: false });
  const autoSaveTimerRef = useRef<number | undefined>(undefined);
  const saveQueueRef = useRef<Promise<unknown>>(Promise.resolve());

  const persistSolution = useCallback((
    taskId: string,
    nextCode: string,
    options?: { showError?: boolean; showSaving?: boolean }
  ) => {
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
          if (options?.showError) onError((err as Error).message);
          throw err;
        } finally {
          if (options?.showSaving) setSavingSolution(false);
        }
      });

    saveQueueRef.current = saveTask.catch(() => undefined);
    return saveTask;
  }, [onError]);

  const handleCodeChange = useCallback((nextCode: string) => {
    setCode(nextCode);
    if (!problem) return;
    draftRef.current = { taskId: problem.task_id, code: nextCode, dirty: true };
    setSolutionDirty(true);
  }, [problem, setCode]);

  const handleSaveSolution = useCallback(async () => {
    if (!problem || isSavingSolution) return;
    onError(undefined);
    try {
      await persistSolution(problem.task_id, code, { showError: true, showSaving: true });
    } catch (err) {
      onError((err as Error).message);
    }
  }, [code, isSavingSolution, onError, persistSolution, problem]);

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

  const clearSolutionDraft = useCallback(() => {
    setCode("");
    setSolutionSavedAt(undefined);
    setSolutionDirty(false);
    draftRef.current = { code: "", dirty: false };
  }, [setCode]);

  const resetSolutionDraft = useCallback((taskId: string, nextCode: string, savedAt?: string) => {
    setCode(nextCode);
    setSolutionSavedAt(savedAt);
    setSolutionDirty(false);
    draftRef.current = { taskId, code: nextCode, dirty: false };
  }, [setCode]);

  const markDraftSaved = useCallback((taskId: string, nextCode: string, savedAt: string) => {
    draftRef.current = { taskId, code: nextCode, dirty: false };
    setSolutionSavedAt(savedAt);
    setSolutionDirty(false);
  }, []);

  return {
    isSavingSolution,
    solutionDirty,
    solutionSavedAt,
    handleCodeChange,
    handleSaveSolution,
    saveDirtyDraftNow,
    clearSolutionDraft,
    resetSolutionDraft,
    markDraftSaved
  };
}
