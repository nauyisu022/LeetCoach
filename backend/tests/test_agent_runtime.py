from fastapi.testclient import TestClient

from app.agent_api import AgentApiService, agent_request_from_coach_chat_request, agent_request_from_coach_request
from app.agent_runtime.commands import command_manifest
from app.agent_runtime.context import build_agent_context
from app.agent_runtime.hooks import AfterCoachResponseEvent, HookResult, run_after_coach_response_hooks
from app.agent_runtime.inspection import (
    agent_command_manifest_items,
    agent_profile_manifest_item,
    agent_tool_manifest_items,
    inspect_agent_invocation,
)
from app.agent_runtime.memory import (
    fetch_memory_records,
    fetch_thread_summary_record,
    memory_record_from_row,
    set_memory_record_status,
    thread_summary_record_from_row,
    update_memory_record,
)
from app.agent_runtime.problem_context import build_agent_problem_payload
from app.agent_runtime.runtime import (
    AgentCommandPlan,
    AgentRuntimeConfig,
    build_agent_invocation,
    build_command_plan,
    default_agent_runtime_config,
    default_agent_runtime_profile,
    normalize_command,
)
from app.agent_runtime.service import (
    AI_EMPTY_RESPONSE_TEXT,
    AgentStreamTurn,
    stream_agent_invocation,
    stream_agent_turn,
    stream_ai_text,
    stream_note_draft_invocation,
)
from app.agent_runtime.tools import (
    AgentToolRequest,
    JudgeContextTool,
    LearningEventContextTool,
    MemoryContextTool,
    NoteContextTool,
    ProblemSearchTool,
    SolutionContextTool,
    ToolResult,
    default_agent_tool_specs,
    judge_context_from_results,
    memory_context_from_results,
    run_agent_tools,
    search_problem_catalog,
)
from app.agent_runtime.turn import AgentTurnInput
from app.db import get_connection, init_db
from app.schemas import AgentCommandRequest, CoachChatRequest, CoachCurrentResult, CoachRequest


EXPECTED_DEFAULT_TOOL_NAMES = [
    "judge_context",
    "solution_context",
    "note_context",
    "memory_context",
    "learning_event_context",
    "artifact_context",
    "problem_search",
]


def _insert_problem(
    conn,
    task_id: str = "two-sum",
    *,
    question_id: int = 1,
    title_zh: str = "两数之和",
    tags_json: str = '["Array", "Hash Table"]',
) -> None:
    conn.execute(
        """
        INSERT INTO problems (
            task_id, question_id, difficulty, tags_json, problem_description,
            title_zh, starter_code, entry_point, test_code, input_output_json, prompt, completion
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task_id,
            question_id,
            "Easy",
            tags_json,
            "description",
            title_zh,
            "code",
            "Solution().twoSum",
            "def check(candidate):\n    assert True",
            "[]",
            "from typing import *",
            "",
        ),
    )


def _problem_payload(
    task_id: str = "two-sum",
    *,
    question_id: int = 1,
    difficulty: str = "Easy",
    tags: list[str] | None = None,
    problem_description: str = "description",
) -> dict:
    return {
        "task_id": task_id,
        "question_id": question_id,
        "difficulty": difficulty,
        "tags": tags or ["Array", "Hash Table"],
        "problem_description": problem_description,
        "practice_context": {},
    }


def _insert_house_robber_family(conn) -> None:
    _insert_problem(
        conn,
        "house-robber",
        question_id=198,
        title_zh="打家劫舍",
        tags_json='["Array", "Dynamic Programming"]',
    )
    _insert_problem(
        conn,
        "house-robber-ii",
        question_id=213,
        title_zh="打家劫舍 II",
        tags_json='["Array", "Dynamic Programming"]',
    )
    _insert_problem(
        conn,
        "house-robber-iii",
        question_id=337,
        title_zh="打家劫舍 III",
        tags_json='["Tree", "Depth-First Search", "Dynamic Programming", "Binary Tree"]',
    )


def test_problem_search_tool_uses_local_catalog(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_house_robber_family(conn)

    result = ProblemSearchTool().search(
        conn,
        query="打家劫舍 有哪些经典题",
        current_task_id="house-robber-iii",
        current_topics=["Tree", "Dynamic Programming", "树", "动态规划"],
    )
    task_ids = [item["task_id"] for item in result.payload["results"]]
    assert "house-robber" in task_ids
    assert "house-robber-ii" in task_ids
    assert "house-robber-iii" not in task_ids
    assert result.payload["interpreted_topics"].count("树") == 1
    assert result.payload["interpreted_topics"].count("动态规划") == 1
    assert "打家劫舍" in result.as_prompt_section()
    conn.close()


def test_search_problem_catalog_resolves_current_topics(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_house_robber_family(conn)

    result = search_problem_catalog(
        conn,
        query="有哪些经典题",
        current_task_id="house-robber-iii",
        limit=4,
    )
    task_ids = [item["task_id"] for item in result.payload["results"]]

    assert result.name == "problem_search"
    assert "动态规划" in result.payload["interpreted_topics"]
    assert "house-robber" in task_ids
    assert "house-robber-iii" not in task_ids
    conn.close()


def test_agent_problem_search_creates_latest_recommendation_set(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_house_robber_family(conn)
    conn.close()

    def connection_factory():
        return get_connection(db_path)

    service = AgentApiService(
        user_id="local",
        connection_factory=connection_factory,
        problem_loader=lambda task_id: {"task_id": task_id},
    )

    search = service.problem_search_response(
        query="打家劫舍 类似题",
        current_task_id="house-robber-iii",
        limit=4,
    )
    latest = service.latest_recommendation_set_response(source_task_id="house-robber-iii")

    assert search.recommendation_set_id is not None
    assert latest.recommendation_set is not None
    assert latest.recommendation_set.id == search.recommendation_set_id
    assert latest.recommendation_set.source_task_id == "house-robber-iii"
    assert [item.task_id for item in latest.recommendation_set.items][:2] == [
        "house-robber",
        "house-robber-ii",
    ]


def test_agent_context_runs_injected_tools(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)

    class FakeTool:
        name = "fake_tool"

        def __init__(self):
            self.seen_request = None

        def should_run(self, request: AgentToolRequest) -> bool:
            self.seen_request = request
            return request.turn.command == "/fake"

        def run(self, request: AgentToolRequest) -> ToolResult:
            return ToolResult(
                name=self.name,
                payload={
                    "task_id": request.turn.task_id,
                    "message": request.turn.message,
                    "code": request.turn.code,
                    "thinking_mode": request.turn.thinking_mode,
                    "topics": request.current_topics,
                },
            )

    tool = FakeTool()
    turn = AgentTurnInput(
        user_id="local",
        task_id="two-sum",
        command="/fake",
        message="tool smoke test",
        code="class Solution: pass",
        submission_id=None,
        current_result=None,
        thinking_mode="enabled",
    )
    context = build_agent_context(
        conn,
        turn=turn,
        problem={"tags": ["Hash Table"]},
        tools=[tool],
    )

    assert tool.seen_request is not None
    assert tool.seen_request.problem["tags"] == ["Hash Table"]
    assert context.tool_results == [
        ToolResult(
            name="fake_tool",
            payload={
                "task_id": "two-sum",
                "message": "tool smoke test",
                "code": "class Solution: pass",
                "thinking_mode": "enabled",
                "topics": ["Array", "Hash Table"],
            },
        )
    ]
    conn.close()


def test_learning_event_context_tool_reads_recent_related_events(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(
            conn,
            task_id="house-robber",
            question_id=198,
            title_zh="打家劫舍",
            tags_json='["Array", "Dynamic Programming"]',
        )
        conn.execute(
            """
            INSERT INTO learning_events (
              user_id, task_id, topic, event_type, content, evidence_message_ids, confidence
            ) VALUES
              ('local', 'house-robber', 'Dynamic Programming', 'mastery', '旧的通过事件不应进入 prompt。', '[]', 0.7),
              ('local', 'house-robber', 'Dynamic Programming', 'mastery', '198 提交通过，掌握线性 DP。', '[]', 0.8),
              ('local', 'other-task', 'Dynamic Programming', 'mistake', 'DP 下标偏移错。', '[]', 0.7),
              ('local', 'graph-task', 'Graph', 'mistake', '图题错误。', '[]', 0.7)
            """
        )

    turn = AgentTurnInput(
        user_id="local",
        task_id="house-robber",
        command="/explain",
        message=None,
        code=None,
        submission_id=None,
        current_result=None,
        thinking_mode=None,
    )
    context = build_agent_context(
        conn,
        turn=turn,
        problem=_problem_payload(task_id="house-robber", tags=["Dynamic Programming"]),
        tools=[LearningEventContextTool()],
    )
    learning_result = context.tool_results[0]

    prompt = learning_result.as_prompt_section()
    assert learning_result.name == "learning_event_context"
    assert "掌握线性 DP" in prompt
    assert "旧的通过事件" not in prompt
    assert "DP 下标偏移错" in prompt
    assert "图题错误" not in prompt
    conn.close()


def test_tool_result_prompt_section_is_explicit():
    result = ToolResult(name="custom_tool", payload={"secret": "raw payload should not leak"})

    assert result.as_prompt_section() == ""
    assert ToolResult(name="custom_tool", payload={}, prompt_section="visible context").as_prompt_section() == "visible context"


def test_agent_tool_runner_isolates_tool_failures(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)

    class BrokenTool:
        name = "broken_tool"

        def should_run(self, request: AgentToolRequest) -> bool:
            return True

        def run(self, request: AgentToolRequest) -> ToolResult:
            raise RuntimeError("tool exploded")

    class HealthyTool:
        name = "healthy_tool"

        def should_run(self, request: AgentToolRequest) -> bool:
            return True

        def run(self, request: AgentToolRequest) -> ToolResult:
            return ToolResult(name=self.name, payload={"value": 1}, prompt_section="healthy context")

    turn = AgentTurnInput(
        user_id="local",
        task_id="two-sum",
        command="/review",
        message=None,
        code=None,
        submission_id=None,
        current_result=None,
        thinking_mode="enabled",
    )
    request = AgentToolRequest(
        conn=conn,
        turn=turn,
        problem={"tags": ["Hash Table"]},
        current_topics=["Hash Table"],
    )

    results = run_agent_tools(request, tools=[BrokenTool(), HealthyTool()])

    assert [result.name for result in results] == ["broken_tool", "healthy_tool"]
    assert results[0].ok is False
    assert results[0].payload["error"]["stage"] == "run"
    assert results[0].payload["error"]["type"] == "RuntimeError"
    assert "tool exploded" in results[0].as_prompt_section()
    assert results[1].ok is True
    assert results[1].as_prompt_section() == "healthy context"
    conn.close()


def test_judge_context_tool_prefers_current_frontend_result(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
        conn.execute(
            """
            INSERT INTO submissions (
              user_id, task_id, code, passed, failed_assertion, stderr, runtime_ms, test_count_estimate, passed_test_count
            ) VALUES ('local', 'two-sum', 'old code', 0, 'old failure', 'old stderr', 5, 1, 0)
            """
        )

    turn = AgentTurnInput(
        user_id="local",
        task_id="two-sum",
        command="/diagnose",
        message=None,
        code="current code",
        submission_id=None,
        current_result=CoachCurrentResult(
            task_id="two-sum",
            mode="run",
            status="failed",
            summary="current run failed",
            passed=False,
            failed_assertion="current failure",
            stderr="current stderr",
            runtime_ms=3,
            test_count_estimate=1,
            passed_test_count=0,
        ),
        thinking_mode="enabled",
    )
    context = build_agent_context(conn, turn=turn, problem={"tags": ["Hash Table"]}, tools=[JudgeContextTool()])
    code, failure = judge_context_from_results(context.tool_results)

    assert code == "current code"
    assert failure["source"] == "current_frontend_result"
    assert failure["failed_assertion"] == "current failure"
    assert "old failure" not in str(failure)
    conn.close()


def test_note_context_tool_reads_existing_practice_note(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
        conn.execute(
            """
            INSERT INTO practice_notes (
              user_id, task_id, content_markdown, ai_summary, mistake_summary, invariant_summary, solution_pattern
            ) VALUES (
              'local', 'two-sum', '# 两数之和\n复习哈希表补数。',
              '用哈希表保存左侧元素。', '不要先排序丢下标。', '只在左侧找 complement。', '一次遍历哈希表'
            )
            """
        )
        note_id = conn.execute("SELECT id FROM practice_notes WHERE task_id = 'two-sum'").fetchone()["id"]
        conn.execute(
            "INSERT INTO practice_note_topics (note_id, topic_name) VALUES (?, ?)",
            (note_id, "Hash Table"),
        )

    turn = AgentTurnInput(
        user_id="local",
        task_id="two-sum",
        command="/review",
        message=None,
        code=None,
        submission_id=None,
        current_result=None,
        thinking_mode="enabled",
    )
    context = build_agent_context(conn, turn=turn, problem={"tags": ["Hash Table"]}, tools=[NoteContextTool()])

    assert context.tool_results[0].name == "note_context"
    section = context.tool_results[0].as_prompt_section()
    assert "当前题已有复习笔记" in section
    assert "用哈希表保存左侧元素" in section
    assert "不要先排序丢下标" in section
    assert "哈希表" in section
    conn.close()


def test_solution_context_tool_reads_saved_and_accepted_code(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
        conn.execute(
            """
            INSERT INTO user_solutions (user_id, task_id, code, language, notes)
            VALUES ('local', 'two-sum', 'saved draft code', 'python', 'try hashmap')
            """
        )
        conn.execute(
            """
            INSERT INTO submissions (
              user_id, task_id, code, passed, failed_assertion, stderr, runtime_ms, test_count_estimate, passed_test_count
            ) VALUES ('local', 'two-sum', 'accepted code', 1, NULL, NULL, 4, 12, 12)
            """
        )

    turn = AgentTurnInput(
        user_id="local",
        task_id="two-sum",
        command="/code-review",
        message=None,
        code="current editor code",
        submission_id=None,
        current_result=None,
        thinking_mode="enabled",
    )
    context = build_agent_context(conn, turn=turn, problem={"tags": ["Hash Table"]}, tools=[SolutionContextTool()])
    result = context.tool_results[0]
    section = result.as_prompt_section()

    assert result.name == "solution_context"
    assert result.payload["saved_solution"]["same_as_current"] is False
    assert "current editor code" in section
    assert "saved draft code" in section
    assert "accepted code" in section
    assert "try hashmap" in section
    conn.close()


def test_memory_context_tool_reads_accepted_scoped_memories(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
        conn.execute(
            """
            INSERT INTO user_memory_items (
                user_id, memory_type, scope, topic, task_id, content, source, confidence, status
            ) VALUES
              ('local', 'strategy', 'task', 'Hash Table', 'two-sum', 'task accepted memory', 'test', 0.9, 'accepted'),
              ('local', 'weakness', 'topic', 'Hash Table', NULL, 'topic accepted memory', 'test', 0.8, 'accepted'),
              ('local', 'habit', 'global', NULL, NULL, 'global accepted memory', 'test', 0.7, 'accepted'),
              ('local', 'strategy', 'task', 'Hash Table', 'two-sum', 'rejected memory', 'test', 0.9, 'rejected'),
              ('local', 'strategy', 'task', 'Hash Table', 'three-sum', 'other task memory', 'test', 0.9, 'accepted')
            """
        )

    turn = AgentTurnInput(
        user_id="local",
        task_id="two-sum",
        command="/explain",
        message=None,
        code=None,
        submission_id=None,
        current_result=None,
        thinking_mode="enabled",
    )
    context = build_agent_context(conn, turn=turn, problem={"tags": ["Hash Table"]}, tools=[MemoryContextTool()])
    memories = memory_context_from_results(context.tool_results)
    contents = [item["content"] for item in memories]

    assert context.tool_results[0].name == "memory_context"
    assert context.tool_results[0].as_prompt_section() == ""
    assert context.memories == memories
    assert "task accepted memory" in contents
    assert "topic accepted memory" in contents
    assert "global accepted memory" in contents
    assert "rejected memory" not in contents
    assert "other task memory" not in contents
    conn.close()


def test_default_agent_tools_have_manifest_metadata():
    specs = default_agent_tool_specs()
    names = [spec.name for spec in specs]

    assert names == EXPECTED_DEFAULT_TOOL_NAMES
    for spec in specs:
        assert spec.description
        assert spec.trigger
        assert spec.prompt_visibility


def test_build_agent_problem_payload_includes_practice_context(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn, task_id="two-sum", tags_json='["Array", "Hash Table"]')
        _insert_problem(
            conn,
            task_id="contains-duplicate",
            question_id=217,
            title_zh="存在重复元素",
            tags_json='["Array", "Hash Table"]',
        )
        row = conn.execute("SELECT * FROM problems WHERE task_id = 'two-sum'").fetchone()
    conn.close()

    payload = build_agent_problem_payload(row, user_id="local")

    assert payload["task_id"] == "two-sum"
    assert payload["question_id"] == 1
    assert payload["tags"] == ["数组", "哈希表"]
    assert payload["problem_description"] == "description"
    assert "weak_topics" in payload["practice_context"]
    assert "same_topic_next" in payload["practice_context"]


def test_default_agent_runtime_config_is_explicit_profile():
    config = default_agent_runtime_config()

    assert [tool.name for tool in config.tools or []] == EXPECTED_DEFAULT_TOOL_NAMES
    assert set(config.route_handlers or {}) == {"diagnose", "explain", "search", "note_draft", "chat"}
    assert [hook.name for hook in config.hooks or []] == ["memory_curator"]


def test_default_agent_runtime_profile_manifest_exposes_composition():
    profile = default_agent_runtime_profile()
    item = agent_profile_manifest_item(profile)

    assert item.name == "teaching-agent-v1"
    assert item.stream_only is True
    assert item.tool_names == EXPECTED_DEFAULT_TOOL_NAMES
    assert item.command_routes == ["chat", "diagnose", "explain", "note_draft", "search"]
    assert item.hook_names == ["memory_curator"]
    assert "coach_messages" in item.state_backends


def test_agent_invocation_builds_turn_context_and_plan(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
        conn.execute(
            """
            INSERT INTO user_memory_items (
                user_id, memory_type, scope, topic, task_id, content, source, confidence, status
            ) VALUES ('local', 'strategy', 'task', 'Hash Table', 'two-sum', '只在左侧找 complement。', 'test', 0.9, 'accepted')
            """
        )

    request = AgentCommandRequest(
        task_id="two-sum",
        command="/diagnose",
        code="current code",
        current_result=CoachCurrentResult(
            task_id="two-sum",
            mode="run",
            status="failed",
            summary="custom run failed",
            passed=False,
            failed_assertion="expected [0,1], got []",
            stderr="",
            runtime_ms=4,
            test_count_estimate=1,
            passed_test_count=0,
        ),
        thinking_mode="enabled",
    )

    invocation = build_agent_invocation(
        conn,
        request=request,
        user_id="local",
        problem={
            "task_id": "two-sum",
            "question_id": 1,
            "difficulty": "Easy",
            "tags": ["Hash Table"],
            "problem_description": "description",
        },
    )

    assert invocation.turn.command == "/diagnose"
    assert invocation.code == "current code"
    assert invocation.failure["source"] == "current_frontend_result"
    assert invocation.problem["practice_context"]["accepted_memories"][0]["content"] == "只在左侧找 complement。"
    assert invocation.plan.command == "/diagnose"
    assert [hook.name for hook in invocation.config.hooks or []] == ["memory_curator"]
    assert "expected [0,1], got []" in invocation.plan.messages[-1]["content"]
    assert "只在左侧找 complement" in invocation.plan.messages[-1]["content"]
    conn.close()


def test_agent_runtime_config_controls_tools_and_route_handlers(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)

    class ProfileTool:
        name = "profile_tool"

        def should_run(self, request: AgentToolRequest) -> bool:
            return True

        def run(self, request: AgentToolRequest) -> ToolResult:
            return ToolResult(
                name=self.name,
                payload={"task_id": request.turn.task_id},
                prompt_section="profile-specific context",
            )

    seen = {}

    def profile_chat_handler(plan_input):
        seen["tool_section"] = plan_input.tool_section
        return AgentCommandPlan(
            command="/profile-chat",
            user_content=plan_input.message or plan_input.definition.default_message,
            messages=[{"role": "user", "content": f"profile handler saw: {plan_input.tool_section}"}],
        )

    class ProfileHook:
        name = "profile_hook"

        def after_coach_response(self, conn, event):
            return HookResult(name=self.name, payload={"command": event.command})

    hook = ProfileHook()

    invocation = build_agent_invocation(
        conn,
        request=AgentCommandRequest(
            task_id="two-sum",
            command="/hint",
            message="给一点提示",
            thinking_mode="enabled",
        ),
        user_id="local",
        problem={
            "task_id": "two-sum",
            "question_id": 1,
            "difficulty": "Easy",
            "tags": ["Hash Table"],
            "problem_description": "description",
        },
        config=AgentRuntimeConfig(
            tools=[ProfileTool()],
            route_handlers={"chat": profile_chat_handler},
            hooks=[hook],
        ),
    )

    assert invocation.context.tool_results[0].name == "profile_tool"
    assert seen["tool_section"] == "profile-specific context"
    assert invocation.config.hooks == [hook]
    assert invocation.plan.command == "/profile-chat"
    assert invocation.plan.messages[-1]["content"] == "profile handler saw: profile-specific context"
    conn.close()


def test_command_registry_normalizes_aliases_and_default_messages():
    assert normalize_command("诊断") == "/diagnose"
    assert normalize_command("搜索") == "/search-problems"
    assert normalize_command("auto", "/hint 给一点提示") == "/hint"

    plan = build_command_plan(
        command="/hint",
        task_id="two-sum",
        problem={
            "task_id": "two-sum",
            "question_id": 1,
            "difficulty": "Easy",
            "tags": ["数组", "哈希表"],
            "problem_description": "description",
        },
        code="class Solution: pass",
        failure=None,
        message=None,
        history=[],
    )

    assert plan.command == "/hint"
    assert plan.user_content == "请给我一个有限提示，不要直接给完整答案。"
    assert "Agent Skill: guided_chat" in plan.messages[-1]["content"]
    assert "用户命令：/hint" in plan.messages[-1]["content"]


def test_command_plan_allows_route_handler_injection():
    seen = {}

    def fake_chat_handler(plan_input):
        seen["command"] = plan_input.command
        seen["skill_section"] = plan_input.skill_section
        seen["tool_section"] = plan_input.tool_section
        return AgentCommandPlan(
            command="/custom-chat",
            user_content=plan_input.message or plan_input.definition.default_message,
            messages=[{"role": "user", "content": "custom handler context"}],
        )

    plan = build_command_plan(
        command="/hint",
        task_id="two-sum",
        problem={
            "task_id": "two-sum",
            "question_id": 1,
            "difficulty": "Easy",
            "tags": ["数组", "哈希表"],
            "problem_description": "description",
        },
        code=None,
        failure=None,
        message="给一点提示",
        history=[],
        tool_results=[ToolResult(name="custom_context", payload={}, prompt_section="tool context")],
        route_handlers={"chat": fake_chat_handler},
    )

    assert seen["command"] == "/hint"
    assert "Agent Skill: guided_chat" in seen["skill_section"]
    assert seen["tool_section"] == "tool context"
    assert plan == AgentCommandPlan(
        command="/custom-chat",
        user_content="给一点提示",
        messages=[{"role": "user", "content": "custom handler context"}],
    )


def test_command_registry_exposes_manifest():
    manifest = command_manifest()
    names = [item["name"] for item in manifest]

    assert "/diagnose" in names
    assert "/note-draft" in names
    assert "/search-problems" in names
    diagnose = next(item for item in manifest if item["name"] == "/diagnose")
    assert diagnose["route"] == "diagnose"
    assert "诊断" in diagnose["aliases"]
    assert diagnose["display_name"] == "诊断"
    assert diagnose["toolbar_icon"] == "diagnose"
    assert diagnose["toolbar_order"] == 20


def test_command_plan_injects_route_skills():
    problem = {
        "task_id": "two-sum",
        "question_id": 1,
        "difficulty": "Easy",
        "tags": ["数组", "哈希表"],
        "problem_description": "description",
    }

    diagnose_plan = build_command_plan(
        command="/diagnose",
        task_id="two-sum",
        problem=problem,
        code="class Solution: pass",
        failure={"failed_assertion": "boom"},
        message=None,
        history=[],
    )
    assert "Agent Skill: diagnose_failure" in diagnose_plan.messages[-1]["content"]
    assert "do not invent a failed case" in diagnose_plan.messages[-1]["content"]

    explain_plan = build_command_plan(
        command="/explain",
        task_id="two-sum",
        problem=problem,
        code=None,
        failure=None,
        message=None,
        history=[],
    )
    assert "Agent Skill: explain_algorithm" in explain_plan.messages[-1]["content"]
    assert "teach from intuition before code" in explain_plan.messages[-1]["content"]

    search_plan = build_command_plan(
        command="auto",
        task_id="two-sum",
        problem=problem,
        code=None,
        failure=None,
        message="有哪些经典题",
        history=[],
        tool_results=[
            ToolResult(
                name="problem_search",
                payload={"query": "经典题", "results": []},
                prompt_section="工具结果：本地题库搜索没有找到匹配题目。",
            )
        ],
    )
    assert search_plan.command == "/search-problems"
    assert "Agent Skill: problem_search" in search_plan.messages[-1]["content"]
    assert "do not invent problems not present in tool results" in search_plan.messages[-1]["content"]


def test_hook_runner_dispatches_after_coach_response(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)

    class FakeHook:
        name = "fake_hook"

        def __init__(self):
            self.seen_event = None

        def after_coach_response(self, conn, event):
            self.seen_event = event
            return HookResult(name=self.name, payload={"task_id": event.task_id, "command": event.command})

    hook = FakeHook()
    event = AfterCoachResponseEvent(
        user_id="local",
        task_id="two-sum",
        command="/diagnose",
        problem={"task_id": "two-sum"},
        user_content="请诊断",
        assistant_text="结论",
        user_message_id=1,
        assistant_message_id=2,
    )

    results = run_after_coach_response_hooks(conn, event, hooks=[hook])

    assert hook.seen_event == event
    assert results == [HookResult(name="fake_hook", payload={"task_id": "two-sum", "command": "/diagnose"})]
    conn.close()


def test_hook_runner_isolates_hook_failures(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)

    class BrokenHook:
        name = "broken_hook"

        def after_coach_response(self, conn, event):
            raise RuntimeError("hook exploded")

    class HealthyHook:
        name = "healthy_hook"

        def after_coach_response(self, conn, event):
            return HookResult(name=self.name, payload={"assistant_message_id": event.assistant_message_id})

    event = AfterCoachResponseEvent(
        user_id="local",
        task_id="two-sum",
        command="/diagnose",
        problem={"task_id": "two-sum"},
        user_content="请诊断",
        assistant_text="结论",
        user_message_id=1,
        assistant_message_id=2,
    )

    results = run_after_coach_response_hooks(conn, event, hooks=[BrokenHook(), HealthyHook()])

    assert [result.name for result in results] == ["broken_hook", "healthy_hook"]
    assert results[0].ok is False
    assert results[0].payload["error"]["type"] == "RuntimeError"
    assert results[0].payload["error"]["message"] == "hook exploded"
    assert results[1] == HookResult(name="healthy_hook", payload={"assistant_message_id": 2})
    conn.close()


def test_stream_ai_text_yields_empty_response_fallback():
    def empty_stream(messages, *, thinking_mode=None):
        return iter(["", "   "])

    assert list(stream_ai_text([{"role": "user", "content": "hi"}], ai_streamer=empty_stream)) == [
        "",
        "   ",
        AI_EMPTY_RESPONSE_TEXT,
    ]


def test_stream_agent_turn_persists_messages_hooks_and_submission_summary(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
        cursor = conn.execute(
            """
            INSERT INTO submissions (
              user_id, task_id, code, passed, failed_assertion, stderr, runtime_ms, test_count_estimate, passed_test_count
            ) VALUES ('local', 'two-sum', 'bad code', 0, 'boom', '', 5, 1, 0)
            """
        )
        submission_id = int(cursor.lastrowid)
    conn.close()

    def fake_stream(messages, *, thinking_mode=None):
        assert thinking_mode == "enabled"
        return iter(["## 结论\n服务层已经持久化。"])

    chunks = list(
        stream_agent_turn(
            AgentStreamTurn(
                user_id="local",
                task_id="two-sum",
                user_content="请诊断",
                messages=[{"role": "user", "content": "prompt"}],
                command="/diagnose",
                problem={"task_id": "two-sum", "question_id": 1, "tags": ["Hash Table"]},
                submission_id=submission_id,
                thinking_mode="enabled",
            ),
            ai_streamer=fake_stream,
        )
    )

    conn = get_connection(db_path)
    messages = conn.execute(
        "SELECT role, content FROM coach_messages WHERE user_id = 'local' AND task_id = 'two-sum' ORDER BY id"
    ).fetchall()
    summary = conn.execute(
        "SELECT summary FROM coach_thread_summaries WHERE user_id = 'local' AND task_id = 'two-sum'"
    ).fetchone()
    memory = conn.execute(
        "SELECT content FROM user_memory_items WHERE user_id = 'local' AND task_id = 'two-sum' AND status = 'proposed'"
    ).fetchone()
    submission = conn.execute("SELECT ai_diagnosis_summary FROM submissions WHERE id = ?", (submission_id,)).fetchone()
    conn.close()

    assert chunks == ["## 结论\n服务层已经持久化。"]
    assert [(row["role"], row["content"]) for row in messages] == [
        ("user", "请诊断"),
        ("assistant", "## 结论\n服务层已经持久化。"),
    ]
    assert "服务层已经持久化" in summary["summary"]
    assert "服务层已经持久化" in memory["content"]
    assert submission["ai_diagnosis_summary"] == "## 结论\n服务层已经持久化。"


def test_stream_agent_turn_allows_custom_hooks(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
        conn.execute(
            """
            CREATE TABLE custom_hook_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command TEXT NOT NULL,
                content TEXT NOT NULL
            )
            """
        )
    conn.close()

    class CustomHook:
        name = "custom_hook"

        def __init__(self):
            self.events = []

        def after_coach_response(self, conn, event):
            self.events.append(event)
            conn.execute(
                """
                INSERT INTO custom_hook_events (command, content)
                VALUES (?, ?)
                """,
                (
                    event.command,
                    f"custom hook saw {event.command}",
                ),
            )
            return HookResult(name=self.name, payload={"command": event.command})

    hook = CustomHook()

    def fake_stream(messages, *, thinking_mode=None):
        return iter(["## 结论\n自定义 hook。"])

    chunks = list(
        stream_agent_turn(
            AgentStreamTurn(
                user_id="local",
                task_id="two-sum",
                user_content="请总结",
                messages=[{"role": "user", "content": "prompt"}],
                command="/review",
                problem={"task_id": "two-sum", "question_id": 1, "tags": ["Hash Table"]},
                hooks=[hook],
            ),
            ai_streamer=fake_stream,
        )
    )

    conn = get_connection(db_path)
    memory_count = conn.execute("SELECT COUNT(*) AS count FROM user_memory_items").fetchone()["count"]
    event = conn.execute("SELECT command, content FROM custom_hook_events").fetchone()
    conn.close()

    assert chunks == ["## 结论\n自定义 hook。"]
    assert len(hook.events) == 1
    assert hook.events[0].command == "/review"
    assert memory_count == 0
    assert event["command"] == "/review"
    assert event["content"] == "custom hook saw /review"


def test_stream_agent_invocation_persists_turn_from_runtime_plan(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
        cursor = conn.execute(
            """
            INSERT INTO submissions (
              user_id, task_id, code, passed, failed_assertion, stderr, runtime_ms, test_count_estimate, passed_test_count
            ) VALUES ('local', 'two-sum', 'bad code', 0, 'boom', '', 5, 1, 0)
            """
        )
        submission_id = int(cursor.lastrowid)
    conn.close()

    request = AgentCommandRequest(
        task_id="two-sum",
        command="/diagnose",
        code="bad code",
        submission_id=submission_id,
        thinking_mode="enabled",
    )
    conn = get_connection(db_path)
    invocation = build_agent_invocation(
        conn,
        request=request,
        user_id="local",
        problem=_problem_payload(),
        config=AgentRuntimeConfig(hooks=[]),
    )
    conn.close()

    def fake_stream(messages, *, thinking_mode=None):
        assert thinking_mode == "enabled"
        assert "请诊断这次算法题提交为什么失败" in messages[-1]["content"]
        return iter(["adapter answer"])

    chunks = list(stream_agent_invocation(invocation, ai_streamer=fake_stream))

    conn = get_connection(db_path)
    messages = conn.execute(
        "SELECT role, content FROM coach_messages WHERE user_id = 'local' AND task_id = 'two-sum' ORDER BY id"
    ).fetchall()
    submission = conn.execute("SELECT ai_diagnosis_summary FROM submissions WHERE id = ?", (submission_id,)).fetchone()
    conn.close()

    assert chunks == ["adapter answer"]
    assert [(row["role"], row["content"]) for row in messages] == [
        ("user", "请诊断我这次提交为什么失败。"),
        ("assistant", "adapter answer"),
    ]
    assert submission["ai_diagnosis_summary"] == "adapter answer"


def test_stream_note_draft_invocation_does_not_write_coach_thread(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
    conn.close()

    request = AgentCommandRequest(task_id="two-sum", command="/note-draft", code="class Solution: pass")
    conn = get_connection(db_path)
    invocation = build_agent_invocation(
        conn,
        request=request,
        user_id="local",
        problem=_problem_payload(),
        config=AgentRuntimeConfig(hooks=[]),
    )
    conn.close()

    def fake_stream(messages, *, thinking_mode=None):
        assert "# 1. two-sum" in messages[-1]["content"]
        return iter(["# 1. two-sum\n"])

    chunks = list(stream_note_draft_invocation(invocation, ai_streamer=fake_stream))

    conn = get_connection(db_path)
    message_count = conn.execute("SELECT COUNT(*) AS count FROM coach_messages").fetchone()["count"]
    conn.close()

    assert chunks == ["# 1. two-sum\n"]
    assert message_count == 0


def test_agent_api_service_wraps_runtime_with_injected_dependencies(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
    conn.close()

    def connection_factory():
        return get_connection(db_path)

    def load_problem(task_id: str):
        conn = get_connection(db_path)
        try:
            return conn.execute("SELECT * FROM problems WHERE task_id = ?", (task_id,)).fetchone()
        finally:
            conn.close()

    captured = {}

    def fake_stream(messages, *, thinking_mode=None):
        captured["thinking_mode"] = thinking_mode
        captured["messages"] = messages
        return iter(["# service draft"])

    service = AgentApiService(
        user_id="local",
        connection_factory=connection_factory,
        problem_loader=load_problem,
        ai_streamer=fake_stream,
    )

    preview = service.preview_command(AgentCommandRequest(task_id="two-sum", command="/explain"))
    chunks = list(
        service.stream_note_draft(
            AgentCommandRequest(
                task_id="two-sum",
                command="/note-draft",
                code="class Solution: pass",
                thinking_mode="enabled",
            )
        )
    )

    conn = get_connection(db_path)
    message_count = conn.execute("SELECT COUNT(*) AS count FROM coach_messages").fetchone()["count"]
    conn.close()

    assert preview.command == "/explain"
    assert preview.tool_results
    assert chunks == ["# service draft"]
    assert captured["thinking_mode"] == "enabled"
    assert "Agent Skill: note_draft" in captured["messages"][0]["content"]
    assert message_count == 0


def test_agent_api_converts_legacy_coach_requests_without_dropping_context():
    current_result = CoachCurrentResult(
        task_id="two-sum",
        mode="run",
        status="failed",
        summary="custom case failed",
        passed=False,
        failed_assertion="expected [0, 1]",
    )

    command_request = agent_request_from_coach_request(
        CoachRequest(
            task_id="two-sum",
            code="class Solution: pass",
            submission_id=7,
            current_result=current_result,
            thinking_mode="enabled",
        ),
        command="/diagnose",
    )
    chat_request = agent_request_from_coach_chat_request(
        CoachChatRequest(
            task_id="two-sum",
            message="哪里错了",
            code="class Solution: pass",
            current_result=current_result,
            thinking_mode="disabled",
        )
    )

    assert command_request.command == "/diagnose"
    assert command_request.current_result == current_result
    assert command_request.thinking_mode == "enabled"
    assert chat_request.command == "auto"
    assert chat_request.message == "哪里错了"
    assert chat_request.current_result == current_result
    assert chat_request.thinking_mode == "disabled"


def test_submission_records_learning_event(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn, tags_json='["Array", "Hash Table"]')
    conn.close()

    from app import main
    from types import SimpleNamespace

    monkeypatch.setattr(
        main,
        "run_submission",
        lambda **kwargs: SimpleNamespace(
            passed=True,
            failed_assertion=None,
            stderr=None,
            stdout=None,
            return_output=None,
            runtime_ms=3,
            execution_ms=1,
            test_count_estimate=1,
            passed_test_count=1,
        ),
    )
    client = TestClient(main.app)
    response = client.post(
        "/api/submissions",
        json={
            "task_id": "two-sum",
            "code": "class Solution:\n    def twoSum(self, nums, target):\n        return [0, 1]\n",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "passed"

    conn = get_connection(db_path)
    event = conn.execute(
        """
        SELECT *
        FROM learning_events
        WHERE user_id = 'local' AND task_id = 'two-sum'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    conn.close()

    assert event is not None
    assert event["topic"] == "Array"
    assert event["event_type"] == "mastery"
    assert "两数之和 提交通过" in event["content"]


def test_agent_stream_creates_proposed_memory_and_summary(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
    conn.close()

    from app import main

    monkeypatch.setattr(
        main,
        "agent_model_streamer",
        lambda messages, **kwargs: iter(["## 结论\n你的代码应该维护哈希表只保存左侧元素。"]),
    )
    client = TestClient(main.app)

    response = client.post(
        "/api/agent/command/stream",
        json={"task_id": "two-sum", "command": "/diagnose", "code": "class Solution: pass"},
    )
    assert response.status_code == 200
    assert "左侧元素" in response.text

    memories = client.get("/api/agent/memories?status=proposed").json()["memories"]
    assert len(memories) == 1
    assert memories[0]["memory_type"] == "weakness"
    assert memories[0]["status"] == "proposed"
    assert "左侧元素" in memories[0]["content"]

    summary = client.get("/api/agent/thread-summary/two-sum").json()
    assert summary["summary"]
    assert "左侧元素" in summary["summary"]


def test_accepted_memory_is_injected_and_rejected_memory_is_excluded(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
        conn.execute(
            """
            INSERT INTO user_memory_items (
                user_id, memory_type, scope, topic, task_id, content, source, confidence, status
            ) VALUES
              ('local', 'strategy', 'task', '哈希表', 'two-sum', '优先想补数映射，不要先排序。', 'test', 0.9, 'accepted'),
              ('local', 'strategy', 'task', '哈希表', 'two-sum', '这条被拒绝，不能进入 prompt。', 'test', 0.9, 'rejected')
            """
        )
    conn.close()

    from app import main

    captured_messages = {}

    def fake_stream(messages, **kwargs):
        captured_messages["text"] = "\n".join(message["content"] for message in messages)
        return iter(["ok"])

    monkeypatch.setattr(main, "agent_model_streamer", fake_stream)
    client = TestClient(main.app)

    response = client.post(
        "/api/agent/command/stream",
        json={"task_id": "two-sum", "command": "/explain"},
    )
    assert response.status_code == 200
    assert "优先想补数映射" in captured_messages["text"]
    assert "这条被拒绝" not in captured_messages["text"]


def test_memory_record_from_row_maps_storage_fields(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
        cursor = conn.execute(
            """
            INSERT INTO user_memory_items (
                user_id, memory_type, scope, topic, task_id, content, source, confidence, status
            ) VALUES ('local', 'habit', 'global', NULL, NULL, 'review failed cases first', 'test', 0.75, 'accepted')
            """
        )
        row = conn.execute("SELECT * FROM user_memory_items WHERE id = ?", (cursor.lastrowid,)).fetchone()
    conn.close()

    record = memory_record_from_row(row)

    assert record.user_id == "local"
    assert record.memory_type == "habit"
    assert record.scope == "global"
    assert record.topic is None
    assert record.task_id is None
    assert record.content == "review failed cases first"
    assert record.confidence == 0.75
    assert record.status == "accepted"


def test_memory_record_services_filter_update_and_set_status(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
        cursor = conn.execute(
            """
            INSERT INTO user_memory_items (
                user_id, memory_type, scope, topic, task_id, content, source, confidence, status
            ) VALUES ('local', 'strategy', 'task', '哈希表', 'two-sum', 'old', 'test', 0.8, 'proposed')
            """
        )
        memory_id = cursor.lastrowid
        conn.execute(
            """
            INSERT INTO user_memory_items (
                user_id, memory_type, scope, topic, task_id, content, source, confidence, status
            ) VALUES ('local', 'habit', 'global', NULL, NULL, 'global habit', 'test', 0.7, 'accepted')
            """
        )

        records = fetch_memory_records(conn, user_id="local", task_id="two-sum")
        updated = update_memory_record(conn, user_id="local", memory_id=memory_id, content="  edited  ")
        accepted = set_memory_record_status(conn, user_id="local", memory_id=memory_id, status="accepted")
        missing = update_memory_record(conn, user_id="local", memory_id=9999, content="missing")
    conn.close()

    assert [record.content for record in records] == ["old", "global habit"]
    assert updated is not None
    assert updated.content == "edited"
    assert accepted is not None
    assert accepted.status == "accepted"
    assert missing is None


def test_thread_summary_record_services_map_storage_fields(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
        conn.execute(
            """
            INSERT INTO coach_thread_summaries (
                user_id, task_id, summary, last_message_id
            ) VALUES ('local', 'two-sum', 'remember complement invariant', 42)
            """
        )
        row = conn.execute(
            "SELECT * FROM coach_thread_summaries WHERE user_id = 'local' AND task_id = 'two-sum'"
        ).fetchone()
        mapped = thread_summary_record_from_row(row)
        fetched = fetch_thread_summary_record(conn, user_id="local", task_id="two-sum")
        missing = fetch_thread_summary_record(conn, user_id="local", task_id="missing")
    conn.close()

    assert mapped.task_id == "two-sum"
    assert mapped.summary == "remember complement invariant"
    assert mapped.last_message_id == 42
    assert mapped.updated_at
    assert fetched == mapped
    assert missing is None


def test_memory_accept_edit_reject_flow(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
        cursor = conn.execute(
            """
            INSERT INTO user_memory_items (
                user_id, memory_type, scope, topic, task_id, content, source, confidence, status
            ) VALUES ('local', 'strategy', 'task', '哈希表', 'two-sum', 'old', 'test', 0.8, 'proposed')
            """
        )
        memory_id = cursor.lastrowid
    conn.close()

    from app.main import app

    client = TestClient(app)
    edited = client.put(f"/api/agent/memories/{memory_id}", json={"content": "edited"}).json()
    assert edited["content"] == "edited"
    accepted = client.post(f"/api/agent/memories/{memory_id}/accept").json()
    assert accepted["status"] == "accepted"
    rejected = client.post(f"/api/agent/memories/{memory_id}/reject").json()
    assert rejected["status"] == "rejected"


def test_agent_search_intent_injects_problem_search_results(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_house_robber_family(conn)
    conn.close()

    from app import main

    captured_messages = {}

    def fake_stream(messages, **kwargs):
        captured_messages["text"] = "\n".join(message["content"] for message in messages)
        return iter(["基于本地题库，先做 198，再做 213。"])

    monkeypatch.setattr(main, "agent_model_streamer", fake_stream)
    client = TestClient(main.app)

    response = client.post(
        "/api/agent/command/stream",
        json={"task_id": "house-robber-iii", "command": "auto", "message": "有哪些经典题"},
    )
    assert response.status_code == 200
    assert "本地题库" in captured_messages["text"]
    assert "house-robber" in captured_messages["text"]
    assert "不要编造" in captured_messages["text"]


def test_agent_code_review_injects_solution_context(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
        conn.execute(
            """
            INSERT INTO user_solutions (user_id, task_id, code, language, notes)
            VALUES ('local', 'two-sum', 'saved draft code', 'python', 'saved note')
            """
        )
        conn.execute(
            """
            INSERT INTO submissions (
              user_id, task_id, code, passed, failed_assertion, stderr, runtime_ms, test_count_estimate, passed_test_count
            ) VALUES ('local', 'two-sum', 'accepted code', 1, NULL, NULL, 4, 12, 12)
            """
        )
    conn.close()

    from app import main

    captured_messages = {}

    def fake_stream(messages, **kwargs):
        captured_messages["text"] = "\n".join(message["content"] for message in messages)
        return iter(["代码 review 完成。"])

    monkeypatch.setattr(main, "agent_model_streamer", fake_stream)
    client = TestClient(main.app)

    response = client.post(
        "/api/agent/command/stream",
        json={"task_id": "two-sum", "command": "/code-review", "code": "current editor code"},
    )

    assert response.status_code == 200
    assert "工具结果：当前解法上下文" in captured_messages["text"]
    assert "current editor code" in captured_messages["text"]
    assert "saved draft code" in captured_messages["text"]
    assert "accepted code" in captured_messages["text"]


def test_agent_review_injects_note_context(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
        conn.execute(
            """
            INSERT INTO practice_notes (
              user_id, task_id, content_markdown, ai_summary, mistake_summary, invariant_summary, solution_pattern
            ) VALUES (
              'local', 'two-sum', '# 两数之和\n复习补数映射。',
              '哈希表找 complement。', '排序会丢原始下标。', '字典只保存已经扫过的左侧元素。', '一次遍历'
            )
            """
        )
    conn.close()

    from app import main

    captured_messages = {}

    def fake_stream(messages, **kwargs):
        captured_messages["text"] = "\n".join(message["content"] for message in messages)
        return iter(["先复习补数映射。"])

    monkeypatch.setattr(main, "agent_model_streamer", fake_stream)
    client = TestClient(main.app)

    response = client.post(
        "/api/agent/command/stream",
        json={"task_id": "two-sum", "command": "/review"},
    )

    assert response.status_code == 200
    assert "工具结果：当前题已有复习笔记" in captured_messages["text"]
    assert "哈希表找 complement" in captured_messages["text"]
    assert "排序会丢原始下标" in captured_messages["text"]


def test_agent_diagnose_uses_current_frontend_run_result(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
    conn.close()

    from app import main

    captured_messages = {}

    def fake_stream(messages, **kwargs):
        captured_messages["text"] = "\n".join(message["content"] for message in messages)
        return iter(["应该检查自定义输入触发的边界。"])

    monkeypatch.setattr(main, "agent_model_streamer", fake_stream)
    client = TestClient(main.app)

    response = client.post(
        "/api/agent/command/stream",
        json={
            "task_id": "two-sum",
            "command": "/diagnose",
            "code": "class Solution: pass",
            "current_result": {
                "task_id": "two-sum",
                "mode": "run",
                "status": "failed",
                "summary": "1/2 个自定义用例通过",
                "passed": False,
                "failed_assertion": "AssertionError: expected [0, 1], got []",
                "stderr": "Traceback from custom run",
                "runtime_ms": 7,
                "execution_ms": 1,
                "test_count_estimate": 2,
                "passed_test_count": 1,
                "case_results": [
                    {
                        "case": {"name": "用例 2", "input": "nums = [2,7]\ntarget = 9", "expectedOutput": "[0,1]"},
                        "response": {
                            "passed": False,
                            "failed_assertion": "expected [0,1], got []",
                            "stderr": "",
                            "stdout": "",
                            "return_output": "[]",
                        },
                    }
                ],
            },
        },
    )

    assert response.status_code == 200
    assert "current_frontend_result" in captured_messages["text"]
    assert "1/2 个自定义用例通过" in captured_messages["text"]
    assert "nums = [2,7]" in captured_messages["text"]
    assert "expected [0,1], got []" in captured_messages["text"]
    assert "不要声称" in captured_messages["text"]


def test_agent_problem_search_endpoint_returns_structured_results(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_house_robber_family(conn)
    conn.close()

    from app.main import app

    client = TestClient(app)
    response = client.get("/api/agent/tools/problem-search?q=打家劫舍&current_task_id=house-robber-iii")
    assert response.status_code == 200
    payload = response.json()
    task_ids = [item["task_id"] for item in payload["results"]]
    assert "house-robber" in task_ids
    assert "house-robber-ii" in task_ids
    assert "house-robber-iii" not in task_ids
    assert len(payload["interpreted_topics"]) == len(set(payload["interpreted_topics"]))


def test_agent_tools_endpoint_returns_manifest(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
    conn.close()

    from app.main import app

    client = TestClient(app)
    response = client.get("/api/agent/tools")
    assert response.status_code == 200
    payload = response.json()
    names = [tool["name"] for tool in payload["tools"]]
    assert names == EXPECTED_DEFAULT_TOOL_NAMES
    assert payload["tools"][0]["trigger"] == "Runs on every agent turn."


def test_agent_commands_endpoint_returns_manifest(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
    conn.close()

    from app.main import app

    client = TestClient(app)
    response = client.get("/api/agent/commands")
    assert response.status_code == 200
    payload = response.json()
    names = [command["name"] for command in payload["commands"]]
    assert "/diagnose" in names
    assert "/note-draft" in names
    assert "/search-problems" in names
    toolbar_commands = sorted(
        (command for command in payload["commands"] if command["toolbar_order"] is not None),
        key=lambda command: command["toolbar_order"],
    )
    assert [command["name"] for command in toolbar_commands] == ["/explain", "/diagnose", "/search-problems"]
    search = next(command for command in payload["commands"] if command["name"] == "/search-problems")
    assert search["route"] == "search"
    assert "找题" in search["aliases"]
    assert search["display_name"] == "找题"
    assert search["toolbar_icon"] == "search"


def test_agent_profile_endpoint_returns_runtime_profile(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    conn.close()

    from app.main import app

    client = TestClient(app)
    response = client.get("/api/agent/profile")
    assert response.status_code == 200
    profile = response.json()["profile"]
    assert profile["name"] == "teaching-agent-v1"
    assert profile["stream_only"] is True
    assert profile["tool_names"] == EXPECTED_DEFAULT_TOOL_NAMES
    assert profile["hook_names"] == ["memory_curator"]
    assert "user_memory_items" in profile["state_backends"]
    assert "learning_events" in profile["state_backends"]
    assert "agent_artifacts" in profile["state_backends"]


def test_agent_command_preview_returns_invocation_context(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)
        conn.execute(
            """
            INSERT INTO user_memory_items (
                user_id, memory_type, scope, topic, task_id, content, source, confidence, status
            ) VALUES ('local', 'strategy', 'task', 'Hash Table', 'two-sum', '只在左侧找 complement。', 'test', 0.9, 'accepted')
            """
        )
    conn.close()

    from app import main

    def fail_if_model_called(*args, **kwargs):
        raise AssertionError("preview must not call model")

    monkeypatch.setattr(main, "agent_model_streamer", fail_if_model_called)
    client = TestClient(main.app)
    response = client.post(
        "/api/agent/command/preview",
        json={
            "task_id": "two-sum",
            "command": "/diagnose",
            "code": "class Solution: pass",
            "current_result": {
                "task_id": "two-sum",
                "mode": "run",
                "status": "failed",
                "summary": "preview failed run",
                "passed": False,
                "failed_assertion": "expected [0,1], got []",
                "runtime_ms": 3,
                "test_count_estimate": 1,
                "passed_test_count": 0,
            },
            "thinking_mode": "enabled",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "/diagnose"
    assert payload["thinking_mode"] == "enabled"
    assert payload["code_present"] is True
    assert payload["failure_present"] is True
    assert payload["failure"]["source"] == "current_frontend_result"
    assert payload["memory_count"] == 1
    assert "Hash Table" in payload["current_topics"]
    tool_names = [item["name"] for item in payload["tool_results"]]
    assert "judge_context" in tool_names
    assert "memory_context" in tool_names
    assert all(isinstance(item["ok"], bool) for item in payload["tool_results"])
    assert "expected [0,1], got []" in payload["messages"][-1]["content"]
    assert "只在左侧找 complement" in payload["messages"][-1]["content"]


def test_agent_inspection_builds_manifest_and_truncated_preview(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LEETCOACH_CATALOG_DB_PATH", str(db_path))
    conn = get_connection(db_path)
    init_db(conn)
    with conn:
        _insert_problem(conn)

    invocation = build_agent_invocation(
        conn,
        request=AgentCommandRequest(
            task_id="two-sum",
            command="/diagnose",
            code="class Solution: pass",
            current_result=CoachCurrentResult(
                task_id="two-sum",
                mode="run",
                status="failed",
                summary="preview failed run",
                passed=False,
                failed_assertion="expected [0,1], got []",
                runtime_ms=3,
                test_count_estimate=1,
                passed_test_count=0,
            ),
            thinking_mode="enabled",
        ),
        user_id="local",
        problem={
            "task_id": "two-sum",
            "question_id": 1,
            "difficulty": "Easy",
            "tags": ["Hash Table"],
            "problem_description": "description" * 100,
        },
    )
    inspection = inspect_agent_invocation(invocation, tool_prompt_limit=24, message_limit=40)
    conn.close()

    assert agent_tool_manifest_items()[0].name == "judge_context"
    assert any(item.name == "/diagnose" for item in agent_command_manifest_items())
    assert inspection.command == "/diagnose"
    assert inspection.thinking_mode == "enabled"
    assert inspection.tool_results[0].ok is True
    assert inspection.tool_results[0].prompt_section.endswith("...")
    assert len(inspection.tool_results[0].prompt_section) == 27
    assert inspection.messages[0]["content"].endswith("...")
    assert len(inspection.messages[0]["content"]) == 43
