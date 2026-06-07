from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class CheckerStrategy:
    build_test_code: Callable[[list[dict[str, str]], str], str]
    custom_compare_mode: str | None = None
    rewrite_examples: Callable[[list[dict[str, Any]]], list[dict[str, str]]] | None = None
    use_error_output_inputs: bool = False


def effective_test_code_for_problem(task_id: str, test_code: str, input_output_json: str) -> str:
    cases = _load_cases(input_output_json)
    strategy = CHECKER_STRATEGIES.get(task_id)
    if strategy:
        source_cases = _string_cases(cases) if strategy.use_error_output_inputs else _without_error_outputs(cases)
        generated = strategy.build_test_code(source_cases, test_code)
        if generated:
            return generated
    return test_code


def effective_input_output_for_problem(task_id: str, input_output_json: str) -> list[dict[str, str]]:
    cases = _load_cases(input_output_json)
    strategy = CHECKER_STRATEGIES.get(task_id)
    if strategy and strategy.rewrite_examples:
        return strategy.rewrite_examples(cases)
    return _without_error_outputs(cases)


def custom_compare_mode_for_problem(task_id: str) -> str | None:
    strategy = CHECKER_STRATEGIES.get(task_id)
    return strategy.custom_compare_mode if strategy else None


def _load_cases(input_output_json: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(input_output_json)
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def _without_error_outputs(cases: list[dict[str, Any]]) -> list[dict[str, str]]:
    clean_cases: list[dict[str, str]] = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        input_text = case.get("input")
        output_text = case.get("output")
        if not isinstance(input_text, str) or not isinstance(output_text, str):
            continue
        if output_text.startswith("Error:"):
            continue
        clean_cases.append({"input": input_text, "output": output_text})
    return clean_cases


def _string_cases(cases: list[dict[str, Any]]) -> list[dict[str, str]]:
    clean_cases: list[dict[str, str]] = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        input_text = case.get("input")
        output_text = case.get("output")
        if isinstance(input_text, str) and isinstance(output_text, str):
            clean_cases.append({"input": input_text, "output": output_text})
    return clean_cases


def _assignment_values(input_text: str) -> dict[str, Any]:
    tree = ast.parse(input_text, mode="exec")
    values: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            value = ast.literal_eval(node.value)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    values[target.id] = value
    return values


def _parse_output(output_text: str) -> Any:
    value = output_text.strip()
    if value == "null":
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    try:
        return ast.literal_eval(value)
    except (SyntaxError, ValueError):
        pass
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return output_text


def _parsed_cases(cases: list[dict[str, str]]) -> list[tuple[dict[str, Any], Any]]:
    parsed: list[tuple[dict[str, Any], Any]] = []
    for case in cases:
        try:
            parsed.append((_assignment_values(case["input"]), _parse_output(case["output"])))
        except (SyntaxError, ValueError):
            continue
    return parsed


def _fallback_if_empty(lines: list[str], fallback_test_code: str) -> str:
    if len(lines) <= 1:
        return fallback_test_code
    return "\n".join(lines) + "\n"


def _build_two_sum_test_code(cases: list[dict[str, str]], fallback_test_code: str) -> str:
    lines = [
        "def check(candidate):",
        "    def assert_two_sum(nums, target):",
        "        actual = candidate(nums=list(nums), target=target)",
        "        assert isinstance(actual, (list, tuple)), f'返回值应为两个下标组成的列表，实际为 {type(actual).__name__}'",
        "        assert len(actual) == 2, f'返回值应包含两个下标，实际为 {actual!r}'",
        "        i, j = actual",
        "        assert isinstance(i, int) and isinstance(j, int), f'下标必须是整数，实际为 {actual!r}'",
        "        assert i != j, f'两个下标不能相同，实际为 {actual!r}'",
        "        assert 0 <= i < len(nums) and 0 <= j < len(nums), f'下标越界：nums={nums!r}，actual={actual!r}'",
        "        assert nums[i] + nums[j] == target, f'下标对应的值之和不等于 target：nums={nums!r}，target={target!r}，actual={actual!r}'",
        "",
    ]
    for inputs, _expected in _parsed_cases(cases):
        nums = inputs.get("nums")
        target = inputs.get("target")
        if isinstance(nums, list) and isinstance(target, int):
            lines.append(f"    assert_two_sum({nums!r}, {target!r})")
    return _fallback_if_empty(lines, fallback_test_code)


def _build_longest_palindrome_test_code(cases: list[dict[str, str]], fallback_test_code: str) -> str:
    lines = [
        "def check(candidate):",
        "    def assert_longest_palindrome(s, expected_length):",
        "        actual = candidate(s=s)",
        "        assert isinstance(actual, str), f'返回值应为字符串，实际为 {type(actual).__name__}'",
        "        assert actual in s, f'返回值 {actual!r} 不是输入字符串的子串'",
        "        assert actual == actual[::-1], f'返回值 {actual!r} 不是回文串'",
        "        assert len(actual) == expected_length, f'返回值长度应为 {expected_length}，实际为 {len(actual)}，返回值为 {actual!r}'",
        "",
    ]
    for inputs, expected in _parsed_cases(cases):
        source = inputs.get("s")
        if isinstance(source, str) and isinstance(expected, str):
            lines.append(f"    assert_longest_palindrome({source!r}, {len(expected)})")
    return _fallback_if_empty(lines, fallback_test_code)


def _build_sort_array_test_code(cases: list[dict[str, str]], fallback_test_code: str) -> str:
    lines = [
        "def check(candidate):",
        "    def assert_sorted(nums):",
        "        original = list(nums)",
        "        actual = candidate(nums=list(nums))",
        "        expected = sorted(original)",
        "        assert actual == expected, f'排序结果错误：输入 {original!r}，期望 {expected!r}，实际 {actual!r}'",
        "",
    ]
    for inputs, _expected in _parsed_cases(cases):
        nums = inputs.get("nums")
        if isinstance(nums, list) and all(isinstance(item, int) for item in nums):
            lines.append(f"    assert_sorted({nums!r})")
    return _fallback_if_empty(lines, fallback_test_code)


def _sort_array_examples(cases: list[dict[str, Any]]) -> list[dict[str, str]]:
    examples: list[dict[str, str]] = []
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("input"), str):
            continue
        try:
            nums = _assignment_values(case["input"]).get("nums")
        except (SyntaxError, ValueError):
            continue
        if isinstance(nums, list) and all(isinstance(item, int) for item in nums):
            examples.append({"input": f"nums = {nums!r}", "output": repr(sorted(nums))})
    return examples


def _build_subsets_test_code(cases: list[dict[str, str]], fallback_test_code: str) -> str:
    lines = [
        "def check(candidate):",
        "    def normalize(items):",
        "        return sorted(tuple(sorted(item)) for item in items)",
        "",
        "    def expected_subsets(nums):",
        "        expected = [[]]",
        "        for num in nums:",
        "            expected += [item + [num] for item in expected]",
        "        return expected",
        "",
        "    def assert_subsets(nums):",
        "        actual = candidate(nums=list(nums))",
        "        assert isinstance(actual, list), f'返回值应为列表，实际为 {type(actual).__name__}'",
        "        expected = expected_subsets(nums)",
        "        assert normalize(actual) == normalize(expected), f'子集集合错误：输入 {nums!r}，期望 {normalize(expected)!r}，实际 {normalize(actual)!r}'",
        "",
    ]
    for inputs, _expected in _parsed_cases(cases):
        nums = inputs.get("nums")
        if isinstance(nums, list):
            lines.append(f"    assert_subsets({nums!r})")
    return _fallback_if_empty(lines, fallback_test_code)


def _build_unique_subsets_test_code(cases: list[dict[str, str]], fallback_test_code: str) -> str:
    lines = [
        "def check(candidate):",
        "    def normalize(items):",
        "        return sorted(tuple(sorted(item)) for item in items)",
        "",
        "    def expected_subsets(nums):",
        "        expected = {()}",
        "        for num in nums:",
        "            expected |= {item + (num,) for item in list(expected)}",
        "        return [list(item) for item in expected]",
        "",
        "    def assert_subsets(nums):",
        "        actual = candidate(nums=list(nums))",
        "        assert isinstance(actual, list), f'返回值应为列表，实际为 {type(actual).__name__}'",
        "        expected = expected_subsets(tuple(sorted(nums)))",
        "        assert normalize(actual) == normalize(expected), f'子集集合错误：输入 {nums!r}，期望 {normalize(expected)!r}，实际 {normalize(actual)!r}'",
        "",
    ]
    for inputs, _expected in _parsed_cases(cases):
        nums = inputs.get("nums")
        if isinstance(nums, list):
            lines.append(f"    assert_subsets({nums!r})")
    return _fallback_if_empty(lines, fallback_test_code)


def _build_permutations_test_code(cases: list[dict[str, str]], fallback_test_code: str) -> str:
    lines = [
        "def check(candidate):",
        "    import math",
        "    def assert_permutations(nums, unique):",
        "        actual = candidate(nums=list(nums))",
        "        assert isinstance(actual, list), f'返回值应为列表，实际为 {type(actual).__name__}'",
        "        normalized = sorted(tuple(item) for item in actual)",
        "        expected_set = {()}",
        "        for num in nums:",
        "            next_set = set()",
        "            for item in expected_set:",
        "                for index in range(len(item) + 1):",
        "                    next_set.add(item[:index] + (num,) + item[index:])",
        "            expected_set = next_set",
        "        expected = sorted(expected_set)",
        "        assert normalized == expected, f'排列集合错误：输入 {nums!r}，期望 {expected!r}，实际 {normalized!r}'",
        "        if not unique:",
        "            expected_count = math.factorial(len(nums))",
        "            assert len(actual) == expected_count, f'排列数量错误：期望 {expected_count}，实际 {len(actual)}'",
        "",
    ]
    unique = "True" if any(inputs.get("nums") and len(inputs["nums"]) != len(set(inputs["nums"])) for inputs, _ in _parsed_cases(cases)) else "False"
    for inputs, _expected in _parsed_cases(cases):
        nums = inputs.get("nums")
        if isinstance(nums, list):
            lines.append(f"    assert_permutations({nums!r}, {unique})")
    return _fallback_if_empty(lines, fallback_test_code)


def _build_nested_set_test_code(
    cases: list[dict[str, str]],
    fallback_test_code: str,
    *,
    function_name: str,
    value_name: str,
    expected_message: str,
) -> str:
    lines = [
        "def check(candidate):",
        "    def normalize(items):",
        "        return sorted(tuple(item) for item in items)",
        "",
        f"    def assert_{function_name}(kwargs, expected):",
        "        actual = candidate(**kwargs)",
        "        assert isinstance(actual, list), f'返回值应为列表，实际为 {type(actual).__name__}'",
        f"        assert normalize(actual) == normalize(expected), f'{expected_message}：输入 {{kwargs!r}}，期望 {{normalize(expected)!r}}，实际 {{normalize(actual)!r}}'",
        "",
    ]
    for inputs, expected in _parsed_cases(cases):
        if isinstance(expected, list):
            lines.append(f"    assert_{function_name}({inputs!r}, {expected!r})")
    return _fallback_if_empty(lines, fallback_test_code)


def _build_group_anagrams_test_code(cases: list[dict[str, str]], fallback_test_code: str) -> str:
    lines = [
        "def check(candidate):",
        "    def normalize(groups):",
        "        return sorted(tuple(sorted(group)) for group in groups)",
        "",
        "    def assert_group_anagrams(strs):",
        "        actual = candidate(strs=list(strs))",
        "        assert isinstance(actual, list), f'返回值应为列表，实际为 {type(actual).__name__}'",
        "        expected_map = {}",
        "        for item in strs:",
        "            expected_map.setdefault(tuple(sorted(item)), []).append(item)",
        "        expected = list(expected_map.values())",
        "        assert normalize(actual) == normalize(expected), f'分组结果错误：输入 {strs!r}，期望 {normalize(expected)!r}，实际 {normalize(actual)!r}'",
        "",
    ]
    for inputs, _expected in _parsed_cases(cases):
        strs = inputs.get("strs")
        if isinstance(strs, list) and all(isinstance(item, str) for item in strs):
            lines.append(f"    assert_group_anagrams({strs!r})")
    return _fallback_if_empty(lines, fallback_test_code)


def _build_generate_parentheses_test_code(cases: list[dict[str, str]], fallback_test_code: str) -> str:
    lines = [
        "def check(candidate):",
        "    def valid(item):",
        "        balance = 0",
        "        for char in item:",
        "            balance += 1 if char == '(' else -1",
        "            if balance < 0:",
        "                return False",
        "        return balance == 0",
        "",
        "    def assert_parentheses(n, expected_count):",
        "        actual = candidate(n=n)",
        "        assert isinstance(actual, list), f'返回值应为列表，实际为 {type(actual).__name__}'",
        "        assert len(set(actual)) == len(actual), f'结果包含重复项：{actual!r}'",
        "        assert len(actual) == expected_count, f'组合数量错误：期望 {expected_count}，实际 {len(actual)}'",
        "        assert all(isinstance(item, str) and len(item) == 2 * n and valid(item) for item in actual), f'存在非法括号串：{actual!r}'",
        "",
    ]
    for inputs, expected in _parsed_cases(cases):
        n = inputs.get("n")
        if isinstance(n, int) and isinstance(expected, list):
            lines.append(f"    assert_parentheses({n!r}, {len(expected)})")
    return _fallback_if_empty(lines, fallback_test_code)


CHECKER_STRATEGIES: dict[str, CheckerStrategy] = {
    "two-sum": CheckerStrategy(_build_two_sum_test_code, custom_compare_mode="unordered_sequence"),
    "longest-palindromic-substring": CheckerStrategy(_build_longest_palindrome_test_code),
    "sort-an-array": CheckerStrategy(_build_sort_array_test_code, rewrite_examples=_sort_array_examples, use_error_output_inputs=True),
    "subsets": CheckerStrategy(_build_subsets_test_code, custom_compare_mode="nested_unordered"),
    "subsets-ii": CheckerStrategy(_build_unique_subsets_test_code, custom_compare_mode="nested_unordered"),
    "permutations": CheckerStrategy(_build_permutations_test_code, custom_compare_mode="nested_unordered"),
    "permutations-ii": CheckerStrategy(_build_permutations_test_code, custom_compare_mode="nested_unordered"),
    "3sum": CheckerStrategy(
        lambda cases, fallback: _build_nested_set_test_code(
            cases,
            fallback,
            function_name="triplets",
            value_name="nums",
            expected_message="三元组集合错误",
        ),
        custom_compare_mode="nested_unordered",
    ),
    "4sum": CheckerStrategy(
        lambda cases, fallback: _build_nested_set_test_code(
            cases,
            fallback,
            function_name="quadruplets",
            value_name="nums",
            expected_message="四元组集合错误",
        ),
        custom_compare_mode="nested_unordered",
    ),
    "combination-sum": CheckerStrategy(
        lambda cases, fallback: _build_nested_set_test_code(
            cases,
            fallback,
            function_name="combinations",
            value_name="candidates",
            expected_message="组合集合错误",
        ),
        custom_compare_mode="nested_unordered",
    ),
    "combination-sum-ii": CheckerStrategy(
        lambda cases, fallback: _build_nested_set_test_code(
            cases,
            fallback,
            function_name="combinations",
            value_name="candidates",
            expected_message="组合集合错误",
        ),
        custom_compare_mode="nested_unordered",
    ),
    "group-anagrams": CheckerStrategy(_build_group_anagrams_test_code, custom_compare_mode="nested_unordered"),
    "generate-parentheses": CheckerStrategy(_build_generate_parentheses_test_code, custom_compare_mode="unordered_sequence"),
}
