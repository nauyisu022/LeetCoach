import { useComposer, useThread, useThreadRuntime } from "@assistant-ui/react";
import * as ToggleGroup from "@radix-ui/react-toggle-group";
import * as Tooltip from "@radix-ui/react-tooltip";
import { FileText, Loader2, MessageSquare, Search, Sparkles, Trash2, X } from "lucide-react";
import { useCallback, useEffect } from "react";
import type { ReactNode } from "react";
import { clearAssistantThread } from "../../lib/api";
import type { AgentThreadMessage, HtmlVisualMode, ThinkingMode } from "../../types/api";
import { CoachRichContent } from "../CoachRichContent";
import type { CoachProblemLink } from "../CoachMarkdown";
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
  onHtmlVisualModeChange,
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
  onHtmlVisualModeChange: (mode: HtmlVisualMode) => void;
  onError: (message: string) => void;
  onThreadReset: (messages: AgentThreadMessage[]) => void;
  problemLinks: CoachProblemLink[];
}) {
  const threadRuntime = useThreadRuntime();
  const composerText = useComposer((state) => state.text);
  const isRunning = useThread((state) => state.isRunning);
  const messageCount = useThread((state) => state.messages.length);
  const enabledModes = [
    ...(context.thinkingMode === "enabled" ? ["thinking"] : []),
    ...(context.htmlVisualMode === "enabled" ? ["html"] : [])
  ];

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
        <div className="coach-actions-header">
          <div className="section-title">
            <Sparkles size={16} />
            AI 教练对话
          </div>
          <CoachTooltip label="清空对话">
            <button className="icon-button coach-tool-button" onClick={() => void clearThread()} disabled={isRunning || messageCount === 0} aria-label="清空对话">
              <Trash2 size={15} />
            </button>
          </CoachTooltip>
        </div>

        <ToggleGroup.Root
          className="coach-mode-row"
          type="multiple"
          value={enabledModes}
          onValueChange={(values) => {
            onThinkingModeChange(values.includes("thinking") ? "enabled" : "disabled");
            onHtmlVisualModeChange(values.includes("html") ? "enabled" : "disabled");
          }}
          aria-label="AI 输出模式"
        >
          <CoachTooltip label={context.thinkingMode === "enabled" ? "DeepSeek Thinking 已开启" : "DeepSeek Thinking 已关闭"}>
            <ToggleGroup.Item
              className={`thinking-toggle ${context.thinkingMode === "enabled" ? "active" : ""}`}
              value="thinking"
              aria-label={context.thinkingMode === "enabled" ? "关闭 Thinking" : "开启 Thinking"}
            >
              <Sparkles size={15} />
              {context.thinkingMode === "enabled" ? "Thinking 开" : "Thinking 关"}
            </ToggleGroup.Item>
          </CoachTooltip>
          <CoachTooltip label={context.htmlVisualMode === "enabled" ? "HTML 可视化已开启；请求会自动注入输出规范" : "HTML 可视化已关闭"}>
            <ToggleGroup.Item
              className={`thinking-toggle html-visual-toggle ${context.htmlVisualMode === "enabled" ? "active" : ""}`}
              value="html"
              aria-label={context.htmlVisualMode === "enabled" ? "关闭 HTML 可视化" : "开启 HTML 可视化"}
            >
              <FileText size={15} />
              {context.htmlVisualMode === "enabled" ? "HTML 开" : "HTML 关"}
            </ToggleGroup.Item>
          </CoachTooltip>
        </ToggleGroup.Root>

        <div className="coach-command-row">
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
        </div>
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

function CoachTooltip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content className="coach-tooltip" side="bottom" sideOffset={6}>
          {label}
          <Tooltip.Arrow className="coach-tooltip-arrow" />
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
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
  return (
    <article className="agent-preview">
      <div className="agent-preview-header">
        <span>Agent Preview</span>
        <button className="icon-button" type="button" onClick={onClearPreview} aria-label="关闭上下文预览">
          <X size={15} />
        </button>
      </div>
      <div className="markdown-body">
        <CoachRichContent markdown={markdown} onProblemLinkClick={onProblemLinkClick} problemLinks={problemLinks} />
      </div>
    </article>
  );
}
