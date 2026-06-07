# LeetCoach Local

Local LeetCode-style learning workbench with Python judge, SQLite state, and Anthropic Claude coaching.

## Setup

```bash
npm install
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
backend/.venv/bin/python -m app.importer
```

Optional AI coach:

```bash
export ANTHROPIC_API_KEY=...
export ANTHROPIC_MODEL=claude-3-5-sonnet-latest
```

## Run

```bash
backend/.venv/bin/uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
npm run dev -- --port 5173
```

Open `http://127.0.0.1:5173`.

## Judge backend

By default the app runs the Python judge locally. To route the generated Python
runner through a Judge0 instance instead:

```bash
export LEETCOACH_JUDGE_BACKEND=judge0
export LEETCOACH_JUDGE0_ENDPOINT=http://127.0.0.1:2358
# Optional when your Judge0 instance requires it:
export LEETCOACH_JUDGE0_AUTH_TOKEN=...
# Optional; Judge0 CE commonly uses 71 for Python 3:
export LEETCOACH_JUDGE0_PYTHON_LANGUAGE_ID=71
```

The API still keeps `运行` and `提交` semantics unchanged: `运行` can use custom
input, while `提交` runs the full stored test harness.

## Dataset

The importer reads JSONL files from:

`/Users/admin/Downloads/leetcode-dataset-check/LeetCodeDataset`

Override with:

```bash
export LEETCODE_DATASET_PATH=/path/to/LeetCodeDataset
```

## CodeTop metadata

Sync public CodeTop metadata into separate SQLite tables:

```bash
backend/.venv/bin/python -m app.codetop --max-pages 1
```

Remove `--max-pages` for a full low-frequency sync. By default this stores question metadata,
companies, departments, jobs, and tags. Optional taxonomy endpoints that return `403` are skipped.
It does not store problem statement content unless you explicitly pass `--include-content`.

Report and import high-frequency CodeTop gaps:

```bash
cd backend
python -m app.codetop_gap --report --top 10
python -m app.codetop_gap --import-top 20 --dry-run
python -m app.codetop_gap --import-top 20
```

AI-assisted test enhancement:

```bash
cd backend
python -m app.ai_test_enhancer --task lru-cache --print-prompt
python -m app.ai_test_enhancer --task lru-cache --strength medium
python -m app.ai_test_enhancer --task lru-cache --strength medium --apply
```

AI-generated tests are validated before apply. Problems track `test_source` and `test_strength`
so imported example tests can stay marked as weak until enhanced.
# LeetCoach
