import { useThread } from "@assistant-ui/react";
import { Loader2 } from "lucide-react";
import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useCoachMarkdownComponents, type CoachProblemLink } from "../CoachMarkdown";
import { textFromThreadMessage } from "./coachRuntimeAdapter";

export function CoachMessages({
  onProblemLinkClick,
  problemLinks
}: {
  onProblemLinkClick: (taskId: string) => void;
  problemLinks: CoachProblemLink[];
}) {
  const markdownComponents = useCoachMarkdownComponents(onProblemLinkClick, problemLinks);
  const messages = useThread((state) => state.messages);
  const isRunning = useThread((state) => state.isRunning);
  const outputRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!outputRef.current) return;
    outputRef.current.scrollTop = outputRef.current.scrollHeight;
  }, [messages, isRunning]);

  return (
    <div className="coach-assistant-thread">
      <div className="coach-output" ref={outputRef}>
        {messages.length === 0 && (
          <span>可以直接提问，例如“为什么这题用哈希表？”或“我的代码哪里错了？”</span>
        )}
        {messages.map((message) => {
          const text = textFromThreadMessage(message);
          return (
            <article className={`chat-message ${message.role}`} key={message.id}>
              <div className="chat-role">{message.role === "user" ? "你" : "AI 教练"}</div>
              <div className="markdown-body">
                <ReactMarkdown components={markdownComponents} remarkPlugins={[remarkGfm]}>
                  {text}
                </ReactMarkdown>
              </div>
            </article>
          );
        })}
        {isRunning && (
          <div className="loading-line">
            <Loader2 className="spin" size={16} />
            AI 正在回答，按 Esc 或停止按钮取消。
          </div>
        )}
      </div>
    </div>
  );
}
