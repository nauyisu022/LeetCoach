import { useComposer, useThread, useThreadRuntime } from "@assistant-ui/react";
import { FileText, Loader2, MessageSquare, Search, Sparkles, Trash2, X } from "lucide-react";
import { useCallback, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { clearAssistantThread } from "../../lib/api";
import type { AgentThreadMessage, ThinkingMode } from "../../types/api";
import { useCoachMarkdownComponents, type CoachProblemLink } from "../CoachMarkdown";
import { createPendingRun } from "./coachRuntimeAdapter";
import type { CoachCommandAction, CoachContext, PendingRunRef } from "./types";

function commandIcon(icon: CoachCommandAction["icon"]) {
  if (icon === "explain") return <FileText size={15} />;
  if (icon === "search") return <Search size={15} />;
  return <MessageSquare size={15} />;
}

export function CoachToolbar({
  context,
  commandActions,
  commandRequest,
  onCommandRequestHandled,
  pendingRunRef,
  onProblemLinkClick,
  contextPreview,
  isPreviewLoading,
  onPreviewContext,
  onClearPreview,
  onThinkingModeChange,
  onError,
  onThreadReset,
  problemLinks
}: {
  context: CoachContext;
  commandActions: CoachCommandAction[];
  commandRequest: { id: number; command: string } | null;
  onCommandRequestHandled: (id: number) => void;
  pendingRunRef: PendingRunRef;
  onProblemLinkClick: (taskId: string) => void;
  contextPreview: string | null;
  isPreviewLoading: boolean;
  onPreviewContext: (message?: string) => void;
  onClearPreview: () => void;
  onThinkingModeChange: (mode: ThinkingMode) => void;
  onError: (message: string) => void;
  onThreadReset: (messages: AgentThreadMessage[]) => void;
  problemLinks: CoachProblemLink[];
}) {
  const threadRuntime = useThreadRuntime();
  const composerText = useComposer((state) => state.text);
  const isRunning = useThread((state) => state.isRunning);
  const messageCount = useThread((state) => state.messages.length);

  async function clearThread() {
    if (!context.taskId || isRunning || messageCount === 0) return;
    try {
      await clearAssistantThread(context.taskId);
      onThreadReset([]);
    } catch (error) {
      onError((error as Error).message);
    }
  }

  const runCommand = useCallback((action: CoachCommandAction) => {
    const userContent = action.defaultMessage ?? (action.command === "/search-problems" ? "有哪些经典题和同类练习？" : action.command);
    pendingRunRef.current = createPendingRun(action.command, userContent);
    onClearPreview();
    threadRuntime.append(userContent);
  }, [onClearPreview, pendingRunRef, threadRuntime]);

  useEffect(() => {
    if (!commandRequest || isRunning) return;
    const action = commandActions.find((item) => item.command === commandRequest.command);
    if (!action) {
      onCommandRequestHandled(commandRequest.id);
      return;
    }
    runCommand(action);
    onCommandRequestHandled(commandRequest.id);
  }, [commandActions, commandRequest, isRunning, onCommandRequestHandled, runCommand]);

  return (
    <>
      <div className="coach-actions">
        <div className="section-title">
          <Sparkles size={16} />
          AI 教练对话
        </div>
        {commandActions.map((action) => (
          <button
            className="ghost-button"
            key={action.command}
            onClick={() => runCommand(action)}
            disabled={isRunning}
          >
            {commandIcon(action.icon)}
            {action.label}
          </button>
        ))}
        <button
          className="ghost-button"
          onClick={() => onPreviewContext(composerText.trim() || undefined)}
          disabled={isRunning || isPreviewLoading}
        >
          {isPreviewLoading ? <Loader2 className="spin" size={15} /> : <FileText size={15} />}
          预览
        </button>
        <button className="icon-button coach-tool-button" onClick={() => void clearThread()} disabled={isRunning || messageCount === 0} title="清空对话" aria-label="清空对话">
          <Trash2 size={15} />
        </button>
        <button
          className={`thinking-toggle ${context.thinkingMode === "enabled" ? "active" : ""}`}
          type="button"
          onClick={() => onThinkingModeChange(context.thinkingMode === "enabled" ? "disabled" : "enabled")}
          aria-pressed={context.thinkingMode === "enabled"}
          title={context.thinkingMode === "enabled" ? "DeepSeek Thinking 已开启" : "DeepSeek Thinking 已关闭"}
        >
          <Sparkles size={15} />
          {context.thinkingMode === "enabled" ? "Thinking 开" : "Thinking 关"}
        </button>
      </div>
      {contextPreview && (
        <CoachPreview
          markdown={contextPreview}
          onClearPreview={onClearPreview}
          onProblemLinkClick={onProblemLinkClick}
          problemLinks={problemLinks}
        />
      )}
    </>
  );
}

function CoachPreview({
  markdown,
  onClearPreview,
  onProblemLinkClick,
  problemLinks
}: {
  markdown: string;
  onClearPreview: () => void;
  onProblemLinkClick: (taskId: string) => void;
  problemLinks: CoachProblemLink[];
}) {
  const markdownComponents = useCoachMarkdownComponents(onProblemLinkClick, problemLinks);
  return (
    <article className="agent-preview">
      <div className="agent-preview-header">
        <span>Agent Preview</span>
        <button className="icon-button" type="button" onClick={onClearPreview} aria-label="关闭上下文预览">
          <X size={15} />
        </button>
      </div>
      <div className="markdown-body">
        <ReactMarkdown components={markdownComponents} remarkPlugins={[remarkGfm]}>
          {markdown}
        </ReactMarkdown>
      </div>
    </article>
  );
}
