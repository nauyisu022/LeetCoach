import json

from app import judge_service
from app.judge import PASS_SENTINEL, TEST_COUNT_PREFIX


PROMPT = "from typing import *"


def test_judge_service_defaults_to_local_backend(monkeypatch):
    monkeypatch.delenv("LEETCOACH_JUDGE_BACKEND", raising=False)

    result = judge_service.run_submission(
        prompt=PROMPT,
        code="def candidate(value):\n    return value\n",
        test_code="def check(candidate):\n    assert candidate(1) == 1\n",
        entry_point="candidate",
    )

    assert result.passed is True
    assert result.passed_test_count == 1


def test_judge0_backend_posts_runner_source_and_parses_success(monkeypatch):
    monkeypatch.setenv("LEETCOACH_JUDGE0_ENDPOINT", "http://judge0.local")
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def read(self):
            return json.dumps(
                {
                    "stdout": f"{TEST_COUNT_PREFIX} 1 1\n{PASS_SENTINEL}\n",
                    "stderr": None,
                    "compile_output": None,
                    "message": None,
                    "status": {"id": 3, "description": "Accepted"},
                    "time": "0.012",
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(judge_service.urllib.request, "urlopen", fake_urlopen)

    result = judge_service.Judge0Backend().run_submission(
        prompt=PROMPT,
        code="def candidate(value):\n    return value\n",
        test_code="def check(candidate):\n    assert candidate(1) == 1\n",
        entry_point="candidate",
    )

    assert captured["url"] == "http://judge0.local/submissions?base64_encoded=false&wait=true"
    assert captured["timeout"] == 20
    assert captured["payload"]["language_id"] == 71
    assert "def candidate(value):" in captured["payload"]["source_code"]
    assert result.passed is True
    assert result.runtime_ms == 12
    assert result.stdout is None
