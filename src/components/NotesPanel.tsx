import { BookMarked, CalendarClock, Loader2, Save, Sparkles, Star } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type {
  PracticeNote,
  PracticeNoteDraftResponse,
  PracticeNoteSaveRequest,
  ProblemDetail,
  TopicMemory
} from "../types/api";

type Props = {
  problem?: ProblemDetail;
  note?: PracticeNote | null;
  suggestedTopics: string[];
  topicMemories: TopicMemory[];
  isLoading: boolean;
  isSaving: boolean;
  isDrafting: boolean;
  onSave: (payload: PracticeNoteSaveRequest) => Promise<PracticeNote>;
  onDraft: (onChunk: (chunk: string) => void) => Promise<PracticeNoteDraftResponse>;
  onReview: (rating: number) => Promise<void>;
};

type NoteDraftState = {
  content_markdown: string;
  ai_summary: string;
  mistake_summary: string;
  invariant_summary: string;
  solution_pattern: string;
};

const emptyDraft: NoteDraftState = {
  content_markdown: "",
  ai_summary: "",
  mistake_summary: "",
  invariant_summary: "",
  solution_pattern: ""
};

export function NotesPanel({
  problem,
  note,
  suggestedTopics,
  topicMemories,
  isLoading,
  isSaving,
  isDrafting,
  onSave,
  onDraft,
  onReview
}: Props) {
  const [draft, setDraft] = useState<NoteDraftState>(emptyDraft);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [sourceSubmissionId, setSourceSubmissionId] = useState<number | null>(null);
  const [reviewingRating, setReviewingRating] = useState<number | null>(null);

  useEffect(() => {
    setDraft({
      content_markdown: note?.content_markdown ?? "",
      ai_summary: note?.ai_summary ?? "",
      mistake_summary: note?.mistake_summary ?? "",
      invariant_summary: note?.invariant_summary ?? "",
      solution_pattern: note?.solution_pattern ?? ""
    });
    setSavedAt(note?.updated_at ?? null);
    setSourceSubmissionId(note?.source_submission_id ?? null);
    setReviewingRating(null);
  }, [note, problem?.task_id]);

  const matchingMemories = useMemo(() => {
    const topicSet = new Set(suggestedTopics);
    return topicMemories.filter((memory) => topicSet.has(memory.topic_label)).slice(0, 3);
  }, [suggestedTopics, topicMemories]);

  if (!problem) {
    return <section className="notes-panel empty-panel">请选择一道题查看 Notes。</section>;
  }

  async function handleDraft() {
    if (draft.content_markdown.trim()) {
      const shouldReplace = window.confirm("AI 草稿会替换当前编辑区内容，但不会自动保存。继续？");
      if (!shouldReplace) return;
    }
    let streamedText = "";
    setDraft((current) => ({
      ...current,
      content_markdown: ""
    }));
    const response = await onDraft((chunk) => {
      streamedText += chunk;
      setDraft((current) => ({
        ...current,
        content_markdown: streamedText
      }));
    });
    setDraft((current) => ({
      ...current,
      content_markdown: response.content_markdown || streamedText
    }));
    setSourceSubmissionId(response.source_submission_id);
  }

  async function handleSave() {
    const saved = await onSave({
      content_markdown: draft.content_markdown,
      ai_summary: optionalText(draft.ai_summary),
      mistake_summary: optionalText(draft.mistake_summary),
      invariant_summary: optionalText(draft.invariant_summary),
      solution_pattern: optionalText(draft.solution_pattern),
      source_submission_id: sourceSubmissionId
    });
    setSavedAt(saved.updated_at);
  }

  async function handleReview(rating: number) {
    setReviewingRating(rating);
    try {
      await onReview(rating);
    } finally {
      setReviewingRating(null);
    }
  }

  return (
    <section
      className="notes-panel"
      onKeyDown={(event) => {
        if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
          event.preventDefault();
          event.stopPropagation();
          void handleSave();
        }
      }}
    >
      <div className="notes-toolbar">
        <div className="section-title">
          <BookMarked size={16} />
          Notes
        </div>
        <button className="ghost-button" onClick={() => void handleDraft()} disabled={isLoading || isDrafting}>
          {isDrafting ? <Loader2 className="spin" size={15} /> : <Sparkles size={15} />}
          AI 草稿
        </button>
        <button className="primary-button" onClick={() => void handleSave()} disabled={isSaving || isDrafting}>
          {isSaving ? <Loader2 className="spin" size={15} /> : <Save size={15} />}
          保存
        </button>
      </div>

      <div className="notes-scroll">
        <div className="notes-meta">
          <span>{suggestedTopics.join("、") || "未标注考点"}</span>
          {savedAt && <small>已保存 {formatTime(savedAt)}</small>}
        </div>

        <div className="note-field-grid">
          <label>
            <span>总结</span>
            <textarea
              value={draft.ai_summary}
              rows={2}
              onChange={(event) => setDraft((current) => ({ ...current, ai_summary: event.target.value }))}
            />
          </label>
          <label>
            <span>错误点</span>
            <textarea
              value={draft.mistake_summary}
              rows={2}
              onChange={(event) => setDraft((current) => ({ ...current, mistake_summary: event.target.value }))}
            />
          </label>
          <label>
            <span>不变量</span>
            <textarea
              value={draft.invariant_summary}
              rows={2}
              onChange={(event) => setDraft((current) => ({ ...current, invariant_summary: event.target.value }))}
            />
          </label>
          <label>
            <span>范式</span>
            <textarea
              value={draft.solution_pattern}
              rows={2}
              onChange={(event) => setDraft((current) => ({ ...current, solution_pattern: event.target.value }))}
            />
          </label>
        </div>

        <label className="note-markdown-field">
          <span>Markdown</span>
          <textarea
            value={draft.content_markdown}
            rows={12}
            onChange={(event) => setDraft((current) => ({ ...current, content_markdown: event.target.value }))}
          />
        </label>

        {note && (
          <div className="review-row">
            <span>
              <CalendarClock size={14} />
              {note.review_at ? `下次 ${formatTime(note.review_at)}` : "未安排"}
            </span>
            {[1, 3, 5].map((rating) => (
              <button
                key={rating}
                className="ghost-button compact"
                onClick={() => void handleReview(rating)}
                disabled={reviewingRating !== null}
              >
                {reviewingRating === rating ? <Loader2 className="spin" size={14} /> : <Star size={14} />}
                {ratingLabel(rating)}
              </button>
            ))}
          </div>
        )}

        {matchingMemories.length > 0 && (
          <div className="topic-memory-list">
            {matchingMemories.map((memory) => (
              <article className="topic-memory" key={memory.topic_name}>
                <div>
                  <strong>{memory.topic_label}</strong>
                  <small>{memory.mastery_level}</small>
                </div>
                <div className="markdown-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{memory.memory_markdown}</ReactMarkdown>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function optionalText(value: string) {
  const text = value.trim();
  return text || null;
}

function formatTime(value: string) {
  return value.replace("T", " ").slice(0, 16);
}

function ratingLabel(rating: number) {
  if (rating <= 1) return "再练";
  if (rating >= 5) return "掌握";
  return "一般";
}
