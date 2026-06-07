export function difficultyLabel(difficulty: string): string {
  if (difficulty === "Easy") return "简单";
  if (difficulty === "Medium") return "中等";
  if (difficulty === "Hard") return "困难";
  return difficulty;
}

export function statusLabel(status: string): string {
  if (status === "unseen") return "未开始";
  if (status === "needs_review") return "需复习";
  if (status === "passed") return "已通过";
  if (status === "attempted") return "已尝试";
  return status.replace("_", " ");
}
