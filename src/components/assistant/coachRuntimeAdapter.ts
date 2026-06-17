import {
  type ChatModelAdapter,
  type ChatModelRunResult,
  type ThreadMessage,
  type ThreadMessageLike,
  useLocalRuntime
} from "@assistant-ui/react";
import { useMemo } from "react";
import { streamAssistantRun } from "../../lib/api";
import type { AgentCommandRequest, AgentThreadMessage } from "../../types/api";
import type { CoachContext, PendingRun, PendingRunRef } from "./types";

export function textFromThreadMessage(message: ThreadMessage): string {
  return message.content
    .map((part) => (part.type === "text" ? part.text : ""))
    .join("")
    .trim();
}

function agentMessageToThreadMessage(message: AgentThreadMessage): ThreadMessageLike {
  const role = message.role === "assistant" ? "assistant" : "user";
  return {
    id: String(message.id),
    role,
    content: message.content,
    createdAt: new Date(message.created_at),
    ...(role === "assistant" ? { status: { type: "complete" as const, reason: "stop" as const } } : {})
  };
}

function latestUserText(messages: readonly ThreadMessage[]): string {
  const latest = [...messages].reverse().find((message) => message.role === "user");
  return latest ? textFromThreadMessage(latest) : "";
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

function shouldIncludeCode(command: string) {
  return command === "auto" || command === "/diagnose" || command === "/search-problems";
}

function shouldIncludeResult(command: string) {
  return command === "auto" || command === "/diagnose" || command === "/search-problems";
}

export function createPendingRun(command: string, message?: string): PendingRun {
  return {
    command,
    message,
    includeCode: shouldIncludeCode(command),
    includeResult: shouldIncludeResult(command)
  };
}

function runPayloadFromContext(context: CoachContext, pending: PendingRun | null, messages: readonly ThreadMessage[]): AgentCommandRequest {
  const command = pending?.command ?? "auto";
  const includeCode = pending?.includeCode ?? shouldIncludeCode(command);
  const includeResult = pending?.includeResult ?? shouldIncludeResult(command);
  const message = pending?.message ?? latestUserText(messages);
  return {
    task_id: context.taskId ?? "",
    command,
    message,
    code: includeCode ? context.code : undefined,
    submission_id: includeResult ? context.submissionId : undefined,
    current_result: includeResult ? context.currentResult : undefined,
    thinking_mode: context.thinkingMode,
    html_visual_mode: context.htmlVisualMode
  };
}

function useCoachChatModel(
  context: CoachContext,
  pendingRunRef: PendingRunRef,
  onRunComplete: (command: string) => void,
  onError: (message: string) => void
): ChatModelAdapter {
  return useMemo<ChatModelAdapter>(() => ({
    run: async function* (options): AsyncGenerator<ChatModelRunResult, void> {
      const pendingRun = pendingRunRef.current;
      pendingRunRef.current = null;
      const payload = runPayloadFromContext(context, pendingRun, options.messages);
      if (!payload.task_id) {
        throw new Error("请先选择一道题。");
      }

      let fullText = "";
      try {
        for await (const event of streamAssistantRun(payload, options.abortSignal)) {
          if (event.type === "text-delta") {
            fullText += event.delta;
            yield { content: [{ type: "text", text: fullText }] };
          } else if (event.type === "error") {
            throw new Error(event.message);
          }
        }
      } catch (error) {
        if (!isAbortError(error)) {
          onError((error as Error).message);
        }
        throw error;
      }

      onRunComplete(payload.command ?? "auto");
      yield {
        content: [{ type: "text", text: fullText }],
        status: { type: "complete", reason: "stop" }
      };
    }
  }), [context, onError, onRunComplete, pendingRunRef]);
}

export function useCoachAssistantRuntime({
  context,
  pendingRunRef,
  initialMessages,
  onRunComplete,
  onError
}: {
  context: CoachContext;
  pendingRunRef: PendingRunRef;
  initialMessages: AgentThreadMessage[];
  onRunComplete: (command: string) => void;
  onError: (message: string) => void;
}) {
  const chatModel = useCoachChatModel(context, pendingRunRef, onRunComplete, onError);
  return useLocalRuntime(chatModel, {
    initialMessages: initialMessages.map(agentMessageToThreadMessage)
  });
}
