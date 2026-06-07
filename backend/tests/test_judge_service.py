from app import judge_service


PROMPT = "from typing import *"


def test_judge_service_runs_local_submission():
    result = judge_service.run_submission(
        prompt=PROMPT,
        code="def candidate(value):\n    return value\n",
        test_code="def check(candidate):\n    assert candidate(1) == 1\n",
        entry_point="candidate",
    )

    assert result.passed is True
    assert result.passed_test_count == 1
