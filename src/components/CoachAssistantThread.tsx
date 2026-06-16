import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useEffect, useRef, useState } from "react";
import { fetchAssistantThread } from "../lib/api";
import { CoachComposer } from "./assistant/CoachComposer";
import { CoachMessages } from "./assistant/CoachMessages";
import { CoachToolbar } from "./assistant/CoachToolbar";
import { useCoachAssistantRuntime } from "./assistant/coachRuntimeAdapter";
import type { CoachAssistantThreadProps, LoadedThread, PendingRun } from "./assistant/types";

export type { CoachCommandAction } from "./assistant/types";

export function CoachAssistantThread(props: CoachAssistantThreadProps) {
  const { context, onError } = props;
  const [loadedThread, setLoadedThread] = useState<LoadedThread | null>(null);
  const [isThreadLoading, setThreadLoading] = useState(false);

  useEffect(() => {
    if (!context.taskId) {
      setLoadedThread(null);
      return;
    }
    let isCurrent = true;
    setThreadLoading(true);
    fetchAssistantThread(context.taskId)
      .then((thread) => {
        if (!isCurrent) return;
        setLoadedThread((current) => ({
          taskId: context.taskId!,
          messages: thread.messages ?? [],
          version: (current && current.taskId === context.taskId ? current.version : 0) + 1
        }));
      })
      .catch((error: Error) => {
        if (isCurrent) onError(error.message);
      })
      .finally(() => {
        if (isCurrent) setThreadLoading(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [context.taskId, onError]);

  if (!context.taskId) {
    return <div className="coach-output"><span>请先选择一道题。</span></div>;
  }

  if (isThreadLoading || !loadedThread || loadedThread.taskId !== context.taskId) {
    return (
      <div className="coach-output">
        <span>Loading...</span>
      </div>
    );
  }

  return (
    <CoachAssistantRuntime
      key={`${loadedThread.taskId}:${loadedThread.version}`}
      {...props}
      initialMessages={loadedThread.messages}
      onThreadReset={(messages) => {
        setLoadedThread((current) => ({
          taskId: context.taskId!,
          messages,
          version: (current?.version ?? 0) + 1
        }));
      }}
    />
  );
}

function CoachAssistantRuntime({
  context,
  initialMessages,
  commandActions,
  problemLinks,
  commandRequest,
  onCommandRequestHandled,
  onProblemLinkClick,
  onPreviewContext,
  onClearPreview,
  contextPreview,
  isPreviewLoading,
  onThinkingModeChange,
  onRunComplete,
  onError,
  onThreadReset
}: CoachAssistantThreadProps & {
  initialMessages: LoadedThread["messages"];
  onThreadReset: (messages: LoadedThread["messages"]) => void;
}) {
  const pendingRunRef = useRef<PendingRun | null>(null);
  const runtime = useCoachAssistantRuntime({
    context,
    pendingRunRef,
    initialMessages,
    onRunComplete,
    onError
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <CoachToolbar
        context={context}
        commandActions={commandActions}
        commandRequest={commandRequest}
        onCommandRequestHandled={onCommandRequestHandled}
        pendingRunRef={pendingRunRef}
        onProblemLinkClick={onProblemLinkClick}
        contextPreview={contextPreview}
        isPreviewLoading={isPreviewLoading}
        onPreviewContext={onPreviewContext}
        onClearPreview={onClearPreview}
        onThinkingModeChange={onThinkingModeChange}
        onError={onError}
        onThreadReset={onThreadReset}
        problemLinks={problemLinks}
      />
      <CoachMessages onProblemLinkClick={onProblemLinkClick} problemLinks={problemLinks} />
      <CoachComposer context={context} pendingRunRef={pendingRunRef} onClearPreview={onClearPreview} />
    </AssistantRuntimeProvider>
  );
}
