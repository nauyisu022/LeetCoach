import type { AgentRecommendationSet } from "../types/api";

type Props = {
  recommendationSet: AgentRecommendationSet | null;
  selectedTaskId?: string;
  onSelect: (taskId: string) => void;
};

export function RecommendationTrail({ recommendationSet, selectedTaskId, onSelect }: Props) {
  if (!recommendationSet || recommendationSet.items.length === 0) return null;

  return (
    <nav className="recommendation-trail" aria-label="当前相似题单">
      <span className="recommendation-trail-label">相似题单</span>
      <span className="recommendation-trail-source">{recommendationSet.source_task_id}</span>
      <div className="recommendation-trail-links">
        {recommendationSet.items.slice(0, 8).map((item) => (
          <a
            className={item.task_id === selectedTaskId ? "active" : ""}
            href={`/problems/${encodeURIComponent(item.task_id)}`}
            key={item.task_id}
            onClick={(event) => {
              event.preventDefault();
              onSelect(item.task_id);
            }}
            title={`${item.question_id}. ${item.title}`}
          >
            {item.question_id}. {item.title}
          </a>
        ))}
      </div>
    </nav>
  );
}
