from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
DEFAULT_LEGACY_DB_PATH = DATA_DIR / "app.legacy.db"
DEFAULT_CATALOG_DB_PATH = DATA_DIR / "catalog.db"
DEFAULT_USER_DB_PATH = DATA_DIR / "user.local.db"
DEFAULT_DATASET_PATH = DATA_DIR / "LeetCodeDataset"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(ROOT_DIR / ".env")
_load_env_file(ROOT_DIR / ".env.local")


def db_path() -> Path:
    return catalog_db_path()


def catalog_db_path() -> Path:
    return Path(os.getenv("LEETCOACH_CATALOG_DB_PATH", str(DEFAULT_CATALOG_DB_PATH)))


def user_db_path() -> Path:
    return Path(os.getenv("LEETCOACH_USER_DB_PATH", str(DEFAULT_USER_DB_PATH)))


def legacy_db_path() -> Path:
    return Path(os.getenv("LEETCOACH_LEGACY_DB_PATH", str(DEFAULT_LEGACY_DB_PATH)))


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

