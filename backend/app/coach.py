from __future__ import annotations

from collections.abc import Iterator

from anthropic import Anthropic

from .config import anthropic_api_key, anthropic_auth_token, anthropic_base_url, anthropic_model


SYSTEM_PROMPT = """你是一个算法题学习教练。默认用中文，目标是帮助学习者理解范式，而不是只给答案。
讲解时按：这题在考什么、最直觉的想法、瓶颈、更好的解法、关键不变量/细节、代码思路、以后怎么识别这种题。
诊断错误时先指出最小错误点，再解释失败 case 为什么触发它。"""


def call_claude(user_prompt: str) -> str:
    return call_claude_messages([{"role": "user", "content": user_prompt}])


def call_claude_messages(messages: list[dict[str, str]]) -> str:
    text = "".join(call_claude_messages_stream(messages)).strip()
    return text or "AI 没有返回内容。请稍后重试，或检查当前模型/API 配置。"


def call_claude_messages_stream(messages: list[dict[str, str]]) -> Iterator[str]:
    api_key = anthropic_api_key()
    auth_token = anthropic_auth_token()
    if not api_key and not auth_token:
        yield "未配置 ANTHROPIC_API_KEY 或 ANTHROPIC_AUTH_TOKEN。已跳过 Claude 调用；你仍然可以使用本地判题。"
        return

    client = Anthropic(api_key=api_key, auth_token=auth_token, base_url=anthropic_base_url())
    with client.messages.stream(
        model=anthropic_model(),
        max_tokens=1800,
        system=SYSTEM_PROMPT,
        messages=messages,
        extra_body=_provider_extra_body(),
    ) as stream:
        for text in stream.text_stream:
            if text:
                yield text


def _provider_extra_body() -> dict | None:
    base_url = anthropic_base_url() or ""
    if "deepseek" in base_url.lower():
        return {"thinking": {"type": "disabled"}}
    return None


def build_diagnose_prompt(problem: dict, code: str, failure: dict | None) -> str:
    practice_section = _practice_section(problem)
    return f"""请诊断这次算法题提交为什么失败。

题目: {problem['question_id']}. {problem['task_id']}
难度: {problem['difficulty']}
标签: {', '.join(problem['tags'])}
{practice_section}

题面:
{problem['problem_description'][:2500]}

用户代码:
```python
{code}
```

失败信息:
{failure or {}}

请按这个格式输出：
## 结论
## 最小错误点
## 失败 case 怎么触发
## 应该维护的不变量
## 最小修改方向
## 下次怎么避免"""


def build_explain_prompt(problem: dict) -> str:
    practice_section = _practice_section(problem)
    return f"""请按我的算法学习格式讲解这道题。

题目: {problem['question_id']}. {problem['task_id']}
难度: {problem['difficulty']}
标签: {', '.join(problem['tags'])}
{practice_section}

题面:
{problem['problem_description'][:3500]}

请按这个格式输出：
## 这题在考什么
## 最直觉的想法
## 瓶颈在哪里
## 更好的解法
## 关键不变量
## 代码思路
## 手动走一遍
## 以后怎么识别这种题"""


def build_chat_context(problem: dict, code: str | None, failure: dict | None) -> str:
    code_section = f"\n当前用户代码：\n```python\n{code[:2500]}\n```\n" if code else ""
    failure_section = f"\n最近失败信息：\n{failure}\n" if failure else ""
    practice_section = _practice_section(problem)
    return f"""当前你正在辅导一道算法题。请默认用中文回答，回答要短而具体，优先围绕当前题，不要跳到无关知识。

题目: {problem['question_id']}. {problem['task_id']}
难度: {problem['difficulty']}
标签: {', '.join(problem['tags'])}
{practice_section}

题面:
{problem['problem_description'][:2600]}
{code_section}{failure_section}

如果用户问“为什么”“怎么想到”“哪里错了”，请用：结论 -> 关键状态/不变量 -> 小例子 -> 下一步建议。
如果用户问完整解法，请用讲解格式；如果用户问局部代码，请只解释局部。"""


def build_note_draft_prompt(
    problem: dict,
    code: str | None,
    failure: dict | None,
    existing_note: str | None = None,
) -> str:
    code_section = f"\n用户当前代码：\n```python\n{code[:2500]}\n```\n" if code else ""
    failure_section = f"\n最近失败信息：\n{failure}\n" if failure else ""
    existing_section = f"\n已有笔记：\n{existing_note[:1800]}\n" if existing_note else ""
    return f"""请把这次算法练习整理成可复习的 Markdown 笔记草稿。

题目: {problem['question_id']}. {problem['task_id']}
难度: {problem['difficulty']}
标签: {', '.join(problem['tags'])}

题面:
{problem['problem_description'][:2200]}
{code_section}{failure_section}{existing_section}

请只输出 Markdown，并严格使用这些小节：
# {problem['question_id']}. {problem['task_id']}
## 考点
## 识别信号
## 关键不变量
## 我的错误点
## 解法范式
## 复杂度
## 下次复习"""


def _practice_section(problem: dict) -> str:
    context = problem.get("practice_context")
    if not context:
        return ""
    weak_topics = context.get("weak_topics") or []
    next_items = context.get("same_topic_next") or []
    lines: list[str] = []
    if weak_topics:
        lines.append("练习画像:")
        for topic in weak_topics[:3]:
            lines.append(
                f"- {topic['label']}: 已过 {topic['passed_count']}/{topic['total_problem_count']}，{topic['recommendation']}"
            )
    if next_items:
        lines.append("同考点后续练习:")
        for item in next_items[:3]:
            lines.append(f"- {item['question_id']}. {item['title']}：{item['reason']}")
    return "\n" + "\n".join(lines) if lines else ""
