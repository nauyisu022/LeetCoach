import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { fetchAssistantThread } from "../lib/api";
import { CoachComposer } from "./assistant/CoachComposer";
import { CoachMessages } from "./assistant/CoachMessages";
import { CoachToolbar } from "./assistant/CoachToolbar";
import { useCoachAssistantRuntime } from "./assistant/coachRuntimeAdapter";
import type { AgentThreadResponse } from "../types/api";
import type { CoachAssistantThreadProps, LoadedThread, PendingRun } from "./assistant/types";

export type { CoachCommandAction } from "./assistant/types";

export function CoachAssistantThread(props: CoachAssistantThreadProps) {
  const { context, onError } = props;
  const queryClient = useQueryClient();
  const [loadedThread, setLoadedThread] = useState<LoadedThread | null>(null);
  const threadQuery = useQuery({
    queryKey: ["assistantThread", context.taskId],
    queryFn: () => fetchAssistantThread(context.taskId!),
    enabled: Boolean(context.taskId),
    staleTime: Infinity
  });

  useEffect(() => {
    if (!context.taskId) {
      setLoadedThread(null);
    }
  }, [context.taskId]);

  useEffect(() => {
    if (threadQuery.error) onError(threadQuery.error.message);
  }, [onError, threadQuery.error]);

  useEffect(() => {
    if (!context.taskId || !threadQuery.data) return;
    setLoadedThread((current) => ({
      taskId: context.taskId!,
      messages: threadQuery.data.messages ?? [],
      version: (current && current.taskId === context.taskId ? current.version : 0) + 1
    }));
  }, [context.taskId, threadQuery.data]);

  if (!context.taskId) {
    return <div className="coach-output"><span>请先选择一道题。</span></div>;
  }

  if (threadQuery.isLoading || !loadedThread || loadedThread.taskId !== context.taskId) {
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
        queryClient.setQueryData<AgentThreadResponse | undefined>(
          ["assistantThread", context.taskId],
          (current) => current ? { ...current, messages } : current
        );
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
  onHtmlVisualModeChange,
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
        onHtmlVisualModeChange={onHtmlVisualModeChange}
        onError={onError}
        onThreadReset={onThreadReset}
        problemLinks={problemLinks}
      />
      <CoachMessages onProblemLinkClick={onProblemLinkClick} problemLinks={problemLinks} />
      <CoachComposer context={context} pendingRunRef={pendingRunRef} onClearPreview={onClearPreview} />
    </AssistantRuntimeProvider>
  );
}
