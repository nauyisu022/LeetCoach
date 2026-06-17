import { useMemo } from "react";
import DOMPurify from "dompurify";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useCoachMarkdownComponents, type CoachProblemLink } from "./CoachMarkdown";

const HTML_MARKER_START = "<!-- html-render-start -->";
const HTML_MARKER_END = "<!-- html-render-end -->";

type RichContentPart =
  | { type: "markdown"; content: string }
  | { type: "html"; content: string };

const ALLOWED_HTML_TAGS = new Set([
  "div",
  "section",
  "span",
  "p",
  "strong",
  "em",
  "small",
  "code",
  "pre",
  "details",
  "summary",
  "table",
  "thead",
  "tbody",
  "tr",
  "th",
  "td",
  "ul",
  "ol",
  "li",
  "br",
  "hr",
  "button",
  "svg",
  "g",
  "path",
  "line",
  "polyline",
  "polygon",
  "circle",
  "rect"
]);

const ALLOWED_CSS_PROPERTIES = new Set([
  "display",
  "box-sizing",
  "position",
  "width",
  "height",
  "min-width",
  "min-height",
  "max-width",
  "max-height",
  "margin",
  "margin-top",
  "margin-right",
  "margin-bottom",
  "margin-left",
  "padding",
  "padding-top",
  "padding-right",
  "padding-bottom",
  "padding-left",
  "border",
  "border-width",
  "border-style",
  "border-color",
  "border-radius",
  "background",
  "background-color",
  "color",
  "font",
  "font-family",
  "font-size",
  "font-weight",
  "font-style",
  "line-height",
  "text-align",
  "white-space",
  "word-break",
  "overflow",
  "overflow-x",
  "overflow-y",
  "opacity",
  "box-shadow",
  "align-items",
  "align-content",
  "justify-content",
  "flex",
  "flex-direction",
  "flex-wrap",
  "gap",
  "row-gap",
  "column-gap",
  "grid-template-columns",
  "grid-template-rows",
  "fill",
  "stroke",
  "stroke-width"
]);

const ALLOWED_HTML_ATTRS = [
  "aria-label",
  "aria-describedby",
  "aria-hidden",
  "class",
  "colspan",
  "cx",
  "cy",
  "d",
  "data-state",
  "fill",
  "height",
  "href",
  "open",
  "points",
  "r",
  "role",
  "rx",
  "ry",
  "stroke",
  "stroke-linecap",
  "stroke-linejoin",
  "stroke-width",
  "style",
  "title",
  "transform",
  "viewBox",
  "width",
  "viewbox",
  "x",
  "x1",
  "x2",
  "y",
  "y1",
  "y2"
];

function splitRichContent(markdown: string): RichContentPart[] {
  const parts: RichContentPart[] = [];
  let cursor = 0;

  while (cursor < markdown.length) {
    const startIndex = markdown.indexOf(HTML_MARKER_START, cursor);
    if (startIndex === -1) {
      parts.push({ type: "markdown", content: markdown.slice(cursor) });
      break;
    }

    const htmlStart = startIndex + HTML_MARKER_START.length;
    const endIndex = markdown.indexOf(HTML_MARKER_END, htmlStart);
    if (endIndex === -1) {
      parts.push({ type: "markdown", content: markdown.slice(cursor) });
      break;
    }

    if (startIndex > cursor) {
      parts.push({ type: "markdown", content: markdown.slice(cursor, startIndex) });
    }

    parts.push({ type: "html", content: markdown.slice(htmlStart, endIndex).trim() });
    cursor = endIndex + HTML_MARKER_END.length;
  }

  return parts.filter((part) => part.content.trim());
}

function isUnsafeStyleValue(value: string) {
  return /url\s*\(|expression\s*\(|javascript:|vbscript:|@import|behavior\s*:/i.test(value);
}

function sanitizeStyle(styleText: string) {
  if (typeof document === "undefined") return "";
  const probe = document.createElement("span");
  probe.setAttribute("style", styleText);
  const rules: string[] = [];

  for (let index = 0; index < probe.style.length; index += 1) {
    const property = probe.style[index].toLowerCase();
    const value = probe.style.getPropertyValue(property).trim();
    if (!ALLOWED_CSS_PROPERTIES.has(property) || !value || isUnsafeStyleValue(value)) continue;
    rules.push(`${property}: ${value}`);
  }

  return rules.join("; ");
}

function sanitizeHtmlFragment(html: string) {
  if (typeof document === "undefined") return "";
  const purified = DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [...ALLOWED_HTML_TAGS],
    ALLOWED_ATTR: ALLOWED_HTML_ATTRS,
    ALLOW_DATA_ATTR: true,
    ALLOW_ARIA_ATTR: true,
    RETURN_TRUSTED_TYPE: false,
    ALLOWED_URI_REGEXP: /^(?:(?:https?):|\/|#)/i,
    FORBID_TAGS: ["script", "style", "iframe", "object", "embed", "link", "meta", "base", "form"],
    FORBID_ATTR: ["srcdoc"]
  });
  const template = document.createElement("template");
  template.innerHTML = purified;

  const walker = document.createTreeWalker(template.content, NodeFilter.SHOW_ELEMENT);
  let current = walker.nextNode();
  while (current) {
    const element = current as Element;
    const style = element.getAttribute("style");
    if (style) {
      const sanitizedStyle = sanitizeStyle(style);
      if (sanitizedStyle) element.setAttribute("style", sanitizedStyle);
      else element.removeAttribute("style");
    }
    if (element.tagName.toLowerCase() === "a" && /^https?:\/\//i.test(element.getAttribute("href") ?? "")) {
      element.setAttribute("target", "_blank");
      element.setAttribute("rel", "noreferrer");
    }
    current = walker.nextNode();
  }

  return template.innerHTML;
}

function SafeHtmlFragment({ html }: { html: string }) {
  const sanitized = useMemo(() => sanitizeHtmlFragment(html), [html]);
  if (!sanitized) return null;
  return <div className="ai-html-fragment" dangerouslySetInnerHTML={{ __html: sanitized }} />;
}

export function CoachRichContent({
  markdown,
  onProblemLinkClick,
  problemLinks = []
}: {
  markdown: string;
  onProblemLinkClick: (taskId: string) => void;
  problemLinks?: CoachProblemLink[];
}) {
  const markdownComponents = useCoachMarkdownComponents(onProblemLinkClick, problemLinks);
  const parts = useMemo(() => splitRichContent(markdown), [markdown]);

  if (!parts.length) return null;

  return (
    <>
      {parts.map((part, index) => (
        part.type === "html" ? (
          <SafeHtmlFragment html={part.content} key={`html:${index}`} />
        ) : (
          <ReactMarkdown components={markdownComponents} key={`markdown:${index}`} remarkPlugins={[remarkGfm]}>
            {part.content}
          </ReactMarkdown>
        )
      ))}
    </>
  );
}
