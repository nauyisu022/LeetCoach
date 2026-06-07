from __future__ import annotations

from . import judge as local_judge
from .judge import DEFAULT_TIMEOUT_SECONDS, JudgeResult


def run_submission(
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
