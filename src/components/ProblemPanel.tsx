import { BookOpen, CheckCircle2, ClipboardList, ExternalLink, Flame } from "lucide-react";
import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import { formatSlug } from "../lib/format";
import { difficultyLabel, statusLabel } from "../lib/labels";
import type { ProblemDetail } from "../types/api";

type Props = {
  problem?: ProblemDetail;
};

export function ProblemPanel({ problem }: Props) {
  const panelRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!panelRef.current) return;
    panelRef.current.scrollLeft = 0;
    panelRef.current.scrollTop = 0;
  }, [problem?.task_id]);

  if (!problem) {
    return <main className="problem-panel empty-panel" ref={panelRef}>请选择一道题开始练习。</main>;
  }

  return (
    <main className="problem-panel" ref={panelRef}>
      <div className="problem-heading">
        <div>
          <div className="problem-kicker">
            #{problem.question_id} · {difficultyLabel(problem.difficulty)}
            {problem.codetop_frequency ? (
              <>
                {" · "}
                <span className={`heat inline ${heatLevel(problem.codetop_frequency)}`}>
                  <Flame size={13} />
                  CodeTop {problem.codetop_frequency}
                </span>
              </>
            ) : null}
          </div>
          <div className="problem-title-row">
            <h2>{problem.title || formatSlug(problem.task_id)}</h2>
            <a
              className="problem-link-button"
              href={leetcodeUrl(problem.task_id)}
              target="_blank"
              rel="noreferrer"
              title="打开 LeetCode 原题"
              aria-label="打开 LeetCode 原题"
            >
              <ExternalLink size={18} />
            </a>
          </div>
        </div>
        <div className={`status-pill ${problem.status}`}>
          <CheckCircle2 size={16} />
          {statusLabel(problem.status)}
        </div>
      </div>

      <div className="tag-row">
        {problem.tags.map((tag) => (
          <span key={tag}>{tag}</span>
        ))}
      </div>

      <section className="statement">
        <div className="section-title">
          <BookOpen size={16} />
          题目
        </div>
        <div className="problem-markdown">
          <ReactMarkdown
            remarkPlugins={[remarkGfm, remarkBreaks]}
            components={{
              img: ({ src = "", alt = "" }) => (
                <img src={proxiedProblemImage(src)} alt={alt || "题目图片"} loading="lazy" />
              )
            }}
          >
            {problem.problem_description}
          </ReactMarkdown>
        </div>
      </section>

      <section className="examples">
        <div className="section-title">
          <ClipboardList size={16} />
          示例测试
        </div>
        {problem.input_output.slice(0, 4).map((example, index) => (
          <div className="example" key={`${example.input}-${index}`}>
            <pre>输入：{example.input}</pre>
            <pre>输出：{example.output}</pre>
          </div>
        ))}
      </section>
    </main>
  );
}

function proxiedProblemImage(src: string) {
  if (!src) return "";
  if (src.startsWith("/api/problem-image")) return src;
  return `/api/problem-image?url=${encodeURIComponent(src)}`;
}

function leetcodeUrl(taskId: string) {
  return `https://leetcode.cn/problems/${encodeURIComponent(taskId)}/`;
}

function heatLevel(frequency: number) {
  if (frequency >= 500) return "critical";
  if (frequency >= 200) return "high";
  if (frequency >= 80) return "medium";
  return "low";
}
