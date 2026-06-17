import type { MutableRefObject } from "react";
import type { AgentThreadMessage, CoachCurrentResult, HtmlVisualMode, ProblemSummary, ThinkingMode } from "../../types/api";

export type CoachCommandAction = {
  command: string;
  label: string;
  icon: "explain" | "diagnose" | "search";
  defaultMessage?: string;
};

export type PendingRun = {
  command: string;
  message?: string;
  includeCode?: boolean;
  includeResult?: boolean;
};

export type PendingRunRef = MutableRefObject<PendingRun | null>;

export type CoachContext = {
  taskId?: string;
  code: string;
  submissionId?: number;
  currentResult?: CoachCurrentResult;
  thinkingMode: ThinkingMode;
  htmlVisualMode: HtmlVisualMode;
};

export type CoachAssistantThreadProps = {
  context: CoachContext;
  problemLinks: ProblemSummary[];
  commandActions: CoachCommandAction[];
  commandRequest: { id: number; command: string } | null;
  onCommandRequestHandled: (id: number) => void;
  onProblemLinkClick: (taskId: string) => void;
  onPreviewContext: (message?: string) => void;
  onClearPreview: () => void;
  contextPreview: string | null;
  isPreviewLoading: boolean;
  onThinkingModeChange: (mode: ThinkingMode) => void;
  onHtmlVisualModeChange: (mode: HtmlVisualMode) => void;
  onRunComplete: (command: string) => void;
  onError: (message: string) => void;
};

export type LoadedThread = {
  taskId: string;
  messages: AgentThreadMessage[];
  version: number;
};
