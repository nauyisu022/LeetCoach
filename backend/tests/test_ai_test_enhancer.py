import json

from app.ai_test_enhancer import (
    build_test_generation_prompt,
    extract_json_object,
    validate_test_code,
)


def _problem():
    return {
        "task_id": "lru-cache",
        "question_id": 146,
        "title_zh": "LRU 缓存",
        "difficulty": "Medium",
        "tags_json": json.dumps(["设计", "哈希表"], ensure_ascii=False),
        "entry_point": "LRUCache",
        "problem_description": "实现 LRUCache。",
        "problem_description_zh": "实现 LRUCache。",
        "test_code": "def check(candidate):\n    obj = candidate(2)\n    assert obj.get(1) == -1\n",
        "starter_code": "class LRUCache:\n    pass\n",
    }


def test_build_test_generation_prompt_contains_protocol():
    prompt = build_test_generation_prompt(_problem())

    assert "def check(candidate)" in prompt
    assert "entry_point: LRUCache" in prompt
    assert "输出 JSON" in prompt


def test_extract_json_object_from_fenced_response():
    payload = extract_json_object(
        '```json\n{"test_strength":"medium","rationale":["x"],"test_code":"def check(candidate):\\n    assert True\\n"}\n```'
    )

    assert payload["test_strength"] == "medium"
    assert "check" in payload["test_code"]


def test_validate_test_code_accepts_plain_assertions():
    result = validate_test_code(
        """
def check(candidate):
    obj = candidate(1)
    obj.put(1, 1)
    assert obj.get(1) == 1
"""
    )

    assert result.ok is True
    assert result.assertion_count == 1


def test_validate_test_code_rejects_dangerous_calls_and_missing_asserts():
    result = validate_test_code(
        """
def check(candidate):
    open('/tmp/x', 'w')
"""
    )

    assert result.ok is False
    assert "disallowed call: open" in result.errors
    assert "test_code must contain at least one assert" in result.errors
