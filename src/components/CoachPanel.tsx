import { Brain, FileText, Loader2, MessageSquare, Search, Send, Sparkles, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { CodeBlock } from "./CodeBlock";
import type { AgentThreadMessage, ThinkingMode } from "../types/api";

export type CoachCommandAction = {
  command: string;
  label: string;
  icon: "explain" | "diagnose" | "search";
};

type Props = {
  messages: AgentThreadMessage[];
  isLoading: boolean;
  commandActions: CoachCommandAction[];
  onCommandAction: (command: string) => void;
  onProblemLinkClick: (taskId: string) => void;
  onPreviewContext: (message?: string) => void;
  onClearPreview: () => void;
  onSend: (message: string) => void;
  onClear: () => void;
  contextPreview: string | null;
  isPreviewLoading: boolean;
  thinkingMode: ThinkingMode;
  onThinkingModeChange: (mode: ThinkingMode) => void;
};

function commandIcon(icon: CoachCommandAction["icon"]) {
  if (icon === "explain") return <FileText size={15} />;
  if (icon === "search") return <Search size={15} />;
  return <MessageSquare size={15} />;
}

function problemTaskIdFromHref(href: string | undefined): string | null {
  if (!href) return null;
  const localMatch = /^\/problems\/([^/?#]+)/.exec(href);
  if (localMatch) return decodeURIComponent(localMatch[1]);
  const leetcodeMatch = /^https?:\/\/(?:leetcode\.cn|leetcode\.com)\/problems\/([^/?#]+)/.exec(href);
  if (leetcodeMatch) return decodeURIComponent(leetcodeMatch[1]);
  return null;
}

export function CoachPanel({
  messages = [],
  isLoading,
  commandActions,
  onCommandAction,
  onProblemLinkClick,
  onPreviewContext,
  onClearPreview,
  onSend,
  onClear,
  contextPreview,
  isPreviewLoading,
  thinkingMode,
  onThinkingModeChange
}: Props) {
  const [draft, setDraft] = useState("");
  const outputRef = useRef<HTMLDivElement | null>(null);
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
    },
    a({ href, children, ...props }) {
      const taskId = problemTaskIdFromHref(href);
      if (!taskId) {
        return (
          <a href={href} target="_blank" rel="noreferrer" {...props}>
            {children}
          </a>
        );
      }
      return (
        <button
          className="markdown-problem-link"
          type="button"
          onClick={() => onProblemLinkClick(taskId)}
        >
          {children}
        </button>
      );
    }
  };

  useEffect(() => {
    if (!outputRef.current) return;
    outputRef.current.scrollTop = outputRef.current.scrollHeight;
  }, [messages, isLoading, contextPreview, isPreviewLoading]);

  function submitDraft() {
    const message = draft.trim();
    if (!message || isLoading) return;
    setDraft("");
    onSend(message);
  }

  function renderMessageContent(message: AgentThreadMessage) {
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
        {commandActions.map((action) => (
          <button
            className="ghost-button"
            key={action.command}
            onClick={() => onCommandAction(action.command)}
            disabled={isLoading}
          >
            {commandIcon(action.icon)}
            {action.label}
          </button>
        ))}
        <button className="icon-button coach-tool-button" onClick={onClear} disabled={isLoading || messages.length === 0} title="清空对话" aria-label="清空对话">
          <Trash2 size={15} />
        </button>
        <button
          className={`thinking-toggle ${thinkingMode === "enabled" ? "active" : ""}`}
          type="button"
          onClick={() => onThinkingModeChange(thinkingMode === "enabled" ? "disabled" : "enabled")}
          aria-pressed={thinkingMode === "enabled"}
          title={thinkingMode === "enabled" ? "DeepSeek Thinking 已开启" : "DeepSeek Thinking 已关闭"}
        >
          <Sparkles size={15} />
          {thinkingMode === "enabled" ? "Thinking 开" : "Thinking 关"}
        </button>
      </div>
      <div className="coach-output" ref={outputRef}>
        {contextPreview && (
          <article className="agent-preview">
            <div className="agent-preview-header">
              <span>Agent Preview</span>
              <button className="icon-button" type="button" onClick={onClearPreview} aria-label="关闭上下文预览">
                <X size={15} />
              </button>
            </div>
            <div className="markdown-body">
              <ReactMarkdown components={markdownComponents} remarkPlugins={[remarkGfm]}>
                {contextPreview}
              </ReactMarkdown>
            </div>
          </article>
        )}
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
