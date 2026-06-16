import { useCallback, useEffect, useRef, useState } from "react";

export type ProblemSelectionHistoryMode = "push" | "replace" | "none";

export function problemTaskIdFromPath(pathname: string): string | undefined {
  const match = /^\/problems\/([^/?#]+)/.exec(pathname);
  return match ? decodeURIComponent(match[1]) : undefined;
}

function problemPath(taskId: string): string {
  return `/problems/${encodeURIComponent(taskId)}`;
}

function syncProblemUrl(taskId: string | undefined, mode: Exclude<ProblemSelectionHistoryMode, "none">) {
  if (!taskId) return;
  const nextPath = problemPath(taskId);
  if (window.location.pathname === nextPath) return;
  const nextUrl = `${nextPath}${window.location.search}${window.location.hash}`;
  window.history[mode === "replace" ? "replaceState" : "pushState"]({ taskId }, "", nextUrl);
}

export function useProblemSelection(storageKey: string) {
  const [selectedTaskId, setSelectedTaskIdState] = useState<string | undefined>(() => (
    problemTaskIdFromPath(window.location.pathname) ?? window.localStorage.getItem(storageKey) ?? undefined
  ));
  const hasBootstrappedSelectionRef = useRef(Boolean(selectedTaskId));
  const didNormalizeInitialUrlRef = useRef(false);

  const setSelectedTaskId = useCallback((
    taskId: string | undefined,
    historyMode: ProblemSelectionHistoryMode = "push"
  ) => {
    setSelectedTaskIdState(taskId);
    if (historyMode !== "none") {
      syncProblemUrl(taskId, historyMode);
    }
  }, []);

  useEffect(() => {
    if (selectedTaskId) {
      window.localStorage.setItem(storageKey, selectedTaskId);
    } else {
      window.localStorage.removeItem(storageKey);
    }
  }, [selectedTaskId, storageKey]);

  useEffect(() => {
    if (didNormalizeInitialUrlRef.current) return;
    didNormalizeInitialUrlRef.current = true;
    if (selectedTaskId && problemTaskIdFromPath(window.location.pathname) !== selectedTaskId) {
      syncProblemUrl(selectedTaskId, "replace");
    }
  }, [selectedTaskId]);

  return {
    selectedTaskId,
    setSelectedTaskId,
    hasBootstrappedSelectionRef
  };
}
