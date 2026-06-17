import { MessagePrimitive, ThreadPrimitive, useMessage } from "@assistant-ui/react";
import { Loader2 } from "lucide-react";
import { createContext, useContext } from "react";
import { CoachRichContent } from "../CoachRichContent";
import type { CoachProblemLink } from "../CoachMarkdown";
import { textFromThreadMessage } from "./coachRuntimeAdapter";

const CoachMessageRenderContext = createContext<{
  onProblemLinkClick: (taskId: string) => void;
  problemLinks: CoachProblemLink[];
} | null>(null);

const threadMessageComponents = {
  Message: CoachThreadMessage
};

export function CoachMessages({
  onProblemLinkClick,
  problemLinks
}: {
  onProblemLinkClick: (taskId: string) => void;
  problemLinks: CoachProblemLink[];
}) {
  return (
    <CoachMessageRenderContext.Provider value={{ onProblemLinkClick, problemLinks }}>
      <ThreadPrimitive.Root className="coach-assistant-thread">
        <ThreadPrimitive.Viewport className="coach-output" autoScroll>
          <ThreadPrimitive.Empty>
            <span>可以直接提问，例如“为什么这题用哈希表？”或“我的代码哪里错了？”</span>
          </ThreadPrimitive.Empty>
          <ThreadPrimitive.Messages components={threadMessageComponents} />
          <ThreadPrimitive.If running>
            <div className="loading-line">
              <Loader2 className="spin" size={16} />
              AI 正在回答，按 Esc 或停止按钮取消。
            </div>
          </ThreadPrimitive.If>
        </ThreadPrimitive.Viewport>
      </ThreadPrimitive.Root>
    </CoachMessageRenderContext.Provider>
  );
}

function CoachThreadMessage() {
  const renderContext = useContext(CoachMessageRenderContext);
  const role = useMessage((message) => message.role);
  const text = useMessage(textFromThreadMessage);

  if (!renderContext) return null;

  return (
    <MessagePrimitive.Root className={`chat-message ${role}`}>
      <div className="chat-role">{role === "user" ? "你" : "AI 教练"}</div>
      <div className="markdown-body">
        <CoachRichContent
          markdown={text}
          onProblemLinkClick={renderContext.onProblemLinkClick}
          problemLinks={renderContext.problemLinks}
        />
      </div>
    </MessagePrimitive.Root>
  );
}
