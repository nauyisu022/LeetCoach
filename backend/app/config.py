from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "app.db"
DEFAULT_DATASET_PATH = Path("/Users/admin/Downloads/leetcode-dataset-check/LeetCodeDataset")


def db_path() -> Path:
    return Path(os.getenv("LEETCOACH_DB_PATH", str(DEFAULT_DB_PATH)))


def dataset_path() -> Path:
    return Path(os.getenv("LEETCODE_DATASET_PATH", str(DEFAULT_DATASET_PATH)))


def anthropic_model() -> str:
    return os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")


def anthropic_base_url() -> str | None:
    return os.getenv("ANTHROPIC_BASE_URL")


def anthropic_api_key() -> str | None:
    return os.getenv("ANTHROPIC_API_KEY")


def anthropic_auth_token() -> str | None:
    return os.getenv("ANTHROPIC_AUTH_TOKEN")


def judge_backend() -> str:
    return os.getenv("LEETCOACH_JUDGE_BACKEND", "local").strip().lower()


def judge0_endpoint() -> str | None:
    value = os.getenv("LEETCOACH_JUDGE0_ENDPOINT") or os.getenv("JUDGE0_ENDPOINT")
    return value.rstrip("/") if value else None


def judge0_auth_token() -> str | None:
    return os.getenv("LEETCOACH_JUDGE0_AUTH_TOKEN") or os.getenv("JUDGE0_AUTH_TOKEN")


def judge0_language_id() -> int:
    return int(os.getenv("LEETCOACH_JUDGE0_PYTHON_LANGUAGE_ID", "71"))
