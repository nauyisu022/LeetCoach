# LeetCoach

LeetCoach is a local coding-practice workbench for LeetCode-style problems. It gives you a browser UI for solving problems, running Python tests, tracking attempts, saving notes, and optionally asking an AI coach for help.

It is designed for local self-hosting: the app code is in this repository, while problem data and personal practice records stay in your own local `data/` directory.

## Features

- Browse problems by difficulty, topic, status, search keyword, and CodeTop frequency.
- Write Python solutions in a Monaco-based editor.
- Run custom test cases before submitting.
- Submit against the stored problem test suite.
- Inspect concrete failing assertions and submission history.
- Save draft solutions and Markdown practice notes.
- Track topic-level practice progress and review state.
- Use an optional Anthropic-compatible AI coach for explanations, debugging, and note drafts.

## Quick Start

Install `uv` if you do not already have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Clone the repository:

```bash
git clone https://github.com/nauyisu022/LeetCoach.git
cd LeetCoach
```

Install frontend dependencies:

```bash
npm install
```

Install backend dependencies:

```bash
uv sync
```

Prepare problem data:

```bash
mkdir -p data/LeetCodeDataset
```

Put your local `LeetCodeDataset-*.jsonl` files under:

```text
data/LeetCodeDataset/
```

Import the problem catalog:

```bash
uv run leetcoach-import
```

Start the backend:

```bash
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Start the frontend in another terminal:

```bash
npm run dev -- --port 5173
```

Open the app:

```text
http://127.0.0.1:5173
```

## Problem Data

This repository does not include a prebuilt problem database. The app expects you to provide your own local dataset and then generate the local catalog database with the importer.

By default, the importer reads from:

```text
data/LeetCodeDataset/
```

You can use a different dataset path:

```bash
export LEETCODE_DATASET_PATH=/path/to/LeetCodeDataset
uv run leetcoach-import
```

Problem data is written to:

```text
data/catalog.db
```

`catalog.db` contains problem metadata, prompts, tests, and CodeTop metadata. It is local data and should not be committed.

## Local User Data

LeetCoach keeps problem data separate from your personal practice data:

```text
data/catalog.db      # problem catalog and public metadata; can be rebuilt
data/user.local.db   # your attempts, submissions, saved code, notes, and AI chat history
```

Back up `data/user.local.db` if you care about your practice history.

Do not commit any files under `data/`. The directory is intentionally ignored by Git.

## Optional AI Coach

AI features are optional. Without API credentials, you can still browse problems, run tests, submit solutions, save notes, and track progress.

Configure Anthropic:

```bash
export ANTHROPIC_API_KEY=...
export ANTHROPIC_MODEL=claude-3-5-sonnet-latest
```

Anthropic-compatible endpoints are also supported:

```bash
export ANTHROPIC_BASE_URL=https://your-endpoint.example.com
export ANTHROPIC_AUTH_TOKEN=...
```

## Judge Backend

LeetCoach runs Python submissions locally. The backend builds a temporary runner, executes it with the local Python interpreter, and reports concrete failing assertions back to the UI.

## CodeTop Metadata

Sync CodeTop metadata into `data/catalog.db`:

```bash
uv run leetcoach-codetop --max-pages 1
```

Run a fuller sync by removing `--max-pages`:

```bash
uv run leetcoach-codetop
```

Report high-frequency CodeTop gaps:

```bash
uv run leetcoach-codetop-gap --report --top 10
```

## Development

Run backend tests:

```bash
uv run pytest backend/tests
```

Run frontend lint:

```bash
npm run lint
```

Build the frontend:

```bash
npm run build
```

## Legacy Database Migration

Older versions used a single SQLite database for both problem data and user data. If you have an old `data/app.db`, mark it as legacy first:

```bash
mv data/app.db data/app.legacy.db
```

Then split it into the current two-database layout:

```bash
uv run leetcoach-split-db --source data/app.legacy.db --replace
```

After migration:

```text
data/catalog.db
data/user.local.db
data/app.legacy.db   # old backup, not used by default
```

## Data Notice

The code in this repository can be cloned and self-hosted. Problem datasets, generated SQLite databases, API keys, local submissions, and AI chat history are not part of the repository and should not be published.

If you fork or deploy this project, generate your own local `catalog.db` and keep `user.local.db` private.

## Common Commands

```bash
# backend health check
curl http://127.0.0.1:8000/api/health

# import problems
uv run leetcoach-import

# backend
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# frontend
npm run dev -- --port 5173
```
