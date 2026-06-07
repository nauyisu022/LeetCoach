from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass
from typing import Any

from .config import anthropic_api_key, anthropic_auth_token, anthropic_base_url, anthropic_model
from .db import get_connection, init_db
from .judge import run_submission

DISALLOWED_CALLS = {
    "eval",
    "exec",
    "open",
    "__import__",
    "compile",
    "input",
    "globals",
    "locals",
    "vars",
}
DISALLOWED_IMPORT_ROOTS = {
    "os",
    "pathlib",
    "shutil",
    "socket",
    "subprocess",
    "sys",
}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: list[str]
    assertion_count: int


def build_test_generation_prompt(problem: dict[str, Any], target_strength: str = "medium") -> str:
    return f"""你是一个严格的算法题测试工程师。请为下面这道 Python LeetCode 风格题生成更强的本地测试。

目标：
- 输出 JSON，不要 Markdown，不要解释性正文。
- 只生成一个字段 test_code，里面必须定义 def check(candidate):。
- 测试必须符合本地 runner：candidate 已经是 entry_point 指向的对象或方法。
- 不要导入 os/pathlib/shutil/socket/subprocess/sys。
- 不要使用 eval/exec/open/input。
- 允许使用 typing、collections、heapq、bisect、math、random，但随机测试必须固定 seed 或只验证性质。
- 不要写“永远通过”的测试。
- 优先覆盖边界、重复值、状态更新、容量为 1、空输入、极端长度的小型样例。
- 多解题不要写死唯一输出顺序；用语义断言验证合法性，例如下标是否满足条件、集合是否相同、输出是否唯一且完整。
- 对列表顺序无关、嵌套列表顺序无关、浮点误差、任意合法答案等情况，必须写 normalize/helper 函数后再 assert。
- 目标强度：{target_strength}。

返回 JSON schema：
{{
  "test_strength": "medium",
  "rationale": ["覆盖点1", "覆盖点2"],
  "test_code": "def check(candidate):\\n    ..."
}}

题目信息：
task_id: {problem['task_id']}
question_id: {problem['question_id']}
title: {problem.get('title_zh') or problem['task_id']}
difficulty: {problem['difficulty']}
tags: {json.loads(problem['tags_json'])}
entry_point: {problem['entry_point']}

题面：
{problem['problem_description_zh'] or problem['problem_description']}

当前测试：
```python
{problem['test_code']}
```

starter code：
```python
{problem['starter_code']}
```"""


def generate_ai_test_proposal(problem: dict[str, Any], target_strength: str = "medium") -> dict[str, Any]:
    prompt = build_test_generation_prompt(problem, target_strength)
    api_key = anthropic_api_key()
    auth_token = anthropic_auth_token()
    if not api_key and not auth_token:
        raise RuntimeError("ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN is required for AI generation")
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key, auth_token=auth_token, base_url=anthropic_base_url())
    response = client.messages.create(
        model=anthropic_model(),
        max_tokens=4000,
        system="You generate strict JSON test proposals for Python algorithm problems.",
        messages=[{"role": "user", "content": prompt}],
    )
    text = "\n".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    return extract_json_object(text)


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end < start:
            raise
        payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("AI response must be a JSON object")
    return payload


def validate_test_code(test_code: str) -> ValidationResult:
    errors: list[str] = []
    try:
        tree = ast.parse(test_code)
    except SyntaxError as exc:
        return ValidationResult(False, [f"syntax error: {exc}"], 0)

    check_defs = [
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "check"
    ]
    if len(check_defs) != 1:
        errors.append("test_code must define exactly one check(candidate) function")
    elif len(check_defs[0].args.args) != 1 or check_defs[0].args.args[0].arg != "candidate":
        errors.append("check function must accept exactly one argument named candidate")

    assertion_count = sum(isinstance(node, ast.Assert) for node in ast.walk(tree))
    if assertion_count == 0:
        errors.append("test_code must contain at least one assert")

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name.split(".")[0] for alias in getattr(node, "names", [])]
            if isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module.split(".")[0])
            blocked = sorted(set(names) & DISALLOWED_IMPORT_ROOTS)
            if blocked:
                errors.append(f"disallowed import: {', '.join(blocked)}")
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in DISALLOWED_CALLS:
                errors.append(f"disallowed call: {name}")

    return ValidationResult(not errors, sorted(set(errors)), assertion_count)


def validate_against_reference(problem: dict[str, Any], test_code: str) -> str | None:
    completion = problem.get("completion") or ""
    if not completion.strip():
        return None
    result = run_submission(
        prompt=problem["prompt"],
        code=completion,
        test_code=test_code,
        entry_point=problem["entry_point"],
    )
    if result.passed:
        return None
    return result.failed_assertion or result.stderr or "reference solution failed generated tests"


def apply_ai_test_code(task_id: str, test_code: str, test_strength: str) -> None:
    conn = get_connection()
    init_db(conn)
    with conn:
        conn.execute(
            """
            UPDATE problems
            SET test_code = ?,
                test_source = 'ai_generated',
                test_strength = ?
            WHERE task_id = ?
            """,
            (test_code, test_strength, task_id),
        )
    conn.close()


def load_problem(task_id: str) -> dict[str, Any]:
    conn = get_connection()
    init_db(conn)
    row = conn.execute("SELECT * FROM problems WHERE task_id = ?", (task_id,)).fetchone()
    conn.close()
    if not row:
        raise ValueError(f"Problem not found: {task_id}")
    return {key: row[key] for key in row.keys()}


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Use AI to draft stronger tests for one local problem.")
    parser.add_argument("--task", required=True, help="Local problem task_id.")
    parser.add_argument("--strength", default="medium", choices=["medium", "strong"])
    parser.add_argument("--print-prompt", action="store_true", help="Print the AI prompt instead of calling the model.")
    parser.add_argument("--proposal-json", help="Validate this JSON proposal text/file instead of calling the model.")
    parser.add_argument("--apply", action="store_true", help="Write validated test_code back to SQLite.")
    args = parser.parse_args()

    problem = load_problem(args.task)
    if args.print_prompt:
        print(build_test_generation_prompt(problem, args.strength))
        return

    if args.proposal_json:
        raw = args.proposal_json
        if raw.endswith(".json"):
            with open(raw, "r", encoding="utf-8") as handle:
                raw = handle.read()
        proposal = extract_json_object(raw)
    else:
        proposal = generate_ai_test_proposal(problem, args.strength)

    test_code = proposal.get("test_code")
    if not isinstance(test_code, str):
        raise SystemExit("proposal missing string field: test_code")
    validation = validate_test_code(test_code)
    reference_error = validate_against_reference(problem, test_code)
    result = {
        "task_id": args.task,
        "validation_ok": validation.ok and reference_error is None,
        "assertion_count": validation.assertion_count,
        "errors": validation.errors + ([reference_error] if reference_error else []),
        "test_strength": proposal.get("test_strength", args.strength),
        "rationale": proposal.get("rationale", []),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.apply:
        if not result["validation_ok"]:
            raise SystemExit("refusing to apply invalid AI-generated tests")
        apply_ai_test_code(args.task, test_code, str(result["test_strength"]))
        print(f"applied {args.task}")


if __name__ == "__main__":
    main()
