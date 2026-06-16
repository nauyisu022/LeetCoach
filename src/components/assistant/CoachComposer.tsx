import { useComposer, useComposerRuntime, useThread, useThreadRuntime } from "@assistant-ui/react";
import { Send, Square } from "lucide-react";
import { useEffect } from "react";
import { createPendingRun } from "./coachRuntimeAdapter";
import type { CoachContext, PendingRunRef } from "./types";

export function CoachComposer({
  context,
  pendingRunRef,
  onClearPreview
}: {
  context: CoachContext;
  pendingRunRef: PendingRunRef;
  onClearPreview: () => void;
}) {
  const composerText = useComposer((state) => state.text);
  const isRunning = useThread((state) => state.isRunning);
  const composerRuntime = useComposerRuntime();
  const threadRuntime = useThreadRuntime();

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape" || !isRunning) return;
      event.preventDefault();
      threadRuntime.cancelRun();
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isRunning, threadRuntime]);

  function sendDraft() {
    const text = composerText.trim();
    if (isRunning || !text) return;
    pendingRunRef.current = createPendingRun("auto", text);
    onClearPreview();
    composerRuntime.send();
  }

  return (
    <div className="coach-input-row">
      <textarea
        aria-label="向 AI 教练提问"
        placeholder="问 AI，例如：这题怎么想到哈希表？"
        value={composerText}
        rows={1}
        onChange={(event) => composerRuntime.setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            sendDraft();
          }
        }}
      />
      {isRunning ? (
        <button className="send-button stop-button" type="button" onClick={() => threadRuntime.cancelRun()} aria-label="停止回答" title="停止回答">
          <Square size={17} />
          <span>停止</span>
        </button>
      ) : (
        <button className="send-button" type="button" onClick={sendDraft} disabled={!context.taskId || !composerText.trim()} aria-label="发送消息" title="发送消息">
          <Send size={18} />
          <span>发送</span>
        </button>
      )}
    </div>
  );
}
