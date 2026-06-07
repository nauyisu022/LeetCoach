import subprocess

from app.judge import _timeout_output, run_custom_input, run_submission


PROMPT = """
from typing import *
"""

TEST_CODE = """
def check(candidate):
    assert candidate(nums=[2, 7, 11, 15], target=9) == [0, 1]
"""


def test_judge_passes_correct_solution():
    code = """
class Solution:
    def twoSum(self, nums: List[int], target: int) -> List[int]:
        seen = {}
        for i, num in enumerate(nums):
            if target - num in seen:
                return [seen[target - num], i]
            seen[num] = i
"""
    result = run_submission(prompt=PROMPT, code=code, test_code=TEST_CODE, entry_point="Solution().twoSum")
    assert result.passed is True
    assert result.test_count_estimate == 1
    assert result.stdout is None


def test_judge_reports_assertion_failure():
    code = """
class Solution:
    def twoSum(self, nums: List[int], target: int) -> List[int]:
        return []
"""
    result = run_submission(prompt=PROMPT, code=code, test_code=TEST_CODE, entry_point="Solution().twoSum")
    assert result.passed is False
    assert result.failed_assertion == "assert candidate(nums=[2, 7, 11, 15], target=9) == [0, 1]"


def test_judge_reports_passed_count_before_first_failure():
    code = """
def candidate(value):
    return value
"""
    test_code = """
def check(candidate):
    assert candidate(1) == 1
    assert candidate(2) == 2
    assert candidate(3) == 4
"""
    result = run_submission(prompt="", code=code, test_code=test_code, entry_point="candidate")

    assert result.passed is False
    assert result.passed_test_count == 2
    assert result.test_count_estimate == 3


def test_judge_reports_runtime_assert_count_for_reused_checker_helpers():
    code = """
def candidate(value):
    return value
"""
    test_code = """
def check(candidate):
    def assert_identity(value):
        assert candidate(value) == value

    for value in range(5):
        assert_identity(value)
"""
    result = run_submission(prompt="", code=code, test_code=test_code, entry_point="candidate")

    assert result.passed is True
    assert result.passed_test_count == 5
    assert result.test_count_estimate == 5


def test_judge_times_out():
    code = """
class Solution:
    def twoSum(self, nums: List[int], target: int) -> List[int]:
        while True:
            pass
"""
    result = run_submission(
        prompt=PROMPT,
        code=code,
        test_code=TEST_CODE,
        entry_point="Solution().twoSum",
        timeout_seconds=1,
    )
    assert result.passed is False
    assert result.failed_assertion == "Execution timed out"


def test_custom_input_runs_named_arguments_from_single_line():
    code = """
class Solution:
    def twoSum(self, nums: List[int], target: int) -> List[int]:
        return [0, 1]
"""
    result = run_custom_input(
        prompt=PROMPT,
        code=code,
        custom_input="nums = [2, 7, 11, 15], target = 9",
        entry_point="Solution().twoSum",
    )
    assert result.passed is True
    assert result.return_output == "[0, 1]"
    assert result.stdout is None


def test_custom_input_separates_prints_from_return_value():
    code = """
class Solution:
    def twoSum(self, nums: List[int], target: int) -> List[int]:
        print("debug", nums, target)
        return [0, 1]
"""
    result = run_custom_input(
        prompt=PROMPT,
        code=code,
        custom_input="nums = [2, 7, 11, 15], target = 9",
        entry_point="Solution().twoSum",
    )
    assert result.passed is True
    assert result.return_output == "[0, 1]"
    assert result.stdout == "debug [2, 7, 11, 15] 9"


def test_custom_input_checks_expected_output_when_provided():
    code = """
class Solution:
    def twoSum(self, nums: List[int], target: int) -> List[int]:
        return [1, 0]
"""
    result = run_custom_input(
        prompt=PROMPT,
        code=code,
        custom_input="nums = [2, 7, 11, 15], target = 9",
        expected_output="[0, 1]",
        entry_point="Solution().twoSum",
    )

    assert result.passed is False
    assert result.failed_assertion == "输出不匹配：期望 [0, 1]，实际 [1, 0]"


def test_custom_input_reports_missing_argument():
    code = """
class Solution:
    def twoSum(self, nums: List[int], target: int) -> List[int]:
        return []
"""
    result = run_custom_input(
        prompt=PROMPT,
        code=code,
        custom_input="nums = [2, 7, 11, 15]",
        entry_point="Solution().twoSum",
    )
    assert result.passed is False
    assert "target" in (result.failed_assertion or "")


def test_custom_input_converts_list_node_arguments_and_output():
    prompt = PROMPT + """
class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next

def list_node(values: list):
    head = None
    for value in reversed(values):
        head = ListNode(value, head)
    return head
"""
    code = """
class Solution:
    def identity(self, node: Optional[ListNode]) -> Optional[ListNode]:
        return node
"""
    result = run_custom_input(
        prompt=prompt,
        code=code,
        custom_input="node = [1, 2, 3]",
        expected_output="[1, 2, 3]",
        entry_point="Solution().identity",
    )
    assert result.passed is True
    assert result.return_output == "[1, 2, 3]"
    assert result.stdout is None


def test_custom_input_fails_when_linked_list_solution_returns_none_instead_of_expected_list():
    prompt = PROMPT + """
class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next

def list_node(values: list):
    head = None
    for value in reversed(values):
        head = ListNode(value, head)
    return head
"""
    code = """
class Solution:
    def reverseList(self, head: Optional[ListNode]) -> Optional[ListNode]:
        prev = None
        cur = head
        while cur:
            nxt = cur.next
            cur.next = prev
            prev = cur
            cur = nxt
"""
    result = run_custom_input(
        prompt=prompt,
        code=code,
        custom_input="head = [5000, -5000, 0, 1000, -1000]",
        expected_output="[-1000, 1000, 0, -5000, 5000]",
        entry_point="Solution().reverseList",
    )

    assert result.passed is False
    assert result.failed_assertion == "输出不匹配：期望 [-1000, 1000, 0, -5000, 5000]，实际 None"


def test_custom_input_accepts_leetcode_json_literals():
    code = """
class Solution:
    def inspect(self, values, flag):
        return values[-1] is None and flag
"""
    result = run_custom_input(
        prompt=PROMPT,
        code=code,
        custom_input="values = [1, null], flag = true",
        entry_point="Solution().inspect",
    )

    assert result.passed is True
    assert result.return_output == "True"
    assert result.stdout is None


def test_custom_input_allows_value_only_for_single_argument():
    code = """
class Solution:
    def lengthOfLongestSubstring(self, s: str) -> int:
        return len(s)
"""
    result = run_custom_input(
        prompt=PROMPT,
        code=code,
        custom_input='"abcabcbb"',
        entry_point="Solution().lengthOfLongestSubstring",
    )

    assert result.passed is True
    assert result.return_output == "8"
    assert result.stdout is None


def test_custom_input_syntax_error_uses_custom_input_traceback_name():
    code = """
class Solution:
    def inspect(self, values):
        return values
"""
    result = run_custom_input(
        prompt=PROMPT,
        code=code,
        custom_input="values = [1, null",
        entry_point="Solution().inspect",
    )

    assert result.passed is False
    assert "<custom-input>" in (result.stderr or "")
    assert "<string>" not in (result.stderr or "")
    assert "SyntaxError:" in (result.failed_assertion or "")


def test_custom_input_user_code_error_uses_user_code_traceback_name():
    code = """
class Solution:
    def inspect(self, values):
        return missing_name
"""
    result = run_custom_input(
        prompt=PROMPT,
        code=code,
        custom_input="values = [1, null]",
        entry_point="Solution().inspect",
    )

    assert result.passed is False
    assert "<user-code>" in (result.stderr or "")
    assert "<string>" not in (result.stderr or "")
    assert result.failed_assertion == "NameError: name 'missing_name' is not defined"


def test_judge_reports_assertion_message_when_present():
    test_code = """
def check(candidate):
    assert candidate() == "ok", "返回值不符合语义约束"
"""
    result = run_submission(prompt="", code="def candidate():\n    return 'bad'\n", test_code=test_code, entry_point="candidate")
    assert result.passed is False
    assert result.failed_assertion == "返回值不符合语义约束"


def test_judge_runtime_prelude_exposes_random_helpers():
    code = """
def candidate():
    return randint(1, 1)
"""
    test_code = """
def check(candidate):
    assert candidate() == 1
"""

    result = run_submission(prompt="", code=code, test_code=test_code, entry_point="candidate")

    assert result.passed is True


def test_custom_input_accepts_json_object_arguments():
    code = """
class Solution:
    def exists(self, board, word):
        return board[0][0] == word[0]
"""
    result = run_custom_input(
        prompt=PROMPT,
        code=code,
        custom_input='{"board": [["A", "B"]], "word": "A"}',
        entry_point="Solution().exists",
    )

    assert result.passed is True
    assert result.return_output == "True"
    assert result.stdout is None


def test_judge_restores_builtin_three_argument_pow_after_math_import_star():
    code = """
def candidate():
    return pow(2, 5, 7)
"""
    test_code = """
def check(candidate):
    assert candidate() == 4
"""

    result = run_submission(prompt="from math import *", code=code, test_code=test_code, entry_point="candidate")

    assert result.passed is True


def test_judge_runtime_prelude_exposes_re_and_pairwise():
    code = """
def candidate():
    return bool(re.search("a+", "aaa")) and list(pairwise([1, 2, 3]))
"""
    test_code = """
def check(candidate):
    assert candidate() == [(1, 2), (2, 3)]
"""

    result = run_submission(prompt="", code=code, test_code=test_code, entry_point="candidate")

    assert result.passed is True


def test_custom_input_repairs_trailing_quote_after_numeric_argument():
    code = """
class Solution:
    def f(self, word: str, m: int):
        return [word, m]
"""
    result = run_custom_input(
        prompt=PROMPT,
        code=code,
        custom_input='word = "987654321", m = 987654321"',
        entry_point="Solution().f",
    )

    assert result.passed is True
    assert result.return_output == "['987654321', 987654321]"
    assert result.stdout is None


def test_timeout_output_decodes_bytes_streams():
    exc = subprocess.TimeoutExpired(["python"], timeout=1, output=b"out", stderr=b"err")

    assert _timeout_output(exc) == "errout"
