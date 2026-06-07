from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from . import judge as local_judge
from .config import judge0_auth_token, judge0_endpoint, judge0_language_id, judge_backend
from .judge import DEFAULT_TIMEOUT_SECONDS, JudgeResult


class JudgeBackend(Protocol):
    def run_submission(
        self,
        *,
        prompt: str,
        code: str,
        test_code: str,
        entry_point: str,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> JudgeResult: ...

    def run_custom_input(
        self,
        *,
        prompt: str,
        code: str,
        custom_input: str,
        expected_output: str | None = None,
        entry_point: str,
        compare_mode: str | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> JudgeResult: ...


class LocalJudgeBackend:
    def run_submission(
        self,
        *,
        prompt: str,
        code: str,
        test_code: str,
        entry_point: str,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> JudgeResult:
        return local_judge.run_submission(
            prompt=prompt,
            code=code,
            test_code=test_code,
            entry_point=entry_point,
            timeout_seconds=timeout_seconds,
        )

    def run_custom_input(
        self,
        *,
        prompt: str,
        code: str,
        custom_input: str,
        expected_output: str | None = None,
        entry_point: str,
        compare_mode: str | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> JudgeResult:
        return local_judge.run_custom_input(
            prompt=prompt,
            code=code,
            custom_input=custom_input,
            expected_output=expected_output,
            entry_point=entry_point,
            compare_mode=compare_mode,
            timeout_seconds=timeout_seconds,
        )


@dataclass
class _Judge0Execution:
    returncode: int
    stdout: str
    stderr: str
    runtime_ms: int
    failure_reason: str | None = None


class Judge0Backend:
    def run_submission(
        self,
        *,
        prompt: str,
        code: str,
        test_code: str,
        entry_point: str,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> JudgeResult:
        test_count = local_judge.estimate_test_count(test_code)
        instrumented_test_code = local_judge._instrument_asserts(test_code)
        runner_source = local_judge._build_runner_source(prompt, code, instrumented_test_code, entry_point, test_count)
        source_lookup = local_judge._submission_source_lookup(prompt, code, instrumented_test_code, entry_point, test_count)
        execution = self._execute(runner_source, timeout_seconds)
        return _submission_result_from_execution(execution, test_count, source_lookup)

    def run_custom_input(
        self,
        *,
        prompt: str,
        code: str,
        custom_input: str,
        expected_output: str | None = None,
        entry_point: str,
        compare_mode: str | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> JudgeResult:
        runner_source = local_judge._build_custom_runner_source(prompt, code, custom_input, entry_point, expected_output, compare_mode)
        normalized_input = local_judge._normalize_custom_input(custom_input)
        source_lookup = local_judge._custom_source_lookup(prompt, code, normalized_input, entry_point, expected_output, compare_mode)
        execution = self._execute(runner_source, timeout_seconds)
        return _custom_result_from_execution(execution, source_lookup)

    def _execute(self, runner_source: str, timeout_seconds: int) -> _Judge0Execution:
        endpoint = judge0_endpoint()
        if not endpoint:
            return _Judge0Execution(
                returncode=1,
                stdout="",
                stderr="",
                runtime_ms=0,
                failure_reason="Judge0 endpoint is not configured",
            )

        payload = {
            "source_code": runner_source,
            "language_id": judge0_language_id(),
            "cpu_time_limit": timeout_seconds,
            "wall_time_limit": timeout_seconds + 2,
        }
        request = urllib.request.Request(
            f"{endpoint}/submissions?base64_encoded=false&wait=true",
            data=json.dumps(payload).encode("utf-8"),
            headers=_judge0_headers(),
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds + 10) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return _Judge0Execution(
                returncode=1,
                stdout="",
                stderr=_read_error_body(exc),
                runtime_ms=int((time.perf_counter() - started) * 1000),
                failure_reason=f"Judge0 request failed with HTTP {exc.code}",
            )
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return _Judge0Execution(
                returncode=1,
                stdout="",
                stderr=str(exc),
                runtime_ms=int((time.perf_counter() - started) * 1000),
                failure_reason="Judge0 request failed",
            )

        return _judge0_execution_from_payload(response_payload, int((time.perf_counter() - started) * 1000))


def run_submission(
    *,
    prompt: str,
    code: str,
    test_code: str,
    entry_point: str,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> JudgeResult:
    return _selected_backend().run_submission(
        prompt=prompt,
        code=code,
        test_code=test_code,
        entry_point=entry_point,
        timeout_seconds=timeout_seconds,
    )


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
    return _selected_backend().run_custom_input(
        prompt=prompt,
        code=code,
        custom_input=custom_input,
        expected_output=expected_output,
        entry_point=entry_point,
        compare_mode=compare_mode,
        timeout_seconds=timeout_seconds,
    )


def _selected_backend() -> JudgeBackend:
    backend = judge_backend()
    if backend == "judge0":
        return Judge0Backend()
    return LocalJudgeBackend()


def _submission_result_from_execution(
    execution: _Judge0Execution,
    test_count: int,
    source_lookup: dict[str, str],
) -> JudgeResult:
    raw_stdout = execution.stdout or ""
    passed_test_count, executed_test_count = local_judge._extract_test_counts(raw_stdout, test_count if execution.returncode == 0 else test_count)
    stdout = local_judge._clean_stdout(raw_stdout)
    stderr = execution.stderr or ""
    if execution.returncode == 0:
        return JudgeResult(True, None, local_judge._trim(stderr) or None, local_judge._trim(stdout) or None, None, execution.runtime_ms, executed_test_count, passed_test_count)

    failed = (
        local_judge._extract_failure(stderr, source_lookup)
        or local_judge._extract_exception_summary(stderr)
        or execution.failure_reason
        or local_judge._trim(stderr)
        or local_judge._trim(stdout)
        or "Submission failed"
    )
    return JudgeResult(False, failed, local_judge._trim(stderr) or None, local_judge._trim(stdout) or None, None, execution.runtime_ms, executed_test_count, passed_test_count)


def _custom_result_from_execution(
    execution: _Judge0Execution,
    source_lookup: dict[str, str],
) -> JudgeResult:
    return_output, printed_output = local_judge._split_custom_stdout(execution.stdout or "")
    stderr = local_judge._trim(execution.stderr or "") or None
    if execution.returncode == 0:
        return JudgeResult(True, None, stderr, printed_output, return_output, execution.runtime_ms, 1, 1)

    failed = (
        local_judge._extract_failure(execution.stderr or "", source_lookup)
        or local_judge._extract_exception_summary(execution.stderr or "")
        or execution.failure_reason
        or stderr
        or printed_output
        or "Custom run failed"
    )
    return JudgeResult(False, failed, stderr, printed_output, return_output, execution.runtime_ms, 1, 0)


def _judge0_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = judge0_auth_token()
    if token:
        headers["X-Auth-Token"] = token
    return headers


def _judge0_execution_from_payload(payload: dict[str, object], fallback_runtime_ms: int) -> _Judge0Execution:
    stdout = str(payload.get("stdout") or "")
    stderr = "\n".join(
        item
        for item in [
            str(payload.get("compile_output") or ""),
            str(payload.get("stderr") or ""),
            str(payload.get("message") or ""),
        ]
        if item.strip()
    )
    status = payload.get("status") if isinstance(payload.get("status"), dict) else {}
    status_id = int(status.get("id") or payload.get("status_id") or 0)
    status_description = str(status.get("description") or "")
    returncode = 0 if status_id == 3 else 1
    runtime_ms = _judge0_runtime_ms(payload, fallback_runtime_ms)
    return _Judge0Execution(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        runtime_ms=runtime_ms,
        failure_reason=None if returncode == 0 else status_description or None,
    )


def _judge0_runtime_ms(payload: dict[str, object], fallback_runtime_ms: int) -> int:
    for key in ("time", "wall_time"):
        value = payload.get(key)
        if value is None:
            continue
        try:
            return int(float(value) * 1000)
        except (TypeError, ValueError):
            continue
    return fallback_runtime_ms


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")
    except Exception:
        return str(exc)
