import { BookMarked, CheckCircle2, Flame, Play, Search, Target, X } from "lucide-react";
import { type KeyboardEvent, useEffect, useMemo, useState } from "react";
import { formatSlug } from "../lib/format";
import { difficultyLabel, statusLabel } from "../lib/labels";
import type {
  Filters,
  PracticeInsightsResponse,
  PracticeQueueResponse,
  ProblemSummary,
  ProblemTag,
  StudyPlanItemsResponse,
  StudyPlanSummary
} from "../types/api";

type Props = {
  problems: ProblemSummary[];
  problemTags: ProblemTag[];
  studyPlans?: StudyPlanSummary[];
  activeStudyPlanSlug?: string;
  activeStudyPlanGroupSlug?: string;
  activeStudyPlanItems?: StudyPlanItemsResponse;
  practiceQueue?: PracticeQueueResponse;
  practiceInsights?: PracticeInsightsResponse;
  selectedTaskId?: string;
  filters: Filters;
  onFiltersChange: (filters: Filters) => void;
  onStudyPlanChange?: (slug?: string) => void;
  onStudyPlanGroupChange?: (groupSlug?: string) => void;
  onSelect: (taskId: string) => void;
  onNextPractice: () => void;
  onClose?: () => void;
};

const INITIAL_VISIBLE_PROBLEM_COUNT = 180;
const VISIBLE_PROBLEM_STEP = 180;
const SHORT_TOPIC_LABELS: Record<string, string> = {
  "Dynamic Programming": "DP",
  "动态规划": "DP",
  "Depth-First Search": "DFS",
  "深度优先搜索": "DFS",
  "Breadth-First Search": "BFS",
  "广度优先搜索": "BFS",
  "Binary Search": "二分",
  "二分查找": "二分",
  "Two Pointers": "双指针",
  "Sliding Window": "滑窗",
  "Prefix Sum": "前缀和",
  "Hash Table": "哈希",
  "Matrix": "矩阵",
  "Bit Manipulation": "位运算",
  "Greedy": "贪心",
  "Sorting": "排序",
  "Backtracking": "回溯",
  "Union Find": "并查集",
  "Monotonic Stack": "单调栈",
  "Monotonic Queue": "单调队列",
  "Priority Queue": "优先队列",
  "Heap (Priority Queue)": "堆",
  "Heap": "堆",
  "Linked List": "链表",
  "Binary Tree": "二叉树",
  "Binary Search Tree": "BST",
  "Divide and Conquer": "分治",
  "Segment Tree": "线段树",
  "Binary Indexed Tree": "树状数组",
  "Ordered Set": "有序集",
  "Topological Sort": "拓扑",
  "Shortest Path": "最短路",
  "String Matching": "串匹配",
  "Hash Function": "哈希函数",
  "Rolling Hash": "滚哈希",
  "Number Theory": "数论",
  "Combinatorics": "组合",
  "Game Theory": "博弈",
  "Line Sweep": "扫描线",
  "Counting Sort": "计数排序",
  "Merge Sort": "归并",
  "Quickselect": "快选",
  "Simulation": "模拟",
  "Enumeration": "枚举",
  "Memoization": "记忆化",
  "Geometry": "几何",
  "Design": "设计"
};

function shortTopicLabel(tag: ProblemTag) {
  return SHORT_TOPIC_LABELS[tag.name] ?? SHORT_TOPIC_LABELS[tag.label] ?? tag.label;
}

export function ProblemList({
  problems,
  problemTags,
  studyPlans = [],
  activeStudyPlanSlug,
  activeStudyPlanGroupSlug,
  activeStudyPlanItems,
  practiceQueue,
  practiceInsights,
  selectedTaskId,
  filters,
  onFiltersChange,
  onStudyPlanChange,
  onStudyPlanGroupChange,
  onSelect,
  onNextPractice,
  onClose
}: Props) {
  const selectedTags = useMemo(() => filters.tags ?? [], [filters.tags]);
  const [visibleProblemCount, setVisibleProblemCount] = useState(INITIAL_VISIBLE_PROBLEM_COUNT);
  const topInsight = practiceInsights?.topics[0];
  const activeStudyPlan = activeStudyPlanItems?.plan ?? studyPlans.find((plan) => plan.slug === activeStudyPlanSlug);
  const activeStudyPlanGroups = activeStudyPlanItems?.groups ?? [];
  const selectedStudyPlanGroup = activeStudyPlanGroups.find((group) => group.group_slug === activeStudyPlanGroupSlug);
  const topicGroups = useMemo(
    () => problemTags.reduce<Array<{ category: string; label: string; count: number; tags: ProblemTag[] }>>(
      (groups, tag) => {
        let group = groups.find((item) => item.category === tag.category);
        if (!group) {
          group = { category: tag.category, label: tag.category_label, count: 0, tags: [] };
          groups.push(group);
        }
        group.count += tag.count;
        group.tags.push(tag);
        return groups;
      },
      []
    ),
    [problemTags]
  );
  const selectedTagLabels = selectedTags
    .map((name) => problemTags.find((tag) => tag.name === name)?.label ?? name);
  const tagLabelByName = useMemo(
    () => new Map(problemTags.flatMap((tag) => [[tag.name, tag.label], [tag.label, tag.label]])),
    [problemTags]
  );
  const visibleProblems = useMemo(
    () => problems.slice(0, visibleProblemCount),
    [problems, visibleProblemCount]
  );
  const hasMoreProblems = visibleProblems.length < problems.length;

  useEffect(() => {
    setVisibleProblemCount(INITIAL_VISIBLE_PROBLEM_COUNT);
  }, [filters, problems.length]);

  function toggleTag(tag: string) {
    const nextTags = selectedTags.includes(tag)
      ? selectedTags.filter((item) => item !== tag)
      : [...selectedTags, tag];
    onFiltersChange({ ...filters, tags: nextTags.length ? nextTags : undefined });
  }

  function handleProblemClick(problem: ProblemSummary) {
    if (problem.available === false) {
      if (problem.leetcode_url) {
        window.open(problem.leetcode_url, "_blank", "noopener,noreferrer");
      }
      return;
    }
    onSelect(problem.task_id);
  }

  function handleProblemKeyDown(event: KeyboardEvent<HTMLDivElement>, problem: ProblemSummary) {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    handleProblemClick(problem);
  }

  return (
    <aside className="sidebar problem-picker">
      <div className="brand">
        <div className="brand-mark">LC</div>
        <div>
          <h1>LeetCoach</h1>
          <span>本地练习 · AI 教练</span>
        </div>
        <button className="icon-button close-drawer" aria-label="关闭题单" onClick={onClose}>
          <X size={18} />
        </button>
      </div>

      <div className="picker-body">
        <div className="picker-controls">
          <section className="study-plan-card" aria-label="题单筛选">
            <div className="study-plan-head">
              <span>
                <BookMarked size={15} />
                题单
              </span>
              {activeStudyPlan ? (
                <small>
                  已过 {activeStudyPlan.passed_count}/{activeStudyPlan.total_count}
                  {activeStudyPlan.missing_count > 0 ? ` · 缺 ${activeStudyPlan.missing_count}` : ""}
                </small>
              ) : (
                <small>{problems.length} 题</small>
              )}
            </div>
            <div className="study-plan-tabs">
              <button
                type="button"
                className={!activeStudyPlanSlug ? "selected" : ""}
                onClick={() => onStudyPlanChange?.(undefined)}
              >
                全部题库
              </button>
              {studyPlans.map((plan) => (
                <button
                  type="button"
                  className={activeStudyPlanSlug === plan.slug ? "selected" : ""}
                  key={plan.slug}
                  onClick={() => onStudyPlanChange?.(plan.slug)}
                >
                  {plan.title.replace(" 题", "")}
                </button>
              ))}
            </div>
            {activeStudyPlan && (
              <div className="study-plan-progress">
                <div>
                  <strong>{Math.round(activeStudyPlan.progress * 100)}%</strong>
                  <span>
                    已通过 {activeStudyPlan.passed_count} · 需复习 {activeStudyPlan.needs_review_count} · 未开始 {activeStudyPlan.unseen_count}
                  </span>
                </div>
                <div className="study-plan-progress-track" aria-hidden="true">
                  <span style={{ width: `${Math.round(activeStudyPlan.progress * 100)}%` }} />
                </div>
              </div>
            )}
            {activeStudyPlanGroups.length > 0 && (
              <div className="study-plan-groups" aria-label="题单分组">
                <button
                  type="button"
                  className={!activeStudyPlanGroupSlug ? "selected" : ""}
                  onClick={() => onStudyPlanGroupChange?.(undefined)}
                >
                  全部分组
                  <small>{activeStudyPlan?.total_count ?? 0}</small>
                </button>
                {activeStudyPlanGroups.map((group) => (
                  <button
                    type="button"
                    className={activeStudyPlanGroupSlug === group.group_slug ? "selected" : ""}
                    key={group.group_slug}
                    onClick={() => onStudyPlanGroupChange?.(group.group_slug)}
                    title={`${group.group_name} · ${group.passed_count}/${group.total_count} 已过`}
                  >
                    {group.group_name}
                    <small>
                      {group.passed_count}/{group.total_count}
                      {group.missing_count > 0 ? ` · 缺 ${group.missing_count}` : ""}
                    </small>
                  </button>
                ))}
              </div>
            )}
          </section>

          <div className="filter-box">
            <label className="search-field">
              <Search size={16} />
              <input
                placeholder="搜索题号、中文名或 slug"
                value={filters.search ?? ""}
                onChange={(event) => onFiltersChange({ ...filters, search: event.target.value })}
              />
            </label>
            <div className="filter-row">
              <select
                value={filters.difficulty ?? ""}
                onChange={(event) => onFiltersChange({ ...filters, difficulty: event.target.value || undefined })}
              >
                <option value="">全部难度</option>
                <option value="Easy">简单</option>
                <option value="Medium">中等</option>
                <option value="Hard">困难</option>
              </select>
              <select
                value={filters.status ?? ""}
                onChange={(event) => onFiltersChange({ ...filters, status: event.target.value || undefined })}
              >
                <option value="">全部状态</option>
                <option value="unseen">未开始</option>
                <option value="needs_review">需复习</option>
                <option value="passed">已通过</option>
              </select>
            </div>
            <div className="topic-filter" aria-label="考点筛选">
              <div className="topic-filter-head">
                <span>考点{selectedTags.length > 0 ? ` · 已选 ${selectedTags.length}` : ""}</span>
                {selectedTags.length > 0 && (
                  <button onClick={() => onFiltersChange({ ...filters, tags: undefined })}>清空</button>
                )}
              </div>
              {selectedTags.length > 0 && (
                <div className="selected-topic-strip" aria-label="已选考点">
                  {selectedTagLabels.map((label) => (
                    <span key={label}>{label}</span>
                  ))}
                </div>
              )}
              <div className="topic-group-list" aria-label="考点分组">
                {topicGroups.map((group) => {
                  const selectedInGroup = group.tags.filter((tag) => selectedTags.includes(tag.name)).length;
                  return (
                    <section className={`topic-group ${selectedInGroup > 0 ? "has-selection" : ""}`} key={group.category}>
                      <div className="topic-group-title">
                        <strong>{group.label}</strong>
                        <small>
                          {selectedInGroup > 0 ? `已选 ${selectedInGroup} / ` : ""}
                          {group.tags.length} 个考点
                        </small>
                      </div>
                      <div className="topic-chip-list">
                        {group.tags.map((tag) => {
                          const selected = selectedTags.includes(tag.name);
                          return (
                            <button
                              key={tag.name}
                              className={`topic-chip ${selected ? "selected" : ""}`}
                              type="button"
                              aria-pressed={selected}
                              onClick={() => toggleTag(tag.name)}
                              title={[tag.label, tag.name, ...tag.aliases].filter(Boolean).join(" / ")}
                            >
                              <span>{shortTopicLabel(tag)}</span>
                              <small>{tag.count}</small>
                            </button>
                          );
                        })}
                      </div>
                    </section>
                  );
                })}
              </div>
            </div>
          </div>

          <section className="practice-queue-card">
            <div className="section-title">
              <Play size={15} />
              智能练习队列
            </div>
            <div className="practice-queue-meta">
              <span>{practiceQueue?.active_topics.length ? `当前考点：${practiceQueue.active_topics.join("、")}` : "按当前筛选生成队列"}</span>
              <small>{practiceQueue?.strategy ?? "待复习 > 未做高频 > 难度递进"}</small>
            </div>
            <button className="primary-button practice-next-button" disabled={!practiceQueue?.next_task_id} onClick={onNextPractice}>
              <Play size={15} />
              下一题
            </button>
            {practiceQueue?.items[0] && (
              <button
                className={`practice-next-card ${selectedTaskId === practiceQueue.items[0].task_id ? "selected" : ""}`}
                onClick={() => onSelect(practiceQueue.items[0].task_id)}
              >
                <span>#{practiceQueue.items[0].question_id}</span>
                <strong>{practiceQueue.items[0].title || formatSlug(practiceQueue.items[0].task_id)}</strong>
                <small>{practiceQueue.items[0].recommendation_reason}</small>
              </button>
            )}
            {topInsight && (
              <button
                className="practice-insight-card"
                disabled={!topInsight.next_task_id}
                onClick={() => topInsight.next_task_id && onSelect(topInsight.next_task_id)}
              >
                <span>
                  <Target size={13} />
                  薄弱考点
                </span>
                <strong>{topInsight.label}</strong>
                <small>
                  已过 {topInsight.passed_count}/{topInsight.total_problem_count} · {topInsight.recommendation}
                </small>
              </button>
            )}
          </section>
        </div>

        <section className="problem-results-panel">
          <div className="problem-list-head">
            <span>{activeStudyPlan ? `${activeStudyPlan.title}${selectedStudyPlanGroup ? ` · ${selectedStudyPlanGroup.group_name}` : ""}` : "题库结果"}</span>
            <strong>
              {visibleProblems.length < problems.length
                ? `已显示 ${visibleProblems.length}/${problems.length} 题`
                : `${problems.length} 题`}
            </strong>
          </div>
          <div className="problem-list">
            <div className="problem-table-header" aria-hidden="true">
              <span>#</span>
              <span>难度</span>
              <span>题目 / 考点</span>
              <span>{activeStudyPlan ? "分组 / 状态" : "热度 / 状态"}</span>
            </div>
            {visibleProblems.map((problem) => {
              const topicLabels = problem.tags.map((tag) => tagLabelByName.get(tag) ?? tag);
              const visibleTopicLabels = topicLabels.slice(0, 3);
              const hiddenTopicCount = Math.max(topicLabels.length - visibleTopicLabels.length, 0);
              return (
                <div
                  key={problem.task_id}
                  className={`problem-row ${selectedTaskId === problem.task_id ? "selected" : ""} ${problem.available === false ? "missing" : ""}`}
                  onClick={() => handleProblemClick(problem)}
                  onKeyDown={(event) => handleProblemKeyDown(event, problem)}
                  role="button"
                  tabIndex={0}
                  title={problem.available === false ? "本地题库暂未补入，点击打开 LeetCode 原题" : undefined}
                >
                  <span className="problem-row-number">{problem.question_id}</span>
                  <span className={`difficulty problem-row-difficulty ${problem.difficulty.toLowerCase()}`}>
                    {difficultyLabel(problem.difficulty)}
                  </span>
                  <div className="problem-row-main">
                    <div className="problem-title-line">
                      <strong className="problem-row-title">{problem.title || formatSlug(problem.task_id)}</strong>
                      {problem.group_name && (
                        <span className="problem-topic-pill plan-group">{problem.group_name}</span>
                      )}
                      {visibleTopicLabels.length > 0 && (
                        <span className="problem-topic-pills" aria-label={`考点：${topicLabels.join("、")}`}>
                          {visibleTopicLabels.map((label) => (
                            <span className="problem-topic-pill" key={label}>{label}</span>
                          ))}
                          {hiddenTopicCount > 0 && (
                            <span className="problem-topic-pill more">+{hiddenTopicCount}</span>
                          )}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="problem-row-meta">
                    <span className="problem-row-heat">
                      <HeatBadge frequency={problem.codetop_frequency} compact />
                    </span>
                    <span className={`status ${problem.status}`}>
                      {problem.status === "passed" && <CheckCircle2 size={13} />}
                      {statusLabel(problem.status)}
                    </span>
                  </div>
                </div>
              );
            })}
            {hasMoreProblems && (
              <div className="problem-list-more">
                <button
                  type="button"
                  onClick={() => setVisibleProblemCount((count) => Math.min(count + VISIBLE_PROBLEM_STEP, problems.length))}
                >
                  加载更多题目
                  <span>还有 {problems.length - visibleProblems.length} 题</span>
                </button>
              </div>
            )}
          </div>
        </section>
      </div>
    </aside>
  );
}

function HeatBadge({ frequency, compact = false }: { frequency?: number | null; compact?: boolean }) {
  if (!frequency) return null;
  return (
    <span className={`heat ${heatLevel(frequency)}`} title={`CodeTop 热度 ${frequency}`}>
      <Flame size={13} />
      {compact ? frequency : `热度 ${frequency}`}
    </span>
  );
}

function heatLevel(frequency: number) {
  if (frequency >= 500) return "critical";
  if (frequency >= 200) return "high";
  if (frequency >= 80) return "medium";
  return "low";
}
