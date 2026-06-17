import { CoachAssistantThread, type CoachCommandAction } from "./CoachAssistantThread";
import type { CoachCurrentResult, HtmlVisualMode, ProblemSummary, ThinkingMode } from "../types/api";

export type { CoachCommandAction };

type Props = {
  taskId?: string;
  code: string;
  submissionId?: number;
  currentResult?: CoachCurrentResult;
  problemLinks: ProblemSummary[];
  commandActions: CoachCommandAction[];
  commandRequest: { id: number; command: string } | null;
  onCommandRequestHandled: (id: number) => void;
  onProblemLinkClick: (taskId: string) => void;
  onPreviewContext: (message?: string) => void;
  onClearPreview: () => void;
  contextPreview: string | null;
  isPreviewLoading: boolean;
  thinkingMode: ThinkingMode;
  onThinkingModeChange: (mode: ThinkingMode) => void;
  htmlVisualMode: HtmlVisualMode;
  onHtmlVisualModeChange: (mode: HtmlVisualMode) => void;
  onRunComplete: (command: string) => void;
  onError: (message: string) => void;
};

export function CoachPanel({
  taskId,
  code,
  submissionId,
  currentResult,
  problemLinks,
  commandActions,
  commandRequest,
  onCommandRequestHandled,
  onProblemLinkClick,
  onPreviewContext,
  onClearPreview,
  contextPreview,
  isPreviewLoading,
  thinkingMode,
  onThinkingModeChange,
  htmlVisualMode,
  onHtmlVisualModeChange,
  onRunComplete,
  onError
}: Props) {
  return (
    <section className="coach-panel">
      <CoachAssistantThread
        context={{ taskId, code, submissionId, currentResult, thinkingMode, htmlVisualMode }}
        problemLinks={problemLinks}
        commandActions={commandActions}
        commandRequest={commandRequest}
        onCommandRequestHandled={onCommandRequestHandled}
        onProblemLinkClick={onProblemLinkClick}
        onPreviewContext={onPreviewContext}
        onClearPreview={onClearPreview}
        contextPreview={contextPreview}
        isPreviewLoading={isPreviewLoading}
        onThinkingModeChange={onThinkingModeChange}
        onHtmlVisualModeChange={onHtmlVisualModeChange}
        onRunComplete={onRunComplete}
        onError={onError}
      />
    </section>
  );
}
