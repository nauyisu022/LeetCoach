import { Brain, FileText, Loader2, MessageSquare, Send, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { CodeBlock } from "./CodeBlock";
import type { CoachMessage } from "../types/api";

type Props = {
  messages: CoachMessage[];
  isLoading: boolean;
  onExplain: () => void;
  onDiagnose: () => void;
  onSend: (message: string) => void;
  onClear: () => void;
};

const markdownComponents: Components = {
  pre({ children }) {
    return <>{children}</>;
  },
  code({ className, children, ...props }) {
    const language = /language-(\w+)/.exec(className ?? "")?.[1] ?? "";
    const code = String(children).replace(/\n$/, "");
    const isBlockCode = Boolean(language) || code.includes("\n");

    if (isBlockCode) {
      return <CodeBlock code={code} language={language} />;
    }

    return (
      <code className={className} {...props}>
        {children}
      </code>
    );
  }
};

export function CoachPanel({ messages = [], isLoading, onExplain, onDiagnose, onSend, onClear }: Props) {
  const [draft, setDraft] = useState("");
  const outputRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!outputRef.current) return;
    outputRef.current.scrollTop = outputRef.current.scrollHeight;
  }, [messages, isLoading]);

  function submitDraft() {
    const message = draft.trim();
    if (!message || isLoading) return;
    setDraft("");
    onSend(message);
  }

  function renderMessageContent(message: CoachMessage) {
    if (message.content) {
      return (
        <ReactMarkdown components={markdownComponents} remarkPlugins={[remarkGfm]}>
          {message.content}
        </ReactMarkdown>
      );
    }

    if (message.role === "assistant" && message.id < 0 && isLoading) {
      return <span className="ai-thinking">AI 正在思考...</span>;
    }

    return <span className="ai-thinking">AI 没有返回内容，请重试。</span>;
  }

  return (
    <section className="coach-panel">
      <div className="coach-actions">
        <div className="section-title">
          <Brain size={16} />
          AI 教练对话
        </div>
        <button className="ghost-button" onClick={onExplain} disabled={isLoading}>
          <FileText size={15} />
          讲解
        </button>
        <button className="ghost-button" onClick={onDiagnose} disabled={isLoading}>
          <MessageSquare size={15} />
          诊断
        </button>
        <button className="ghost-button" onClick={onClear} disabled={isLoading || messages.length === 0}>
          <Trash2 size={15} />
          清空
        </button>
      </div>
      <div className="coach-output" ref={outputRef}>
        {messages.length > 0 ? (
          messages.map((message) => (
            <article className={`chat-message ${message.role}`} key={message.id}>
              <div className="chat-role">{message.role === "user" ? "你" : "AI 教练"}</div>
              <div className="markdown-body">
                {renderMessageContent(message)}
              </div>
            </article>
          ))
        ) : (
          <span>可以直接提问，例如“为什么这题用哈希表？”或“我的代码哪里错了？”</span>
        )}
        {isLoading && (
          <div className="loading-line">
            <Loader2 className="spin" size={16} />
            AI 正在回答，按 Esc 停止。
          </div>
        )}
      </div>
      <div className="coach-input-row">
        <textarea
          value={draft}
          placeholder="问 AI，例如：这题怎么想到哈希表？"
          rows={1}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submitDraft();
            }
          }}
        />
        <button className="send-button" onClick={submitDraft} disabled={isLoading || !draft.trim()} aria-label="发送消息">
          <Send size={18} />
          <span>发送</span>
        </button>
      </div>
    </section>
  );
}
