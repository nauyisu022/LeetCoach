from __future__ import annotations

import json
import ast
import re
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path

MAX_OUTPUT_CHARS = 6000
DEFAULT_TIMEOUT_SECONDS = 10
PASS_SENTINEL = "__LEETCOACH_PASS__"
TEST_COUNT_PREFIX = "__LEETCOACH_TEST_COUNTS__"
RUNTIME_PRELUDE = "from random import *"
RUNTIME_POSTLUDE = "\n".join(
    [
        "import re",
        "from random import *",
        "pow = __builtins__['pow'] if isinstance(__builtins__, dict) else __builtins__.pow",
        "try:",
        "    pairwise",
        "except NameError:",
        "    def pairwise(iterable):",
        "        iterator = iter(iterable)",
        "        try:",
        "            previous = next(iterator)",
        "        except StopIteration:",
        "            return",
        "        for item in iterator:",
        "            yield previous, item",
        "            previous = item",
    ]
)
VIRTUAL_RUNTIME_FILENAME = "<leetcoach-runtime>"
VIRTUAL_PROMPT_FILENAME = "<problem-prompt>"
VIRTUAL_USER_CODE_FILENAME = "<user-code>"
VIRTUAL_TEST_CODE_FILENAME = "<test-code>"
VIRTUAL_SUBMISSION_HARNESS_FILENAME = "<leetcoach-submit-harness>"
VIRTUAL_CUSTOM_INPUT_FILENAME = "<custom-input>"
VIRTUAL_CUSTOM_HARNESS_FILENAME = "<leetcoach-custom-harness>"
VIRTUAL_CUSTOM_HELPERS_FILENAME = "<leetcoach-custom-helpers>"
RETURN_VALUE_PREFIX = "__LEETCOACH_RETURN__"
TEST_COUNTER_HELPERS = """
__leetcoach_passed_assertions = 0
__leetcoach_seen_assertions = 0

def __leetcoach_assert(__condition, __source, __message=None):
    global __leetcoach_passed_assertions, __leetcoach_seen_assertions
    __leetcoach_seen_assertions += 1
    if __condition:
        __leetcoach_passed_assertions += 1
        return
    if __message is not None:
        raise AssertionError(__message)
    raise AssertionError(__source)
""".strip()
RUNNER_HELPERS = """
import linecache as __leetcoach_linecache

def __leetcoach_register_source(__source, __filename):
    __leetcoach_linecache.cache[__filename] = (
        len(__source),
        None,
        __source.splitlines(True),
        __filename,
    )

def __leetcoach_exec(__source, __filename):
    __leetcoach_register_source(__source, __filename)
    exec(compile(__source, __filename, "exec"), globals())

def __leetcoach_exec_into(__source, __filename, __locals):
    __leetcoach_register_source(__source, __filename)
    exec(compile(__source, __filename, "exec"), globals(), __locals)
""".strip()
CUSTOM_RUN_HELPERS = """
import ast as __leetcoach_ast
import inspect as __leetcoach_inspect
import json as __leetcoach_json

def __leetcoach_display(value):
    if value is None:
        return None
    if 'ListNode' in globals() and isinstance(value, ListNode):
        items = []
        seen = 0
        while value is not None and seen < 10000:
            items.append(value.val)
            value = value.next
            seen += 1
        return items
    if 'TreeNode' in globals() and isinstance(value, TreeNode):
        items = []
        queue = deque([value])
        while queue:
            node = queue.popleft()
            if node is None:
                items.append(None)
                continue
            items.append(node.val)
            queue.append(node.left)
            queue.append(node.right)
        while items and items[-1] is None:
            items.pop()
        return items
    return value

def __leetcoach_prepare_arg(name, value, annotation):
    annotation_text = str(annotation)
    if isinstance(value, list) and 'ListNode' in annotation_text and 'list_node' in globals():
        return list_node(value)
    if isinstance(value, list) and 'TreeNode' in annotation_text and 'tree_node' in globals():
        return tree_node(value)
    return value

def __leetcoach_parse_expected(text):
    text = text.strip()
    if text == 'null':
        return None
    if text == 'true':
        return True
    if text == 'false':
        return False
    try:
        return __leetcoach_ast.literal_eval(text)
    except Exception:
        pass
    try:
        return __leetcoach_json.loads(text)
    except Exception:
        return text
""".strip()


@dataclass
class JudgeResult:
    passed: bool
    failed_assertion: str | None
    stderr: str | None
    stdout: str | None
    return_output: str | None
    runtime_ms: int
    test_count_estimate: int
    passed_test_count: int


def estimate_test_count(test_code: str) -> int:
    return len(re.findall(r"^\s*assert\s+", test_code, re.MULTILINE))


class _AssertCounterTransformer(ast.NodeTransformer):
    def __init__(self, source: str) -> None:
        self.source = source

    def visit_Assert(self, node: ast.Assert) -> ast.AST:
        self.generic_visit(node)
        source = ast.get_source_segment(self.source, node) or "AssertionError"
        args: list[ast.expr] = [node.test, ast.Constant(source)]
        if node.msg is not None:
            args.append(node.msg)
        replacement = ast.Expr(
            value=ast.Call(
                func=ast.Name(id="__leetcoach_assert", ctx=ast.Load()),
                args=args,
                keywords=[],
            )
        )
        return ast.copy_location(replacement, node)


def _instrument_asserts(test_code: str) -> str:
    try:
        tree = ast.parse(test_code)
        tree = _AssertCounterTransformer(test_code).visit(tree)
        ast.fix_missing_locations(tree)
        return ast.unparse(tree)
    except (SyntaxError, ValueError):
        return test_code


def run_submission(
    *,
    prompt: str,
    code: str,
    test_code: str,
    entry_point: str,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> JudgeResult:
    test_count = estimate_test_count(test_code)
    instrumented_test_code = _instrument_asserts(test_code)
    runner_source = _build_runner_source(prompt, code, instrumented_test_code, entry_point, test_count)
    source_lookup = _submission_source_lookup(prompt, code, instrumented_test_code, entry_point, test_count)
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="leetcoach-") as temp_dir:
        try:
            completed = _run_python_runner(runner_source, temp_dir, timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            runtime_ms = int((time.perf_counter() - started) * 1000)
            return JudgeResult(
                passed=False,
                failed_assertion="Execution timed out",
                stderr=_trim(_timeout_output(exc)),
                stdout=None,
                return_output=None,
                runtime_ms=runtime_ms,
                test_count_estimate=test_count,
                passed_test_count=0,
            )

    runtime_ms = int((time.perf_counter() - started) * 1000)
    raw_stdout = completed.stdout or ""
    passed_test_count, executed_test_count = _extract_test_counts(raw_stdout, test_count if completed.returncode == 0 else test_count)
    stdout = _clean_stdout(raw_stdout)
    stderr = completed.stderr or ""
    if completed.returncode == 0:
        return JudgeResult(True, None, _trim(stderr) or None, _trim(stdout) or None, None, runtime_ms, executed_test_count, passed_test_count)

    failed = _extract_failure(stderr, source_lookup) or _extract_exception_summary(stderr) or _trim(stderr) or _trim(stdout) or "Submission failed"
    return JudgeResult(False, failed, _trim(stderr) or None, _trim(stdout) or None, None, runtime_ms, executed_test_count, passed_test_count)


def run_custom_input(
    *,
    prompt: str,
    code: str,
    custom_input: str,
    expected_output: str | None = None,
    entry_point: str,
    compare_mode: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> JudgeResult:
    runner_source = _build_custom_runner_source(prompt, code, custom_input, entry_point, expected_output, compare_mode)
    normalized_input = _normalize_custom_input(custom_input)
    source_lookup = _custom_source_lookup(prompt, code, normalized_input, entry_point, expected_output, compare_mode)
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="leetcoach-") as temp_dir:
        try:
            completed = _run_python_runner(runner_source, temp_dir, timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            runtime_ms = int((time.perf_counter() - started) * 1000)
            return JudgeResult(
                passed=False,
                failed_assertion="Execution timed out",
                stderr=_trim(_timeout_output(exc)),
                stdout=None,
                return_output=None,
                runtime_ms=runtime_ms,
                test_count_estimate=1,
                passed_test_count=0,
            )

    runtime_ms = int((time.perf_counter() - started) * 1000)
    return_output, printed_output = _split_custom_stdout(completed.stdout or "")
    stderr = _trim(completed.stderr or "") or None
    if completed.returncode == 0:
        return JudgeResult(True, None, stderr, printed_output, return_output, runtime_ms, 1, 1)

    failed = _extract_failure(completed.stderr or "", source_lookup) or _extract_exception_summary(completed.stderr or "") or stderr or printed_output or "Custom run failed"
    return JudgeResult(False, failed, stderr, printed_output, return_output, runtime_ms, 1, 0)


def _build_runner_source(prompt: str, code: str, test_code: str, entry_point: str, test_count: int) -> str:
    harness = "\n".join(
        [
            "candidate = " + entry_point,
            "try:",
            "    check(candidate)",
            "finally:",
            "    print(" + json.dumps(TEST_COUNT_PREFIX) + " + f' {__leetcoach_passed_assertions} {__leetcoach_seen_assertions}')",
            "print(" + json.dumps(PASS_SENTINEL) + ")",
        ]
    )
    return "\n".join(
        [
            RUNNER_HELPERS,
            _exec_segment(RUNTIME_PRELUDE, VIRTUAL_RUNTIME_FILENAME),
            _exec_segment(prompt, VIRTUAL_PROMPT_FILENAME),
            _exec_segment(RUNTIME_POSTLUDE, VIRTUAL_RUNTIME_FILENAME),
            _exec_segment(code, VIRTUAL_USER_CODE_FILENAME),
            _exec_segment(TEST_COUNTER_HELPERS, VIRTUAL_RUNTIME_FILENAME),
            _exec_segment(test_code, VIRTUAL_TEST_CODE_FILENAME),
            _exec_segment(harness, VIRTUAL_SUBMISSION_HARNESS_FILENAME),
        ]
    )


def _build_custom_runner_source(
    prompt: str,
    code: str,
    custom_input: str,
    entry_point: str,
    expected_output: str | None = None,
    compare_mode: str | None = None,
) -> str:
    normalized_input = _normalize_custom_input(custom_input)
    harness = _custom_harness_source(normalized_input, entry_point, expected_output, compare_mode)
    return "\n".join(
        [
            RUNNER_HELPERS,
            _exec_segment(RUNTIME_PRELUDE, VIRTUAL_RUNTIME_FILENAME),
            _exec_segment(prompt, VIRTUAL_PROMPT_FILENAME),
            _exec_segment(RUNTIME_POSTLUDE, VIRTUAL_RUNTIME_FILENAME),
            _exec_segment(code, VIRTUAL_USER_CODE_FILENAME),
            _exec_segment(CUSTOM_RUN_HELPERS, VIRTUAL_CUSTOM_HELPERS_FILENAME),
            _exec_segment(harness, VIRTUAL_CUSTOM_HARNESS_FILENAME),
        ]
    )


def _exec_segment(source: str, filename: str) -> str:
    return "\n".join(
        [
            "__leetcoach_segment = " + json.dumps(source),
            "__leetcoach_exec(__leetcoach_segment, " + json.dumps(filename) + ")",
        ]
    )


def _run_python_runner(runner_source: str, temp_dir: str, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    runner_path = Path(temp_dir) / "runner.py"
    runner_path.write_text(runner_source, encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-I", str(runner_path)],
        cwd=temp_dir,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
    )


def _submission_source_lookup(prompt: str, code: str, test_code: str, entry_point: str, test_count: int) -> dict[str, str]:
    harness = "\n".join(
        [
            "candidate = " + entry_point,
            "try:",
            "    check(candidate)",
            "finally:",
            "    print(" + json.dumps(TEST_COUNT_PREFIX) + " + f' {__leetcoach_passed_assertions} {__leetcoach_seen_assertions}')",
            "print(" + json.dumps(PASS_SENTINEL) + ")",
        ]
    )
    return {
        VIRTUAL_RUNTIME_FILENAME: RUNTIME_POSTLUDE,
        VIRTUAL_PROMPT_FILENAME: prompt,
        VIRTUAL_USER_CODE_FILENAME: code,
        VIRTUAL_TEST_CODE_FILENAME: test_code,
        VIRTUAL_SUBMISSION_HARNESS_FILENAME: harness,
    }


def _custom_source_lookup(
    prompt: str,
    code: str,
    normalized_input: str,
    entry_point: str,
    expected_output: str | None = None,
    compare_mode: str | None = None,
) -> dict[str, str]:
    harness = _custom_harness_source(normalized_input, entry_point, expected_output, compare_mode)
    return {
        VIRTUAL_RUNTIME_FILENAME: RUNTIME_POSTLUDE,
        VIRTUAL_PROMPT_FILENAME: prompt,
        VIRTUAL_USER_CODE_FILENAME: code,
        VIRTUAL_CUSTOM_HELPERS_FILENAME: CUSTOM_RUN_HELPERS,
        VIRTUAL_CUSTOM_INPUT_FILENAME: normalized_input,
        VIRTUAL_CUSTOM_HARNESS_FILENAME: harness,
    }


def _custom_harness_source(
    normalized_input: str,
    entry_point: str,
    expected_output: str | None = None,
    compare_mode: str | None = None,
) -> str:
    return "\n".join(
        [
            "candidate = " + entry_point,
            "null = None",
            "true = True",
            "false = False",
            "__leetcoach_scope = {}",
            "__leetcoach_raw_input = " + json.dumps(normalized_input),
            "__leetcoach_signature = __leetcoach_inspect.signature(candidate)",
            "__leetcoach_params = list(__leetcoach_signature.parameters.items())",
            "if __leetcoach_raw_input.strip() and len(__leetcoach_params) == 1:",
            "    try:",
            "        __leetcoach_register_source(__leetcoach_raw_input, " + json.dumps(VIRTUAL_CUSTOM_INPUT_FILENAME) + ")",
            "        __leetcoach_scope[__leetcoach_params[0][0]] = eval(compile(__leetcoach_raw_input, " + json.dumps(VIRTUAL_CUSTOM_INPUT_FILENAME) + ", 'eval'), globals())",
            "    except SyntaxError:",
            "        __leetcoach_exec_into(__leetcoach_raw_input, " + json.dumps(VIRTUAL_CUSTOM_INPUT_FILENAME) + ", __leetcoach_scope)",
            "else:",
            "    __leetcoach_exec_into(__leetcoach_raw_input, " + json.dumps(VIRTUAL_CUSTOM_INPUT_FILENAME) + ", __leetcoach_scope)",
            "__leetcoach_kwargs = {}",
            "__leetcoach_missing = []",
            "for __name, __param in __leetcoach_params:",
            "    if __name in __leetcoach_scope:",
            "        __leetcoach_kwargs[__name] = __leetcoach_prepare_arg(__name, __leetcoach_scope[__name], __param.annotation)",
            "    elif __param.default is __leetcoach_inspect._empty:",
            "        __leetcoach_missing.append(__name)",
            "if __leetcoach_missing:",
            "    raise TypeError('Missing custom input value(s): ' + ', '.join(__leetcoach_missing))",
            "__leetcoach_result = candidate(**__leetcoach_kwargs)",
            "__leetcoach_display_result = __leetcoach_display(__leetcoach_result)",
            "print(" + json.dumps(RETURN_VALUE_PREFIX) + " + ' ' + repr(__leetcoach_display_result))",
            "__leetcoach_expected_output = " + json.dumps(expected_output),
            "__leetcoach_compare_mode = " + json.dumps(compare_mode),
            "if __leetcoach_expected_output is not None:",
            "    __leetcoach_expected = __leetcoach_parse_expected(__leetcoach_expected_output)",
            "    if __leetcoach_compare_mode == 'nested_unordered':",
            "        def __leetcoach_normalize_nested(items):",
            "            return sorted(tuple(sorted(item)) for item in items)",
            "        __leetcoach_matches = __leetcoach_normalize_nested(__leetcoach_display_result) == __leetcoach_normalize_nested(__leetcoach_expected)",
            "    elif __leetcoach_compare_mode in ('unordered_sequence', 'unordered'):",
            "        __leetcoach_matches = sorted(__leetcoach_display_result) == sorted(__leetcoach_expected)",
            "    else:",
            "        __leetcoach_matches = __leetcoach_display_result == __leetcoach_expected",
            "    if not __leetcoach_matches:",
            "        raise AssertionError(f'输出不匹配：期望 {__leetcoach_expected!r}，实际 {__leetcoach_display_result!r}')",
        ]
    )


def _normalize_custom_input(custom_input: str) -> str:
    value = custom_input.strip()
    if not value:
        return ""
    dict_assignments = _dict_input_to_assignments(value)
    if dict_assignments is not None:
        return dict_assignments
    try:
        compile(value, "<custom-input>", "exec")
        return value
    except SyntaxError:
        parts = _split_top_level_commas(value)
        if len(parts) <= 1 or not all("=" in part for part in parts):
            return value
        normalized = "\n".join(_repair_assignment_part(part) for part in parts)
        try:
            compile(normalized, "<custom-input>", "exec")
            return normalized
        except SyntaxError:
            return value


def _repair_assignment_part(part: str) -> str:
    name, value = part.split("=", 1)
    value = value.strip()
    if re.fullmatch(r"-?\d+\"", value):
        value = value[:-1]
    return f"{name.strip()} = {value}"


def _dict_input_to_assignments(value: str) -> str | None:
    if not value.startswith("{") or not value.endswith("}"):
        return None
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return "\n".join(f"{key} = {repr(item)}" for key, item in payload.items())


def _split_top_level_commas(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escaped = False
    for index, char in enumerate(value):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            parts.append(value[start:index])
            start = index + 1
    parts.append(value[start:])
    return parts


def _extract_failure(stderr: str, source_lookup: dict[str, str] | None = None) -> str | None:
    if "AssertionError" not in stderr:
        return None
    lines = [line for line in stderr.splitlines() if line.strip()]
    for line in reversed(lines):
        stripped = line.strip()
        if stripped.startswith("AssertionError:") and stripped != "AssertionError:":
            return stripped.removeprefix("AssertionError:").strip()
        if stripped.startswith("assert "):
            return stripped
    if source_lookup:
        for line in reversed(lines):
            match = re.match(r'File "(<[^"]+>)", line (\d+), in .+', line.strip())
            if not match:
                continue
            filename = match.group(1)
            source = source_lookup.get(filename)
            if source is None:
                continue
            source_lines = source.splitlines()
            line_number = int(match.group(2))
            if 1 <= line_number <= len(source_lines):
                source_line = source_lines[line_number - 1].strip()
                if source_line.startswith("assert "):
                    return source_line
    return "AssertionError"


def _extract_exception_summary(stderr: str) -> str | None:
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("File ") or line.startswith("Traceback "):
            continue
        if set(line) == {"^"}:
            continue
        return line
    return None


def _clean_stdout(value: str) -> str:
    return "\n".join(
        line for line in value.splitlines()
        if line.strip() != PASS_SENTINEL and not line.startswith(TEST_COUNT_PREFIX)
    )


def _split_custom_stdout(value: str) -> tuple[str | None, str | None]:
    return_output: str | None = None
    printed_lines: list[str] = []
    for line in value.splitlines():
        if line.startswith(RETURN_VALUE_PREFIX):
            return_output = line.removeprefix(RETURN_VALUE_PREFIX).strip()
        else:
            printed_lines.append(line)
    return return_output, _trim("\n".join(printed_lines)) or None


def _extract_passed_test_count(stdout: str, fallback: int) -> int:
    return _extract_test_counts(stdout, fallback)[0]


def _extract_test_counts(stdout: str, fallback: int) -> tuple[int, int]:
    for line in reversed(stdout.splitlines()):
        if not line.startswith(TEST_COUNT_PREFIX):
            continue
        parts = line.split()
        if len(parts) >= 3:
            try:
                passed_count = int(parts[1])
                executed_count = int(parts[2])
                return passed_count, max(executed_count, passed_count)
            except ValueError:
                return fallback, fallback
    return fallback, fallback


def _trim(value: str) -> str:
    cleaned = textwrap.dedent(value).strip()
    if len(cleaned) <= MAX_OUTPUT_CHARS:
        return cleaned
    return cleaned[:MAX_OUTPUT_CHARS] + "\n...[truncated]"


def _timeout_output(exc: subprocess.TimeoutExpired) -> str:
    return _decode_process_output(exc.stderr) + _decode_process_output(exc.stdout)


def _decode_process_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
