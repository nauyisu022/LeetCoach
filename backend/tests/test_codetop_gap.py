from pathlib import Path

from app.codetop_gap import (
    build_class_test_code,
    build_function_test_code,
    classify_gap,
    estimate_assertions,
    upsert_problem,
)
from app.db import get_connection, init_db


def test_classify_gap_buckets():
    assert classify_gap("146", "lru-cache") == "numeric"
    assert classify_gap("剑指 Offer 09", "yong-liang-ge-zhan-shi-xian-dui-lie-lcof") == "offer"
    assert classify_gap("面试题 16.25", "lru-cache-lcci") == "lcci"
    assert classify_gap("补充题1", "https://example.com/article") == "supplement_url"
    assert classify_gap("补充题14", "") == "supplement_slug"


def test_build_class_test_code_from_leetcode_design_example():
    description = """
    示例：

    输入
    ["LRUCache", "put", "put", "get"]
    [[2], [1, 1], [2, 2], [1]]
    输出
    [null, null, null, 1]
    """

    test_code = build_class_test_code(description, "LRUCache")

    assert "obj_0 = candidate(*[2])" in test_code
    assert "obj_0.put(*[1, 1])" in test_code
    assert "assert obj_0.get(*[1]) == 1" in test_code
    assert estimate_assertions(test_code) == 1


def test_build_function_test_code_from_examples():
    description = """
    **示例 1：**
    **输入：** nums = [2,7,11,15], target = 9
    **输出：** [0,1]

    **示例 2：**
    **输入：** nums = [3,2,4], target = 6
    **输出：** [1,2]
    """

    test_code = build_function_test_code(description)

    assert "candidate(nums = [2, 7, 11, 15], target = 9)" in test_code
    assert "== [0, 1]" in test_code
    assert estimate_assertions(test_code) == 2


def test_upsert_problem_writes_gap_import_row(tmp_path: Path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)

    with conn:
        upsert_problem(
            conn,
            {
                "task_id": "lru-cache",
                "question_id": 146,
                "difficulty": "Medium",
                "tags": ["设计", "哈希表"],
                "problem_description": "LRU 缓存",
                "title_zh": "LRU 缓存",
                "problem_description_zh": "LRU 缓存",
                "starter_code": "class LRUCache:\n    pass\n",
                "entry_point": "LRUCache",
                "test_code": "def check(candidate):\n    assert True\n",
                "test_source": "leetcode_examples",
                "test_strength": "weak",
                "input_output": [],
                "prompt": "from typing import *",
                "completion": "",
                "estimated_date": None,
            },
        )

    row = conn.execute("SELECT task_id, question_id, entry_point FROM problems").fetchone()
    conn.close()

    assert row["task_id"] == "lru-cache"
    assert row["question_id"] == 146
    assert row["entry_point"] == "LRUCache"
