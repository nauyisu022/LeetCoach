from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from ..notes import fetch_note, fetch_note_topics
from ..practice import topic_names_for_problem
from ..topic_taxonomy import display_topic_labels, normalize_topic_name, topic_aliases
from .artifacts import RECOMMENDATION_SET_TYPE
from .memory import (
    fetch_accepted_memories_for_context,
    fetch_recent_learning_events_for_context,
    learning_event_rows_for_prompt,
    memory_rows_for_prompt,
)
from .turn import AgentTurnInput


@dataclass(frozen=True)
class ToolResult:
    name: str
    payload: dict[str, Any]
    prompt_section: str = ""
    ok: bool = True

    def as_prompt_section(self) -> str:
        return self.prompt_section


@dataclass(frozen=True)
class AgentToolSpec:
    name: str
    description: str
    trigger: str
    prompt_visibility: str


@dataclass(frozen=True)
class AgentToolRequest:
    conn: sqlite3.Connection
    turn: AgentTurnInput
    problem: dict[str, Any]
    current_topics: list[str]


class AgentTool(Protocol):
    name: str

    def should_run(self, request: AgentToolRequest) -> bool:
        ...

    def run(self, request: AgentToolRequest) -> ToolResult:
        ...


class ProblemSearchTool:
    name = "problem_search"
    spec = AgentToolSpec(
        name=name,
        description="Search the local problem catalog for related or next-practice problems.",
        trigger="Runs for /search-problems, /next, or problem recommendation/search wording.",
        prompt_visibility="Visible as a tool result section when it runs.",
    )

    def should_run(self, request: AgentToolRequest) -> bool:
        return should_search_problems(request.turn.command, request.turn.message)

    def run(self, request: AgentToolRequest) -> ToolResult:
        return self.search(
            request.conn,
            query=request.turn.message or request.turn.command,
            current_task_id=request.turn.task_id,
            current_topics=request.current_topics,
        )

    def search(
        self,
        conn: sqlite3.Connection,
        *,
        query: str,
        current_task_id: str | None,
        current_topics: list[str],
        limit: int = 8,
    ) -> ToolResult:
        normalized_query = " ".join(query.split())
        interpreted_topics = _interpreted_topics(normalized_query, current_topics)
        terms = _search_terms(normalized_query)
        rows = _search_problem_rows(
            conn,
            query=normalized_query,
            terms=terms,
            topics=interpreted_topics,
            current_task_id=current_task_id,
            limit=limit,
        )
        payload = {
            "query": normalized_query,
            "interpreted_topics": list(dict.fromkeys(display_topic_labels(interpreted_topics))),
            "results": [_problem_payload(row) for row in rows],
        }
        return ToolResult(name=self.name, payload=payload, prompt_section=_problem_search_prompt_section(payload))


def search_problem_catalog(
    conn: sqlite3.Connection,
    *,
    query: str,
    current_task_id: str | None = None,
    limit: int = 8,
) -> ToolResult:
    current_topics = list(topic_names_for_problem(conn, current_task_id)) if current_task_id else []
    return ProblemSearchTool().search(
        conn,
        query=query,
        current_task_id=current_task_id,
        current_topics=current_topics,
        limit=limit,
    )


class JudgeContextTool:
    name = "judge_context"
    spec = AgentToolSpec(
        name=name,
        description="Resolve the current code and latest failure context from frontend run result or submissions.",
        trigger="Runs on every agent turn.",
        prompt_visibility="Visible only when failure context exists.",
    )

    def should_run(self, request: AgentToolRequest) -> bool:
        return True

    def run(self, request: AgentToolRequest) -> ToolResult:
        resolved_code = request.turn.code or ""
        failure = None
        submission = None

        if request.turn.current_result and request.turn.current_result.task_id == request.turn.task_id:
            failure = _failure_from_current_result(request.turn.current_result)
        elif request.turn.submission_id:
            submission = request.conn.execute(
                "SELECT * FROM submissions WHERE user_id = ? AND id = ?",
                (request.turn.user_id, request.turn.submission_id),
            ).fetchone()
        else:
            submission = request.conn.execute(
                "SELECT * FROM submissions WHERE user_id = ? AND task_id = ? ORDER BY id DESC LIMIT 1",
                (request.turn.user_id, request.turn.task_id),
            ).fetchone()

        if submission:
            resolved_code = resolved_code or submission["code"]
            if not submission["passed"]:
                failure = {
                    "source": "submission_history",
                    "mode": "submit",
                    "submission_id": submission["id"],
                    "failed_assertion": submission["failed_assertion"],
                    "stderr": submission["stderr"],
                    "runtime_ms": submission["runtime_ms"],
                }

        payload = {
            "resolved_code": resolved_code,
            "failure": failure,
        }
        return ToolResult(name=self.name, payload=payload, prompt_section=_judge_context_prompt_section(failure))


class NoteContextTool:
    name = "note_context"
    spec = AgentToolSpec(
        name=name,
        description="Read the current problem's saved practice note and note topics.",
        trigger="Runs for note, review, memory, note-draft, or note/review wording.",
        prompt_visibility="Visible as a tool result section when it runs.",
    )

    def should_run(self, request: AgentToolRequest) -> bool:
        return should_fetch_note_context(request.turn.command, request.turn.message)

    def run(self, request: AgentToolRequest) -> ToolResult:
        row = fetch_note(request.conn, user_id=request.turn.user_id, task_id=request.turn.task_id)
        note = None
        if row:
            note = {
                "id": row["id"],
                "task_id": row["task_id"],
                "content_markdown": _truncate_text(row["content_markdown"], 1400),
                "ai_summary": row["ai_summary"],
                "mistake_summary": row["mistake_summary"],
                "invariant_summary": row["invariant_summary"],
                "solution_pattern": row["solution_pattern"],
                "review_at": row["review_at"],
                "topics": display_topic_labels(fetch_note_topics(request.conn, row["id"])),
                "updated_at": row["updated_at"],
            }
        payload = {"note": note}
        return ToolResult(name=self.name, payload=payload, prompt_section=_note_context_prompt_section(note))


class SolutionContextTool:
    name = "solution_context"
    spec = AgentToolSpec(
        name=name,
        description="Read current editor code, saved solution draft, and latest accepted submission.",
        trigger="Runs for diagnose, code-review, note, note-draft, review, or code/solution wording.",
        prompt_visibility="Visible as a tool result section when it runs.",
    )

    def should_run(self, request: AgentToolRequest) -> bool:
        return should_fetch_solution_context(request.turn.command, request.turn.message)

    def run(self, request: AgentToolRequest) -> ToolResult:
        saved_row = request.conn.execute(
            """
            SELECT id, user_id, task_id, code, language, notes, created_at, updated_at
            FROM user_solutions
            WHERE user_id = ? AND task_id = ?
            """,
            (request.turn.user_id, request.turn.task_id),
        ).fetchone()
        accepted_row = request.conn.execute(
            """
            SELECT id, task_id, code, runtime_ms, execution_ms, test_count_estimate, passed_test_count, created_at
            FROM submissions
            WHERE user_id = ? AND task_id = ? AND passed = 1
            ORDER BY id DESC
            LIMIT 1
            """,
            (request.turn.user_id, request.turn.task_id),
        ).fetchone()
        current_code = request.turn.code or ""
        saved_solution = None
        if saved_row:
            saved_solution = {
                "id": saved_row["id"],
                "language": saved_row["language"],
                "notes": saved_row["notes"],
                "code": _truncate_text(saved_row["code"], 1800),
                "same_as_current": bool(current_code and saved_row["code"] == current_code),
                "updated_at": saved_row["updated_at"],
            }
        accepted_submission = None
        if accepted_row:
            accepted_submission = {
                "id": accepted_row["id"],
                "code": _truncate_text(accepted_row["code"], 1800),
                "runtime_ms": accepted_row["runtime_ms"],
                "execution_ms": accepted_row["execution_ms"],
                "test_count_estimate": accepted_row["test_count_estimate"],
                "passed_test_count": accepted_row["passed_test_count"],
                "created_at": accepted_row["created_at"],
            }
        payload = {
            "current_code": _truncate_text(current_code, 1800) if current_code else None,
            "saved_solution": saved_solution,
            "latest_accepted_submission": accepted_submission,
        }
        return ToolResult(name=self.name, payload=payload, prompt_section=_solution_context_prompt_section(payload))


class MemoryContextTool:
    name = "memory_context"
    spec = AgentToolSpec(
        name=name,
        description="Read accepted task, topic, and global learning memories for the current turn.",
        trigger="Runs on every agent turn.",
        prompt_visibility="Not rendered as a separate tool section; injected through practice_context.accepted_memories.",
    )

    def should_run(self, request: AgentToolRequest) -> bool:
        return True

    def run(self, request: AgentToolRequest) -> ToolResult:
        rows = fetch_accepted_memories_for_context(
            request.conn,
            user_id=request.turn.user_id,
            task_id=request.turn.task_id,
            topics=request.current_topics,
        )
        return ToolResult(
            name=self.name,
            payload={
                "topics": request.current_topics,
                "memories": memory_rows_for_prompt(rows),
            },
        )


class LearningEventContextTool:
    name = "learning_event_context"
    spec = AgentToolSpec(
        name=name,
        description="Read recent task/topic learning events as short-term learning state.",
        trigger="Runs on every agent turn.",
        prompt_visibility="Visible only when recent learning events exist.",
    )

    def should_run(self, request: AgentToolRequest) -> bool:
        return True

    def run(self, request: AgentToolRequest) -> ToolResult:
        rows = fetch_recent_learning_events_for_context(
            request.conn,
            user_id=request.turn.user_id,
            task_id=request.turn.task_id,
            topics=request.current_topics,
        )
        events = learning_event_rows_for_prompt(rows)
        return ToolResult(
            name=self.name,
            payload={"events": events},
            prompt_section=_learning_event_context_prompt_section(events),
        )


class ArtifactContextTool:
    name = "artifact_context"
    spec = AgentToolSpec(
        name=name,
        description="Read active agent artifacts that explain the user's current learning path.",
        trigger="Runs on every agent turn.",
        prompt_visibility="Visible only when a current artifact is relevant.",
    )

    def should_run(self, request: AgentToolRequest) -> bool:
        return True

    def run(self, request: AgentToolRequest) -> ToolResult:
        rows = request.conn.execute(
            """
            SELECT *
            FROM agent_artifacts
            WHERE user_id = ?
              AND artifact_type = ?
              AND status = 'active'
            ORDER BY id DESC
            LIMIT 5
            """,
            (request.turn.user_id, RECOMMENDATION_SET_TYPE),
        ).fetchall()
        artifact = None
        for row in rows:
            payload = json.loads(row["payload_json"])
            task_ids = {item.get("task_id") for item in payload.get("items") or []}
            if row["source_task_id"] == request.turn.task_id or request.turn.task_id in task_ids:
                artifact = {
                    "id": row["id"],
                    "type": row["artifact_type"],
                    "source_task_id": row["source_task_id"],
                    "title": row["title"],
                    "query": payload.get("query"),
                    "interpreted_topics": payload.get("interpreted_topics") or [],
                    "items": payload.get("items") or [],
                    "created_at": row["created_at"],
                }
                break
        payload = {"artifact": artifact}
        return ToolResult(name=self.name, payload=payload, prompt_section=_artifact_context_prompt_section(artifact))


def default_agent_tools() -> list[AgentTool]:
    return [
        JudgeContextTool(),
        SolutionContextTool(),
        NoteContextTool(),
        MemoryContextTool(),
        LearningEventContextTool(),
        ArtifactContextTool(),
        ProblemSearchTool(),
    ]


def default_agent_tool_specs() -> list[AgentToolSpec]:
    return [agent_tool_spec(tool) for tool in default_agent_tools()]


def agent_tool_spec(tool: AgentTool) -> AgentToolSpec:
    spec = getattr(tool, "spec", None)
    if isinstance(spec, AgentToolSpec):
        return spec
    return AgentToolSpec(
        name=tool.name,
        description="Custom agent tool.",
        trigger="Injected by caller.",
        prompt_visibility="Depends on the custom tool result.",
    )


def run_agent_tools(
    request: AgentToolRequest,
    tools: Sequence[AgentTool] | None = None,
) -> list[ToolResult]:
    results: list[ToolResult] = []
    selected_tools = default_agent_tools() if tools is None else tools
    for tool in selected_tools:
        try:
            should_run = tool.should_run(request)
        except Exception as exc:
            results.append(_tool_error_result(tool, "should_run", exc))
            continue
        if not should_run:
            continue
        try:
            results.append(tool.run(request))
        except Exception as exc:
            results.append(_tool_error_result(tool, "run", exc))
    return results


def _tool_error_result(tool: AgentTool, stage: str, exc: Exception) -> ToolResult:
    name = str(getattr(tool, "name", tool.__class__.__name__))
    error_type = type(exc).__name__
    error_message = _truncate_text(str(exc), 500) or error_type
    payload = {
        "error": {
            "stage": stage,
            "type": error_type,
            "message": error_message,
        }
    }
    prompt_section = f"工具结果：{name} 运行失败，阶段={stage}，错误={error_type}: {error_message}"
    return ToolResult(name=name, payload=payload, prompt_section=prompt_section, ok=False)


def _problem_search_prompt_section(payload: dict[str, Any]) -> str:
    results = payload.get("results") or []
    if not results:
        return "工具结果：本地题库搜索没有找到匹配题目。"
    lines = ["工具结果：已搜索本地题库，候选题如下。"]
    interpreted_topics = payload.get("interpreted_topics") or []
    if interpreted_topics:
        lines.append(f"解释出的主题：{', '.join(interpreted_topics)}")
    for index, item in enumerate(results, start=1):
        tags = ", ".join(item.get("tags") or [])
        title = item.get("title") or item.get("task_id")
        task_id = item.get("task_id")
        lines.append(
            f"{index}. [{item.get('question_id')}. {title}](/problems/{task_id}) ({task_id})"
            f" | {item.get('difficulty')} | {tags}"
        )
    return "\n".join(lines)


def _judge_context_prompt_section(failure: dict[str, Any] | None) -> str:
    if not failure:
        return ""
    return f"工具结果：当前判题上下文\n{failure}"


def _note_context_prompt_section(note: dict[str, Any] | None) -> str:
    if not note:
        return "工具结果：当前题还没有保存的复习笔记。"
    lines = ["工具结果：当前题已有复习笔记。"]
    if note.get("topics"):
        lines.append(f"笔记主题：{', '.join(note['topics'])}")
    for label, key in (
        ("AI 摘要", "ai_summary"),
        ("错误总结", "mistake_summary"),
        ("关键不变量", "invariant_summary"),
        ("解法范式", "solution_pattern"),
    ):
        value = note.get(key)
        if value:
            lines.append(f"{label}: {value}")
    content = note.get("content_markdown")
    if content:
        lines.append(f"笔记正文摘录:\n{content}")
    return "\n".join(lines)


def _artifact_context_prompt_section(artifact: dict[str, Any] | None) -> str:
    if not artifact:
        return ""
    lines = [
        "工具结果：当前学习路径 artifact。",
        f"类型：{artifact.get('type')}",
        f"来源题：{artifact.get('source_task_id')}",
        f"标题：{artifact.get('title')}",
        f"用户原问题：{artifact.get('query')}",
    ]
    topics = artifact.get("interpreted_topics") or []
    if topics:
        lines.append(f"主题：{'、'.join(topics)}")
    items = artifact.get("items") or []
    if items:
        lines.append("同一题单：")
        for item in items[:8]:
            lines.append(
                f"- {item.get('question_id')}. {item.get('title')} ({item.get('task_id')}) "
                f"{item.get('difficulty')}"
            )
    lines.append("回答时可利用这条学习路径说明用户为什么来到当前题，但不要复述完整旧聊天。")
    return "\n".join(lines)


def _learning_event_context_prompt_section(events: list[dict[str, str]]) -> str:
    if not events:
        return ""
    lines = ["工具结果：近期学习事件（短期/近期状态，不等同于长期记忆）。"]
    for event in events[:6]:
        source = event.get("task_id") or event.get("topic") or "global"
        lines.append(f"- [{event.get('type')}] {source}: {event.get('content')}")
    lines.append("回答时优先利用这些事件保持练习连续性；如果和当前题无关，不要强行引用。")
    return "\n".join(lines)


def _solution_context_prompt_section(payload: dict[str, Any]) -> str:
    lines = ["工具结果：当前解法上下文。"]
    current_code = payload.get("current_code")
    saved = payload.get("saved_solution")
    accepted = payload.get("latest_accepted_submission")
    if current_code:
        lines.append(f"当前编辑器代码:\n```python\n{current_code}\n```")
    if saved:
        lines.append(
            "已保存草稿: "
            f"language={saved.get('language')}, updated_at={saved.get('updated_at')}, "
            f"same_as_current={saved.get('same_as_current')}"
        )
        if saved.get("notes"):
            lines.append(f"草稿备注: {saved['notes']}")
        if saved.get("code") and not saved.get("same_as_current"):
            lines.append(f"已保存草稿代码摘录:\n```python\n{saved['code']}\n```")
    else:
        lines.append("当前题还没有保存草稿。")
    if accepted:
        lines.append(
            f"最近通过提交: id={accepted.get('id')}, passed_test_count={accepted.get('passed_test_count')}/"
            f"{accepted.get('test_count_estimate')}, created_at={accepted.get('created_at')}"
        )
        if accepted.get("code") and accepted.get("code") != current_code:
            lines.append(f"最近通过代码摘录:\n```python\n{accepted['code']}\n```")
    return "\n".join(lines)


def _search_problem_rows(
    conn: sqlite3.Connection,
    *,
    query: str,
    terms: list[str],
    topics: list[str],
    current_task_id: str | None,
    limit: int,
) -> list[sqlite3.Row]:
    score_params: list[Any] = []
    where_params: list[Any] = []
    score_parts: list[str] = []
    where_parts: list[str] = []

    for term in terms[:6]:
        like = f"%{term}%"
        score_parts.append(
            """
            CASE
              WHEN p.title_zh LIKE ? THEN 10
              WHEN p.task_id LIKE ? THEN 8
              WHEN CAST(p.question_id AS TEXT) = ? THEN 10
              ELSE 0
            END
            """
        )
        score_params.extend([like, like, term])
        where_parts.append("(p.title_zh LIKE ? OR p.task_id LIKE ? OR CAST(p.question_id AS TEXT) = ?)")
        where_params.extend([like, like, term])

    for topic in topics[:5]:
        aliases = topic_aliases(topic)
        placeholders = ", ".join("?" for _ in aliases)
        score_parts.append(
            f"CASE WHEN EXISTS (SELECT 1 FROM json_each(p.tags_json) WHERE value IN ({placeholders})) THEN 5 ELSE 0 END"
        )
        score_params.extend(aliases)
        where_parts.append(f"EXISTS (SELECT 1 FROM json_each(p.tags_json) WHERE value IN ({placeholders}))")
        where_params.extend(aliases)

    if not where_parts:
        where_parts.append("1 = 1")

    score_sql = " + ".join(score_parts) if score_parts else "0"
    current_filter = ""
    if current_task_id:
        current_filter = "AND p.task_id != ?"
        where_params.append(current_task_id)
    params = [*score_params, *where_params, limit]
    return conn.execute(
        f"""
        SELECT p.task_id, p.question_id, p.title_zh, p.difficulty, p.tags_json,
               COALESCE(c.frequency, 0) AS codetop_frequency,
               ({score_sql}) AS relevance_score
        FROM problems p
        LEFT JOIN codetop_problem_signals c ON c.task_id = p.task_id
        WHERE ({' OR '.join(where_parts)})
          {current_filter}
        ORDER BY relevance_score DESC,
                 COALESCE(c.frequency, 0) DESC,
                 CASE p.difficulty WHEN 'Easy' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END,
                 p.question_id
        LIMIT ?
        """,
        params,
    ).fetchall()


def _problem_payload(row: sqlite3.Row) -> dict[str, Any]:
    raw_tags = json.loads(row["tags_json"])
    return {
        "task_id": row["task_id"],
        "question_id": row["question_id"],
        "title": row["title_zh"] or row["task_id"],
        "difficulty": row["difficulty"],
        "tags": display_topic_labels(raw_tags),
        "codetop_frequency": row["codetop_frequency"],
    }


def _interpreted_topics(query: str, current_topics: list[str]) -> list[str]:
    lowered = query.lower()
    topics: list[str] = []
    concept_map = {
        "树形dp": ["Tree", "Binary Tree", "Dynamic Programming"],
        "树形 dp": ["Tree", "Binary Tree", "Dynamic Programming"],
        "动态规划": ["Dynamic Programming"],
        "dp": ["Dynamic Programming"],
        "回溯": ["Backtracking"],
        "dfs": ["Depth-First Search"],
        "深搜": ["Depth-First Search"],
        "二叉树": ["Binary Tree"],
        "树": ["Tree"],
        "哈希": ["Hash Table"],
        "堆": ["Heap (Priority Queue)"],
        "优先队列": ["Heap (Priority Queue)"],
        "二分": ["Binary Search"],
        "滑窗": ["Sliding Window"],
        "双指针": ["Two Pointers"],
    }
    for keyword, mapped_topics in concept_map.items():
        if keyword in lowered or keyword in query:
            topics.extend(mapped_topics)
    for topic in current_topics:
        if topic:
            topics.append(normalize_topic_name(topic))
    return list(dict.fromkeys(topics))


def _search_terms(query: str) -> list[str]:
    cleaned = re.sub(r"[，。！？、；：,.!?;:()（）\[\]【】]", " ", query)
    stop_words = {
        "有哪些",
        "经典题",
        "经典",
        "题目",
        "相关",
        "类似",
        "推荐",
        "同类",
        "本题",
        "leetcode",
        "LeetCode",
    }
    terms = [item.strip() for item in cleaned.split() if item.strip() and item.strip() not in stop_words]
    if "打家劫舍" in query:
        terms.extend(["打家劫舍", "house-robber"])
    return list(dict.fromkeys(terms))


def should_search_problems(command: str, message: str | None) -> bool:
    if command in {"/search-problems", "/next"}:
        return True
    text = message or ""
    triggers = (
        "经典题",
        "类似题",
        "同类题",
        "相关题",
        "推荐",
        "有哪些题",
        "找几道",
        "下一题",
        "练习题",
    )
    return any(trigger in text for trigger in triggers)


def should_fetch_note_context(command: str, message: str | None) -> bool:
    if command in {"/note", "/note-draft", "/review", "/memory"}:
        return True
    text = (message or "").lower()
    triggers = ("笔记", "note", "notes", "复习", "总结", "错题")
    return any(trigger in text for trigger in triggers)


def should_fetch_solution_context(command: str, message: str | None) -> bool:
    if command in {"/diagnose", "/code-review", "/note", "/note-draft", "/review"}:
        return True
    text = (message or "").lower()
    triggers = ("代码", "实现", "草稿", "解法", "提交", "通过", "code", "solution")
    return any(trigger in text for trigger in triggers)


def judge_context_from_results(tool_results: list[ToolResult], fallback_code: str | None = None) -> tuple[str, dict[str, Any] | None]:
    for result in tool_results:
        if result.name != "judge_context":
            continue
        return result.payload.get("resolved_code") or fallback_code or "", result.payload.get("failure")
    return fallback_code or "", None


def memory_context_from_results(tool_results: list[ToolResult]) -> list[dict[str, str]]:
    for result in tool_results:
        if result.name != "memory_context":
            continue
        memories = result.payload.get("memories") or []
        return [
            {"scope": str(item.get("scope") or "memory"), "content": str(item.get("content") or "")}
            for item in memories
            if item.get("content")
        ]
    return []


def note_content_from_results(tool_results: list[ToolResult]) -> str | None:
    for result in tool_results:
        if result.name != "note_context":
            continue
        note = result.payload.get("note") or {}
        content = note.get("content_markdown")
        return str(content) if content else None
    return None


def _failure_from_current_result(current_result: Any) -> dict[str, Any] | None:
    if current_result.passed:
        return None
    failure: dict[str, Any] = {
        "source": "current_frontend_result",
        "mode": current_result.mode,
        "status": current_result.status,
        "summary": current_result.summary,
        "failed_assertion": current_result.failed_assertion,
        "stderr": current_result.stderr,
        "stdout": current_result.stdout,
        "return_output": current_result.return_output,
        "runtime_ms": current_result.runtime_ms,
        "execution_ms": current_result.execution_ms,
        "passed_test_count": current_result.passed_test_count,
        "test_count_estimate": current_result.test_count_estimate,
    }
    case_failures = []
    for item in current_result.case_results or []:
        response = item.get("response") or {}
        if response.get("passed"):
            continue
        case = item.get("case") or {}
        case_failures.append(
            {
                "name": case.get("name"),
                "input": _truncate_text(case.get("input"), 800),
                "expected_output": _truncate_text(case.get("expectedOutput"), 400),
                "failed_assertion": _truncate_text(response.get("failed_assertion"), 800),
                "stderr": _truncate_text(response.get("stderr"), 800),
                "stdout": _truncate_text(response.get("stdout"), 400),
                "return_output": _truncate_text(response.get("return_output"), 400),
            }
        )
    if case_failures:
        failure["case_failures"] = case_failures[:4]
    return {key: value for key, value in failure.items() if value is not None}


def _truncate_text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else f"{text[:limit]}..."
