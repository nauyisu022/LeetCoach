import { Children, useMemo, type ReactNode } from "react";
import type { Components } from "react-markdown";
import { CodeBlock } from "./CodeBlock";

export type CoachProblemLink = {
  task_id: string;
  question_id: number;
  title: string;
};

function problemTaskIdFromHref(href: string | undefined): string | null {
  if (!href) return null;
  const localMatch = /^\/problems\/([^/?#]+)/.exec(href);
  if (localMatch) return decodeURIComponent(localMatch[1]);
  const leetcodeMatch = /^https?:\/\/(?:leetcode\.cn|leetcode\.com)\/problems\/([^/?#]+)/.exec(href);
  if (leetcodeMatch) return decodeURIComponent(leetcodeMatch[1]);
  return null;
}

function titleMatchLength(textAfterNumber: string, title: string): number | null {
  if (/^\s+\d{1,5}\.(?!\d)/.test(textAfterNumber)) return null;

  const leadingWhitespace = /^\s*/.exec(textAfterNumber)?.[0] ?? "";
  const candidate = textAfterNumber.slice(leadingWhitespace.length);
  if (title && candidate.startsWith(title)) {
    return leadingWhitespace.length + title.length;
  }
  return 0;
}

function linkifyProblemReferences(
  children: ReactNode,
  problemByQuestionId: Map<number, CoachProblemLink>,
  onProblemLinkClick: (taskId: string) => void
): ReactNode {
  return Children.map(children, (child) => {
    if (typeof child !== "string") return child;

    const nodes: ReactNode[] = [];
    const problemNumberPattern = /\b(\d{1,5})\.(?!\d)/g;
    let lastIndex = 0;
    let match: RegExpExecArray | null;

    while ((match = problemNumberPattern.exec(child)) !== null) {
      const questionId = Number(match[1]);
      const problem = problemByQuestionId.get(questionId);
      if (!problem) continue;

      const matchEnd = match.index + match[0].length;
      const extraLength = titleMatchLength(child.slice(matchEnd), problem.title);
      if (extraLength === null) continue;

      if (match.index > lastIndex) {
        nodes.push(child.slice(lastIndex, match.index));
      }

      const linkEnd = matchEnd + extraLength;
      const label = child.slice(match.index, linkEnd);
      nodes.push(
        <button
          className="markdown-problem-link"
          key={`${problem.task_id}:${match.index}`}
          type="button"
          onClick={() => onProblemLinkClick(problem.task_id)}
        >
          {label}
        </button>
      );
      lastIndex = linkEnd;
      problemNumberPattern.lastIndex = linkEnd;
    }

    if (lastIndex === 0) return child;
    if (lastIndex < child.length) {
      nodes.push(child.slice(lastIndex));
    }
    return nodes;
  });
}

export function useCoachMarkdownComponents(
  onProblemLinkClick: (taskId: string) => void,
  problemLinks: CoachProblemLink[] = []
): Components {
  const problemByQuestionId = useMemo(
    () => new Map(problemLinks.map((problem) => [problem.question_id, problem])),
    [problemLinks]
  );

  return useMemo(
    () => ({
      p({ children }) {
        return <p>{linkifyProblemReferences(children, problemByQuestionId, onProblemLinkClick)}</p>;
      },
      li({ children }) {
        return <li>{linkifyProblemReferences(children, problemByQuestionId, onProblemLinkClick)}</li>;
      },
      strong({ children }) {
        return <strong>{linkifyProblemReferences(children, problemByQuestionId, onProblemLinkClick)}</strong>;
      },
      em({ children }) {
        return <em>{linkifyProblemReferences(children, problemByQuestionId, onProblemLinkClick)}</em>;
      },
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
    }),
    [onProblemLinkClick, problemByQuestionId]
  );
}
