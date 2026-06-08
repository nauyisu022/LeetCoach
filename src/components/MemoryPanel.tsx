import { Archive, Check, Database, Loader2, Pencil, Save, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { AgentMemoryItem, ProblemDetail } from "../types/api";

type Props = {
  problem?: ProblemDetail;
  memories: AgentMemoryItem[];
  isLoading: boolean;
  updatingMemoryId: number | null;
  onAccept: (memoryId: number) => Promise<void>;
  onReject: (memoryId: number) => Promise<void>;
  onArchive: (memoryId: number) => Promise<void>;
  onSave: (memoryId: number, content: string) => Promise<void>;
};

export function MemoryPanel({
  problem,
  memories,
  isLoading,
  updatingMemoryId,
  onAccept,
  onReject,
  onArchive,
  onSave
}: Props) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    setEditingId(null);
    setDraft("");
  }, [problem?.task_id]);

  const proposed = useMemo(() => memories.filter((memory) => memory.status === "proposed"), [memories]);
  const accepted = useMemo(() => memories.filter((memory) => memory.status === "accepted"), [memories]);

  function startEdit(memory: AgentMemoryItem) {
    setEditingId(memory.id);
    setDraft(memory.content);
  }

  async function saveEdit(memory: AgentMemoryItem) {
    const content = draft.trim();
    if (!content) return;
    await onSave(memory.id, content);
    setEditingId(null);
    setDraft("");
  }

  if (!problem) {
    return <section className="memory-panel empty-panel">请选择一道题查看 Memory。</section>;
  }

  return (
    <section className="memory-panel">
      <div className="memory-toolbar">
        <div className="section-title">
          <Database size={16} />
          Memory
        </div>
        {isLoading && <Loader2 className="spin" size={15} />}
      </div>

      <div className="memory-scroll">
        <MemoryGroup
          title="待确认"
          emptyText="暂无待确认记忆"
          memories={proposed}
          editingId={editingId}
          draft={draft}
          updatingMemoryId={updatingMemoryId}
          onDraftChange={setDraft}
          onEdit={startEdit}
          onSave={saveEdit}
          primaryAction={(memory) => ({
            label: "接受",
            icon: <Check size={14} />,
            onClick: () => onAccept(memory.id)
          })}
          secondaryAction={(memory) => ({
            label: "拒绝",
            icon: <X size={14} />,
            onClick: () => onReject(memory.id)
          })}
        />

        <MemoryGroup
          title="已确认"
          emptyText="暂无已确认记忆"
          memories={accepted}
          editingId={editingId}
          draft={draft}
          updatingMemoryId={updatingMemoryId}
          onDraftChange={setDraft}
          onEdit={startEdit}
          onSave={saveEdit}
          primaryAction={(memory) => ({
            label: "编辑",
            icon: <Pencil size={14} />,
            onClick: () => startEdit(memory)
          })}
          secondaryAction={(memory) => ({
            label: "归档",
            icon: <Archive size={14} />,
            onClick: () => onArchive(memory.id)
          })}
        />
      </div>
    </section>
  );
}

type MemoryAction = {
  label: string;
  icon: ReactNode;
  onClick: () => void | Promise<void>;
};

type MemoryGroupProps = {
  title: string;
  emptyText: string;
  memories: AgentMemoryItem[];
  editingId: number | null;
  draft: string;
  updatingMemoryId: number | null;
  onDraftChange: (value: string) => void;
  onEdit: (memory: AgentMemoryItem) => void;
  onSave: (memory: AgentMemoryItem) => Promise<void>;
  primaryAction: (memory: AgentMemoryItem) => MemoryAction;
  secondaryAction: (memory: AgentMemoryItem) => MemoryAction;
};

function MemoryGroup({
  title,
  emptyText,
  memories,
  editingId,
  draft,
  updatingMemoryId,
  onDraftChange,
  onEdit,
  onSave,
  primaryAction,
  secondaryAction
}: MemoryGroupProps) {
  return (
    <div className="memory-group">
      <div className="memory-group-head">
        <strong>{title}</strong>
        <span>{memories.length}</span>
      </div>
      {memories.length ? (
        memories.map((memory) => {
          const isEditing = editingId === memory.id;
          const isUpdating = updatingMemoryId === memory.id;
          const primary = primaryAction(memory);
          const secondary = secondaryAction(memory);
          return (
            <article className="memory-item" key={memory.id}>
              <div className="memory-meta">
                <span>{memoryTypeLabel(memory.memory_type)}</span>
                <small>{scopeLabel(memory)}</small>
              </div>
              {isEditing ? (
                <textarea
                  value={draft}
                  rows={4}
                  onChange={(event) => onDraftChange(event.target.value)}
                />
              ) : (
                <p>{memory.content}</p>
              )}
              <div className="memory-actions">
                {isEditing ? (
                  <button
                    className="primary-button compact"
                    disabled={isUpdating || !draft.trim()}
                    onClick={() => void onSave(memory)}
                  >
                    {isUpdating ? <Loader2 className="spin" size={14} /> : <Save size={14} />}
                    保存
                  </button>
                ) : (
                  <button
                    className="ghost-button compact"
                    disabled={isUpdating}
                    onClick={() => {
                      if (primary.label === "编辑") {
                        onEdit(memory);
                        return;
                      }
                      void primary.onClick();
                    }}
                  >
                    {isUpdating ? <Loader2 className="spin" size={14} /> : primary.icon}
                    {primary.label}
                  </button>
                )}
                <button
                  className="ghost-button compact"
                  disabled={isUpdating}
                  onClick={() => void secondary.onClick()}
                >
                  {secondary.icon}
                  {secondary.label}
                </button>
              </div>
            </article>
          );
        })
      ) : (
        <div className="memory-empty">{emptyText}</div>
      )}
    </div>
  );
}

function memoryTypeLabel(type: string) {
  return {
    preference: "偏好",
    weakness: "弱点",
    strength: "优势",
    habit: "习惯",
    goal: "目标",
    strategy: "策略"
  }[type] ?? type;
}

function scopeLabel(memory: AgentMemoryItem) {
  if (memory.scope === "task" && memory.task_id) return memory.task_id;
  if (memory.scope === "topic" && memory.topic) return memory.topic;
  return "全局";
}
