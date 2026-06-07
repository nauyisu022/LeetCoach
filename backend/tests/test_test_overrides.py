from app.judge import run_custom_input, run_submission
from app.semantic_tests import custom_compare_mode_for_problem, effective_input_output_for_problem, effective_test_code_for_problem


def test_two_sum_override_accepts_reversed_valid_indices():
    input_output_json = """[
        {"input": "nums = [2, 7, 11, 15]\\ntarget = 9", "output": "[0, 1]"}
    ]"""
    test_code = effective_test_code_for_problem("two-sum", "def check(candidate): pass", input_output_json)
    code = """
class Solution:
    def twoSum(self, nums, target):
        return [1, 0]
"""

    result = run_submission(prompt="", code=code, test_code=test_code, entry_point="Solution().twoSum")

    assert result.passed is True


def test_two_sum_override_rejects_indices_that_do_not_match_target():
    input_output_json = """[
        {"input": "nums = [2, 7, 11, 15]\\ntarget = 9", "output": "[0, 1]"}
    ]"""
    test_code = effective_test_code_for_problem("two-sum", "def check(candidate): pass", input_output_json)
    code = """
class Solution:
    def twoSum(self, nums, target):
        return [0, 2]
"""

    result = run_submission(prompt="", code=code, test_code=test_code, entry_point="Solution().twoSum")

    assert result.passed is False
    assert "不等于 target" in (result.failed_assertion or "")


def test_two_sum_custom_run_accepts_reversed_expected_order():
    code = """
class Solution:
    def twoSum(self, nums, target):
        return [1, 0]
"""

    result = run_custom_input(
        prompt="",
        code=code,
        custom_input="nums = [2, 7, 11, 15], target = 9",
        expected_output="[0, 1]",
        entry_point="Solution().twoSum",
        compare_mode=custom_compare_mode_for_problem("two-sum"),
    )

    assert result.passed is True


def test_longest_palindrome_override_accepts_alternate_valid_answer():
    input_output_json = """[
        {"input": "s = \\"babad\\"", "output": "aba"},
        {"input": "s = \\"cbbd\\"", "output": "bb"}
    ]"""
    test_code = effective_test_code_for_problem("longest-palindromic-substring", "def check(candidate): pass", input_output_json)
    code = """
class Solution:
    def longestPalindrome(self, s: str) -> str:
        if s == "babad":
            return "bab"
        return "bb"
"""

    result = run_submission(prompt="", code=code, test_code=test_code, entry_point="Solution().longestPalindrome")

    assert result.passed is True


def test_longest_palindrome_override_rejects_non_longest_palindrome_with_message():
    input_output_json = """[
        {"input": "s = \\"aaaa\\"", "output": "aaaa"}
    ]"""
    test_code = effective_test_code_for_problem("longest-palindromic-substring", "def check(candidate): pass", input_output_json)
    code = """
class Solution:
    def longestPalindrome(self, s: str) -> str:
        return "aaa"
"""

    result = run_submission(prompt="", code=code, test_code=test_code, entry_point="Solution().longestPalindrome")

    assert result.passed is False
    assert "返回值长度应为 4" in (result.failed_assertion or "")


def test_sort_array_override_repairs_error_examples_and_checks_sorted_result():
    input_output_json = """[
        {"input": "nums = [-4,-2,-3,-1]", "output": "Error: name 'randint' is not defined"},
        {"input": "nums = [5, -1, 3, -2, 4, 0]", "output": "Error: name 'randint' is not defined"}
    ]"""
    examples = effective_input_output_for_problem("sort-an-array", input_output_json)
    test_code = effective_test_code_for_problem("sort-an-array", "def check(candidate): pass", input_output_json)
    code = """
class Solution:
    def sortArray(self, nums):
        return sorted(nums)
"""

    result = run_submission(prompt="", code=code, test_code=test_code, entry_point="Solution().sortArray")

    assert examples[0]["output"] == "[-4, -3, -2, -1]"
    assert examples[1]["output"] == "[-2, -1, 0, 3, 4, 5]"
    assert result.passed is True


def test_sort_array_override_reports_wrong_order_with_message():
    input_output_json = """[
        {"input": "nums = [3, 1, 2]", "output": "Error: name 'randint' is not defined"}
    ]"""
    test_code = effective_test_code_for_problem("sort-an-array", "def check(candidate): pass", input_output_json)
    code = """
class Solution:
    def sortArray(self, nums):
        return nums
"""

    result = run_submission(prompt="", code=code, test_code=test_code, entry_point="Solution().sortArray")

    assert result.passed is False
    assert "排序结果错误" in (result.failed_assertion or "")


def test_subsets_override_accepts_any_output_order():
    input_output_json = """[
        {"input": "nums = [6, 1, 5]", "output": "[[], [5], [1], [1, 5], [6], [6, 5], [6, 1], [6, 1, 5]]"}
    ]"""
    test_code = effective_test_code_for_problem("subsets", "def check(candidate): pass", input_output_json)
    code = """
class Solution:
    def subsets(self, nums):
        ans = []
        path = []

        def dfs(index):
            if index == len(nums):
                ans.append(path[:])
                return
            dfs(index + 1)
            path.append(nums[index])
            dfs(index + 1)
            path.pop()

        dfs(0)
        return ans
"""

    result = run_submission(prompt="", code=code, test_code=test_code, entry_point="Solution().subsets")

    assert result.passed is True


def test_subsets_override_rejects_missing_subset_with_message():
    input_output_json = """[
        {"input": "nums = [1, 2]", "output": "[[], [2], [1], [1, 2]]"}
    ]"""
    test_code = effective_test_code_for_problem("subsets", "def check(candidate): pass", input_output_json)
    code = """
class Solution:
    def subsets(self, nums):
        return [[], [nums[0]], [nums[1]]]
"""

    result = run_submission(prompt="", code=code, test_code=test_code, entry_point="Solution().subsets")

    assert result.passed is False
    assert "子集集合错误" in (result.failed_assertion or "")


def test_subsets_custom_run_accepts_different_subset_order():
    code = """
class Solution:
    def subsets(self, nums):
        return [[], [1], [2], [1, 2]]
"""

    result = run_custom_input(
        prompt="",
        code=code,
        custom_input="nums = [1, 2]",
        expected_output="[[], [2], [1], [1, 2]]",
        entry_point="Solution().subsets",
        compare_mode="nested_unordered",
    )

    assert result.passed is True


def test_permutations_override_accepts_any_result_order():
    input_output_json = """[
        {"input": "nums = [1, 2, 3]", "output": "[[1,2,3],[1,3,2],[2,1,3],[2,3,1],[3,1,2],[3,2,1]]"}
    ]"""
    test_code = effective_test_code_for_problem("permutations", "def check(candidate): pass", input_output_json)
    code = """
class Solution:
    def permute(self, nums):
        return [[3,2,1],[3,1,2],[2,3,1],[2,1,3],[1,3,2],[1,2,3]]
"""

    result = run_submission(prompt="", code=code, test_code=test_code, entry_point="Solution().permute")

    assert result.passed is True


def test_permutations_override_rejects_missing_permutation():
    input_output_json = """[
        {"input": "nums = [1, 2, 3]", "output": "[[1,2,3],[1,3,2],[2,1,3],[2,3,1],[3,1,2],[3,2,1]]"}
    ]"""
    test_code = effective_test_code_for_problem("permutations", "def check(candidate): pass", input_output_json)
    code = """
class Solution:
    def permute(self, nums):
        return [[1,2,3]]
"""

    result = run_submission(prompt="", code=code, test_code=test_code, entry_point="Solution().permute")

    assert result.passed is False
    assert "排列集合错误" in (result.failed_assertion or "")


def test_group_anagrams_override_accepts_any_group_order():
    input_output_json = """[
        {"input": "strs = ['eat', 'tea', 'tan', 'ate', 'nat', 'bat']", "output": "[['bat'],['nat','tan'],['ate','eat','tea']]"}
    ]"""
    test_code = effective_test_code_for_problem("group-anagrams", "def check(candidate): pass", input_output_json)
    code = """
class Solution:
    def groupAnagrams(self, strs):
        return [['tea', 'eat', 'ate'], ['bat'], ['tan', 'nat']]
"""

    result = run_submission(prompt="", code=code, test_code=test_code, entry_point="Solution().groupAnagrams")

    assert result.passed is True


def test_effective_examples_filter_error_outputs_for_general_problems():
    input_output_json = """[
        {"input": "x = 1", "output": "Error: list index out of range"},
        {"input": "x = 2", "output": "3"}
    ]"""

    examples = effective_input_output_for_problem("some-problem", input_output_json)

    assert examples == [{"input": "x = 2", "output": "3"}]
